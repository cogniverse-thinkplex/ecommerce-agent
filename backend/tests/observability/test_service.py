from app.agent.state import CustomerAgentState
from app.auth.models import AuthenticatedUser
from app.observability.models import FeedbackCreate, IssueFeedbackCreate
from app.observability.service import ObservabilityConflict, ObservabilityService, ObservabilityNotFound
from app.persistence.models import ConversationRecord, UserRecord
from app.persistence.sqlite import SqliteUnitOfWork


def user(user_id="customer-1", role="customer"):
    return AuthenticatedUser(user_id=user_id, email=f"{user_id}@example.com", display_name=user_id, role=role, status="active", must_change_password=False)


def service(tmp_path):
    unit = SqliteUnitOfWork(tmp_path / "app.db"); unit.initialize()
    with unit.transaction():
        for uid in ("customer-1", "customer-2"):
            unit.users.create(UserRecord(user_id=uid, email=f"{uid}@example.com", display_name=uid, password_hash="h", role="customer"))
        unit.conversations.save(ConversationRecord(conversation_id="conv-1", owner_user_id="customer-1", state=CustomerAgentState(conversation_id="conv-1")))
    return ObservabilityService(unit), unit


def test_customer_submits_feedback_only_for_owned_conversation(tmp_path):
    observed, _ = service(tmp_path)
    created = observed.submit_feedback(user(), "conv-1", FeedbackCreate(rating="not_helpful", category="incorrect", comment="Wrong"))
    assert created.rating == "not_helpful"
    assert not hasattr(created, "developer_note")

    try:
        observed.submit_feedback(user("customer-2"), "conv-1", FeedbackCreate(rating="helpful"))
    except ObservabilityNotFound:
        pass
    else:
        raise AssertionError("foreign conversation was exposed")


def test_customer_submits_standalone_issue_feedback(tmp_path):
    observed, unit = service(tmp_path)

    created = observed.submit_issue_feedback(
        user(),
        IssueFeedbackCreate(category="interface", comment="会话列表在窄屏下会遮住标题。"),
    )

    assert created.conversation_id is None
    assert created.rating == "not_helpful"
    assert created.category == "interface"
    stored = unit.feedback.get(created.feedback_id)
    assert stored is not None
    assert stored.comment == "会话列表在窄屏下会遮住标题。"


def test_issue_feedback_may_only_reference_owned_conversation(tmp_path):
    observed, _ = service(tmp_path)

    created = observed.submit_issue_feedback(
        user(),
        IssueFeedbackCreate(
            conversation_id="conv-1", category="incorrect", comment="订单状态不正确。"
        ),
    )
    assert created.conversation_id == "conv-1"

    try:
        observed.submit_issue_feedback(
            user("customer-2"),
            IssueFeedbackCreate(
                conversation_id="conv-1", category="incorrect", comment="不应允许关联。"
            ),
        )
    except ObservabilityNotFound:
        pass
    else:
        raise AssertionError("foreign conversation was exposed")


def test_capture_issue_aggregates_and_redacts(tmp_path):
    observed, unit = service(tmp_path)
    observed.capture_issue(source="mcp", severity="error", error_code="TIMEOUT", exception=TimeoutError("secret"), context={"api_key": "sk-secret", "tool": "lookup"})
    observed.capture_issue(source="mcp", severity="error", error_code="TIMEOUT", exception=TimeoutError("other"), context={"api_key": "other", "tool": "lookup"})
    issues, total = unit.runtime_issues.list_filtered()
    assert total == 1
    assert issues[0].occurrence_count == 2
    assert issues[0].context["api_key"] == "[REDACTED]"


def test_issue_cannot_be_marked_verified_without_passing_regression(tmp_path):
    observed, unit = service(tmp_path)
    observed.capture_issue(source="api", severity="error", error_code="BROKEN")
    issue = unit.runtime_issues.list_filtered()[0][0]

    try:
        observed.review_issue(user(role="developer"), issue.issue_id, status="resolved_verified", developer_note=None)
    except ObservabilityConflict:
        pass
    else:
        raise AssertionError("issue was verified without a passing regression case")
