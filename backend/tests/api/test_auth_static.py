from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.auth.service import AuthService
from app.persistence.sqlite import SqliteUnitOfWork


def _client(tmp_path: Path) -> TestClient:
    unit = SqliteUnitOfWork(tmp_path / "auth.db")
    unit.initialize()
    return TestClient(create_app(auth_service=AuthService(unit), auth_required=True))


def test_public_authentication_pages_are_chinese_and_accessible(tmp_path: Path):
    client = _client(tmp_path)

    login = client.get("/login/")
    register = client.get("/register/")
    change = client.get("/change-password/", follow_redirects=False)

    assert login.status_code == 200 and "欢迎回来" in login.text
    assert register.status_code == 200 and "创建账户" in register.text
    assert "普通用户进入客服中心" not in login.text
    assert "工程观测控制台" not in login.text
    assert "账户登录" not in login.text
    assert 'class="auth-visual"' in login.text
    assert 'data-password-toggle' in login.text
    assert 'data-pending-label="正在登录…"' in login.text
    assert 'auth.css?v=20261023-ac' in login.text
    assert 'auth.js?v=20261023-ac' in login.text
    assert 'autocomplete="current-password"' in login.text
    assert 'autocomplete="new-password"' in register.text
    assert 'name="role"' not in register.text.lower()
    assert change.status_code == 307 and change.headers["location"] == "/login/"


def test_auth_assets_do_not_store_tokens_in_browser_storage(tmp_path: Path):
    client = _client(tmp_path)

    script = client.get("/auth/auth.js").text

    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert "/api/v1/auth/login" in script
    assert "/api/v1/auth/register" in script
    assert "/api/v1/auth/change-password" in script
    assert "data-password-toggle" in script
    assert "pendingLabel" in script


def test_auth_styles_are_responsive_and_keep_forms_usable_without_image(tmp_path: Path):
    client = _client(tmp_path)

    styles = client.get("/auth/auth.css").text

    assert '/auth/auth-fulfillment.webp' in styles
    assert "@media (max-width: 760px)" in styles
    assert ".auth-visual::before" in styles
    assert "background-color:" in styles
    assert ":focus-visible" in styles


def test_account_page_separates_profile_account_and_security_information(tmp_path: Path):
    client = _client(tmp_path)
    page = client.get("/account/", follow_redirects=False)
    assert page.status_code == 307 and page.headers["location"] == "/login/"
    public_client = TestClient(create_app(auth_required=False))
    public_page = public_client.get("/account/").text
    css = public_client.get("/account/account.css").text
    assert "账户信息" in public_page
    assert "安全设置" in public_page
    assert "收货地址" in public_page
    assert 'id="address-list"' in public_page
    assert "新增地址" in public_page
    assert "/account/address/" in public_page
    assert "登录邮箱" in public_page
    assert "购买账户" in public_page
    assert ".settings-section" in css
    assert "@media (max-width:680px)" in css

    script = public_client.get("/account/account.js").text
    assert 'request("/api/v1/auth/addresses")' in script

    editor = public_client.get("/account/address/").text
    assert 'id="address-form"' in editor
    assert "收货人" in editor and "手机号码" in editor
    assert "保存地址" in editor

    spending = public_client.get("/account/spending/").text
    spending_js = public_client.get("/account/spending/spending.js").text
    assert "消费分析" in spending
    assert 'data-customer-shell' in spending
    assert 'data-back-label="返回客服中心"' in spending
    assert "返回客服中心" in spending
    assert 'data-period="week"' in spending and 'data-period="month"' in spending and 'data-period="year"' in spending
    assert "演示历史数据" in spending
    assert 'id="spending-trend"' in spending and 'id="category-chart"' in spending
    assert "/api/v1/auth/spending?period=" in spending_js
