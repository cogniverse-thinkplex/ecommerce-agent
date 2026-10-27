from datetime import date
from pathlib import Path

from app.account.spending import SpendingService, demo_purchase_date
from app.auth.models import AuthenticatedUser
from app.persistence.models import UserRecord
from app.persistence.sqlite import SqliteUnitOfWork
from app.tools.retail_port import RetailToolResult, ToolBackendInfo


class SpendingPort:
    @property
    def backend(self): return ToolBackendInfo(kind="test", name="test", managed_by_mcp=False)
    @property
    def policy(self): return ""
    def list_tools(self): return []
    def call_tool(self, name, arguments, call_id=None):
        if name == "get_user_details": content = {"orders": ["#A", "#B"]}
        else:
            content = {
                "#A": {"order_id":"#A","status":"delivered","items":[{"name":"Headphones","price":80},{"name":"T-Shirt","price":20}],"payment_history":[{"transaction_type":"payment","amount":100},{"transaction_type":"refund","amount":25}]},
                "#B": {"order_id":"#B","status":"cancelled","items":[{"name":"Mystery Box","price":50}],"payment_history":[{"transaction_type":"payment","amount":50}]},
            }[arguments["order_id"]]
        return RetailToolResult(call_id=call_id or "x", name=name, content=content, raw_content="", error=False)


def setup(tmp_path: Path):
    unit=SqliteUnitOfWork(tmp_path/"spending.db");unit.initialize()
    with unit.transaction(): unit.users.create(UserRecord(user_id="u1",email="a@example.com",display_name="A",password_hash="x",role="customer",retail_user_id="r1"))
    actor=AuthenticatedUser(user_id="u1",email="a@example.com",display_name="A",role="customer",status="active",must_change_password=False,retail_user_id="r1")
    return unit,actor


def test_demo_purchase_dates_are_stable_and_bounded():
    first=demo_purchase_date("#W123", anchor=date(2026,10,23))
    assert first == demo_purchase_date("#W123", anchor=date(2026,10,23))
    assert date(2024,10,24) <= first <= date(2026,10,23)


def test_spending_subtracts_refunds_excludes_cancelled_and_preserves_category_total(tmp_path: Path):
    unit,actor=setup(tmp_path)
    service=SpendingService(unit,SpendingPort(),today=date(2026,10,23))
    result=service.summary(actor,"year")
    assert result["summary"]["net_spend"] == 75.0
    assert result["summary"]["refund_amount"] == 25.0
    assert result["summary"]["order_count"] == 1
    assert round(sum(row["amount"] for row in result["categories"]),2) == 75.0
    assert {row["category"] for row in result["categories"]} == {"数码", "服饰"}
    assert result["demo_data"] is True


def test_spending_empty_customer_returns_zero_series(tmp_path: Path):
    unit,actor=setup(tmp_path)
    port=SpendingPort()
    port.call_tool=lambda name,arguments,call_id=None: RetailToolResult(call_id="x",name=name,content={"orders":[]},raw_content="",error=False)
    result=SpendingService(unit,port,today=date(2026,10,23)).summary(actor,"month")
    assert result["summary"] == {"net_spend":0.0,"refund_amount":0.0,"order_count":0,"average_order_value":0.0}
    assert len(result["series"]) == 12
