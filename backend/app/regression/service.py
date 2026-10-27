from __future__ import annotations

from datetime import datetime, timezone
from sqlite3 import IntegrityError
from typing import Callable, Literal
from uuid import uuid4

from app.auth.models import AuthenticatedUser
from app.evaluation.runtime_task_runner import run_retail_task_subset
from app.persistence.models import AgentRunRecord, RegressionCaseRecord, RegressionCaseRunRecord
from app.persistence.sqlite import SqliteUnitOfWork
from app.observability.redaction import sanitize_context
from app.regression.models import (
    RegressionBatch,
    RegressionBatchCommand,
    RegressionCaseCreate,
    RegressionCasePage,
    RegressionCaseUpdate,
)

ExecutionResult = tuple[Literal["passed", "failed", "blocked"], str | None, str | None]
CaseExecutor = Callable[[RegressionCaseRecord, RegressionBatchCommand], ExecutionResult]


class RegressionCaseNotFound(KeyError):
    pass


class RegressionBatchNotFound(KeyError):
    pass


class RegressionCaseInvalid(ValueError):
    pass


class RegressionService:
    def __init__(self, unit_of_work: SqliteUnitOfWork, executor: CaseExecutor | None = None) -> None:
        self._unit = unit_of_work
        self._executor = executor or _execute_case

    def list_cases(self, status: str | None = None) -> RegressionCasePage:
        items = self._unit.regression_cases.list_all()
        if status:
            items = [item for item in items if item.status == status]
        return RegressionCasePage(items=items, total=len(items))

    def create_case(self, actor: AuthenticatedUser, command: RegressionCaseCreate) -> RegressionCaseRecord:
        now = datetime.now(timezone.utc)
        record = RegressionCaseRecord(
            case_id=str(uuid4()), created_by_user_id=actor.user_id,
            created_at=now, updated_at=now, **command.model_dump(),
        )
        if record.status == "active":
            _validate_activation(record)
        try:
            with self._unit.transaction():
                self._unit.regression_cases.create(record)
        except IntegrityError as exc:
            raise RegressionCaseInvalid("该来源已存在回归用例。") from exc
        return record

    def update_case(self, case_id: str, command: RegressionCaseUpdate) -> RegressionCaseRecord:
        current = self._unit.regression_cases.get(case_id)
        if current is None:
            raise RegressionCaseNotFound(case_id)
        changes = command.model_dump(exclude_none=True)
        updated = current.model_copy(update={**changes, "updated_at": datetime.now(timezone.utc)})
        if updated.status == "active":
            _validate_activation(updated)
        with self._unit.transaction():
            self._unit.regression_cases.update(updated)
        return updated

    def create_from_issue(self, actor: AuthenticatedUser, issue_id: str) -> RegressionCaseRecord:
        existing = self._unit.regression_cases.get_by_origin("issue", issue_id)
        if existing is not None:
            return existing
        issue = self._unit.runtime_issues.get(issue_id)
        if issue is None:
            raise RegressionCaseNotFound(issue_id)
        return self.create_case(actor, RegressionCaseCreate(
            name=f"问题回归：{issue.summary}",
            description=f"来源 {issue.source} / {issue.error_code}",
            origin_type="issue", origin_id=issue.issue_id,
            fixture_type="tau2_task",
            fixture=sanitize_context({
                "error_code": issue.error_code,
                "source": issue.source,
                "conversation_id": issue.last_conversation_id,
                "context": issue.context,
            }),
        ))

    def create_from_feedback(self, actor: AuthenticatedUser, feedback_id: str) -> RegressionCaseRecord:
        existing = self._unit.regression_cases.get_by_origin("feedback", feedback_id)
        if existing is not None:
            return existing
        feedback = self._unit.feedback.get(feedback_id)
        if feedback is None:
            raise RegressionCaseNotFound(feedback_id)
        messages = self._unit.messages.list_for_conversation(feedback.conversation_id)
        replay = [
            {"role": message.role, "content": message.text}
            for message in messages if message.text and message.role in {"user", "assistant"}
        ]
        return self.create_case(actor, RegressionCaseCreate(
            name=f"反馈回归：{feedback.category or feedback.rating}",
            description=feedback.comment or "由用户反馈生成。",
            origin_type="feedback", origin_id=feedback.feedback_id,
            fixture_type="conversation_replay",
            fixture=sanitize_context({"messages": replay, "conversation_id": feedback.conversation_id}),
        ))

    def create_from_run(self, actor: AuthenticatedUser, run_id: str) -> RegressionCaseRecord:
        existing = self._unit.regression_cases.get_by_origin("conversation", run_id)
        if existing is not None:
            return existing
        run = self._unit.agent_runs.get(run_id)
        if run is None:
            raise RegressionCaseNotFound(run_id)
        return self.create_case(actor, RegressionCaseCreate(
            name=f"运行回归：{run.run_id[:8]}",
            description=f"{run.source} / {run.status} / {run.stopped_reason or '无停止原因'}",
            origin_type="conversation", origin_id=run.run_id,
            fixture_type="conversation_replay",
            fixture=sanitize_context({
                "messages": [{"role": "user", "content": "请根据来源运行补充稳定重放输入。"}],
                "source_run_id": run.run_id,
                "conversation_id": run.conversation_id,
            }),
        ))

    def issue_can_be_verified(self, issue_id: str) -> bool:
        case = self._unit.regression_cases.get_by_origin("issue", issue_id)
        if case is None:
            return False
        latest = self._unit.regression_case_runs.latest_for_case(case.case_id)
        return latest is not None and latest.status == "passed"

    def run_batch(
        self,
        case_ids: list[str],
        planner_type: Literal["rule", "llm"] = "rule",
        max_steps: int = 8,
        verify_outcome_execution: bool = True,
    ) -> RegressionBatch:
        command = RegressionBatchCommand(
            case_ids=case_ids, planner_type=planner_type, max_steps=max_steps,
            verify_outcome_execution=verify_outcome_execution,
        )
        cases: list[RegressionCaseRecord] = []
        for case_id in dict.fromkeys(command.case_ids):
            case = self._unit.regression_cases.get(case_id)
            if case is None:
                raise RegressionCaseInvalid(f"回归用例不存在：{case_id}")
            if case.status != "active":
                raise RegressionCaseInvalid(f"回归用例尚未激活：{case.name}")
            cases.append(case)

        batch_id = str(uuid4())
        results: list[RegressionCaseRunRecord] = []
        for case in cases:
            created_at = datetime.now(timezone.utc)
            agent_run_id = str(uuid4())
            with self._unit.transaction():
                self._unit.agent_runs.create(AgentRunRecord(
                    run_id=agent_run_id, source="regression",
                    planner_type=command.planner_type,
                    tool_backend="tau2-retail-mcp", status="running",
                    started_at=created_at,
                ))
            try:
                result_status, reason, _ = self._executor(case, command)
            except Exception as exc:
                result_status, reason = "blocked", type(exc).__name__
            finished_at = datetime.now(timezone.utc)
            with self._unit.transaction():
                self._unit.agent_runs.finish(
                    agent_run_id,
                    status=("succeeded" if result_status == "passed" else "failed" if result_status == "failed" else "cancelled"),
                    stopped_reason=("regression_completed" if result_status == "passed" else "regression_failed" if result_status == "failed" else "environment_blocked"),
                    business_success=(result_status == "passed") if result_status != "blocked" else None,
                    error_code="REGRESSION_BLOCKED" if result_status == "blocked" else None,
                    finished_at=finished_at,
                    duration_ms=max(0, int((finished_at-created_at).total_seconds()*1000)),
                    step_count=0,
                )
            result = RegressionCaseRunRecord(
                case_run_id=str(uuid4()), case_id=case.case_id,
                agent_run_id=agent_run_id, batch_id=batch_id, status=result_status,
                failure_reason=reason, created_at=created_at,
                finished_at=finished_at,
            )
            with self._unit.transaction():
                self._unit.regression_case_runs.create(result)
            results.append(result)
        return _summarize_batch(batch_id, command.planner_type, results)

    def get_batch(self, batch_id: str) -> RegressionBatch:
        results = self._unit.regression_case_runs.list_for_batch(batch_id)
        if not results:
            raise RegressionBatchNotFound(batch_id)
        return _summarize_batch(batch_id, "rule", results)


