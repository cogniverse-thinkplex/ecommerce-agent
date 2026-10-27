from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.agent.state import ConversationMessage, CustomerAgentState
from app.persistence.models import (
    AuditEventRecord,
    ConversationRecord,
    MessageRecord,
    PendingActionRecord,
)
from app.persistence.sqlite import SqliteUnitOfWork


def _uow(tmp_path: Path) -> SqliteUnitOfWork:
    unit = SqliteUnitOfWork(tmp_path / "agent.db")
    unit.initialize()
    return unit


def _conversation(conversation_id: str = "conv-1") -> ConversationRecord:
    state = CustomerAgentState(
        conversation_id=conversation_id,
        messages=[ConversationMessage(role="user", content="hello")],
    )
    return ConversationRecord(
        conversation_id=conversation_id,
        title="订单咨询",
        state=state,
    )


def _action(action_id: str = "action-1") -> PendingActionRecord:
    return PendingActionRecord(
        action_id=action_id,
        conversation_id="conv-1",
        tool_name="cancel_pending_order",
        arguments={"order_id": "#W2378156", "reason": "ordered by mistake"},
        fingerprint="fingerprint-1",
        idempotency_key="mutation-1",
        confirmation_summary="取消订单 #W2378156",
    )


def test_initialize_is_idempotent_and_enables_foreign_keys_and_wal(tmp_path: Path):
    unit = _uow(tmp_path)

    unit.initialize()

    assert unit.pragma("foreign_keys") == 1
    assert str(unit.pragma("journal_mode")).lower() == "wal"
    assert unit.applied_migrations() == [1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 14]


def test_conversation_round_trips_agent_state_and_archives_without_deleting(tmp_path: Path):
    unit = _uow(tmp_path)
    record = _conversation()

    with unit.transaction():
        unit.conversations.save(record)

    loaded = unit.conversations.get("conv-1")
    assert loaded is not None
    assert loaded.state == record.state
    assert [item.conversation_id for item in unit.conversations.list_active()] == [
        "conv-1"
    ]

    with unit.transaction():
        assert unit.conversations.archive("conv-1") is True

    assert unit.conversations.get("conv-1") is not None
    assert unit.conversations.list_active() == []


def test_messages_are_ordered_and_request_id_is_unique(tmp_path: Path):
    unit = _uow(tmp_path)
    with unit.transaction():
        unit.conversations.save(_conversation())
        unit.messages.append(
            MessageRecord(
                message_id="message-2",
                conversation_id="conv-1",
                sequence=2,
                role="assistant",
                kind="text",
                text="second",
            )
        )
        unit.messages.append(
            MessageRecord(
                message_id="message-1",
                conversation_id="conv-1",
                sequence=1,
                role="user",
                kind="text",
                text="first",
                request_id="request-1",
            )
        )

    assert [item.text for item in unit.messages.list_for_conversation("conv-1")] == [
        "first",
        "second",
    ]

    with pytest.raises(sqlite3.IntegrityError):
        with unit.transaction():
            unit.messages.append(
                MessageRecord(
                    message_id="message-3",
                    conversation_id="conv-1",
                    sequence=3,
                    role="user",
                    kind="text",
                    text="duplicate",
                    request_id="request-1",
                )
            )


def test_pending_action_compare_and_set_and_idempotency_are_atomic(tmp_path: Path):
    unit = _uow(tmp_path)
    with unit.transaction():
        unit.conversations.save(_conversation())
        unit.pending_actions.create(_action())

    with unit.transaction():
        assert unit.pending_actions.transition(
            "action-1", expected="pending", target="executing"
        ) is True
        assert unit.pending_actions.transition(
            "action-1", expected="pending", target="executing"
        ) is False

    loaded = unit.pending_actions.get("action-1")
    assert loaded is not None
    assert loaded.status == "executing"

    with pytest.raises(sqlite3.IntegrityError):
        with unit.transaction():
            unit.pending_actions.create(_action("action-2"))


def test_audit_events_are_append_only_and_ordered(tmp_path: Path):
    unit = _uow(tmp_path)
    with unit.transaction():
        unit.conversations.save(_conversation())
        unit.audit_events.append(
            AuditEventRecord(
                event_id="event-2",
                conversation_id="conv-1",
                event_type="operation.succeeded",
                payload={"state_changed": True},
            )
        )
        unit.audit_events.append(
            AuditEventRecord(
                event_id="event-1",
                conversation_id="conv-1",
                event_type="confirmation.requested",
                payload={"action_id": "action-1"},
            )
        )

    events = unit.audit_events.list_for_conversation("conv-1")
    assert {item.event_id for item in events} == {"event-1", "event-2"}
    assert unit.audit_events.update_forbidden("event-1") is False


def test_transaction_rolls_back_all_repository_writes(tmp_path: Path):
    unit = _uow(tmp_path)

    with pytest.raises(RuntimeError, match="abort"):
        with unit.transaction():
            unit.conversations.save(_conversation())
            unit.messages.append(
                MessageRecord(
                    message_id="message-1",
                    conversation_id="conv-1",
                    sequence=1,
                    role="user",
                    kind="text",
                    text="must roll back",
                )
            )
            raise RuntimeError("abort")

    assert unit.conversations.get("conv-1") is None
    assert unit.messages.list_for_conversation("conv-1") == []

