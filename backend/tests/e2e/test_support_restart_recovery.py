from pathlib import Path

from app.agent.state import CustomerAgentState
from app.persistence.models import ConversationRecord, PendingActionRecord
from app.persistence.sqlite import SqliteUnitOfWork


def test_executing_action_survives_restart_without_automatic_replay(tmp_path: Path):
    path = tmp_path / "recovery.db"
    first = SqliteUnitOfWork(path)
    first.initialize()
    with first.transaction():
        first.conversations.save(
            ConversationRecord(
                conversation_id="conv-1",
                state=CustomerAgentState(conversation_id="conv-1"),
            )
        )
        first.pending_actions.create(
            PendingActionRecord(
                action_id="action-1",
                conversation_id="conv-1",
                tool_name="cancel_pending_order",
                arguments={"order_id": "#W1"},
                fingerprint="fp-1",
                idempotency_key="key-1",
                confirmation_summary="取消订单",
                status="executing",
            )
        )
    first.close()

    restarted = SqliteUnitOfWork(path)
    restarted.initialize()

    assert restarted.pending_actions.get("action-1").status == "executing"

