from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.auth.service import AuthService
from app.persistence.sqlite import SqliteUnitOfWork
from app.tools.retail_port import RetailToolResult, ToolBackendInfo


class _RetailProfilePort:
    def __init__(self) -> None:
        self.address = {
            "address1": "12 Main Street",
            "address2": "Suite 3",
            "city": "Austin",
            "state": "TX",
            "country": "USA",
            "zip": "78701",
        }
        self.calls: list[tuple[str, dict]] = []

    @property
    def backend(self) -> ToolBackendInfo:
        return ToolBackendInfo(kind="test", name="test", managed_by_mcp=False)

    @property
    def policy(self) -> str:
        return ""

    def list_tools(self) -> list:
        return []

    def call_tool(self, name: str, arguments: dict, call_id: str | None = None) -> RetailToolResult:
        self.calls.append((name, arguments))
        if name == "get_user_details":
            content = {"user_id": arguments["user_id"], "address": dict(self.address)}
        elif name == "modify_user_address":
            self.address = {key: value for key, value in arguments.items() if key != "user_id"}
            content = {"user_id": arguments["user_id"], "address": dict(self.address)}
        else:
            raise AssertionError(name)
        return RetailToolResult(call_id=call_id or "test", name=name, content=content, raw_content="", error=False)


def _client(tmp_path: Path) -> tuple[TestClient, AuthService]:
    unit = SqliteUnitOfWork(tmp_path / "auth.db")
    unit.initialize()
    auth = AuthService(unit)
    return TestClient(create_app(auth_service=auth, auth_required=True)), auth


def test_customer_register_me_logout_flow(tmp_path: Path):
    client, _ = _client(tmp_path)

    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": "customer@example.com",
            "display_name": "Customer",
            "password": "CustomerPass@123",
        },
    )

    assert registered.status_code == 201
    assert registered.json()["redirect_to"] == "/support/"
    cookie = registered.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert client.get("/api/v1/auth/me").json()["role"] == "customer"
    assert "retail_user_id" not in client.get("/api/v1/auth/me").json()
    assert client.get("/api/v1/auth/me").json()["retail_account_linked"] is False
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_seeded_developer_login_requires_password_change(tmp_path: Path):
    client, _ = _client(tmp_path)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@local.dev", "password": "Admin@123456"},
    )

    assert login.status_code == 200
    assert login.json()["redirect_to"] == "/change-password/"
    assert client.get("/dashboard/", follow_redirects=False).status_code == 307
    changed = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Admin@123456", "new_password": "ChangedAdmin@123"},
    )
    assert changed.status_code == 200
    assert changed.json()["redirect_to"] == "/dashboard/"
    assert client.get("/dashboard/").status_code == 200


def test_invalid_credentials_are_generic(tmp_path: Path):
    client, _ = _client(tmp_path)

    response = client.post(
        "/api/v1/auth/login", json={"email": "missing@example.com", "password": "wrong"}
    )

    assert response.status_code == 401
    assert response.json()["detail"]["message"] == "邮箱或密码不正确。"


def test_customer_can_patch_own_profile(tmp_path: Path):
    client, _ = _client(tmp_path)
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "customer@example.com",
            "display_name": "Old Name",
            "password": "CustomerPass@123",
        },
    )

    response = client.patch(
        "/api/v1/auth/me",
        json={"display_name": "  New Name  "},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "New Name"
    assert response.json()["email"] == "customer@example.com"
    assert "retail_user_id" not in response.json()


def test_profile_patch_requires_login_and_non_blank_name(tmp_path: Path):
    client, _ = _client(tmp_path)
    assert client.patch(
        "/api/v1/auth/me", json={"display_name": "Name"}
    ).status_code == 401
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "customer@example.com",
            "display_name": "Customer",
            "password": "CustomerPass@123",
        },
    )
    assert client.patch(
        "/api/v1/auth/me", json={"display_name": "   "}
    ).status_code == 422


