from pathlib import Path

import pytest

from app.agent.state import CustomerAgentState
from app.persistence.models import (
    ConversationRecord,
    PendingActionRecord,
    UserRecord,
)
from app.persistence.sqlite import SqliteUnitOfWork
from app.support.handoff import HandoffActiveError, HumanHandoffService
from app.support.service import SupportService


def _unit(tmp_path: Path) -> SqliteUnitOfWork:
    unit = SqliteUnitOfWork(tmp_path / "handoff-service.db")
    unit.initialize()
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
        unit.conversations.save(
            ConversationRecord(
                conversation_id="conversation-1",
                owner_user_id="customer-1",
                state=CustomerAgentState(conversation_id="conversation-1"),
            )
        )
    return unit


def test_create_handoff_is_idempotent_and_owner_scoped(tmp_path: Path):
    service = HumanHandoffService(_unit(tmp_path))

    first = service.create_or_get_active(
        "conversation-1",
        "customer-1",
        reason="customer_requested",
        customer_message="请转人工",
    )
    second = service.create_or_get_active(
        "conversation-1",
        "customer-1",
        reason="customer_requested",
        customer_message="再次请求",
    )

    assert first.ticket_id == second.ticket_id
    assert service.get_for_owner("conversation-1", "customer-1") == first
    with pytest.raises(KeyError):
        service.get_for_owner("conversation-1", "another-customer")


class AgentMustNotExecute:
    def confirm_pending_and_continue(self, *args, **kwargs):
        raise AssertionError("write execution must be blocked during handoff")


def test_active_handoff_blocks_pending_write_confirmation(tmp_path: Path):
    unit = _unit(tmp_path)
    handoffs = HumanHandoffService(unit)
    with unit.transaction():
        unit.pending_actions.create(
            PendingActionRecord(
                action_id="action-1",
                conversation_id="conversation-1",
                tool_name="cancel_pending_order",
                arguments={"order_id": "#W1234567"},
                fingerprint="fingerprint",
                idempotency_key="key",
                confirmation_summary="取消订单 #W1234567",
            )
        )
    handoffs.create_or_get_active(
        "conversation-1", "customer-1", reason="customer_requested"
    )
    support = SupportService(
        AgentMustNotExecute(), unit, handoff_service=handoffs
    )

    with pytest.raises(HandoffActiveError):
        support.confirm_action(
            "conversation-1",
            "action-1",
            request_id="confirm-1",
            owner_user_id="customer-1",
        )

    assert unit.pending_actions.get("action-1").status == "pending"


def test_customer_can_read_latest_terminal_handoff(tmp_path: Path):
    service = HumanHandoffService(_unit(tmp_path))
    ticket = service.create_or_get_active(
        "conversation-1", "customer-1", reason="customer_requested"
    )
    service.resolve(ticket.ticket_id, "customer-1")

    restored = service.get_for_owner("conversation-1", "customer-1")

    assert restored.ticket_id == ticket.ticket_id
    assert restored.status == "resolved"


def test_pending_action_claim_is_conditioned_on_no_active_handoff(tmp_path: Path):
    unit = _unit(tmp_path)
    with unit.transaction():
        unit.pending_actions.create(
            PendingActionRecord(
                action_id="action-atomic",
                conversation_id="conversation-1",
                tool_name="cancel_pending_order",
                arguments={"order_id": "#W1234567"},
                fingerprint="atomic-fingerprint",
                idempotency_key="atomic-key",
                confirmation_summary="取消订单 #W1234567",
            )
        )
    HumanHandoffService(unit).create_or_get_active(
        "conversation-1", "customer-1", reason="customer_requested"
    )

    with unit.transaction():
        claimed = unit.pending_actions.claim_if_no_active_handoff(
            "action-atomic", "conversation-1"
        )

    assert claimed is False
    assert unit.pending_actions.get("action-atomic").status == "pending"
