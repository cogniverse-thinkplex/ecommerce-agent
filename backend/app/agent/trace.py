from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.state import CustomerAgentState, PendingAction


TraceSource = Literal["message", "event"]


class TraceEntry(BaseModel):
    sequence: int
    source: TraceSource
    kind: str
    created_at: datetime
    content: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SessionTrace(BaseModel):
    conversation_id: str
    entries: list[TraceEntry]
    pending_action: PendingAction | None = None
    confirmed_fingerprints: list[str] = Field(default_factory=list)


def build_session_trace(state: CustomerAgentState) -> SessionTrace:
    unsorted_entries: list[TraceEntry] = []
    for message in state.messages:
        unsorted_entries.append(
            TraceEntry(
                sequence=0,
                source="message",
                kind=message.role,
                created_at=message.created_at,
                content=message.content,
                tool_name=message.tool_name,
                tool_call_id=message.tool_call_id,
            )
        )
    for event in state.events:
        unsorted_entries.append(
            TraceEntry(
                sequence=0,
                source="event",
                kind=event.event_type,
                created_at=event.created_at,
                payload=event.payload,
            )
        )

    entries = [
        entry.model_copy(update={"sequence": index})
        for index, entry in enumerate(
            sorted(unsorted_entries, key=lambda entry: entry.created_at),
            start=1,
        )
    ]
    return SessionTrace(
        conversation_id=state.conversation_id,
        entries=entries,
        pending_action=state.confirmation.pending,
        confirmed_fingerprints=state.confirmation.confirmed_fingerprints,
    )
