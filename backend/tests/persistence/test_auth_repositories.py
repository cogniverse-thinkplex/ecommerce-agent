from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.auth.passwords import verify_password
from app.persistence.models import AuthAuditEventRecord, AuthSessionRecord, UserRecord
from app.persistence.sqlite import SqliteUnitOfWork


def test_auth_migration_seeds_initial_developer_and_is_idempotent(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "auth.db")
    unit.initialize()
    unit.initialize()

    admin = unit.users.get_by_email(" ADMIN@LOCAL.DEV ")

    assert unit.applied_migrations() == [1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 14]
    assert admin is not None
    assert admin.role == "developer"
    assert admin.must_change_password is True
    assert verify_password("Admin@123456", admin.password_hash)
    assert "Admin@123456" not in admin.password_hash


def test_user_session_and_auth_audit_round_trip(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "auth.db")
    unit.initialize()
    user = UserRecord(
        user_id="customer-1",
        email="customer@example.com",
        display_name="Customer",
        password_hash="hash",
        role="customer",
        retail_user_id="retail-customer-1",
    )
    session = AuthSessionRecord(
        session_id="session-1",
        user_id=user.user_id,
        token_hash="token-hash",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
    )
    event = AuthAuditEventRecord(
        event_id="event-1", user_id=user.user_id, event_type="registered"
    )

    with unit.transaction():
        unit.users.create(user)
        unit.auth_sessions.create(session)
        unit.auth_audit_events.append(event)

    assert unit.users.get_by_email(" CUSTOMER@example.com ").user_id == "customer-1"
    assert unit.users.get("customer-1").retail_user_id == "retail-customer-1"
    assert unit.auth_sessions.get_by_token_hash("token-hash").session_id == "session-1"
    assert unit.auth_audit_events.list_for_user("customer-1")[0].event_type == "registered"
    assert unit.auth_sessions.revoke_all_for_user("customer-1") == 1
    assert unit.auth_sessions.get_by_token_hash("token-hash").revoked_at is not None


def test_normalized_email_is_unique_and_transaction_rolls_back(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "auth.db")
    unit.initialize()
    first = UserRecord(
        user_id="one", email="user@example.com", display_name="One", password_hash="h", role="customer"
    )
    duplicate = first.model_copy(update={"user_id": "two", "email": " USER@EXAMPLE.COM "})

    with unit.transaction():
        unit.users.create(first)
    with pytest.raises(Exception):
        with unit.transaction():
            unit.users.create(duplicate)

    assert unit.users.get("two") is None
