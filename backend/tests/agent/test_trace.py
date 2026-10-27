from datetime import UTC, datetime

from app.agent.state import (
    AgentEvent,
    ConfirmationState,
    ConversationMessage,
    CustomerAgentState,
    PendingAction,
)
from app.agent.trace import build_session_trace


def test_build_session_trace_merges_messages_and_events_by_time():
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="user",
                content="Find user Yusuf Rossi",
                created_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
            ),
            ConversationMessage(
                role="tool",
                content="yusuf_rossi_9620",
                tool_name="find_user_id_by_name_zip",
                tool_call_id="call-1",
                created_at=datetime(2026, 1, 1, 12, 0, 2, tzinfo=UTC),
            ),
        ],
        events=[
            AgentEvent(
                event_type="policy_guard.allowed",
                payload={
                    "tool": "find_user_id_by_name_zip",
                    "tool_type": "read",
                },
                created_at=datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC),
            )
        ],
        confirmation=ConfirmationState(
            pending=PendingAction(
                name="cancel_pending_order",
                arguments={"order_id": "#W0000000"},
                fingerprint="cancel_pending_order:abc123",
            ),
            confirmed_fingerprints=["refund_order:def456"],
        ),
    )

    trace = build_session_trace(state)

    assert trace.conversation_id == "conv-1"
    assert trace.pending_action is not None
    assert trace.pending_action.name == "cancel_pending_order"
    assert trace.confirmed_fingerprints == ["refund_order:def456"]
    assert [entry.sequence for entry in trace.entries] == [1, 2, 3]
    assert [(entry.source, entry.kind) for entry in trace.entries] == [
        ("message", "user"),
        ("event", "policy_guard.allowed"),
        ("message", "tool"),
    ]
    assert trace.entries[0].content == "Find user Yusuf Rossi"
    assert trace.entries[1].payload == {
        "tool": "find_user_id_by_name_zip",
        "tool_type": "read",
    }
    assert trace.entries[2].tool_name == "find_user_id_by_name_zip"
