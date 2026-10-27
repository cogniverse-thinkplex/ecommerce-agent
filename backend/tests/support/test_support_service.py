from pathlib import Path
from datetime import datetime, timezone

from app.agent.runtime import AgentAutoRunResult
from app.agent.session_service import ConfirmAndContinueResult
from app.agent.nodes.confirmation_node import ConfirmationNodeResult
from app.agent.nodes.tool_node import ToolNodeResult
from app.agent.state import (
    ConfirmationState,
    ConversationMessage,
    CustomerAgentState,
    PendingAction,
)
from app.persistence.sqlite import SqliteUnitOfWork
from app.persistence.models import MessageRecord
from app.support.service import SupportService, summarize_question


class StubAgentService:
    def __init__(self) -> None:
        self.states: dict[str, CustomerAgentState] = {}
        self.auto_runs = 0
        self.confirmations = 0

    def start_session(
        self, conversation_id: str, *, authenticated_user_id: str | None = None
    ) -> CustomerAgentState:
        messages = (
            [
                ConversationMessage(
                    role="tool",
                    tool_name="find_user_id_by_email",
                    tool_call_id="platform-account-link",
                    content=authenticated_user_id,
                )
            ]
            if authenticated_user_id
            else []
        )
        state = CustomerAgentState(
            conversation_id=conversation_id,
            messages=messages,
        )
        self.states[conversation_id] = state
        return state

    def get_session(self, conversation_id: str) -> CustomerAgentState:
        return self.states[conversation_id]

    def auto_run(self, conversation_id: str, content: str, max_steps: int = 6):
        self.auto_runs += 1
        state = self.states[conversation_id].model_copy(
            update={
                "messages": [
                    ConversationMessage(role="user", content=content),
                    ConversationMessage(role="assistant", content="我来帮您处理。"),
                ],
                "confirmation": ConfirmationState(
                    pending=PendingAction(
                        name="cancel_pending_order",
                        arguments={"order_id": "#W2378156", "reason": "mistake"},
                        fingerprint="fp-1",
                    )
                ),
            }
        )
        self.states[conversation_id] = state
        return AgentAutoRunResult(
            state=state, turns=[], stopped_reason="pending_confirmation"
        )

    def confirm_pending_and_continue(
        self, conversation_id: str, *, confirmed: bool, user_text: str,
        objective: str, max_steps: int = 6
    ):
        self.confirmations += 1
        state = self.states[conversation_id].model_copy(
            update={
                "messages": [
                    *self.states[conversation_id].messages,
                    ConversationMessage(
                        role="tool",
                        tool_name="cancel_pending_order",
                        content='{"order_id":"#W2378156","status":"cancelled"}',
                    ),
                    ConversationMessage(
                        role="assistant",
                        content="订单 #W2378156 已成功取消，当前状态为已取消。",
                    ),
                ],
                "confirmation": ConfirmationState(
                    pending=None, confirmed_fingerprints=["fp-1"]
                )
            }
        )
        self.states[conversation_id] = state
        return ConfirmAndContinueResult(
            state=state,
            confirmation=ConfirmationNodeResult(
                state=state, confirmed=confirmed
            ),
            executed=ToolNodeResult(state=state, executed=True),
        )


