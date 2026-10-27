from fastapi.testclient import TestClient

from app.api.main import create_app


def test_dashboard_exposes_exactly_eight_product_modules():
    response = TestClient(create_app()).get("/dashboard/")
    assert response.status_code == 200
    assert "Agent 质量控制台" in response.text
    expected = {"quality":"质量总览","runs":"会话观测","regression":"回归中心","issues":"问题中心","feedback":"用户反馈","handoffs":"人工接管","rag":"Policy RAG","system":"系统管理"}
    for view, label in expected.items():
        assert f'data-view="{view}"' in response.text
        assert f'data-dashboard-view="{view}"' in response.text
        assert label in response.text
    assert response.text.count("data-view=") == 8


def test_dashboard_removes_demo_and_generic_tool_surfaces():
    text = TestClient(create_app()).get("/dashboard/").text
    for removed in ("工具运行器","运行任务 0 换货演示","运行任务 1 换货演示","运行任务 2 退货演示","对话测试台","会话审计","配置详情","config-policy","environment-summary"):
        assert removed not in text


def test_dashboard_javascript_uses_formal_quality_and_regression_apis():
    text = TestClient(create_app()).get("/dashboard/app.js").text
    assert "selectDashboardView" in text
    assert "syncViewFromUrl" in text
    assert 'searchParams.get("view")' in text
    assert 'window.addEventListener("popstate"' in text
    for route in ("/api/v1/quality/overview","/api/v1/quality/trends","/api/v1/runs","/api/v1/regression/cases","/api/v1/regression/batches","/api/v1/observability/issues","/api/v1/observability/feedback","/api/v1/system/status","/api/v1/admin/developers"):
        assert route in text
    assert "runTaskZeroDemo" not in text
    assert "runSelectedTool" not in text
    assert "/admin/reset" not in text


def test_dashboard_quality_view_includes_operations_alerts_and_version_compare():
    client = TestClient(create_app())
    html = client.get("/dashboard/").text
    script = client.get("/dashboard/app.js").text
    for element_id in ("operations-metrics", "active-alerts", "version-comparison"):
        assert f'id="{element_id}"' in html
    assert "/api/v1/quality/operations" in script
    assert "政策证据" in script and "业务结果" in script


def test_dashboard_has_responsive_navigation_and_stable_controls():
    client = TestClient(create_app())
    html = client.get("/dashboard/").text
    css = client.get("/dashboard/styles.css").text
    assert 'id="nav-toggle"' in html
    assert 'id="nav-scrim"' in html
    assert 'id="quality-range"' in html
    assert 'id="run-batch-button"' in html
    assert 'id="developer-form"' in html
    assert "@media(max-width:760px)" in css
    assert "grid-template-columns" in css


def test_dashboard_handoff_route_has_queue_detail_and_transition_controls():
    client = TestClient(create_app())
    html = client.get("/dashboard/").text
    javascript = client.get("/dashboard/app.js").text

    assert 'data-dashboard-view="handoffs"' in html
    assert 'id="handoff-status-filter"' in html
    assert 'id="handoffs-list"' in html
    assert 'id="handoff-detail"' in html
    assert "/api/v1/admin/handoffs" in javascript
    assert "loadHandoffs" in javascript
    assert "claim" in javascript
    assert "resolve" in javascript
    assert "cancel" in javascript
