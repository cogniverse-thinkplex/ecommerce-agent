import json
from datetime import UTC, datetime

from app.agent.trace import TraceEntry
from app.evaluation.runtime_task_runner import (
    _run_with_confirmed_writes,
    diagnose_session_task_check,
    save_runtime_task_subset_artifact,
    run_retail_task_subset,
    _summarize_runtime_subset_results,
    _summarize_failure,
    _verify_outcome_execution,
)
from app.evaluation.outcome_evaluator import BusinessOutcomeCheck
from app.evaluation.session_task_check import SessionTaskCheck
from app.agent.state import ConfirmationState, CustomerAgentState, PendingAction
from app.agent.nodes.tool_proposal_node import ToolProposal
from app.agent.session_service import AgentSessionService
from app.evaluation.tau_retail_tasks import ExpectedActionSummary, RetailTaskSummary
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.retail_port import RetailToolDefinition
from tests.agent.test_session_service import RecordingPort, SequencedProposalGenerator


def test_run_retail_task_subset_reports_task_alignment():
    results = run_retail_task_subset(["0"], max_steps=6)

    assert len(results) == 1
    result = results[0]
    assert result.task_id == "0"
    assert result.planner_type == "rule"
    assert result.stopped_reason == "pending_confirmation"
    assert result.check.matched_prefix_count >= 4
    assert result.check.business_success is True
    assert result.step_budget == 6
    assert result.check.unexpected_actions == []
    assert result.diagnostic.first_mismatch_index is None
    assert result.diagnostic.expected_action is None
    assert result.diagnostic.actual_action is None
    assert result.diagnostic.message == "动作序列完全匹配。"
    assert result.failure_summary.category == "pending_confirmation"
    assert result.failure_summary.rejection_kind is None
    assert result.failure_summary.planner_terminal_kind is None
    assert result.trace_entries
    assert any(entry.kind == "tool_proposal.accepted" for entry in result.trace_entries)
    assert result.action_timeline[0].expected_action == "find_user_id_by_name_zip"
    assert result.action_timeline[0].actual_action == "find_user_id_by_name_zip"
    assert result.action_timeline[0].matched is True
    assert result.action_timeline[0].trace_sequence is not None
    assert "name and zip" in result.action_timeline[0].rationale
    assert result.action_timeline[0].rejection_reason is None


def test_run_retail_task_subset_can_verify_confirmed_database_change():
    result = run_retail_task_subset(
        ["0"],
        max_steps=6,
        verify_outcome_execution=True,
    )[0]

    assert result.step_count == 5
    assert result.check.business_success is True
    assert result.check.business_success_basis == "confirmed_state_change"
    assert result.check.confirmation_gate_success is True
    assert result.check.confirmed_outcome_success is True
    assert result.check.outcome is not None
    assert result.check.outcome.arguments_match is True
    assert result.check.outcome.confirmation_executed is True
    assert result.check.outcome.state_changed is True
    assert result.check.outcome.status == "confirmed_state_verified"
    assert result.failure_summary.category == "business_success"
    assert any(entry.kind == "policy_guard.confirmed" for entry in result.trace_entries)
    assert any(entry.kind == "tool_executor.executed" for entry in result.trace_entries)


def test_long_rule_subset_distinguishes_business_failure_from_trace_deviation():
    results = run_retail_task_subset(
        ["0", "1", "2"],
        max_steps=12,
        verify_outcome_execution=True,
    )

    summary = _summarize_runtime_subset_results(results)

    assert summary.confirmed_outcome_success_count == 3
    assert summary.failed_task_ids == []
    assert summary.deviation_task_ids == ["2"]
    assert results[2].step_count == 9
    assert results[2].failure_summary.category == "business_success"


def test_rule_subset_completes_pending_tshirt_modifications():
    results = run_retail_task_subset(
        ["3", "4"],
        max_steps=12,
        verify_outcome_execution=True,
    )

    summary = _summarize_runtime_subset_results(results)

    assert summary.confirmed_outcome_success_count == 2
    assert summary.failed_task_ids == []
    assert all(result.check.confirmed_outcome_success for result in results)
    assert results[0].check.outcome.executed_write_count == 1
    assert results[1].check.outcome.executed_write_count == 2


