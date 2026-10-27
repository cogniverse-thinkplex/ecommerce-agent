from pathlib import Path
from fastapi.testclient import TestClient
from app.api.main import create_app
from app.auth.service import AuthService
from app.persistence.sqlite import SqliteUnitOfWork
from app.tools.retail_port import RetailToolResult, ToolBackendInfo
from app.agent.session_service import AgentSessionService
from app.agent.session_store import PersistentSessionStore
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.support.service import SupportService

class Port:
    @property
    def backend(self): return ToolBackendInfo(kind="fake",name="fake",managed_by_mcp=True)
    @property
    def policy(self): return ""
    def list_tools(self): return []
    def call_tool(self,name,arguments,call_id=None):
        if name=="get_user_details": content={"user_id":arguments["user_id"],"orders":["#W1"]}
        else: content={"order_id":"#W1","status":"pending","items":[],"payment_history":[],"payment_method":"card_9876","address":{}}
        return RetailToolResult(call_id=call_id or "",name=name,content=content,raw_content="",error=False)

def client(tmp_path:Path):
    unit=SqliteUnitOfWork(tmp_path/"orders-api.db");unit.initialize();port=Port()
    agent=AgentSessionService(GuardedRetailToolExecutor(port),session_store=PersistentSessionStore(unit))
    app=create_app(service=agent,support_service=SupportService(agent,unit),auth_service=AuthService(unit,retail_identity_resolver=lambda _:"retail-1",retail_tool_port=port),auth_required=True)
    result=TestClient(app);result.post("/api/v1/auth/register",json={"email":"buyer@example.com","display_name":"Buyer","password":"StrongPassword@123"});return result

def test_customer_can_list_and_open_only_owned_order(tmp_path:Path):
    api=client(tmp_path)
    assert api.get("/api/v1/orders").json()["orders"][0]["order_id"]=="#W1"
    assert api.get("/api/v1/orders/%23W1").status_code==200
    assert api.get("/api/v1/orders/%23OTHER").status_code==404
    assistant=api.post("/api/v1/orders/%23W1/assistant",json={})
    assert assistant.status_code==200
    assert assistant.json()["conversation_id"]

def test_orders_page_requires_login_and_contains_agent_workspace(tmp_path:Path):
    api=client(tmp_path)
    api.post("/api/v1/auth/logout")
    assert api.get("/orders/",follow_redirects=False).headers["location"]=="/login/"
    public=TestClient(create_app(auth_required=False)).get("/orders/").text
    css=TestClient(create_app(auth_required=False)).get("/orders/orders.css").text
    assert "我的订单" in public and 'id="assistant-panel"' in public
    assert "cancel_pending_order" not in public
    assert "[hidden]{display:none!important}" in css
