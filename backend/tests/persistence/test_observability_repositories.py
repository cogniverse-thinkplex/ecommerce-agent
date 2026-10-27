from datetime import datetime, timedelta, timezone

from app.persistence.models import FeedbackRecord, RuntimeIssueRecord
from app.persistence.models import ConversationRecord, UserRecord
from app.agent.state import CustomerAgentState
from app.persistence.sqlite import SqliteUnitOfWork


NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


def test_runtime_issues_are_aggregated_by_fingerprint(tmp_path):
    unit = SqliteUnitOfWork(tmp_path / "app.db")
    unit.initialize()
    first = RuntimeIssueRecord(
        issue_id="issue-1",
        fingerprint="same",
        source="mcp",
        severity="error",
        error_code="MCP_TIMEOUT",
        summary="MCP request timed out",
        first_seen_at=NOW,
        last_seen_at=NOW,
        context={"tool": "get_order_details"},
    )
    second = first.model_copy(
        update={"issue_id": "issue-2", "last_seen_at": NOW + timedelta(minutes=2)}
    )

    with unit.transaction():
        unit.runtime_issues.upsert_occurrence(first)
        aggregated = unit.runtime_issues.upsert_occurrence(second)

    assert aggregated.issue_id == "issue-1"
    assert aggregated.occurrence_count == 2
    assert aggregated.first_seen_at == NOW
    assert aggregated.last_seen_at == NOW + timedelta(minutes=2)


def test_feedback_and_issue_review_persist_after_reconnect(tmp_path):
    path = tmp_path / "app.db"
    unit = SqliteUnitOfWork(path)
    unit.initialize()
    with unit.transaction():
        unit.users.create(UserRecord(user_id="customer-1", email="customer@example.com", display_name="Customer", password_hash="hash", role="customer"))
        unit.conversations.save(ConversationRecord(conversation_id="conversation-1", owner_user_id="customer-1", state=CustomerAgentState(conversation_id="conversation-1")))
        unit.feedback.append(
            FeedbackRecord(
                feedback_id="feedback-1",
                user_id="customer-1",
                conversation_id="conversation-1",
                rating="not_helpful",
                category="incorrect",
                comment="The answer was wrong",
                created_at=NOW,
                updated_at=NOW,
            )
        )
    unit.close()

    reopened = SqliteUnitOfWork(path)
    reopened.initialize()
    feedback = reopened.feedback.get("feedback-1")

    assert feedback is not None
    assert feedback.rating == "not_helpful"
    assert feedback.status == "new"
