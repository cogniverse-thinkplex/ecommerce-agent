from app.agent.proposal_generator import RuleBasedProposalGenerator
from app.agent.session_service import AgentSessionService
from app.evaluation.session_task_check import compare_session_to_task
from app.evaluation.tau_retail_tasks import load_retail_task_summary
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.tau_retail_adapter import TauRetailAdapter


def test_runtime_smoke_matches_initial_tau_retail_task_actions():
    task = load_retail_task_summary("0")
    service = AgentSessionService(
        GuardedRetailToolExecutor(TauRetailAdapter.from_default_data()),
        proposal_generator=RuleBasedProposalGenerator(),
    )
    service.start_session("conv-1")

    result = service.auto_run(
        "conv-1",
        (
            f"{task.known_info}\n"
            f"{task.reason_for_call}\n"
            f"{task.task_instructions}"
        ),
        max_steps=6,
    )
    check = compare_session_to_task(result.state, task)

    assert result.stopped_reason == "pending_confirmation"
    assert check.matched_prefix_count >= 4
    assert check.unexpected_actions == []
