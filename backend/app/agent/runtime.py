from __future__ import annotations

import re
from typing import Literal, Protocol

from pydantic import BaseModel

from app.agent.nodes.planner_node import apply_planner_decision
from app.agent.order_identity import canonicalize_retail_order_id
from app.agent.nodes.proposal_validation_node import (
    validate_skill_policy,
    validate_tool_proposal,
)
from app.agent.nodes.skill_node import route_skill_action
from app.agent.nodes.tool_proposal_node import (
    ToolProposal,
    ToolProposalResult,
    apply_tool_proposal,
)
from app.agent.proposal_generator import (
    LLMProposalGenerator,
    PlannerDecision,
    ProposalGenerator,
    RuleBasedProposalGenerator,
)
from app.agent.progress import (
    AgentProgressEvent,
    ProgressSink,
    emit_progress,
    tool_started_event,
)
from app.agent.response_composer import compose_tool_response
from app.agent.response_quality import append_response_quality_event
from app.agent.skills import SkillDefinition, SkillRegistry
from app.agent.state import (
    ConversationMessage,
    CustomerAgentState,
    WriteObjective,
    append_event,
    initialize_objective_ledger,
)
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.rag.models import PolicySearchResult


class PolicyRetriever(Protocol):
    def search(self, query: str, top_k: int = 6) -> PolicySearchResult: ...


class AgentTurnResult(BaseModel):
    state: CustomerAgentState
    proposal: ToolProposal | None = None
    proposal_result: ToolProposalResult | None = None


AutoRunStoppedReason = Literal["pending_confirmation", "no_proposal", "max_steps"]


class AgentAutoRunResult(BaseModel):
    state: CustomerAgentState
    turns: list[AgentTurnResult]
    stopped_reason: AutoRunStoppedReason


class AgentRuntime(Protocol):
    def run_step(
        self,
        state: CustomerAgentState,
        user_message: str,
        *,
        append_no_proposal: bool = True,
    ) -> AgentTurnResult:
        raise NotImplementedError

    def run_until_blocked(
        self,
        state: CustomerAgentState,
        user_message: str,
        *,
        max_steps: int = 6,
        progress_sink: ProgressSink | None = None,
    ) -> AgentAutoRunResult:
        raise NotImplementedError


