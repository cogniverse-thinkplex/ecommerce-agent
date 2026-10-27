from app.agent.session_service import AgentSessionService
from app.agent.state import CustomerAgentState
from app.tools.guarded_executor import GuardedRetailToolExecutor


class EmptyPort:
    @property
    def backend(self):
        from app.tools.retail_port import ToolBackendInfo
        return ToolBackendInfo(kind="fake",name="fake",managed_by_mcp=True)
    @property
    def policy(self): return ""
    def list_tools(self): return []
    def call_tool(self,*args,**kwargs): raise AssertionError
    def db_hash(self): return None


def test_sets_trusted_active_order_and_audit_event():
    service = AgentSessionService(GuardedRetailToolExecutor(EmptyPort()))
    service.start_session("conv-1", authenticated_user_id="retail-1")
    state = service.set_active_order_context("conv-1", "#W123")
    assert state.objective_ledger.active_order_id == "#W123"
    assert state.events[-1].event_type == "conversation.order_context_set"
    assert state.events[-1].payload["source"] == "order_center"