def _validate_activation(case: RegressionCaseRecord) -> None:
    if not case.expected:
        raise RegressionCaseInvalid("激活回归用例前必须设置至少一项明确预期。")
    if case.fixture_type == "tau2_task" and not case.fixture.get("task_id"):
        raise RegressionCaseInvalid("tau2 用例缺少 task_id。")
    if case.fixture_type == "conversation_replay":
        messages = case.fixture.get("messages")
        if not isinstance(messages, list) or not messages:
            raise RegressionCaseInvalid("会话重放用例缺少 messages。")


def _execute_case(case: RegressionCaseRecord, command: RegressionBatchCommand) -> ExecutionResult:
    if case.fixture_type != "tau2_task":
        return "blocked", "当前会话快照缺少可隔离重放的 Retail 数据状态。", None
    result = run_retail_task_subset(
        [str(case.fixture["task_id"])], split=case.fixture.get("split", "base"),
        max_steps=command.max_steps, planner_type=command.planner_type,
        verify_outcome_execution=command.verify_outcome_execution,
    )[0]
    passed = bool(result.check.business_success)
    reason = None if passed else result.failure_summary.recommended_action
    return ("passed" if passed else "failed"), reason, None


def _summarize_batch(batch_id: str, planner_type: Literal["rule", "llm"], results: list[RegressionCaseRunRecord]) -> RegressionBatch:
    passed = sum(item.status == "passed" for item in results)
    failed = sum(item.status == "failed" for item in results)
    blocked = sum(item.status == "blocked" for item in results)
    status: Literal["passed", "failed", "blocked"] = "failed" if failed else ("blocked" if blocked else "passed")
    return RegressionBatch(
        batch_id=batch_id, status=status, planner_type=planner_type,
        total_count=len(results), passed_count=passed, failed_count=failed,
        blocked_count=blocked, results=results,
    )
