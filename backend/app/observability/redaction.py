from __future__ import annotations

from typing import Any

from app.operations.redaction import redact


SENSITIVE_KEYS = {
    "password", "temporary_password", "authorization", "cookie", "session",
    "token", "api_key", "apikey", "email", "phone", "telephone", "address",
    "payment", "card", "arguments", "free_text", "content", "message",
}


def sanitize_context(value: Any, *, max_string_length: int = 500) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            result[str(key)] = "[REDACTED]" if any(token in normalized for token in SENSITIVE_KEYS) else sanitize_context(item, max_string_length=max_string_length)
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize_context(item, max_string_length=max_string_length) for item in value]
    if isinstance(value, str):
        masked = redact(value)
        return masked if len(masked) <= max_string_length else masked[:max_string_length] + "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(type(value).__name__)
