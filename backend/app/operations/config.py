from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


class ProductionConfigError(RuntimeError):
    """Raised when production starts with an unsafe runtime configuration."""


def validate_runtime_config(environ: Mapping[str, str]) -> None:
    if environ.get("ECOM_ENV", "development").strip().lower() != "production":
        return

    errors: list[str] = []
    _require_equal(environ, errors, "ECOM_AGENT_STORE", "sqlite")
    database_path = environ.get("ECOM_AGENT_SQLITE_PATH", "").strip()
    if not database_path or not Path(database_path).is_absolute():
        errors.append("ECOM_AGENT_SQLITE_PATH must be an absolute path")
    _require_equal(environ, errors, "ECOM_AGENT_TOOL_BACKEND", "mcp")
    if not environ.get("ECOM_AGENT_MCP_URL", "").strip():
        errors.append("ECOM_AGENT_MCP_URL is required")
    _require_equal(environ, errors, "ECOM_AGENT_PROPOSAL_GENERATOR", "llm")
    _require_equal(environ, errors, "ECOM_AUTH_COOKIE_SECURE", "true")
    _require_equal(environ, errors, "ECOM_POLICY_MODEL_LOCAL_ONLY", "true")

    model = environ.get("ECOM_AGENT_PROPOSAL_LLM", "").strip()
    if not model:
        errors.append("ECOM_AGENT_PROPOSAL_LLM is required")
    elif model.startswith("dashscope/") and not environ.get("DASHSCOPE_API_KEY", "").strip():
        errors.append("DASHSCOPE_API_KEY is required for a dashscope model")
    elif model.startswith("openai/") and not environ.get("OPENAI_API_KEY", "").strip():
        errors.append("OPENAI_API_KEY is required for an openai model")
    elif model.startswith("anthropic/") and not environ.get("ANTHROPIC_API_KEY", "").strip():
        errors.append("ANTHROPIC_API_KEY is required for an anthropic model")

    if errors:
        raise ProductionConfigError("Unsafe production configuration: " + "; ".join(errors))


def _require_equal(
    environ: Mapping[str, str], errors: list[str], name: str, expected: str
) -> None:
    if environ.get(name, "").strip().lower() != expected:
        errors.append(f"{name} must be {expected}")