class BaselineAgentRuntime:
    """Baseline runtime backed by the current proposal generator contract."""

    def __init__(
        self,
        executor: GuardedRetailToolExecutor,
        proposal_generator: ProposalGenerator | None,
        skill_registry: SkillRegistry | list[SkillDefinition] | None = None,
        policy_retriever: PolicyRetriever | None = None,
    ) -> None:
        self._executor = executor
        self._proposal_generator = proposal_generator
        self._skill_registry = _coerce_skill_registry(skill_registry)
        self._policy_retriever = policy_retriever

    @property
    def proposal_generator(self) -> ProposalGenerator | None:
        return self._proposal_generator

    def run_step(
        self,
        state: CustomerAgentState,
        user_message: str,
        *,
        append_no_proposal: bool = True,
    ) -> AgentTurnResult:
        state_with_user_message = self._ground_policy(_append_user_message(state, user_message), user_message)
        return self._run_agent_step(
            state_with_user_message,
            user_message,
            append_no_proposal=append_no_proposal,
        )

    def run_until_blocked(
        self,
        state: CustomerAgentState,
        user_message: str,
        *,
        max_steps: int = 6,
        progress_sink: ProgressSink | None = None,
    ) -> AgentAutoRunResult:
        current_state = self._ground_policy(_append_user_message(state, user_message), user_message)
        turns: list[AgentTurnResult] = []
        stopped_reason: AutoRunStoppedReason = "max_steps"

        for step_index in range(max_steps):
            if current_state.confirmation.pending is not None:
                stopped_reason = "pending_confirmation"
                break
            event_count_before_turn = len(current_state.events)
            emit_progress(
                progress_sink,
                AgentProgressEvent(stage="planning", message="正在分析您的请求"),
            )
            def counted_progress(event: AgentProgressEvent) -> None:
                if event.stage in {"tool_completed", "awaiting_confirmation"}:
                    event = event.model_copy(
                        update={"completed": step_index + 1, "total": max_steps}
                    )
                emit_progress(progress_sink, event)

            turn = self._run_agent_step(
                current_state,
                user_message,
                append_no_proposal=False,
                progress_sink=counted_progress,
            )
            if turn.proposal is None:
                stopped_reason = "no_proposal"
                current_state = _append_no_proposal_message(turn.state, user_message)
                break
            turns.append(turn)
            current_state = turn.state
            if any(
                event.event_type == "policy_guard.identity_denied"
                for event in current_state.events[event_count_before_turn:]
            ):
                stopped_reason = "no_proposal"
                break
            if current_state.confirmation.pending is not None:
                stopped_reason = "pending_confirmation"
                break

        emit_progress(
            progress_sink,
            AgentProgressEvent(stage="composing", message="正在整理回复"),
        )

        return AgentAutoRunResult(
            state=current_state,
            turns=turns,
            stopped_reason=stopped_reason,
        )

    def _ground_policy(self, state: CustomerAgentState, user_message: str) -> CustomerAgentState:
        if self._policy_retriever is None or not _should_retrieve_policy(state, user_message):
            return state
        state = append_event(state, "rag.started", {"query": user_message})
        try:
            result = self._policy_retriever.search(user_message, top_k=6)
        except Exception as exc:
            return append_event(state, "rag.degraded", {"reason": type(exc).__name__, "hits": []})
        hits = [hit.model_dump(mode="json") for hit in result.hits]
        event_type = "rag.completed" if result.dense_available else "rag.degraded"
        return append_event(state, event_type, {
            "query": result.query,
            "dense_available": result.dense_available,
            "degraded_reason": result.degraded_reason,
            "hits": hits,
        })

    def _run_agent_step(
        self,
        state: CustomerAgentState,
        user_message: str,
        *,
        append_no_proposal: bool,
        progress_sink: ProgressSink | None = None,
    ) -> AgentTurnResult:
        if self._proposal_generator is None:
            next_state = _append_no_proposal_message(state, user_message) if append_no_proposal else state
            return AgentTurnResult(state=next_state)

        if _has_planner_decision(self._proposal_generator):
            decision = self._proposal_generator.decide(state, user_message)
            state = _initialize_write_plan(
                state,
                decision.write_plan,
                self._executor.list_tools(),
            )
            proposal = decision.to_tool_proposal()
            if proposal is None:
                fallback = self._fallback_terminal_decision(
                    state,
                    user_message,
                    decision,
                )
                if fallback is not None:
                    state, proposal = fallback
                else:
                    handled_state = apply_planner_decision(state, decision)
                    if handled_state is not None:
                        return AgentTurnResult(state=handled_state)
        else:
            proposal = self._proposal_generator.generate(state, user_message)

        if proposal is not None:
            routed = route_skill_action(state, self._skill_registry, proposal)
            if routed.result is not None:
                repaired = self._repair_rejected_skill_route(
                    state,
                    user_message,
                    proposal,
                    routed.result,
                )
                if repaired is None:
                    return AgentTurnResult(
                        state=routed.result.state,
                        proposal=proposal,
                        proposal_result=routed.result,
                    )
                state, proposal = repaired
                routed = route_skill_action(state, self._skill_registry, proposal)
                if routed.result is not None:
                    return AgentTurnResult(
                        state=routed.result.state,
                        proposal=proposal,
                        proposal_result=routed.result,
                    )
            state = routed.state
            proposal = routed.proposal or proposal

        if proposal is None:
            next_state = _append_no_proposal_message(state, user_message) if append_no_proposal else state
            return AgentTurnResult(state=next_state)

        state, proposal = _normalize_read_order_proposal(state, proposal)

        known_product_fallback = self._replace_broad_discovery_proposal(
            state,
            user_message,
            proposal,
        )
        if known_product_fallback is not None:
            state, proposal = known_product_fallback

        locked_order_proposal = self._enforce_locked_order_proposal(
            state,
            proposal,
        )
        if locked_order_proposal is not None:
            state, proposal = locked_order_proposal

        repeated_read_fallback = self._replace_repeated_read_proposal(
            state,
            user_message,
            proposal,
        )
        if repeated_read_fallback is not None:
            state, proposal = repeated_read_fallback

        rejected = validate_tool_proposal(state, self._executor.list_tools(), proposal)
        if rejected is not None:
            repaired = self._repair_rejected_tool_proposal(
                state,
                user_message,
                proposal,
                rejected,
            )
            if repaired is not None:
                state, proposal = repaired
                routed = route_skill_action(state, self._skill_registry, proposal)
                if routed.result is not None:
                    return AgentTurnResult(
                        state=routed.result.state,
                        proposal=proposal,
                        proposal_result=routed.result,
                    )
                state = routed.state
                proposal = routed.proposal
                rejected = validate_tool_proposal(
                    state,
                    self._executor.list_tools(),
                    proposal,
                )
                if rejected is None:
                    rejected = validate_skill_policy(
                        state,
                        self._skill_registry,
                        proposal,
                    )
                if rejected is None:
                    emit_progress(progress_sink, tool_started_event(proposal.tool_name))
                    proposal_result = apply_tool_proposal(state, self._executor, proposal)
                    emit_progress(
                        progress_sink,
                        AgentProgressEvent(
                            stage=(
                                "awaiting_confirmation"
                                if _confirmation_required(proposal_result)
                                else "tool_completed"
                            ),
                            message=(
                                "操作已准备，等待您的确认"
                                if _confirmation_required(proposal_result)
                                else "查询步骤已完成"
                            ),
                            tool_name=proposal.tool_name,
                        ),
                    )
                    next_state = _append_tool_response_message(proposal_result.state)
                    return AgentTurnResult(
                        state=next_state,
                        proposal=proposal,
                        proposal_result=proposal_result.model_copy(
                            update={"state": next_state}
                        ),
                    )
            return AgentTurnResult(
                state=rejected.state,
                proposal=proposal,
                proposal_result=rejected,
            )

        rejected = validate_skill_policy(state, self._skill_registry, proposal)
        if rejected is not None:
            repaired = self._repair_rejected_skill_policy(
                state,
                proposal,
                rejected,
            )
            if repaired is None:
                return AgentTurnResult(
                    state=rejected.state,
                    proposal=proposal,
                    proposal_result=rejected,
                )
            state, proposal = repaired
            rejected = validate_skill_policy(state, self._skill_registry, proposal)
            if rejected is not None:
                return AgentTurnResult(
                    state=rejected.state,
                    proposal=proposal,
                    proposal_result=rejected,
                )

        emit_progress(progress_sink, tool_started_event(proposal.tool_name))
        proposal_result = apply_tool_proposal(state, self._executor, proposal)
        emit_progress(
            progress_sink,
            AgentProgressEvent(
                stage=(
                    "awaiting_confirmation"
                    if _confirmation_required(proposal_result)
                    else "tool_completed"
                ),
                message=(
                    "操作已准备，等待您的确认"
                    if _confirmation_required(proposal_result)
                    else "查询步骤已完成"
                ),
                tool_name=proposal.tool_name,
            ),
        )
        next_state = _append_tool_response_message(proposal_result.state)
        return AgentTurnResult(
            state=next_state,
            proposal=proposal,
            proposal_result=proposal_result.model_copy(update={"state": next_state}),
        )

    def _fallback_terminal_decision(
        self,
        state: CustomerAgentState,
        user_message: str,
        decision: PlannerDecision,
    ) -> tuple[CustomerAgentState, ToolProposal] | None:
        return None

    def _replace_repeated_read_proposal(
        self,
        state: CustomerAgentState,
        user_message: str,
        proposal: ToolProposal,
    ) -> tuple[CustomerAgentState, ToolProposal] | None:
        return None

    def _enforce_locked_order_proposal(
        self,
        state: CustomerAgentState,
        proposal: ToolProposal,
    ) -> tuple[CustomerAgentState, ToolProposal] | None:
        return None

    def _replace_broad_discovery_proposal(
        self,
        state: CustomerAgentState,
        user_message: str,
        proposal: ToolProposal,
    ) -> tuple[CustomerAgentState, ToolProposal] | None:
        return None

    def _repair_rejected_skill_route(
        self,
        state: CustomerAgentState,
        user_message: str,
        proposal: ToolProposal,
        rejected: ToolProposalResult,
    ) -> tuple[CustomerAgentState, ToolProposal] | None:
        return None

    def _repair_rejected_skill_policy(
        self,
        state: CustomerAgentState,
        proposal: ToolProposal,
        rejected: ToolProposalResult,
    ) -> tuple[CustomerAgentState, ToolProposal] | None:
        return None

    def _repair_rejected_tool_proposal(
        self,
        state: CustomerAgentState,
        user_message: str,
        proposal: ToolProposal,
        rejected: ToolProposalResult,
    ) -> tuple[CustomerAgentState, ToolProposal] | None:
        return None


