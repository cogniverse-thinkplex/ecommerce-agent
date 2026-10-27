from __future__ import annotations

from typing import Protocol

from app.agent.state import CustomerAgentState
from app.persistence.models import ConversationRecord
from app.persistence.sqlite import SqliteUnitOfWork


class SessionStore(Protocol):
    def create(self, state: CustomerAgentState) -> None: ...
    def get(self, conversation_id: str) -> CustomerAgentState | None: ...
    def save(self, state: CustomerAgentState) -> None: ...
    def list(self) -> list[CustomerAgentState]: ...
    def archive(self, conversation_id: str) -> bool: ...
    def clear(self) -> int: ...


class InMemorySessionStore:
    def __init__(self) -> None:
        self._states: dict[str, CustomerAgentState] = {}

    def create(self, state: CustomerAgentState) -> None:
        self._states[state.conversation_id] = state

    def get(self, conversation_id: str) -> CustomerAgentState | None:
        return self._states.get(conversation_id)

    def save(self, state: CustomerAgentState) -> None:
        self._states[state.conversation_id] = state

    def list(self) -> list[CustomerAgentState]:
        return list(self._states.values())

    def archive(self, conversation_id: str) -> bool:
        return self._states.pop(conversation_id, None) is not None

    def clear(self) -> int:
        count = len(self._states)
        self._states.clear()
        return count


class PersistentSessionStore:
    def __init__(self, unit_of_work: SqliteUnitOfWork) -> None:
        self._unit = unit_of_work

    def create(self, state: CustomerAgentState) -> None:
        with self._unit.transaction():
            self._unit.conversations.save(
                ConversationRecord(conversation_id=state.conversation_id, state=state)
            )

    def get(self, conversation_id: str) -> CustomerAgentState | None:
        record = self._unit.conversations.get(conversation_id)
        if record is None or record.status != "active":
            return None
        return record.state

    def save(self, state: CustomerAgentState) -> None:
        existing = self._unit.conversations.get(state.conversation_id)
        record = (
            existing.model_copy(update={"state": state})
            if existing is not None
            else ConversationRecord(conversation_id=state.conversation_id, state=state)
        )
        with self._unit.transaction():
            self._unit.conversations.save(record)

    def list(self) -> list[CustomerAgentState]:
        return [record.state for record in self._unit.conversations.list_active()]

    def archive(self, conversation_id: str) -> bool:
        with self._unit.transaction():
            return self._unit.conversations.archive(conversation_id)

    def clear(self) -> int:
        records = self._unit.conversations.list_active()
        with self._unit.transaction():
            for record in records:
                self._unit.conversations.archive(record.conversation_id)
        return len(records)

