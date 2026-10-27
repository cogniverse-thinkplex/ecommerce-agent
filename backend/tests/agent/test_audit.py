from datetime import UTC, datetime, timedelta

from app.agent.audit import build_session_audit
from app.agent.state import (
    AgentEvent,
    CompletedWrite,
    CustomerAgentState,
    ObjectiveLedger,
    WriteObjective,
)


def test_build_session_audit_correlates_plan_confirmation_execution_and_state_change():
    created_at = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
    fingerprint = "cancel_pending_order:abc123"
    state = CustomerAgentState(
        conversation_id="conv-audit",
        objective_ledger=ObjectiveLedger(
            original_objective="Cancel order #W1234567",
            write_plan=[
                WriteObjective(
                    objective_id="cancel-1",
                    tool_name="cancel_pending_order",
                    order_id="#W1234567",
                    intent="Cancel the pending order",
                    status="completed",
                    completed_fingerprint=fingerprint,
                )
            ],
            completed_writes=[
                CompletedWrite(
                    name="cancel_pending_order",
                    arguments={"order_id": "#W1234567", "reason": "mistake"},
                    fingerprint=fingerprint,
                )
            ],
        ),
        events=[
            AgentEvent(
                event_type="policy_guard.requires_confirmation",
                payload={
                    "tool": "cancel_pending_order",
                    "fingerprint": fingerprint,
                    "arguments": {"order_id": "#W1234567", "reason": "mistake"},
                },
                created_at=created_at,
            ),
            AgentEvent(
                event_type="policy_guard.confirmed",
                payload={"tool": "cancel_pending_order", "fingerprint": fingerprint},
                created_at=created_at + timedelta(seconds=1),
            ),
            AgentEvent(
                event_type="tool_executor.executed",
                payload={
                    "tool": "cancel_pending_order",
                    "tool_type": "write",
                    "fingerprint": fingerprint,
                    "error": False,
                    "state_changed": True,
                    "state_verification_available": True,
                },
                created_at=created_at + timedelta(seconds=2),
            ),
        ],
    )

    audit = build_session_audit(state)

    assert audit.conversation_id == "conv-audit"
    assert audit.original_objective == "Cancel order #W1234567"
    assert audit.summary.total_objectives == 1
    assert audit.summary.completed_objectives == 1
    assert audit.summary.verified_state_changes == 1
    objective = audit.objectives[0]
    assert objective.objective_id == "cancel-1"
    assert objective.arguments == {"order_id": "#W1234567", "reason": "mistake"}
    assert objective.confirmation_status == "confirmed"
    assert objective.execution_status == "succeeded"
    assert objective.state_verification == "changed"
    assert [entry.kind for entry in audit.timeline] == [
        "confirmation_requested",
        "confirmed",
        "executed",
    ]


def test_build_session_audit_includes_rejected_plan_objective():
    fingerprint = "modify_pending_order_address:def456"
    state = CustomerAgentState(
        conversation_id="conv-rejected",
        objective_ledger=ObjectiveLedger(
            write_plan=[
                WriteObjective(
                    objective_id="address-1",
                    tool_name="modify_pending_order_address",
                    order_id="#W7654321",
                    intent="Update the delivery address",
                )
            ]
        ),
        events=[
            AgentEvent(
                event_type="policy_guard.requires_confirmation",
                payload={
                    "tool": "modify_pending_order_address",
                    "fingerprint": fingerprint,
                    "arguments": {"order_id": "#W7654321", "city": "Shanghai"},
                },
            ),
            AgentEvent(
                event_type="policy_guard.rejected",
                payload={
                    "tool": "modify_pending_order_address",
                    "fingerprint": fingerprint,
                },
            ),
        ],
    )

    audit = build_session_audit(state)

    assert audit.summary.rejected_objectives == 1
    assert audit.objectives[0].confirmation_status == "rejected"
    assert audit.objectives[0].execution_status == "not_executed"
    assert audit.objectives[0].state_verification == "not_run"