_POLICY_INTENT = re.compile(
    r"政策|规则|七天|退货|退款|换货|取消|运费|发货|物流|地址|预售|跨境|免税|争议|售后"
)


def _should_retrieve_policy(state: CustomerAgentState, user_message: str) -> bool:
    return bool(state.objective_ledger.active_policy_id or _POLICY_INTENT.search(user_message))


class LLMPlannerRuntime(BaselineAgentRuntime):
    """Runtime branch for LLM planner decisions."""

    def __init__(
        self,
        executor: GuardedRetailToolExecutor,
        proposal_generator: LLMProposalGenerator,
        skill_registry: SkillRegistry | list[SkillDefinition] | None = None,
        policy_retriever: PolicyRetriever | None = None,
    ) -> None:
        super().__init__(executor, proposal_generator, skill_registry=skill_registry, policy_retriever=policy_retriever)
        self._terminal_fallback = RuleBasedProposalGenerator()

    def _fallback_terminal_decision(
        self,
        state: CustomerAgentState,
        user_message: str,
        decision: PlannerDecision,
    ) -> tuple[CustomerAgentState, ToolProposal] | None:
        if decision.action == "tool_call":
            return None
        proposal = self._terminal_fallback.generate(state, user_message)
        if proposal is None:
            return None
        next_state = append_event(
            state,
            "planner.terminal_fallback",
            {
                "terminal_action": decision.action,
                "fallback_tool": proposal.tool_name,
            },
        )
        return next_state, proposal

    def _replace_broad_discovery_proposal(
        self,
        state: CustomerAgentState,
        user_message: str,
        proposal: ToolProposal,
    ) -> tuple[CustomerAgentState, ToolProposal] | None:
        if proposal.tool_name not in {"get_user_details", "list_all_product_types"}:
            return None
        fallback = self._terminal_fallback.generate(state, user_message)
        if fallback is None or fallback.tool_name != "get_product_details":
            return None
        if not any(tool.name == fallback.tool_name for tool in self._executor.list_tools()):
            return None
        product_id = fallback.arguments.get("product_id")
        next_state = append_event(
            state,
            "planner.known_product_fallback",
            {
                "replaced_tool": proposal.tool_name,
                "fallback_tool": fallback.tool_name,
                "product_id": product_id,
            },
        )
        return next_state, fallback

    def _repair_rejected_skill_route(
        self,
        state: CustomerAgentState,
        user_message: str,
        proposal: ToolProposal,
        rejected: ToolProposalResult,
    ) -> tuple[CustomerAgentState, ToolProposal] | None:
        reason = _latest_event_reason(rejected.state, "skill_node.rejected")
        if reason != "unknown_skill_action":
            return None
        fallback = self._terminal_fallback.generate(state, user_message)
        if fallback is None or not any(
            tool.name == fallback.tool_name for tool in self._executor.list_tools()
        ):
            return None
        next_state = append_event(
            state,
            "planner.rejected_skill_fallback",
            {
                "reason": reason,
                "skill_id": proposal.skill_id,
                "skill_action": proposal.skill_action,
                "fallback_tool": fallback.tool_name,
            },
        )
        return next_state, fallback

    def _repair_rejected_skill_policy(
        self,
        state: CustomerAgentState,
        proposal: ToolProposal,
        rejected: ToolProposalResult,
    ) -> tuple[CustomerAgentState, ToolProposal] | None:
        reason = _latest_event_reason(rejected.state, "skill_policy.rejected")
        if reason != "unknown_skill":
            return None
        if not any(tool.name == proposal.tool_name for tool in self._executor.list_tools()):
            return None
        next_state = append_event(
            state,
            "planner.invalid_skill_metadata_removed",
            {
                "reason": reason,
                "skill_id": proposal.skill_id,
                "tool": proposal.tool_name,
            },
        )
        return next_state, proposal.model_copy(
            update={"skill_id": "", "skill_action": ""}
        )

    def _replace_repeated_read_proposal(
        self,
        state: CustomerAgentState,
        user_message: str,
        proposal: ToolProposal,
    ) -> tuple[CustomerAgentState, ToolProposal] | None:
        if proposal.tool_name == "get_order_details":
            proposed_order_id = proposal.arguments.get("order_id")
            if (
                proposed_order_id
                and proposed_order_id
                not in state.objective_ledger.inspected_order_ids
            ):
                return None
        locked_order_id = state.objective_ledger.locked_order_id
        if (
            proposal.tool_name == "get_order_details"
            and locked_order_id
            and proposal.arguments.get("order_id") == locked_order_id
        ):
            return None
        if not _is_loop_guarded_read_tool(proposal.tool_name, self._executor.list_tools()):
            return None
        if not any(
            message.role == "tool" and message.tool_name == proposal.tool_name
            for message in state.messages
        ):
            return None
        fallback = self._terminal_fallback.generate(state, user_message)
        if fallback is None or fallback.tool_name == proposal.tool_name:
            return None
        next_state = append_event(
            state,
            "planner.repeated_read_fallback",
            {
                "repeated_tool": proposal.tool_name,
                "fallback_tool": fallback.tool_name,
            },
        )
        return next_state, fallback

    def _enforce_locked_order_proposal(
        self,
        state: CustomerAgentState,
        proposal: ToolProposal,
    ) -> tuple[CustomerAgentState, ToolProposal] | None:
        locked_order_id = state.objective_ledger.locked_order_id
        if proposal.tool_name != "get_order_details" or not locked_order_id:
            return None
        proposed_order_id = proposal.arguments.get("order_id")
        if proposed_order_id == locked_order_id:
            return None
        next_state = append_event(
            state,
            "planner.locked_order_redirect",
            {
                "proposed_order_id": proposed_order_id,
                "locked_order_id": locked_order_id,
            },
        )
        return next_state, proposal.model_copy(
            update={"arguments": {"order_id": locked_order_id}}
        )

    def _repair_rejected_tool_proposal(
        self,
        state: CustomerAgentState,
        user_message: str,
        proposal: ToolProposal,
        rejected: ToolProposalResult,
    ) -> tuple[CustomerAgentState, ToolProposal] | None:
        reason = _latest_rejection_reason(rejected.state)
        if reason != "unknown_tool":
            return None
        fallback = self._terminal_fallback.generate(state, user_message)
        if fallback is not None and any(
            tool.name == fallback.tool_name for tool in self._executor.list_tools()
        ):
            next_state = append_event(
                state,
                "planner.rejected_tool_fallback",
                {
                    "reason": reason,
                    "rejected_tool": proposal.tool_name,
                    "fallback_tool": fallback.tool_name,
                },
            )
            return next_state, fallback
        repaired = self.proposal_generator.repair_rejected_tool(
            proposal=proposal,
            available_tools=self._executor.list_tools(),
            error=rejected.error,
        )
        if repaired is None:
            return None
        next_state = append_event(
            state,
            "planner.rejected_tool_repair",
            {
                "reason": reason,
                "rejected_tool": proposal.tool_name,
                "repaired_tool": repaired.tool_name,
            },
        )
        return next_state, repaired


