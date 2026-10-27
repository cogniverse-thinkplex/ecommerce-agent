from __future__ import annotations

from collections.abc import Callable
import hashlib
from datetime import datetime, timezone
import logging

from app.agent.nodes.confirmation_node import (
    ConfirmationNodeResult,
    ConfirmationReply,
    apply_confirmation_reply,
)
from app.agent.nodes.tool_node import (
    ToolCallRequest,
    ToolNodeResult,
    apply_tool_call,
)
from app.agent.nodes.tool_proposal_node import (
    ToolProposal,
    ToolProposalResult,
    apply_tool_proposal,
)
from app.agent.proposal_generator import ProposalGenerator
from app.agent.progress import ProgressSink
from app.agent.runtime import (
    AgentAutoRunResult,
    AgentRuntime,
    AgentTurnResult,
    BaselineAgentRuntime,
)
from app.agent.response_composer import compose_tool_response
from app.agent.response_quality import append_response_quality_event
from app.agent.audit import SessionAudit, build_session_audit
from app.agent.state import AgentEvent, ConversationMessage, CustomerAgentState, append_event
from app.agent.trace import SessionTrace, build_session_trace
from app.agent.session_store import InMemorySessionStore, SessionStore
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.retail_port import RetailToolDefinition, ToolBackendInfo
from app.telemetry.models import FinishRunCommand, RecordStepCommand, StartRunCommand
from app.telemetry.service import RunTelemetryService
from pydantic import BaseModel


logger = logging.getLogger(__name__)


class SessionIndexItem(BaseModel):
    conversation_id: str
    message_count: int
    event_count: int
    has_pending_action: bool


class RuntimeResetResult(BaseModel):
    sessions_cleared: int
    backend: ToolBackendInfo


class ConfirmAndContinueResult(BaseModel):
    state: CustomerAgentState
    confirmation: ConfirmationNodeResult
    executed: ToolNodeResult | None = None
    auto_run: AgentAutoRunResult | None = None