def test_multi_write_runner_confirms_each_exact_write_and_continues():
    actions = [
        ExpectedActionSummary(
            action_id="address",
            name="modify_pending_order_address",
            arguments={"order_id": "#W1", "city": "Charlotte"},
        ),
        ExpectedActionSummary(
            action_id="items",
            name="modify_pending_order_items",
            arguments={"order_id": "#W1", "item_ids": ["old"], "new_item_ids": ["new"]},
        ),
    ]
    tools = [
        RetailToolDefinition(
            name=action.name,
            tool_type="write",
            description="",
            parameters_schema={},
        )
        for action in actions
    ]
    service = AgentSessionService(
        GuardedRetailToolExecutor(RecordingPort(tools)),
        proposal_generator=SequencedProposalGenerator(
            [
                ToolProposal(tool_name=action.name, arguments=action.arguments)
                for action in actions
            ]
        ),
    )
    service.start_session("conv-1")
    task = RetailTaskSummary(
        task_id="multi",
        reason_for_call="",
        known_info="",
        unknown_info="",
        task_instructions="",
        reward_basis=[],
        expected_actions=actions,
    )

    result = _run_with_confirmed_writes(
        service,
        conversation_id="conv-1",
        objective="update address and items",
        task=task,
        max_steps=4,
    )

    assert result.auto_run.stopped_reason == "no_proposal"
    assert result.executed_write_count == 2
    assert result.state.confirmation.pending is None
    assert [
        event.payload["tool"]
        for event in result.state.events
        if event.event_type == "tool_executor.executed"
    ] == ["modify_pending_order_address", "modify_pending_order_items"]


def test_multi_write_runner_does_not_confirm_wrong_intermediate_arguments():
    action = ExpectedActionSummary(
        action_id="address",
        name="modify_pending_order_address",
        arguments={"order_id": "#W1", "city": "Charlotte"},
    )
    service = AgentSessionService(
        GuardedRetailToolExecutor(
            RecordingPort(
                [RetailToolDefinition(name=action.name, tool_type="write", description="", parameters_schema={})]
            )
        ),
        proposal_generator=SequencedProposalGenerator(
            [ToolProposal(tool_name=action.name, arguments={"order_id": "#W1", "city": "Boston"})]
        ),
    )
    service.start_session("conv-1")
    task = RetailTaskSummary(
        task_id="multi",
        reason_for_call="",
        known_info="",
        unknown_info="",
        task_instructions="",
        reward_basis=[],
        expected_actions=[action],
    )

    result = _run_with_confirmed_writes(
        service,
        conversation_id="conv-1",
        objective="update address",
        task=task,
        max_steps=2,
    )

    assert result.executed_write_count == 0
    assert result.state.confirmation.pending is not None
    assert not any(event.event_type == "tool_executor.executed" for event in result.state.events)


def test_verify_outcome_execution_revalidates_current_pending_action():
    service = _StalePendingService()
    check = SessionTaskCheck(
        task_id="demo",
        expected_actions=["cancel_pending_order"],
        actual_actions=["cancel_pending_order"],
        matched_prefix_count=1,
        exact_match=True,
        business_success=True,
        confirmation_gate_success=True,
        business_success_basis="target_write_pending",
        outcome=BusinessOutcomeCheck(
            applicable=True,
            target_action="cancel_pending_order",
            expected_arguments={"order_id": "#W1234567"},
            actual_arguments={"order_id": "#W1234567"},
            tool_match=True,
            arguments_match=True,
            confirmation_gate_reached=True,
            success=True,
            status="pending_confirmation_verified",
        ),
        missing_actions=[],
        unexpected_actions=[],
    )

    result = _verify_outcome_execution(
        service,
        conversation_id="conv-1",
        check=check,
    )

    assert result == check
    assert service.confirmation_calls == 0
    assert service.tool_calls == 0


def test_runtime_summary_marks_unknown_cost_as_unavailable():
    result = run_retail_task_subset(["0"], max_steps=6)[0].model_copy(
        update={"cost": None}
    )

    summary = _summarize_runtime_subset_results([result])

    assert summary.cost_available is False
    assert summary.total_cost is None
    assert summary.average_cost is None


def test_diagnose_session_task_check_reports_first_mismatch():
    diagnostic = diagnose_session_task_check(
        SessionTaskCheck(
            task_id="demo",
            expected_actions=["find_user_id_by_name_zip", "get_order_details"],
            actual_actions=["find_user_id_by_name_zip", "get_product_details"],
            matched_prefix_count=1,
            exact_match=False,
            missing_actions=["get_order_details"],
            unexpected_actions=["get_product_details"],
        )
    )

    assert diagnostic.first_mismatch_index == 1
    assert diagnostic.expected_action == "get_order_details"
    assert diagnostic.actual_action == "get_product_details"