def _append_user_message(
    state: CustomerAgentState,
    content: str,
) -> CustomerAgentState:
    state = initialize_objective_ledger(state, content)
    return state.model_copy(
        update={
            "messages": [
                *state.messages,
                ConversationMessage(role="user", content=content),
            ]
        }
    )


def _initialize_write_plan(
    state: CustomerAgentState,
    raw_plan: list[dict],
    tools: list,
) -> CustomerAgentState:
    if state.objective_ledger.write_plan or not raw_plan:
        return state
    write_tools = {tool.name for tool in tools if tool.tool_type == "write"}
    objectives: list[WriteObjective] = []
    used_ids: set[str] = set()
    for raw in raw_plan:
        tool_name = raw.get("tool_name")
        if not isinstance(tool_name, str) or tool_name not in write_tools:
            continue
        base_id = _normalize_objective_id(raw.get("objective_id"), len(objectives) + 1)
        objective_id = base_id
        suffix = 2
        while objective_id in used_ids:
            objective_id = f"{base_id}-{suffix}"
            suffix += 1
        used_ids.add(objective_id)
        order_id = canonicalize_retail_order_id(raw.get("order_id"))
        intent = raw.get("intent")
        objectives.append(
            WriteObjective(
                objective_id=objective_id,
                tool_name=tool_name,
                order_id=order_id,
                intent=intent if isinstance(intent, str) else "",
            )
        )
        if len(objectives) == 8:
            break
    if not objectives:
        return state
    next_state = state.model_copy(
        update={
            "objective_ledger": state.objective_ledger.model_copy(
                update={"write_plan": objectives}
            )
        }
    )
    return append_event(
        next_state,
        "objective_plan.created",
        {"objective_count": len(objectives)},
    )


