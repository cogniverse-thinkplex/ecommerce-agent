from __future__ import annotations

from typing import Any

from app.tools.retail_port import RetailToolPort


class RetailIdentityResolver:
    def __init__(self, port: RetailToolPort) -> None:
        self._port = port

    def __call__(self, email: str) -> str | None:
        result = self._port.call_tool(
            "find_user_id_by_email",
            {"email": email},
            call_id="registration-identity-lookup",
        )
        if result.error:
            return None
        return _user_id(result.content)


def _user_id(content: Any) -> str | None:
    if isinstance(content, str):
        normalized = content.strip()
        return normalized or None
    if isinstance(content, dict):
        value = content.get("user_id")
        return str(value) if value is not None else None
    return None
