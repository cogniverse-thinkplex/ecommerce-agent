from pathlib import Path

from fastapi.testclient import TestClient

from app.agent.progress import AgentProgressEvent
from app.agent.runtime import AgentAutoRunResult
from app.agent.state import ConversationMessage, CustomerAgentState
from app.api.main import create_app
from app.persistence.sqlite import SqliteUnitOfWork
from app.support.service import SupportService


class StreamingAgent:
    def __init__(self) -> None:
        self.states = {}

    def start_session(self, conversation_id, *, authenticated_user_id=None):
        state = CustomerAgentState(conversation_id=conversation_id)
        self.states[conversation_id] = state
        return state

    def get_session(self, conversation_id):
        return self.states[conversation_id]

    def auto_run(self, conversation_id, content, max_steps=6, progress_sink=None):
        progress_sink(
            AgentProgressEvent(stage="planning", message="正在分析您的请求")
        )
        state = self.states[conversation_id].model_copy(
            update={
                "messages": [
                    *self.states[conversation_id].messages,
                    ConversationMessage(role="user", content=content),
                    ConversationMessage(role="assistant", content="查询完成。"),
                ]
            }
        )
        self.states[conversation_id] = state
        return AgentAutoRunResult(state=state, turns=[], stopped_reason="no_proposal")


def test_support_message_stream_emits_accepted_progress_block_completed(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "stream.db")
    unit.initialize()
    support = SupportService(StreamingAgent(), unit)
    client = TestClient(create_app(support_service=support))
    conversation_id = client.post("/api/v1/support/conversations").json()[
        "conversation_id"
    ]

    response = client.post(
        f"/api/v1/support/conversations/{conversation_id}/messages/stream",
        headers={"Accept": "text/event-stream"},
        json={"content": "查询订单", "request_id": "stream-request-1"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [
        line.removeprefix("event: ")
        for line in response.text.splitlines()
        if line.startswith("event: ")
    ]
    assert events == ["accepted", "progress", "block", "completed"]
    ids = [
        int(line.removeprefix("id: "))
        for line in response.text.splitlines()
        if line.startswith("id: ")
    ]
    assert ids == sorted(ids)
    assert "查询完成。" in response.text
    assert unit.messages.count_user_messages(conversation_id) == 1


def test_support_message_stream_duplicate_request_does_not_duplicate_user_message(
    tmp_path: Path,
):
    unit = SqliteUnitOfWork(tmp_path / "stream-idempotent.db")
    unit.initialize()
    support = SupportService(StreamingAgent(), unit)
    client = TestClient(create_app(support_service=support))
    conversation_id = client.post("/api/v1/support/conversations").json()[
        "conversation_id"
    ]
    endpoint = f"/api/v1/support/conversations/{conversation_id}/messages/stream"
    payload = {"content": "查询订单", "request_id": "same-request"}

    assert client.post(endpoint, json=payload).status_code == 200
    assert client.post(endpoint, json=payload).status_code == 200

    assert unit.messages.count_user_messages(conversation_id) == 1
