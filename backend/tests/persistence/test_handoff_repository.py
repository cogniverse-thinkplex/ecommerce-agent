from pathlib import Path

from app.agent.state import CustomerAgentState
from app.persistence.models import ConversationRecord, HumanHandoffRecord, UserRecord
from app.persistence.sqlite import SqliteUnitOfWork


def _seed(unit: SqliteUnitOfWork) -> None:
    with unit.transaction():
        unit.users.create(
            UserRecord(
                user_id="customer-1",
                email="customer@example.com",
                display_name="Customer",
                password_hash="hash",
                role="customer",
            )
        )
        unit.users.create(
            UserRecord(
                user_id="developer-1",
                email="developer@example.com",
                display_name="Developer",
                password_hash="hash",
                role="developer",
            )
        )
        unit.conversations.save(
            ConversationRecord(
                conversation_id="conversation-1",
                owner_user_id="customer-1",
                state=CustomerAgentState(conversation_id="conversation-1"),
            )
        )


def test_handoff_repository_persists_and_finds_active_ticket(tmp_path: Path):
    path = tmp_path / "handoff.db"
    unit = SqliteUnitOfWork(path)
    unit.initialize()
    _seed(unit)
    ticket = HumanHandoffRecord(
        ticket_id="ticket-1",
        conversation_id="conversation-1",
        owner_user_id="customer-1",
        reason="customer_requested",
        customer_message="请转人工",
        context_summary="客户主动申请人工服务。",
    )

    with unit.transaction():
        unit.human_handoffs.create(ticket)
    unit.close()

    reopened = SqliteUnitOfWork(path)
    reopened.initialize()
    loaded = reopened.human_handoffs.get_active_for_conversation(
        "conversation-1", "customer-1"
    )

    assert loaded is not None
    assert loaded.ticket_id == "ticket-1"
    assert loaded.status == "open"
    assert reopened.applied_migrations()[-1] == 14


def test_handoff_claim_is_compare_and_set_atomic(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "handoff-claim.db")
    unit.initialize()
    _seed(unit)
    with unit.transaction():
        unit.human_handoffs.create(
            HumanHandoffRecord(
                ticket_id="ticket-1",
                conversation_id="conversation-1",
                owner_user_id="customer-1",
                reason="agent_escalated",
            )
        )

    with unit.transaction():
        first = unit.human_handoffs.claim("ticket-1", "developer-1")
    with unit.transaction():
        second = unit.human_handoffs.claim("ticket-1", "developer-2")

    assert first is True
    assert second is False
    loaded = unit.human_handoffs.get("ticket-1")
    assert loaded is not None
    assert loaded.status == "in_progress"
    assert loaded.assigned_developer_user_id == "developer-1"