class MultiStepAgent(StubAgentService):
    def confirm_pending_and_continue(
        self, conversation_id: str, *, confirmed: bool, user_text: str,
        objective: str, max_steps: int = 6
    ):
        self.confirmations += 1
        current = self.states[conversation_id]
        pending = current.confirmation.pending
        assert pending is not None
        if self.confirmations == 1:
            executed_state = current.model_copy(
                update={
                    "messages": [
                        *current.messages,
                        ConversationMessage(
                            role="tool", tool_name="cancel_pending_order",
                            content='{"order_id":"#W2378156","status":"cancelled"}',
                        ),
                        ConversationMessage(
                            role="assistant", content="订单 #W2378156 已成功取消，当前状态为已取消。",
                        ),
                    ],
                    "confirmation": ConfirmationState(pending=None, confirmed_fingerprints=["fp-1"]),
                }
            )
            final_state = executed_state.model_copy(
                update={
                    "confirmation": ConfirmationState(
                        pending=PendingAction(
                            name="modify_pending_order_address",
                            arguments={"order_id": "#W7654321", "address1": "88 New Road"},
                            fingerprint="fp-2",
                        ),
                        confirmed_fingerprints=["fp-1"],
                    )
                }
            )
            self.states[conversation_id] = final_state
            return ConfirmAndContinueResult(
                state=final_state,
                confirmation=ConfirmationNodeResult(state=executed_state, confirmed=True),
                executed=ToolNodeResult(state=executed_state, executed=True),
                auto_run=AgentAutoRunResult(
                    state=final_state, turns=[], stopped_reason="pending_confirmation"
                ),
            )
        final_state = current.model_copy(
            update={
                "messages": [
                    *current.messages,
                    ConversationMessage(
                        role="tool", tool_name="modify_pending_order_address",
                        content='{"order_id":"#W7654321","status":"pending"}',
                    ),
                    ConversationMessage(
                        role="assistant", content="订单 #W7654321 的收货地址已成功修改。",
                    ),
                ],
                "confirmation": ConfirmationState(
                    pending=None, confirmed_fingerprints=["fp-1", "fp-2"]
                ),
            }
        )
        self.states[conversation_id] = final_state
        return ConfirmAndContinueResult(
            state=final_state,
            confirmation=ConfirmationNodeResult(state=final_state, confirmed=True),
            executed=ToolNodeResult(state=final_state, executed=True),
        )


class FailingWriteAgent(StubAgentService):
    def confirm_pending_and_continue(
        self, conversation_id: str, *, confirmed: bool, user_text: str,
        objective: str, max_steps: int = 6
    ):
        self.confirmations += 1
        state = self.states[conversation_id].model_copy(
            update={"confirmation": ConfirmationState(pending=None, confirmed_fingerprints=["fp-1"])}
        )
        self.states[conversation_id] = state
        return ConfirmAndContinueResult(
            state=state,
            confirmation=ConfirmationNodeResult(state=state, confirmed=True),
            executed=ToolNodeResult(state=state, executed=False, error="backend failed"),
        )


def _service(tmp_path: Path) -> tuple[SupportService, StubAgentService]:
    unit = SqliteUnitOfWork(tmp_path / "support.db")
    unit.initialize()
    agent = StubAgentService()
    return SupportService(agent, unit), agent


def test_submit_message_persists_user_reply_and_pending_action(tmp_path: Path):
    service, _ = _service(tmp_path)
    conversation = service.create_conversation()

    result = service.submit_message(
        conversation.conversation_id,
        content="请取消订单 #W2378156",
        request_id="request-1",
    )

    assert [block.type for block in result.blocks] == ["text", "confirmation"]
    assert result.pending_action_id is not None
    restored = service.get_conversation(conversation.conversation_id)
    assert restored.title == "请取消订单 #W2378156"
    assert restored.message_count == 1
    assert restored.last_question_at is not None


def test_question_summary_normalizes_and_truncates_to_32_characters():
    summary = summarize_question(
        "  请   帮我查询这个订单的配送状态以及为什么一直没有更新，"
        "我还想了解后续应该怎样处理  "
    )

    assert summary.startswith("请 帮我查询这个订单")
    assert "  " not in summary
    assert len(summary) == 32
    assert summary.endswith("…")


def test_legacy_default_title_is_backfilled_from_first_question(tmp_path: Path):
    service, _ = _service(tmp_path)
    conversation = service.create_conversation()
    with service._unit.transaction():
        service._unit.messages.append(
            MessageRecord(
                message_id="legacy-first",
                conversation_id=conversation.conversation_id,
                sequence=service._unit.messages.next_sequence(conversation.conversation_id),
                role="user",
                kind="text",
                text="第一条问题",
            )
        )

    service.submit_message(conversation.conversation_id, content="第二条问题", request_id="two")

    assert service.get_conversation(conversation.conversation_id).title == "第一条问题"


def test_reject_action_refreshes_sort_time_without_counting_a_question(tmp_path: Path):
    service, _ = _service(tmp_path)
    conversation = service.create_conversation()
    result = service.submit_message(conversation.conversation_id, content="请取消订单", request_id="one")
    record = service._unit.conversations.get(conversation.conversation_id)
    old_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with service._unit.transaction():
        service._unit.conversations.save(record.model_copy(update={"updated_at": old_time}))

    service.reject_action(conversation.conversation_id, result.pending_action_id, request_id="two")

    refreshed = service.get_conversation(conversation.conversation_id)
    assert refreshed.updated_at > old_time
    assert refreshed.message_count == 1