class AgentSessionService:
    def __init__(
        self,
        executor: GuardedRetailToolExecutor,
        proposal_generator: ProposalGenerator | None = None,
        executor_factory: Callable[[], GuardedRetailToolExecutor] | None = None,
        runtime: AgentRuntime | None = None,
        runtime_factory: Callable[[GuardedRetailToolExecutor], AgentRuntime] | None = None,
        session_store: SessionStore | None = None,
        telemetry_service: RunTelemetryService | None = None,
        telemetry_source: str = "sandbox",
    ) -> None:
        self._executor = executor
        self._executor_factory = executor_factory
        self._proposal_generator = proposal_generator
        self._runtime_factory = runtime_factory
        self._runtime = runtime or self._build_runtime(executor)
        self._session_store = session_store or InMemorySessionStore()
        self._telemetry_service = telemetry_service
        self._telemetry_source = telemetry_source
        if isinstance(self._session_store, InMemorySessionStore):
            # Compatibility for existing benchmark helpers that seed private state.
            self._sessions = self._session_store._states

    def start_session(
        self, conversation_id: str, *, authenticated_user_id: str | None = None
    ) -> CustomerAgentState:
        state = CustomerAgentState(conversation_id=conversation_id)
        if authenticated_user_id is not None:
            state = state.model_copy(
                update={
                    "messages": [
                        ConversationMessage(
                            role="tool",
                            tool_name="find_user_id_by_email",
                            tool_call_id="platform-account-link",
                            content=authenticated_user_id,
                        )
                    ],
                    "events": [
                        AgentEvent(
                            event_type="identity.platform_account_linked",
                            payload={"user_id": authenticated_user_id},
                        )
                    ],
                }
            )
        self._session_store.create(state)
        return state

    @property
    def tool_backend(self) -> ToolBackendInfo:
        return self._executor.backend

    @property
    def policy(self) -> str:
        return self._executor.policy

    @property
    def proposal_generator(self) -> ProposalGenerator | None:
        return getattr(self._runtime, "proposal_generator", self._proposal_generator)

    def list_tools(self) -> list[RetailToolDefinition]:
        return self._executor.list_tools()

    def backend_state_hash(self) -> str | None:
        return self._executor.db_hash()

    def reset_runtime_state(self) -> RuntimeResetResult:
        sessions_cleared = self._session_store.clear()
        if self._executor_factory is not None:
            self._executor = self._executor_factory()
            self._runtime = self._build_runtime(self._executor)
        return RuntimeResetResult(
            sessions_cleared=sessions_cleared,
            backend=self.tool_backend,
        )

    def list_sessions(self) -> list[SessionIndexItem]:
        return [
            SessionIndexItem(
                conversation_id=state.conversation_id,
                message_count=len(state.messages),
                event_count=len(state.events),
                has_pending_action=state.confirmation.pending is not None,
            )
            for state in self._session_store.list()
        ]

    def list_events(
        self,
        conversation_id: str,
        event_type_prefix: str | None = None,
    ) -> list[AgentEvent]:
        state = self.get_session(conversation_id)
        if event_type_prefix is None:
            return state.events
        return [
            event
            for event in state.events
            if event.event_type.startswith(event_type_prefix)
        ]

    def get_trace(self, conversation_id: str) -> SessionTrace:
        return build_session_trace(self.get_session(conversation_id))

    def get_audit(self, conversation_id: str) -> SessionAudit:
        return build_session_audit(self.get_session(conversation_id))

    def get_session(self, conversation_id: str) -> CustomerAgentState:
        state = self._session_store.get(conversation_id)
        if state is None:
            raise KeyError(f"Unknown conversation_id: {conversation_id}")
        return state

    def set_active_order_context(self, conversation_id: str, order_id: str) -> CustomerAgentState:
        state = self.get_session(conversation_id)
        ledger = state.objective_ledger.model_copy(update={"active_order_id": order_id})
        next_state = state.model_copy(update={"objective_ledger": ledger})
        next_state = append_event(
            next_state,
            "conversation.order_context_set",
            {"order_id": order_id, "source": "order_center"},
        )
        self._session_store.save(next_state)
        return next_state

    def set_active_policy_context(self, conversation_id: str, policy_id: str) -> CustomerAgentState:
        state = self.get_session(conversation_id)
        ledger = state.objective_ledger.model_copy(update={"active_policy_id": policy_id})
        next_state = state.model_copy(update={"objective_ledger": ledger})
        next_state = append_event(next_state, "conversation.policy_context_set", {"policy_id": policy_id, "source": "help_center"})
        self._session_store.save(next_state)
        return next_state

    def delete_session(self, conversation_id: str) -> None:
        if not self._session_store.archive(conversation_id):
            raise KeyError(f"Unknown conversation_id: {conversation_id}")

    def add_user_message(
        self,
        conversation_id: str,
        content: str,
    ) -> CustomerAgentState:
        state = self.get_session(conversation_id)
        next_state = state.model_copy(
            update={
                "messages": [
                    *state.messages,
                    ConversationMessage(role="user", content=content),
                ]
            }
        )
        self._session_store.save(next_state)
        return next_state

    def apply_tool_request(
        self,
        conversation_id: str,
        request: ToolCallRequest,
    ) -> ToolNodeResult:
        state = self.get_session(conversation_id)
        result = apply_tool_call(state, self._executor, request)
        next_state = self._append_tool_response_message(result.state)
        self._session_store.save(next_state)
        return result.model_copy(update={"state": next_state})

    def apply_tool_proposal(
        self,
        conversation_id: str,
        proposal: ToolProposal,
    ) -> ToolProposalResult:
        state = self.get_session(conversation_id)
        result = apply_tool_proposal(state, self._executor, proposal)
        self._session_store.save(result.state)
        return result

    def apply_confirmation_reply(
        self,
        conversation_id: str,
        confirmed: bool,
        user_text: str,
    ) -> ConfirmationNodeResult:
        state = self.get_session(conversation_id)
        result = apply_confirmation_reply(
            state,
            ConfirmationReply(confirmed=confirmed, user_text=user_text),
        )
        self._session_store.save(result.state)
        return result

    def confirm_pending_and_continue(
        self,
        conversation_id: str,
        *,
        confirmed: bool,
        user_text: str,
        objective: str,
        max_steps: int = 6,
    ) -> ConfirmAndContinueResult:
        state = self.get_session(conversation_id)
        pending = state.confirmation.pending
        confirmation = self.apply_confirmation_reply(
            conversation_id,
            confirmed=confirmed,
            user_text=user_text,
        )
        if not confirmation.confirmed or pending is None:
            return ConfirmAndContinueResult(
                state=confirmation.state,
                confirmation=confirmation,
            )

        executed = self.apply_tool_request(
            conversation_id,
            ToolCallRequest(
                name=pending.name,
                arguments=pending.arguments,
                call_id=f"confirmed-{pending.fingerprint}",
            ),
        )
        if not executed.executed or executed.error:
            return ConfirmAndContinueResult(
                state=executed.state,
                confirmation=confirmation,
                executed=executed,
            )

        has_pending_plan_item = any(
            item.status == "pending"
            for item in executed.state.objective_ledger.write_plan
        )
        if has_pending_plan_item:
            continuation_objective = (
                "Continue the original objective using NEXT_WRITE_OBJECTIVE from the "
                "trusted OBJECTIVE_LEDGER. Resolve only that objective and do not repeat "
                f"completed writes. Original objective: {objective}"
            )
        else:
            continuation_objective = (
                f"Completed write: {pending.name}. Continue only the remaining parts "
                "of the original objective without restarting completed lookups. "
                f"Original objective: {objective}"
            )
        auto_run = self.auto_run(
            conversation_id,
            continuation_objective,
            max_steps=max_steps,
        )
        repeated = auto_run.state.confirmation.pending
        completed_fingerprints = {
            item.fingerprint for item in auto_run.state.objective_ledger.completed_writes
        }
        repeated_completed_write = (
            repeated is not None
            and not has_pending_plan_item
            and repeated.name == pending.name
            and repeated.arguments.get("order_id") == pending.arguments.get("order_id")
        )
        if repeated is not None and (
            repeated.fingerprint in completed_fingerprints or repeated_completed_write
        ):
            next_confirmation = auto_run.state.confirmation.model_copy(
                update={"pending": None}
            )
            deduplicated_state = append_event(
                auto_run.state.model_copy(
                    update={"confirmation": next_confirmation}
                ),
                "planner.completed_write_deduplicated",
                {
                    "tool": repeated.name,
                    "fingerprint": repeated.fingerprint,
                },
            )
            self._session_store.save(deduplicated_state)
            auto_run = auto_run.model_copy(update={"state": deduplicated_state})
        return ConfirmAndContinueResult(
            state=auto_run.state,
            confirmation=confirmation,
            executed=executed,
            auto_run=auto_run,
        )

    def run_turn(self, conversation_id: str, content: str) -> AgentTurnResult:
        state = self.get_session(conversation_id)
        result = self._runtime.run_step(state, content, append_no_proposal=True)
        self._session_store.save(result.state)
        return result

    def auto_run(
        self,
        conversation_id: str,
        content: str,
        *,
        max_steps: int = 6,
        telemetry_source: str | None = None,
        progress_sink: ProgressSink | None = None,
    ) -> AgentAutoRunResult:
        state = self.get_session(conversation_id)
        run = self._start_telemetry_run(
            conversation_id,
            source=telemetry_source or self._telemetry_source,
        )
        initial_event_count = len(state.events)
        try:
            result = self._runtime.run_until_blocked(
                state,
                content,
                max_steps=max_steps,
                progress_sink=progress_sink,
            )
            self._session_store.save(result.state)
            self._finish_telemetry_run(run, result, initial_event_count)
            return result
        except Exception as exc:
            if run is not None and self._telemetry_service is not None:
                self._safe_telemetry(
                    lambda: self._telemetry_service.finish_run(
                        run.run_id,
                        FinishRunCommand(
                            status="failed",
                            stopped_reason="exception",
                            error_code=type(exc).__name__,
                        ),
                    )
                )
            raise

    def _start_telemetry_run(self, conversation_id: str, *, source: str):
        if self._telemetry_service is None:
            return None
        generator = self.proposal_generator
        model = getattr(generator, "model", None)
        planner_type = "llm" if model else "rule"
        policy = self.policy
        return self._safe_telemetry(
            lambda: self._telemetry_service.start_run(
                StartRunCommand(
                    conversation_id=conversation_id if source == "support" else None,
                    source=source,
                    planner_type=planner_type,
                    model=model,
                    tool_backend=self.tool_backend.name,
                    policy_version=(
                        hashlib.sha256(policy.encode()).hexdigest()[:12]
                        if policy
                        else None
                    ),
                )
            )
        )

    def _finish_telemetry_run(
        self,
        run,
        result: AgentAutoRunResult,
        initial_event_count: int,
    ) -> None:
        if run is None or self._telemetry_service is None:
            return
        rag_started_at = None
        for event in result.state.events[initial_event_count:]:
            if event.event_type == "rag.started":
                rag_started_at = event.created_at
            kind = _telemetry_event_kind(event.event_type)
            if kind is None:
                continue
            name = str(event.payload.get("tool") or event.event_type)
            status = (
                "failed"
                if event.payload.get("error") or event.event_type == "rag.degraded"
                else "succeeded"
            )
            started_at = (
                rag_started_at
                if event.event_type in {"rag.completed", "rag.degraded"}
                and rag_started_at is not None
                else event.created_at
            )
            self._safe_telemetry(
                lambda event=event, kind=kind, name=name, status=status: (
                    self._telemetry_service.record_step(
                        run.run_id,
                        RecordStepCommand(
                            kind=kind,
                            name=name,
                            status=status,
                            summary=event.payload,
                            started_at=started_at,
                            finished_at=event.created_at,
                        ),
                    )
                )
            )
        client = getattr(self.proposal_generator, "client", None)
        usage_available = bool(getattr(client, "usage_available", False))
        status = (
            "waiting_confirmation"
            if result.stopped_reason == "pending_confirmation"
            else "failed"
            if result.stopped_reason == "max_steps"
            else "succeeded"
        )
        self._safe_telemetry(
            lambda: self._telemetry_service.finish_run(
                run.run_id,
                FinishRunCommand(
                    status=status,
                    stopped_reason=result.stopped_reason,
                    prompt_tokens=(
                        int(getattr(client, "prompt_tokens", 0))
                        if usage_available
                        else None
                    ),
                    completion_tokens=(
                        int(getattr(client, "completion_tokens", 0))
                        if usage_available
                        else None
                    ),
                    total_tokens=(
                        int(getattr(client, "total_tokens", 0))
                        if usage_available
                        else None
                    ),
                    estimated_cost_cny=(
                        getattr(client, "estimated_list_cost_cny", None)
                        if usage_available
                        else None
                    ),
                ),
            )
        )

    @staticmethod
    def _safe_telemetry(operation):
        try:
            return operation()
        except Exception:
            logger.exception("Agent telemetry write failed")
            return None

    def _build_runtime(
        self,
        executor: GuardedRetailToolExecutor,
    ) -> AgentRuntime:
        if self._runtime_factory is not None:
            return self._runtime_factory(executor)
        return BaselineAgentRuntime(
            executor,
            self._proposal_generator,
        )

    def _append_tool_response_message(
        self,
        state: CustomerAgentState,
    ) -> CustomerAgentState:
        if not state.messages:
            return state
        response = compose_tool_response(state.messages[-1])
        if response is None:
            return state
        next_state = state.model_copy(
            update={
                "messages": [
                    *state.messages,
                    ConversationMessage(role="assistant", content=response),
                ]
            }
        )
        return append_response_quality_event(next_state, response, source="tool")


def _telemetry_event_kind(event_type: str):
    if event_type == "tool_proposal.accepted":
        return "planner"
    if event_type.startswith("policy_guard."):
        return "confirmation" if "confirmation" in event_type else "guard"
    if event_type.startswith("tool_executor."):
        return "tool"
    if event_type.startswith("planner."):
        return "response"
    if event_type in {"rag.completed", "rag.degraded", "response.quality_checked"}:
        return "response"
    return None
