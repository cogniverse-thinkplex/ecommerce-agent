from dataclasses import dataclass
from pathlib import Path
import pytest
from app.auth.models import AuthenticatedUser
from app.orders.service import OrderCenterService, OrderNotFoundError
from app.persistence.sqlite import SqliteUnitOfWork
from app.tools.retail_port import RetailToolResult, ToolBackendInfo

@dataclass
class FakePort:
    fail_order: str | None = None
    @property
    def backend(self): return ToolBackendInfo(kind="fake", name="fake", managed_by_mcp=True)
    @property
    def policy(self): return ""
    def list_tools(self): return []
    def call_tool(self, name, arguments, call_id=None):
        if name == "get_user_details":
            content = {"user_id": arguments["user_id"], "orders": ["#W1", "#W2"]}
            return RetailToolResult(call_id=call_id or "", name=name, content=content, raw_content="", error=False)
        order_id = arguments["order_id"]
        if order_id == self.fail_order: return RetailToolResult(call_id=call_id or "", name=name, content="boom", raw_content="boom", error=True)
        content = {"order_id":order_id,"status":"pending" if order_id=="#W1" else "delivered","items":[{"item_id":"I1","name":"Desk Lamp","price":120.0,"options":{"color":"black"}}],"payment_history":[{"transaction_type":"payment","amount":120.0}],"payment_method":"card_1234567890","address":{"address1":"Main St","city":"Austin","state":"TX","country":"US","zip":"78701"}}
        return RetailToolResult(call_id=call_id or "", name=name, content=content, raw_content="", error=False)

def actor(retail_user_id="retail-1"):
    return AuthenticatedUser(user_id="customer-1",email="a@example.com",display_name="A",role="customer",status="active",must_change_password=False,retail_user_id=retail_user_id)

def test_lists_owned_orders_filters_status_and_masks_payment(tmp_path:Path):
    unit=SqliteUnitOfWork(tmp_path/"orders.db");unit.initialize();service=OrderCenterService(unit,FakePort())
    result=service.list_orders(actor(),status="pending");assert len(result.orders)==1;assert result.orders[0].order_id=="#W1"
    detail=service.get_order(actor(),"#W1");assert detail.net_amount==120.0;assert detail.payment_method=="•••• 7890"

def test_partial_tool_failure_keeps_order_summary(tmp_path:Path):
    unit=SqliteUnitOfWork(tmp_path/"orders.db");unit.initialize();result=OrderCenterService(unit,FakePort(fail_order="#W2")).list_orders(actor())
    assert len(result.orders)==2;assert next(row for row in result.orders if row.order_id=="#W2").available is False

def test_rejects_unknown_or_unlinked_order(tmp_path:Path):
    unit=SqliteUnitOfWork(tmp_path/"orders.db");unit.initialize();service=OrderCenterService(unit,FakePort())
    with pytest.raises(OrderNotFoundError):service.get_order(actor(),"#OTHER")
    with pytest.raises(OrderNotFoundError):service.get_order(actor(None),"#W1")
