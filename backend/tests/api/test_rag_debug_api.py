from pathlib import Path
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.auth.service import AuthService
from app.help.service import HelpService
from app.persistence.sqlite import SqliteUnitOfWork
from app.rag.ingestion import PolicyIngestionService
from app.rag.retrieval import PolicyRetrievalService


class NoDense:
    model_name="BAAI/bge-small-zh-v1.5"; available=False
    def embed(self,texts): raise RuntimeError


def test_rag_debug_is_developer_only_and_reports_degradation(tmp_path: Path):
    unit=SqliteUnitOfWork(tmp_path/"rag-api.db");unit.initialize()
    corpus=Path(__file__).parents[2]/"app/rag/corpus/taobao_policies.json"
    PolicyIngestionService(unit,corpus).ingest()
    help_service=HelpService(unit,PolicyRetrievalService(unit,NoDense()))
    client=TestClient(create_app(auth_service=AuthService(unit),help_service=help_service,auth_required=True))
    client.post("/api/v1/auth/register",json={"email":"customer@example.com","display_name":"Customer","password":"CustomerPass@123"})
    assert client.get("/api/v1/rag/status").status_code==403
    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login",json={"email":"admin@local.dev","password":"Admin@123456"})
    client.post("/api/v1/auth/change-password",json={"current_password":"Admin@123456","new_password":"ChangedAdmin@123"})
    status=client.get("/api/v1/rag/status").json()
    assert status["model"]=="BAAI/bge-small-zh-v1.5" and status["document_count"]>=10
    debug=client.get("/api/v1/rag/debug",params={"q":"七天退货"}).json()
    assert debug["dense_available"] is False and debug["hits"][0]["bm25_rank"] is not None