def test_linked_retail_account_starts_as_authenticated(tmp_path: Path):
    service, agent = _service(tmp_path)

    conversation = service.create_conversation(
        retail_user_id="ivan_santos_6635",
    )

    assert conversation.authenticated is True
    messages = service.list_messages(conversation.conversation_id)
    assert messages[0].text == (
        "您好，我是在线客服。您的购买账户已关联，可以直接查询订单或办理售后。"
    )
    state = agent.get_session(conversation.conversation_id)
    assert state.messages[0].tool_name == "find_user_id_by_email"
    assert state.messages[0].content == "ivan_santos_6635"


def test_duplicate_request_id_returns_existing_result_without_second_agent_run(tmp_path: Path):
    service, agent = _service(tmp_path)
    conversation = service.create_conversation()

    first = service.submit_message(
        conversation.conversation_id, content="cancel", request_id="same-request"
    )
    second = service.submit_message(
        conversation.conversation_id, content="cancel", request_id="same-request"
    )

    assert second == first
    assert agent.auto_runs == 1


def test_confirm_action_is_compare_and_set_idempotent(tmp_path: Path):
    service, agent = _service(tmp_path)
    conversation = service.create_conversation()
    turn = service.submit_message(
        conversation.conversation_id, content="cancel", request_id="request-1"
    )

    first = service.confirm_action(
        conversation.conversation_id, turn.pending_action_id, request_id="confirm-1"
    )
    second = service.confirm_action(
        conversation.conversation_id, turn.pending_action_id, request_id="confirm-2"
    )

    assert first.blocks[0].type == "operation_result"
    assert first.blocks[0].title == "订单已取消"
    assert first.blocks[0].data == {
        "status": "succeeded",
        "action": "取消订单",
        "order_id": "#W2378156",
        "order_status": "cancelled",
        "verification": "tool_result",
    }
    assert second.blocks[-1].data["already_resolved"] is True
    assert agent.confirmations == 1


def test_confirm_action_returns_and_persists_next_confirmation_for_multi_step_request(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "multi-step.db")
    unit.initialize()
    agent = MultiStepAgent()
    service = SupportService(agent, unit)
    conversation = service.create_conversation()
    first_turn = service.submit_message(
        conversation.conversation_id,
        content="取消一个订单并修改另一个订单的地址",
        request_id="request-1",
    )

    first = service.confirm_action(
        conversation.conversation_id,
        first_turn.pending_action_id,
        request_id="confirm-1",
    )

    assert [block.type for block in first.blocks] == ["operation_result", "text", "confirmation"]
    assert first.pending_action_id is not None
    assert first.pending_action_id != first_turn.pending_action_id
    assert first.blocks[-1].data["action_id"] == first.pending_action_id
    assert first.blocks[-1].title == "确认修改配送地址"

    second = service.confirm_action(
        conversation.conversation_id,
        first.pending_action_id,
        request_id="confirm-2",
    )

    assert second.pending_action_id is None
    assert second.blocks[0].title == "配送地址已修改"
    assert agent.confirmations == 2


def test_confirm_action_never_reports_success_when_write_execution_fails(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "failed-write.db")
    unit.initialize()
    agent = FailingWriteAgent()
    service = SupportService(agent, unit)
    conversation = service.create_conversation()
    turn = service.submit_message(
        conversation.conversation_id, content="取消订单", request_id="request-1"
    )

    result = service.confirm_action(
        conversation.conversation_id, turn.pending_action_id, request_id="confirm-1"
    )

    assert result.pending_action_id is None
    assert result.blocks[0].title == "操作未完成"
    assert result.blocks[0].data == {
        "status": "failed",
        "action": "取消订单",
        "order_id": "#W2378156",
    }


def test_reject_action_does_not_execute_agent_write(tmp_path: Path):
    service, agent = _service(tmp_path)
    conversation = service.create_conversation()
    turn = service.submit_message(
        conversation.conversation_id, content="cancel", request_id="request-1"
    )

    result = service.reject_action(
        conversation.conversation_id, turn.pending_action_id, request_id="reject-1"
    )

    assert result.blocks[-1].data["status"] == "rejected"
    assert agent.confirmations == 0