def _normalize_objective_id(value: object, index: int) -> str:
    if isinstance(value, str):
        normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
        if normalized:
            return normalized[:48]
    return f"objective-{index}"


def _confirmation_required(result: ToolProposalResult) -> bool:
    return bool(result.tool_result and result.tool_result.confirmation_required)


def _normalize_read_order_proposal(
    state: CustomerAgentState,
    proposal: ToolProposal,
) -> tuple[CustomerAgentState, ToolProposal]:
    if proposal.tool_name != "get_order_details":
        return state, proposal
    original = proposal.arguments.get("order_id")
    normalized = canonicalize_retail_order_id(original)
    if normalized is None or normalized == original:
        return state, proposal
    arguments = {**proposal.arguments, "order_id": normalized}
    next_state = append_event(
        state,
        "planner.order_id_normalized",
        {
            "tool_name": proposal.tool_name,
            "original": original,
            "normalized": normalized,
        },
    )
    return next_state, proposal.model_copy(update={"arguments": arguments})


def _has_planner_decision(proposal_generator: ProposalGenerator) -> bool:
    return callable(getattr(proposal_generator, "decide", None))


def _coerce_skill_registry(
    skill_registry: SkillRegistry | list[SkillDefinition] | None,
) -> SkillRegistry | None:
    if skill_registry is None:
        return None
    if isinstance(skill_registry, SkillRegistry):
        return skill_registry
    return SkillRegistry(skill_registry)


