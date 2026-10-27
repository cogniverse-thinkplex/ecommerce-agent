from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
import sqlite3

from app.persistence.models import AuditEventRecord, HandoffStatus, HumanHandoffRecord
from app.persistence.sqlite import SqliteUnitOfWork


class HandoffActiveError(RuntimeError):
    pass


class HandoffConflictError(RuntimeError):
    pass


class HumanHandoffService:
    def __init__(self, unit_of_work: SqliteUnitOfWork) -> None:
        self._unit = unit_of_work

    def create_or_get_active(
        self,
        conversation_id: str,
        owner_user_id: str,
        *,
        reason: str,
        customer_message: str | None = None,
        context_summary: str = "",
    ) -> HumanHandoffRecord:
        conversation = self._unit.conversations.get_for_owner(
            conversation_id, owner_user_id
        )
        if conversation is None or conversation.status != "active":
            raise KeyError(conversation_id)
        ticket = HumanHandoffRecord(
            ticket_id=str(uuid4()),
            conversation_id=conversation_id,
            owner_user_id=owner_user_id,
            reason=reason,
            customer_message=customer_message,
            context_summary=context_summary,
        )
        try:
            with self._unit.transaction():
                existing = self._unit.human_handoffs.get_active_for_conversation(
                    conversation_id, owner_user_id
                )
                if existing is not None:
                    return existing
                if self._unit.pending_actions.has_executing_for_conversation(
                    conversation_id
                ):
                    raise HandoffConflictError("账户操作正在完成，请稍后再申请人工服务。")
                self._unit.human_handoffs.create(ticket)
                self._audit(ticket, "handoff.opened", {"reason": reason})
        except sqlite3.IntegrityError:
            winner = self._unit.human_handoffs.get_active_for_conversation(
                conversation_id, owner_user_id
            )
            if winner is None:
                raise
            return winner
        return ticket

    def get_for_owner(
        self, conversation_id: str, owner_user_id: str
    ) -> HumanHandoffRecord:
        ticket = self._unit.human_handoffs.get_latest_for_conversation(
            conversation_id, owner_user_id
        )
        if ticket is None:
            raise KeyError(conversation_id)
        return ticket

    def active_for_conversation(self, conversation_id: str) -> HumanHandoffRecord | None:
        return self._unit.human_handoffs.get_active_for_conversation(conversation_id)

    def list_for_developer(
        self, status: HandoffStatus | None = None
    ) -> list[HumanHandoffRecord]:
        return self._unit.human_handoffs.list(status)

    def get_for_developer(self, ticket_id: str) -> HumanHandoffRecord:
        return self._require(ticket_id)

    def conversation_messages(self, ticket_id: str):
        ticket = self._require(ticket_id)
        return self._unit.messages.list_for_conversation(ticket.conversation_id)

    def claim(self, ticket_id: str, developer_user_id: str) -> HumanHandoffRecord:
        with self._unit.transaction():
            if not self._unit.human_handoffs.claim(ticket_id, developer_user_id):
                raise HandoffConflictError("工单已被其他开发人员处理。")
            ticket = self._require(ticket_id)
            self._audit(
                ticket,
                "handoff.claimed",
                {"developer_user_id": developer_user_id},
            )
        return ticket

    def resolve(self, ticket_id: str, developer_user_id: str) -> HumanHandoffRecord:
        return self._transition(ticket_id, developer_user_id, "resolved")

    def cancel(self, ticket_id: str, developer_user_id: str) -> HumanHandoffRecord:
        return self._transition(ticket_id, developer_user_id, "cancelled")

    def _transition(
        self, ticket_id: str, developer_user_id: str, target: HandoffStatus
    ) -> HumanHandoffRecord:
        ticket = self._require(ticket_id)
        if (
            ticket.status == "in_progress"
            and ticket.assigned_developer_user_id
            and ticket.assigned_developer_user_id != developer_user_id
        ):
            raise HandoffConflictError("工单已由其他开发人员接入。")
        expected: HandoffStatus = ticket.status
        if expected not in {"open", "in_progress"}:
            raise HandoffConflictError("工单已经结束。")
        with self._unit.transaction():
            if not self._unit.human_handoffs.transition(
                ticket_id,
                expected=expected,
                target=target,
                developer_user_id=developer_user_id,
            ):
                raise HandoffConflictError("工单状态已变化，请刷新后重试。")
            updated = self._require(ticket_id)
            self._audit(
                updated,
                f"handoff.{target}",
                {"developer_user_id": developer_user_id},
            )
        return updated

    def _require(self, ticket_id: str) -> HumanHandoffRecord:
        ticket = self._unit.human_handoffs.get(ticket_id)
        if ticket is None:
            raise KeyError(ticket_id)
        return ticket

    def _audit(
        self, ticket: HumanHandoffRecord, event_type: str, payload: dict
    ) -> None:
        self._unit.audit_events.append(
            AuditEventRecord(
                event_id=str(uuid4()),
                conversation_id=ticket.conversation_id,
                event_type=event_type,
                payload={"ticket_id": ticket.ticket_id, **payload},
            )
        )