def test_summarize_failure_keeps_exact_pending_confirmation_a_successful_gate():
    check = SessionTaskCheck(
        task_id="demo",
        expected_actions=["exchange_delivered_order_items"],
        actual_actions=["exchange_delivered_order_items"],
        matched_prefix_count=1,
        exact_match=True,
        missing_actions=[],
        unexpected_actions=[],
    )
    diagnostic = diagnose_session_task_check(check)

    summary = _summarize_failure(
        stopped_reason="pending_confirmation",
        diagnostic=diagnostic,
        trace_entries=[
            TraceEntry(
                sequence=1,
                source="event",
                kind="tool_proposal.rejected",
                created_at=datetime.now(UTC),
                payload={"reason": "missing_required_arguments"},
            )
        ],
    )

    assert summary.category == "pending_confirmation"
    assert summary.rejection_kind is None
    assert summary.first_mismatch_index is None


def test_summarize_failure_treats_recovered_rejection_as_diagnostic():
    check = SessionTaskCheck(
        task_id="demo",
        expected_actions=["get_product_details", "get_user_details"],
        actual_actions=["get_product_details", "get_order_details"],
        matched_prefix_count=1,
        exact_match=False,
        missing_actions=["get_user_details"],
        unexpected_actions=["get_order_details"],
    )

    summary = _summarize_failure(
        stopped_reason="max_steps",
        diagnostic=diagnose_session_task_check(check),
        trace_entries=[
            TraceEntry(
                sequence=1,
                source="event",
                kind="skill_node.rejected",
                created_at=datetime.now(UTC),
                payload={"reason": "unknown_skill_action"},
            ),
            TraceEntry(
                sequence=2,
                source="event",
                kind="planner.rejected_skill_fallback",
                created_at=datetime.now(UTC),
                payload={"fallback_tool": "get_product_details"},
            ),
        ],
    )

    assert summary.category == "action_deviation"
    assert summary.rejection_kind is None
    assert summary.recovery_kinds == ["planner.rejected_skill_fallback"]


def test_save_runtime_task_subset_artifact_writes_result_json(tmp_path):
    results = run_retail_task_subset(["0"], max_steps=6)

    artifact = save_runtime_task_subset_artifact(
        results,
        output_dir=tmp_path,
        run_name="runtime-subset-demo",
        max_steps=6,
    )

    artifact_file = tmp_path / "runtime-subset-demo" / "runtime_subset.json"
    assert artifact.run_name == "runtime-subset-demo"
    assert artifact.path == str(artifact_file)
    payload = json.loads(artifact_file.read_text())
    assert payload["run_name"] == "runtime-subset-demo"
    assert payload["task_ids"] == ["0"]
    assert payload["planner_type"] == "rule"
    assert payload["max_steps"] == 6
    assert payload["summary"]["total_tasks"] == 1
    assert payload["summary"]["exact_match_count"] == 1
    assert payload["summary"]["business_success_count"] == 1
    assert payload["summary"]["business_failed_task_ids"] == []
    assert payload["summary"]["failed_task_ids"] == []
    assert payload["summary"]["stopped_reasons"] == {"pending_confirmation": 1}
    assert payload["summary"]["deviation_task_ids"] == []
    assert payload["results"][0]["task_id"] == "0"
    assert payload["results"][0]["planner_type"] == "rule"
    assert payload["results"][0]["step_budget"] == 6
    assert payload["results"][0]["diagnostic"]["message"] == "动作序列完全匹配。"
    assert payload["results"][0]["failure_summary"]["category"] == "pending_confirmation"
    assert payload["results"][0]["failure_summary"]["rejection_kind"] is None
    assert payload["results"][0]["trace_entries"]
    assert payload["results"][0]["action_timeline"][0]["matched"] is True
    assert payload["results"][0]["action_timeline"][0]["rationale"]


class _StalePendingService:
    def __init__(self) -> None:
        self.confirmation_calls = 0
        self.tool_calls = 0
        self.state = CustomerAgentState(
            conversation_id="conv-1",
            confirmation=ConfirmationState(
                pending=PendingAction(
                    name="cancel_pending_order",
                    arguments={"order_id": "#W7654321"},
                    fingerprint="stale",
                )
            ),
        )

    def get_session(self, conversation_id: str) -> CustomerAgentState:
        return self.state

    def apply_confirmation_reply(self, *args, **kwargs):
        self.confirmation_calls += 1

    def apply_tool_request(self, *args, **kwargs):
        self.tool_calls += 1

    def backend_state_hash(self) -> str:
        return "hash"