def _append_no_proposal_message(
    state: CustomerAgentState,
    user_message: str = "",
) -> CustomerAgentState:
    if state.messages and state.messages[-1].role == "assistant":
        return state
    content = (
        "请提供订单号（例如 #W1234567），我可以为您查询该订单的最新状态和可办理的售后操作。"
        if "订单" in user_message
        else "请补充您要查询或办理的具体信息，我会继续为您处理。"
    )
    return state.model_copy(
        update={
            "messages": [
                *state.messages,
                ConversationMessage(
                    role="assistant",
                    content=content,
                ),
            ]
        }
    )


def _append_tool_response_message(
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


def _is_loop_guarded_read_tool(
    tool_name: str,
    tools: list,
) -> bool:
    if tool_name not in {"find_user_id_by_name_zip", "get_user_details", "get_order_details"}:
        return False
    for tool in tools:
        if tool.name == tool_name:
            return tool.tool_type == "read"
    return False


def _latest_rejection_reason(state: CustomerAgentState) -> str | None:
    for event in reversed(state.events):
        if event.event_type == "tool_proposal.rejected":
            reason = event.payload.get("reason")
            return reason if isinstance(reason, str) else None
    return None


def _latest_event_reason(
    state: CustomerAgentState,
    event_type: str,
) -> str | None:
    for event in reversed(state.events):
        if event.event_type == event_type:
            reason = event.payload.get("reason")
            return reason if isinstance(reason, str) else None
    return None
