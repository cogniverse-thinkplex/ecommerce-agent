from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from threading import RLock
from uuid import uuid4

from app.auth.models import AuthenticatedUser
from app.observability.models import FeedbackCreate, FeedbackPublic, IssueFeedbackCreate, ObservabilityOverview
from app.observability.redaction import sanitize_context
from app.persistence.models import FeedbackRecord, RuntimeIssueRecord
from app.persistence.sqlite import SqliteUnitOfWork

logger = logging.getLogger(__name__)


class ObservabilityNotFound(KeyError): pass
class ObservabilityForbidden(PermissionError): pass
class ObservabilityConflict(ValueError): pass


class ObservabilityService:
    def __init__(self, unit_of_work: SqliteUnitOfWork) -> None:
        self._unit = unit_of_work
        self._lock = RLock()

    def submit_feedback(self, actor: AuthenticatedUser, conversation_id: str, command: FeedbackCreate) -> FeedbackPublic:
        conversation = self._unit.conversations.get_for_owner(conversation_id, actor.user_id)
        if conversation is None or actor.role != "customer":
            raise ObservabilityNotFound(conversation_id)
        if command.message_id:
            ids = {item.message_id for item in self._unit.messages.list_for_conversation(conversation_id)}
            if command.message_id not in ids:
                raise ObservabilityNotFound(command.message_id)
        now = datetime.now(timezone.utc)
        record = FeedbackRecord(feedback_id=str(uuid4()), user_id=actor.user_id, conversation_id=conversation_id, message_id=command.message_id, rating=command.rating, category=command.category, comment=command.comment, created_at=now, updated_at=now)
        with self._unit.transaction(): self._unit.feedback.append(record)
        return self._public_feedback(record)

    def submit_issue_feedback(self, actor: AuthenticatedUser, command: IssueFeedbackCreate) -> FeedbackPublic:
        if actor.role != "customer":
            raise ObservabilityNotFound(command.conversation_id or "feedback")
        if command.conversation_id is not None:
            conversation = self._unit.conversations.get_for_owner(command.conversation_id, actor.user_id)
            if conversation is None:
                raise ObservabilityNotFound(command.conversation_id)
        now = datetime.now(timezone.utc)
        record = FeedbackRecord(
            feedback_id=str(uuid4()),
            user_id=actor.user_id,
            conversation_id=command.conversation_id,
            rating="not_helpful",
            category=command.category,
            comment=command.comment,
            created_at=now,
            updated_at=now,
        )
        with self._unit.transaction():
            self._unit.feedback.append(record)
        return self._public_feedback(record)

    def list_own_feedback(self, actor: AuthenticatedUser, conversation_id: str) -> list[FeedbackPublic]:
        if self._unit.conversations.get_for_owner(conversation_id, actor.user_id) is None:
            raise ObservabilityNotFound(conversation_id)
        return [self._public_feedback(item) for item in self._unit.feedback.list_for_conversation(conversation_id)]

    def list_feedback_for_developer(self, actor: AuthenticatedUser, **filters):
        self._require_developer(actor)
        with self._lock:
            items, total = self._unit.feedback.list_filtered(**filters)
        return {"items": [item.model_dump(mode="json") for item in items], "total": total}

    def get_feedback_for_developer(self, actor: AuthenticatedUser, feedback_id: str):
        self._require_developer(actor)
        with self._lock: item = self._unit.feedback.get(feedback_id)
        if item is None: raise ObservabilityNotFound(feedback_id)
        return item.model_dump(mode="json")

    def review_feedback(self, actor: AuthenticatedUser, feedback_id: str, *, status: str, developer_note: str | None):
        self._require_developer(actor); now = datetime.now(timezone.utc)
        with self._unit.transaction():
            item = self._unit.feedback.update_review(feedback_id, status=status, developer_note=developer_note, resolved_by_user_id=actor.user_id if status in {"resolved", "dismissed"} else None, updated_at=now)
        return item.model_dump(mode="json")

    def capture_issue(self, *, source: str, severity: str, error_code: str, exception: BaseException | None = None, request_id: str | None = None, conversation_id: str | None = None, context: dict | None = None) -> None:
        try:
            safe = sanitize_context(context or {})
            location = safe.get("tool") or safe.get("path") or safe.get("component") or "unknown"
            exception_type = type(exception).__name__ if exception else "None"
            fingerprint = hashlib.sha256(f"{source}|{error_code}|{exception_type}|{location}".encode()).hexdigest()
            now = datetime.now(timezone.utc)
            record = RuntimeIssueRecord(issue_id=str(uuid4()), fingerprint=fingerprint, source=source, severity=severity, error_code=error_code, summary=str(error_code).replace("_", " ").title(), sanitized_detail=exception_type if exception else None, first_seen_at=now, last_seen_at=now, last_request_id=request_id, last_conversation_id=conversation_id, context=safe)
            with self._lock:
                with self._unit.transaction(): self._unit.runtime_issues.upsert_occurrence(record)
        except Exception:
            logger.exception("Runtime issue capture failed")

    def list_issues_for_developer(self, actor: AuthenticatedUser, **filters):
        self._require_developer(actor)
        with self._lock: items, total = self._unit.runtime_issues.list_filtered(**filters)
        return {"items": [item.model_dump(mode="json") for item in items], "total": total}

    def get_issue_for_developer(self, actor: AuthenticatedUser, issue_id: str):
        self._require_developer(actor)
        with self._lock: item = self._unit.runtime_issues.get(issue_id)
        if item is None: raise ObservabilityNotFound(issue_id)
        return item.model_dump(mode="json")

    def review_issue(self, actor: AuthenticatedUser, issue_id: str, *, status: str, developer_note: str | None):
        self._require_developer(actor)
        if status == "resolved_verified":
            case = self._unit.regression_cases.get_by_origin("issue", issue_id)
            latest = self._unit.regression_case_runs.latest_for_case(case.case_id) if case else None
            if latest is None or latest.status != "passed":
                raise ObservabilityConflict("关联回归用例的最新运行尚未通过。")
        now = datetime.now(timezone.utc); resolved = now if status in {"resolved", "resolved_verified", "ignored"} else None
        with self._unit.transaction(): item = self._unit.runtime_issues.update_review(issue_id, status=status, developer_note=developer_note, resolved_by_user_id=actor.user_id if resolved else None, resolved_at=resolved)
        return item.model_dump(mode="json")

    def overview(self, actor: AuthenticatedUser) -> ObservabilityOverview:
        self._require_developer(actor)
        with self._lock:
            feedback, _ = self._unit.feedback.list_filtered(limit=100, offset=0)
            issues, _ = self._unit.runtime_issues.list_filtered(limit=100, offset=0)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        return ObservabilityOverview(issues_24h=sum(i.occurrence_count for i in issues if i.last_seen_at >= cutoff), open_critical_issues=sum(1 for i in issues if i.status == "open" and i.severity == "critical"), new_feedback=sum(1 for f in feedback if f.status == "new"), negative_feedback=sum(1 for f in feedback if f.rating == "not_helpful"))

    @staticmethod
    def _public_feedback(record: FeedbackRecord) -> FeedbackPublic:
        return FeedbackPublic(feedback_id=record.feedback_id, conversation_id=record.conversation_id, message_id=record.message_id, rating=record.rating, category=record.category, comment=record.comment, status=record.status, created_at=record.created_at.isoformat(), updated_at=record.updated_at.isoformat())

    @staticmethod
    def _require_developer(actor: AuthenticatedUser) -> None:
        if actor.role != "developer": raise ObservabilityForbidden()
