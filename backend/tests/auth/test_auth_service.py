from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.auth.service import (
    AuthService,
    AuthenticationError,
    ConflictError,
    PasswordChangeRequired,
)
from app.persistence.sqlite import SqliteUnitOfWork


def _service(tmp_path: Path) -> tuple[AuthService, SqliteUnitOfWork]:
    unit = SqliteUnitOfWork(tmp_path / "auth.db")
    unit.initialize()
    return AuthService(unit, session_hours=12), unit


def test_customer_registration_issues_persisted_hashed_session(tmp_path: Path):
    service, unit = _service(tmp_path)

    issued = service.register_customer(
        email=" Customer@Example.com ",
        display_name="Customer",
        password="CustomerPass@123",
    )

    assert issued.user.email == "customer@example.com"
    assert issued.user.role == "customer"
    assert issued.raw_token
    assert unit.auth_sessions.get_by_token_hash(service.token_hash(issued.raw_token))
    assert unit.users.get(issued.user.user_id).password_hash != "CustomerPass@123"
    assert service.authenticate(issued.raw_token) == issued.user


def test_customer_registration_binds_matching_retail_identity(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "auth.db")
    unit.initialize()
    service = AuthService(
        unit,
        retail_identity_resolver=lambda email: (
            "ivan_santos_6635"
            if email == "ivan.santos3158@example.com"
            else None
        ),
    )

    issued = service.register_customer(
        email="Ivan.Santos3158@example.com",
        display_name="Ivan Santos",
        password="CustomerPass@123",
    )

    assert issued.user.retail_user_id == "ivan_santos_6635"
    assert unit.users.get(issued.user.user_id).retail_user_id == "ivan_santos_6635"


def test_customer_registration_rejects_email_without_retail_identity(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "auth.db")
    unit.initialize()
    service = AuthService(unit, retail_identity_resolver=lambda email: None)

    with pytest.raises(AuthenticationError, match="购买账户"):
        service.register_customer(
            email="unknown@example.com",
            display_name="Unknown",
            password="CustomerPass@123",
        )

    assert unit.users.get_by_email("unknown@example.com") is None


def test_existing_customer_is_linked_on_next_login(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "auth.db")
    unit.initialize()
    legacy = AuthService(unit)
    legacy.register_customer(
        email="ivan.santos3158@example.com",
        display_name="Ivan Santos",
        password="CustomerPass@123",
    )
    strict = AuthService(
        unit,
        retail_identity_resolver=lambda email: "ivan_santos_6635",
    )

    issued = strict.login(
        email="ivan.santos3158@example.com",
        password="CustomerPass@123",
    )

    assert issued.user.retail_user_id == "ivan_santos_6635"
    assert unit.users.get(issued.user.user_id).retail_user_id == "ivan_santos_6635"


def test_existing_customer_without_purchase_account_cannot_login(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "auth.db")
    unit.initialize()
    legacy = AuthService(unit)
    legacy.register_customer(
        email="unknown@example.com",
        display_name="Unknown",
        password="CustomerPass@123",
    )
    strict = AuthService(unit, retail_identity_resolver=lambda email: None)

    with pytest.raises(AuthenticationError, match="购买账户"):
        strict.login(email="unknown@example.com", password="CustomerPass@123")


def test_unlinked_legacy_session_requires_fresh_login_without_lookup(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "auth.db")
    unit.initialize()
    legacy = AuthService(unit)
    issued = legacy.register_customer(
        email="ivan.santos3158@example.com",
        display_name="Ivan Santos",
        password="CustomerPass@123",
    )
    lookups: list[str] = []
    strict = AuthService(
        unit,
        retail_identity_resolver=lambda email: lookups.append(email) or "ivan_santos_6635",
    )

    with pytest.raises(AuthenticationError, match="重新登录"):
        strict.authenticate(issued.raw_token)

    assert lookups == []


def test_customer_can_update_own_display_name_without_changing_identity(tmp_path: Path):
    service, unit = _service(tmp_path)
    issued = service.register_customer(
        email="customer@example.com",
        display_name="Old Name",
        password="CustomerPass@123",
    )

    updated = service.update_profile(issued.user, display_name="  New Name  ")

    assert updated.display_name == "New Name"
    assert updated.email == issued.user.email
    assert updated.retail_user_id == issued.user.retail_user_id
    assert unit.users.get(issued.user.user_id).display_name == "New Name"


def test_customer_profile_rejects_blank_display_name(tmp_path: Path):
    service, _ = _service(tmp_path)
    issued = service.register_customer(
        email="customer@example.com",
        display_name="Customer",
        password="CustomerPass@123",
    )

    with pytest.raises(ValueError, match="姓名"):
        service.update_profile(issued.user, display_name="   ")


def test_duplicate_registration_and_invalid_login_are_safe(tmp_path: Path):
    service, _ = _service(tmp_path)
    service.register_customer(
        email="user@example.com", display_name="User", password="CustomerPass@123"
    )

    with pytest.raises(ConflictError):
        service.register_customer(
            email=" USER@example.com ", display_name="Other", password="CustomerPass@123"
        )
    with pytest.raises(AuthenticationError, match="邮箱或密码不正确"):
        service.login(email="user@example.com", password="wrong")


def test_seeded_developer_must_change_password_and_old_session_is_revoked(tmp_path: Path):
    service, unit = _service(tmp_path)
    issued = service.login(email="admin@local.dev", password="Admin@123456")

    assert issued.user.must_change_password is True
    with pytest.raises(PasswordChangeRequired):
        service.require_password_changed(issued.user)

    replacement = service.change_password(
        issued.raw_token,
        current_password="Admin@123456",
        new_password="ChangedAdmin@123",
    )

    assert replacement.user.must_change_password is False
    with pytest.raises(AuthenticationError):
        service.authenticate(issued.raw_token)
    assert service.authenticate(replacement.raw_token).role == "developer"
    assert unit.users.get(replacement.user.user_id).password_hash != "ChangedAdmin@123"


def test_logout_expired_and_disabled_sessions_do_not_authenticate(tmp_path: Path):
    service, unit = _service(tmp_path)
    issued = service.register_customer(
        email="user@example.com", display_name="User", password="CustomerPass@123"
    )
    service.logout(issued.raw_token)
    with pytest.raises(AuthenticationError):
        service.authenticate(issued.raw_token)

    issued = service.login(email="user@example.com", password="CustomerPass@123")
    record = unit.auth_sessions.get_by_token_hash(service.token_hash(issued.raw_token))
    unit._connection.execute(
        "UPDATE auth_sessions SET expires_at = ? WHERE session_id = ?",
        ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), record.session_id),
    )
    unit._connection.commit()
    with pytest.raises(AuthenticationError):
        service.authenticate(issued.raw_token)
