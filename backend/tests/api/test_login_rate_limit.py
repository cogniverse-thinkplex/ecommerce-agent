from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.auth.service import AuthService
from app.operations.rate_limit import LoginRateLimiter
from app.persistence.sqlite import SqliteUnitOfWork


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _client(tmp_path: Path, clock: Clock) -> tuple[TestClient, LoginRateLimiter]:
    unit = SqliteUnitOfWork(tmp_path / "rate-limit.db")
    unit.initialize()
    auth = AuthService(unit)
    limiter = LoginRateLimiter(max_failures=3, window_seconds=60, block_seconds=120, clock=clock)
    return TestClient(create_app(auth_service=auth, login_limiter=limiter, auth_required=True)), limiter


def test_login_is_blocked_after_failure_threshold_and_retry_after_is_returned(tmp_path: Path):
    clock = Clock()
    client, _ = _client(tmp_path, clock)

    for _ in range(3):
        assert client.post("/api/v1/auth/login", json={"email": "USER@example.com", "password": "wrong"}).status_code == 401
    blocked = client.post("/api/v1/auth/login", json={"email": " user@EXAMPLE.com ", "password": "wrong"})

    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "120"
    assert blocked.json()["detail"]["code"] == "login_rate_limited"


def test_block_expires_and_successful_login_clears_only_its_key(tmp_path: Path):
    clock = Clock()
    client, limiter = _client(tmp_path, clock)
    client.post("/api/v1/auth/register", json={"email": "user@example.com", "display_name": "User", "password": "CustomerPass@123"})
    client.post("/api/v1/auth/logout")
    for _ in range(2):
        client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "wrong"})

    success = client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "CustomerPass@123"})

    assert success.status_code == 200
    assert limiter.snapshot() == {}
    for _ in range(3):
        client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "wrong"})
    clock.now += 121
    assert client.post("/api/v1/auth/login", json={"email": "user@example.com", "password": "CustomerPass@123"}).status_code == 200


def test_limiter_state_uses_hashes_not_plaintext_identifiers():
    clock = Clock()
    limiter = LoginRateLimiter(max_failures=1, window_seconds=60, block_seconds=120, clock=clock)
    key = limiter.key("203.0.113.4", "Person@Example.com")
    limiter.record_failure(key)

    serialized = repr(limiter.snapshot())
    assert "Person" not in serialized
    assert "example.com" not in serialized
    assert "203.0.113.4" not in serialized

