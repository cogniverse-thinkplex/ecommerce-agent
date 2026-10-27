from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_product_startup_script_enables_sqlite_and_mcp_without_hardcoded_secret():
    script = (ROOT / "scripts/run_local_product.sh").read_text()

    assert "ECOM_AGENT_STORE" in script and "sqlite" in script
    assert "ECOM_AGENT_TOOL_BACKEND" in script and "mcp" in script
    assert "run_retail_mcp.sh" in script
    assert "run_backend_api.sh" in script
    assert "trap" in script
    assert "sk-" not in script


def test_compose_defines_api_mcp_healthchecks_and_persistent_data():
    compose = (ROOT / "docker-compose.yml").read_text()

    assert "api:" in compose
    assert "retail-mcp:" in compose
    assert "healthcheck:" in compose
    assert "agent-data:" in compose
    assert "ECOM_AGENT_MCP_URL: http://retail-mcp:8765/mcp" in compose
    assert "ECOM_AGENT_SQLITE_PATH: /app/data/ecommerce_agent.db" in compose
    assert "http://127.0.0.1:8000/ready" in compose


def test_production_compose_adds_single_node_runtime_guards():
    compose = (ROOT / "docker-compose.production.yml").read_text()

    assert compose.count("restart: unless-stopped") == 3
    assert compose.count("read_only: true") == 3
    assert "max-size: \"10m\"" in compose
    assert "max-file: \"3\"" in compose
    assert "mem_limit:" in compose
    assert "cpus:" in compose


def test_production_environment_template_and_runbook_are_safe_and_actionable():
    example = (ROOT / ".env.production.example").read_text()
    runbook = (ROOT / "docs/operations/production-runbook.md").read_text()

    assert "ECOM_ENV=production" in example
    assert "ECOM_AUTH_COOKIE_SECURE=true" in example
    assert "DASHSCOPE_API_KEY=" in example
    assert "sk-" not in example
    assert "backup_sqlite.py" in runbook
    assert "restore_sqlite.py" in runbook
    assert "/ready" in runbook


def test_environment_example_contains_no_working_secret_and_documents_product_defaults():
    example = (ROOT / ".env.example").read_text()

    assert "ECOM_AGENT_STORE=sqlite" in example
    assert "ECOM_AGENT_TOOL_BACKEND=mcp" in example
    assert "ECOM_AGENT_MCP_URL=http://127.0.0.1:8765/mcp" in example
    assert "sk-d8c2309" not in example

