from fastapi.testclient import TestClient

from app.api.main import create_app


def test_customer_pages_use_single_back_bar_instead_of_duplicate_navigation():
    client=TestClient(create_app(auth_required=False))
    pages={"/orders/":"我的订单","/help/":"购物帮助","/account/spending/":"消费分析","/account/":"账户设置"}
    for path,current in pages.items():
        html=client.get(path).text
        assert '/customer-shell.css' in html
        assert '/customer-shell.js' in html
        assert 'data-customer-shell' in html
        assert "返回客服中心" in html and current in html
        assert "customer-nav" not in html
    help_html=client.get("/help/").text
    assert "政策与服务" not in help_html
    assert "帮助中心" not in help_html
    assert "购物政策与帮助" not in client.get("/support/").text


def test_shared_shell_uses_green_active_state_and_responsive_back_bar():
    client=TestClient(create_app(auth_required=False))
    response=client.get("/customer-shell.css")
    assert response.status_code==200
    css=response.text
    assert "#176b66" in css
    assert "#ef654f" not in css and "#d44e3b" not in css
    assert "overflow-x:auto" not in css
    assert "nth-child" not in css and ".customer-back" in css
    assert ".status-tabs button.active" in css and ".scope" in css


def test_shared_customer_shell_exposes_consistent_async_states():
    client=TestClient(create_app(auth_required=False))
    response=client.get("/customer-shell.js")
    assert response.status_code==200
    script=response.text
    for name in ("renderLoading", "renderEmpty", "renderError", "customer-header"):
        assert name in script
    css=client.get("/customer-shell.css").text
    for selector in (".customer-state", ".customer-state-error", ".customer-state-action"):
        assert selector in css
    for path in ("/orders/orders.js", "/help/help.js", "/account/spending/spending.js"):
        page_script=client.get(path).text
        assert 'from "/customer-shell.js"' in page_script
        assert "renderLoading" in page_script and "renderError" in page_script
