import pytest

from app.operations.config import ProductionConfigError, validate_runtime_config


def _production_env() -> dict[str, str]:
    return {
        "ECOM_ENV": "production",
        "ECOM_AGENT_STORE": "sqlite",
        "ECOM_AGENT_SQLITE_PATH": "/app/data/ecommerce_agent.db",
        "ECOM_AGENT_TOOL_BACKEND": "mcp",
        "ECOM_AGENT_MCP_URL": "http://retail-mcp:8765/mcp",
        "ECOM_AGENT_PROPOSAL_GENERATOR": "llm",
        "ECOM_AGENT_PROPOSAL_LLM": "dashscope/qwen3.8-max",
        "DASHSCOPE_API_KEY": "secret-value",
        "ECOM_AUTH_COOKIE_SECURE": "true",
        "ECOM_POLICY_MODEL_LOCAL_ONLY": "true",
    }


def test_non_production_configuration_is_not_restricted():
    validate_runtime_config({"ECOM_ENV": "development"})


def test_complete_production_configuration_is_accepted():
    validate_runtime_config(_production_env())


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ECOM_AGENT_STORE", "memory"),
        ("ECOM_AGENT_SQLITE_PATH", "data/app.db"),
        ("ECOM_AGENT_TOOL_BACKEND", "tau2_python"),
        ("ECOM_AGENT_PROPOSAL_GENERATOR", "rule"),
        ("ECOM_AUTH_COOKIE_SECURE", "false"),
        ("ECOM_POLICY_MODEL_LOCAL_ONLY", "false"),
        ("DASHSCOPE_API_KEY", ""),
    ],
)
def test_unsafe_production_configuration_is_rejected_without_secret_values(key, value):
    environment = _production_env()
    environment[key] = value

    with pytest.raises(ProductionConfigError) as error:
        validate_runtime_config(environment)

    assert key in str(error.value)
    assert "secret-value" not in str(error.value)

