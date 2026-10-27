import json
import logging

from fastapi.testclient import TestClient

from app.api.main import create_app


class StubReadinessChecker:
    def __init__(self, ready: bool) -> None:
        self.ready = ready

    def check(self):
        return {
            "status": "ready" if self.ready else "not_ready",
            "checks": {
                "database": {"status": "ok"},
                "tools": {"status": "ok" if self.ready else "error", "detail": "unavailable"},
            },
        }


def test_liveness_stays_up_when_readiness_dependency_is_down():
    client = TestClient(create_app(readiness_checker=StubReadinessChecker(False)))

    assert client.get("/health").status_code == 200
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["tools"]["status"] == "error"


def test_operational_headers_apply_to_public_and_generated_request_id_is_safe():
    client = TestClient(create_app(readiness_checker=StubReadinessChecker(True)))

    response = client.get("/health", headers={"x-request-id": "bad\nvalue"})

    assert "\n" not in response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_request_log_is_structured_and_does_not_contain_sensitive_headers(caplog):
    client = TestClient(create_app(readiness_checker=StubReadinessChecker(True)))
    caplog.set_level(logging.INFO, logger="ecommerce_agent.http")

    client.get("/health", headers={"x-request-id": "trace-123", "authorization": "Bearer hidden"})

    record = next(record for record in caplog.records if record.name == "ecommerce_agent.http")
    event = json.loads(record.message)
    assert event["request_id"] == "trace-123"
    assert event["method"] == "GET"
    assert event["path"] == "/health"
    assert event["status_code"] == 200
    assert "duration_ms" in event
    assert "hidden" not in record.message

