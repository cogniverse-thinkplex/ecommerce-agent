from typing import Any

from app.auth.retail_identity import RetailIdentityResolver
from app.tools.retail_port import RetailToolResult


class IdentityPort:
    def __init__(self, content: Any, *, error: bool = False) -> None:
        self.content = content
        self.error = error
        self.calls = []

    def call_tool(self, name, arguments, call_id=None):
        self.calls.append((name, arguments, call_id))
        return RetailToolResult(
            call_id=call_id or "call",
            name=name,
            content=self.content,
            raw_content=str(self.content),
            error=self.error,
        )


def test_retail_identity_resolver_uses_email_lookup_tool():
    port = IdentityPort("ivan_santos_6635")

    resolved = RetailIdentityResolver(port)("ivan.santos3158@example.com")

    assert resolved == "ivan_santos_6635"
    assert port.calls == [
        (
            "find_user_id_by_email",
            {"email": "ivan.santos3158@example.com"},
            "registration-identity-lookup",
        )
    ]


def test_retail_identity_resolver_returns_none_for_failed_lookup():
    assert RetailIdentityResolver(IdentityPort("not found", error=True))(
        "unknown@example.com"
    ) is None
