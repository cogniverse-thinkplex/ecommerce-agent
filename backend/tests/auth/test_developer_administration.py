from pathlib import Path

import pytest

from app.auth.service import AuthService, AuthorizationError, ConflictError
from app.persistence.sqlite import SqliteUnitOfWork


def _developer_service(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "auth.db")
    unit.initialize()
    service = AuthService(unit)
    admin_session = service.login(email="admin@local.dev", password="Admin@123456")
    return service, unit, admin_session.user


def test_developer_can_create_and_list_developer(tmp_path: Path):
    service, unit, admin = _developer_service(tmp_path)

    created = service.create_developer(
        admin,
        email="Dev@Example.com",
        display_name="Developer",
        temporary_password="DeveloperPass@123",
    )

    assert created.role == "developer"
    assert created.must_change_password is True
    assert unit.users.get(created.user_id).created_by_user_id == admin.user_id
    assert {user.email for user in service.list_developers(admin)} == {
        "admin@local.dev",
        "dev@example.com",
    }


def test_customer_cannot_manage_developers_and_duplicate_is_rejected(tmp_path: Path):
    service, _, admin = _developer_service(tmp_path)
    customer = service.register_customer(
        email="customer@example.com", display_name="Customer", password="CustomerPass@123"
    ).user

    with pytest.raises(AuthorizationError):
        service.list_developers(customer)
    with pytest.raises(ConflictError):
        service.create_developer(
            admin,
            email=" ADMIN@LOCAL.DEV ",
            display_name="Duplicate",
            temporary_password="DeveloperPass@123",
        )


def test_cannot_disable_self_or_last_active_developer(tmp_path: Path):
    service, _, admin = _developer_service(tmp_path)

    with pytest.raises(ConflictError):
        service.set_developer_status(admin, admin.user_id, "disabled")

    second = service.create_developer(
        admin,
        email="dev@example.com",
        display_name="Developer",
        temporary_password="DeveloperPass@123",
    )
    service.set_developer_status(admin, second.user_id, "disabled")
    assert service.list_developers(admin)[1].status == "disabled"
