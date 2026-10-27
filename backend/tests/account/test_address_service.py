from pathlib import Path

import pytest

from app.account.address_service import AddressConflictError, CustomerAddressService
from app.auth.models import AuthenticatedUser
from app.persistence.sqlite import SqliteUnitOfWork
from app.persistence.models import UserRecord
from app.tools.retail_port import RetailToolResult, ToolBackendInfo


class FakeRetailPort:
    def __init__(self, fail_sync: bool = False): self.fail_sync, self.calls = fail_sync, []
    @property
    def backend(self): return ToolBackendInfo(kind="test", name="test", managed_by_mcp=False)
    @property
    def policy(self): return ""
    def list_tools(self): return []
    def call_tool(self, name, arguments, call_id=None):
        self.calls.append((name, arguments))
        if name == "get_user_details":
            content = {"name": {"first_name": "Alice", "last_name": "Li"}, "address": {"address1":"1 Main St","address2":"","city":"Austin","state":"TX","country":"USA","zip":"78701"}}
            return RetailToolResult(call_id="1", name=name, content=content, raw_content="", error=False)
        return RetailToolResult(call_id="2", name=name, content={}, raw_content="", error=self.fail_sync)


def actor():
    return AuthenticatedUser(user_id="u1", email="a@example.com", display_name="Alice", role="customer", status="active", must_change_password=False, retail_user_id="retail-1")


def unit_with_user(path: Path) -> SqliteUnitOfWork:
    unit = SqliteUnitOfWork(path); unit.initialize()
    with unit.transaction():
        unit.users.create(UserRecord(user_id="u1", email="a@example.com", display_name="Alice", password_hash="x", role="customer", retail_user_id="retail-1"))
    return unit


def test_first_list_imports_retail_default_address(tmp_path: Path):
    unit = unit_with_user(tmp_path / "import.db")
    items = CustomerAddressService(unit, FakeRetailPort()).list(actor())
    assert len(items) == 1 and items[0].is_default is True
    assert items[0].recipient_name == "Alice Li" and items[0].phone == ""


def test_default_sync_failure_does_not_change_local_default(tmp_path: Path):
    unit = unit_with_user(tmp_path / "rollback.db")
    port = FakeRetailPort(); service = CustomerAddressService(unit, port)
    original = service.list(actor())[0]
    added = service.create(actor(), recipient_name="Bob", phone="13900000000", address1="2 Lake Rd", address2="", city="Seattle", state="WA", country="USA", zip="98101")
    port.fail_sync = True
    with pytest.raises(AddressConflictError): service.set_default(actor(), added.address_id)
    assert service.get(actor(), original.address_id).is_default is True
    assert service.get(actor(), added.address_id).is_default is False


def test_default_address_cannot_be_archived(tmp_path: Path):
    unit = unit_with_user(tmp_path / "delete.db")
    service = CustomerAddressService(unit, FakeRetailPort())
    default = service.list(actor())[0]
    with pytest.raises(AddressConflictError, match="默认地址"):
        service.archive(actor(), default.address_id)