def test_customer_can_read_and_update_own_retail_address(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "auth-address.db")
    unit.initialize()
    port = _RetailProfilePort()
    auth = AuthService(
        unit,
        retail_identity_resolver=lambda _email: "retail-customer-1",
        retail_tool_port=port,
    )
    client = TestClient(create_app(auth_service=auth, auth_required=True))
    client.post(
        "/api/v1/auth/register",
        json={"email": "customer@example.com", "display_name": "Customer", "password": "CustomerPass@123"},
    )

    current = client.get("/api/v1/auth/address")
    updated = client.put(
        "/api/v1/auth/address",
        json={
            "address1": "88 Lake Road",
            "address2": "",
            "city": "Seattle",
            "state": "WA",
            "country": "USA",
            "zip": "98101",
        },
    )

    assert current.status_code == 200
    assert current.json()["address1"] == "12 Main Street"
    assert updated.status_code == 200
    assert updated.json() == {
        "address1": "88 Lake Road",
        "address2": "",
        "city": "Seattle",
        "state": "WA",
        "country": "USA",
        "zip": "98101",
    }
    assert port.calls[-1] == (
        "modify_user_address",
        {
            "user_id": "retail-customer-1",
            "address1": "88 Lake Road",
            "address2": "",
            "city": "Seattle",
            "state": "WA",
            "country": "USA",
            "zip": "98101",
        },
    )


def test_customer_manages_address_book_without_supplying_owner_id(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "address-book-api.db"); unit.initialize()
    port = _RetailProfilePort()
    auth = AuthService(unit, retail_identity_resolver=lambda _email: "retail-customer-1", retail_tool_port=port)
    client = TestClient(create_app(auth_service=auth, auth_required=True))
    client.post("/api/v1/auth/register", json={"email":"customer@example.com","display_name":"Customer","password":"CustomerPass@123"})

    imported = client.get("/api/v1/auth/addresses")
    created = client.post("/api/v1/auth/addresses", json={
        "recipient_name":"Bob Chen","phone":"13900000000","address1":"88 Lake Road","address2":"",
        "city":"Seattle","state":"WA","country":"USA","zip":"98101",
    })
    address_id = created.json()["address_id"]
    selected = client.post(f"/api/v1/auth/addresses/{address_id}/default")
    removed_default = client.delete(f"/api/v1/auth/addresses/{address_id}")

    assert imported.status_code == 200 and imported.json()[0]["is_default"] is True
    assert created.status_code == 201 and "owner_user_id" not in created.json()
    assert selected.status_code == 200 and selected.json()["is_default"] is True
    assert removed_default.status_code == 409


def test_customer_cannot_read_another_customers_address(tmp_path: Path):
    unit = SqliteUnitOfWork(tmp_path / "address-owner-api.db"); unit.initialize()
    port = _RetailProfilePort()
    auth = AuthService(unit, retail_identity_resolver=lambda email: "retail-1" if email.startswith("one") else "retail-2", retail_tool_port=port)
    first = TestClient(create_app(auth_service=auth, auth_required=True))
    second = TestClient(create_app(auth_service=auth, auth_required=True))
    first.post("/api/v1/auth/register", json={"email":"one@example.com","display_name":"One","password":"CustomerPass@123"})
    second.post("/api/v1/auth/register", json={"email":"two@example.com","display_name":"Two","password":"CustomerPass@123"})
    address_id = first.get("/api/v1/auth/addresses").json()[0]["address_id"]
    assert second.get(f"/api/v1/auth/addresses/{address_id}").status_code == 404


def test_customer_spending_api_validates_period_and_returns_demo_metrics(tmp_path: Path):
    class Port(_RetailProfilePort):
        def call_tool(self, name, arguments, call_id=None):
            if name == "get_user_details":
                return RetailToolResult(call_id="u",name=name,content={"orders":["#W1"]},raw_content="",error=False)
            if name == "get_order_details":
                content={"order_id":"#W1","status":"delivered","items":[{"name":"Headphones","price":120}],"payment_history":[{"transaction_type":"payment","amount":120}]}
                return RetailToolResult(call_id="o",name=name,content=content,raw_content="",error=False)
            return super().call_tool(name, arguments, call_id)
    unit=SqliteUnitOfWork(tmp_path/"spending-api.db");unit.initialize();port=Port()
    auth=AuthService(unit,retail_identity_resolver=lambda _email:"retail-1",retail_tool_port=port)
    client=TestClient(create_app(auth_service=auth,auth_required=True))
    client.post("/api/v1/auth/register",json={"email":"customer@example.com","display_name":"Customer","password":"CustomerPass@123"})
    response=client.get("/api/v1/auth/spending?period=year")
    assert response.status_code==200 and response.json()["demo_data"] is True
    assert response.json()["summary"]["net_spend"]==120.0
    assert client.get("/api/v1/auth/spending?period=day").status_code==422
