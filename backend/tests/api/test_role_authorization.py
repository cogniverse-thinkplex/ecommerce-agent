from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.auth.service import AuthService
from app.persistence.sqlite import SqliteUnitOfWork


def _client(tmp_path: Path) -> TestClient:
    unit = SqliteUnitOfWork(tmp_path / "auth.db")
    unit.initialize()
    return TestClient(create_app(auth_service=AuthService(unit), auth_required=True))


def test_unauthenticated_pages_redirect_to_login(tmp_path: Path):
    client = _client(tmp_path)

    assert client.get("/support/", follow_redirects=False).headers["location"] == "/login/"
    assert client.get("/dashboard/", follow_redirects=False).headers["location"] == "/login/"
    assert client.get("/tools").status_code == 401


def test_customer_cannot_access_dashboard_or_engineering_api(tmp_path: Path):
    client = _client(tmp_path)
    client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "display_name": "User", "password": "CustomerPass@123"},
    )

    assert client.get("/support/").status_code == 200
    dashboard = client.get("/dashboard/", follow_redirects=False)
    assert dashboard.status_code == 307
    assert dashboard.headers["location"] == "/support/"
    assert client.get("/tools").status_code == 403


def test_developer_can_access_existing_dashboard_and_admin_api(tmp_path: Path):
    client = _client(tmp_path)
    client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local.dev", "password": "Admin@123456"},
    )
    client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Admin@123456", "new_password": "ChangedAdmin@123"},
    )

    assert client.get("/dashboard/").status_code == 200
    support = client.get("/support/", follow_redirects=False)
    assert support.status_code == 307
    assert support.headers["location"] == "/dashboard/"
    assert client.get("/tools").status_code == 200
    created = client.post(
        "/api/v1/admin/developers",
        json={"email": "dev@example.com", "display_name": "Dev", "temporary_password": "DeveloperPass@123"},
    )
    assert created.status_code == 201
    assert created.json()["email"] == "dev@example.com"
