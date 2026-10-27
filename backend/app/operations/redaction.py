from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any


_SECRET_KEYS = re.compile(r"password|passwd|authorization|cookie|token|api[_-]?key|secret", re.I)
_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+={0,2}")
_EMAIL = re.compile(r"(?<![\w.+-])([A-Za-z0-9._%+-])[^@\s]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_PHONE = re.compile(r"(?<!\d)(1\d{2})\d{4}(\d{4})(?!\d)")


def redact(value: Any, key: str | None = None) -> Any:
    if key is not None and _SECRET_KEYS.search(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(item_key): redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        masked = _BEARER.sub(r"\1[REDACTED]", value)
        masked = _EMAIL.sub(r"\1***@\2", masked)
        return _PHONE.sub(r"\1****\2", masked)
    return value

