from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import logging
from threading import RLock
from typing import TypeVar
from uuid import uuid4

from app.observability.redaction import sanitize_context
from app.persistence.models import AgentRunRecord, AgentRunStepRecord
from app.persistence.sqlite import SqliteUnitOfWork
from app.telemetry.models import FinishRunCommand, RecordStepCommand, StartRunCommand


logger = logging.getLogger(__name__)
T = TypeVar("T")


class RunTelemetryService:
    def __init__(self, unit_of_work: SqliteUnitOfWork) -> None:
        self._unit = unit_of_work
        self._lock = RLock()

    def start_run(self, command: StartRunCommand) -> AgentRunRecord:
        record = AgentRunRecord(
            run_id=str(uuid4()),
            conversation_id=command.conversation_id,
            source=command.source,
            planner_type=command.planner_type,
            model=command.model,
            tool_backend=command.tool_backend,
            policy_version=command.policy_version,
            data_version=command.data_version,
            status="running",
            started_at=command.started_at or datetime.now(timezone.utc),
        )
        with self._lock, self._unit.transaction():
            self._unit.agent_runs.create(record)
        return record

    def record_step(
        self,
        run_id: str,
        command: RecordStepCommand,
    ) -> AgentRunStepRecord:
        started_at = command.started_at or datetime.now(timezone.utc)
        finished_at = command.finished_at
        duration_ms = command.duration_ms
        if duration_ms is None and finished_at is not None:
            duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
        record = AgentRunStepRecord(
            step_id=str(uuid4()),
            run_id=run_id,
            kind=command.kind,
            name=command.name,
            status=command.status,
            summary=sanitize_context(command.summary),
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
        )
        with self._lock, self._unit.transaction():
            return self._unit.agent_run_steps.append(record)

    def finish_run(
        self,
        run_id: str,
        command: FinishRunCommand,
    ) -> AgentRunRecord:
        with self._lock:
            current = self._unit.agent_runs.get(run_id)
            if current is None:
                raise KeyError(run_id)
            finished_at = command.finished_at or datetime.now(timezone.utc)
            duration_ms = max(
                0, int((finished_at - current.started_at).total_seconds() * 1000)
            )
            step_count = len(self._unit.agent_run_steps.list_for_run(run_id))
            with self._unit.transaction():
                return self._unit.agent_runs.finish(
                    run_id,
                    **command.model_dump(exclude={"finished_at"}),
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    step_count=step_count,
                )

    def recover_stale_runs(self, cutoff: datetime) -> int:
        recovered = 0
        for record in self._unit.agent_runs.list_all():
            if record.status != "running" or record.started_at >= cutoff:
                continue
            self.finish_run(
                record.run_id,
                FinishRunCommand(
                    status="failed",
                    stopped_reason="stale_run_recovered",
                    error_code="stale_run_recovered",
                    finished_at=cutoff,
                ),
            )
            recovered += 1
        return recovered

    def safe_capture(self, operation: Callable[[], T], *, source: str) -> T | None:
        try:
            return operation()
        except Exception:
            logger.exception("Telemetry capture failed for %s", source)
            return None
