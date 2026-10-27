from pathlib import Path

from app.agent.proposal_generator import ModelProviderError
from app.agent.state import CustomerAgentState
from app.persistence.sqlite import SqliteUnitOfWork
from app.support.service import SupportService
from fastapi.testclient import TestClient

from app.api.main import create_app
from backend.tests.api.test_support_api import _client


def test_support_rejects_blank_and_oversized_messages(tmp_path: Path):
    client = _client(tmp_path)
    conversation_id = client.post("/api/v1/support/conversations").json()[
        "conversation_id"
    ]
    endpoint = f"/api/v1/support/conversations/{conversation_id}/messages"

    blank = client.post(endpoint, json={"content": "   ", "request_id": "blank"})
    oversized = client.post(
        endpoint, json={"content": "x" * 8001, "request_id": "large"}
    )

    assert blank.status_code == 422
    assert oversized.status_code == 422


def test_support_returns_stable_safe_not_found_error(tmp_path: Path):
    client = _client(tmp_path)

    response = client.get("/api/v1/support/conversations/missing")

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "code": "not_found",
            "message": "未找到该会话。",
            "recoverable": False,
        }
    }


class QuotaExhaustedAgent:
    def __init__(self) -> None:
        self.states: dict[str, CustomerAgentState] = {}

    def start_session(self, conversation_id, *, authenticated_user_id=None):
        state = CustomerAgentState(conversation_id=conversation_id)
        self.states[conversation_id] = state
        return state

    def get_session(self, conversation_id):
        return self.states[conversation_id]

    def auto_run(self, conversation_id, content, max_steps=6):
        raise ModelProviderError(
            model="dashscope/qwen3.8-max",
            reason="quota_exhausted",
        )


def test_support_reports_model_quota_exhaustion_as_recoverable_503(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "support-provider-error.db")
    unit.initialize()
    client = TestClient(create_app(support_service=SupportService(QuotaExhaustedAgent(), unit)))
    conversation_id = client.post("/api/v1/support/conversations").json()[
        "conversation_id"
    ]

    response = client.post(
        f"/api/v1/support/conversations/{conversation_id}/messages",
        json={"content": "查询订单", "request_id": "provider-error"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "model_quota_exhausted",
            "message": "智能客服模型的可用额度已耗尽，请稍后重试或联系管理员切换模型。",
            "recoverable": True,
        }
    }

