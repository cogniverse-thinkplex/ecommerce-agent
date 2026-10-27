import pytest


@pytest.fixture(autouse=True)
def legacy_app_tests_disable_product_auth_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("ECOM_AUTH_REQUIRED", "false")
    monkeypatch.setenv("ECOM_AGENT_PROPOSAL_GENERATOR", "rule")
    monkeypatch.setenv("ECOM_AGENT_TOOL_BACKEND", "tau2_python")
    monkeypatch.setenv("ECOM_AGENT_STORE", "memory")
    monkeypatch.setenv("ECOM_AGENT_SQLITE_PATH", str(tmp_path / "app.db"))
