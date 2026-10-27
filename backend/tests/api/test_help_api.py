from pathlib import Path
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.agent.session_service import AgentSessionService
from app.agent.session_store import PersistentSessionStore
from app.auth.service import AuthService
from app.support.service import SupportService
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.retail_port import RetailToolResult, ToolBackendInfo
from app.persistence.sqlite import SqliteUnitOfWork
from app.rag.ingestion import PolicyIngestionService
from app.rag.retrieval import PolicyRetrievalService
from app.help.service import HelpService


class NoDense:
    model_name="none";available=False
    def embed(self,texts): raise RuntimeError


class Port:
    @property
    def backend(self): return ToolBackendInfo(kind="fake",name="fake",managed_by_mcp=True)
    @property
    def policy(self): return ""
    def list_tools(self): return []
    def call_tool(self,name,arguments,call_id=None):
        return RetailToolResult(call_id=call_id or "",name=name,content={},raw_content="",error=False)


def test_help_search_detail_and_assistant_require_customer(tmp_path:Path):
    unit=SqliteUnitOfWork(tmp_path/"help.db");unit.initialize()
    corpus=Path(__file__).parents[2]/"app/rag/corpus/taobao_policies.json"
    PolicyIngestionService(unit,corpus).ingest()
    help_service=HelpService(unit,PolicyRetrievalService(unit,NoDense()))
    port=Port()
    agent=AgentSessionService(GuardedRetailToolExecutor(port),session_store=PersistentSessionStore(unit))
    support=SupportService(agent,unit)
    auth=AuthService(unit,retail_identity_resolver=lambda _:"retail-1",retail_tool_port=port)
    api=TestClient(create_app(service=agent,support_service=support,auth_service=auth,help_service=help_service,auth_required=True))
    api.post("/api/v1/auth/register",json={"email":"help@example.com","display_name":"Help","password":"StrongPassword@123"})
    assert api.get("/api/v1/help/categories").json()["categories"]
    search=api.get("/api/v1/help/search",params={"q":"七天退货"}).json()
    assert search["hits"] and search["dense_available"] is False
    assert api.get("/api/v1/help/articles/seven-day-return").status_code==200
    assistant=api.post("/api/v1/help/articles/seven-day-return/assistant",json={})
    assert assistant.status_code==200 and assistant.json()["conversation_id"]
    api.post("/api/v1/auth/logout")
    assert api.get("/help/",follow_redirects=False).headers["location"]=="/login/"
