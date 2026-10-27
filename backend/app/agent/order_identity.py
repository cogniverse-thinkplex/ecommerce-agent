from __future__ import annotations

import re


_RETAIL_ORDER_ID_PATTERN = re.compile(r"#?W(?P<digits>[0-9]+)", re.IGNORECASE)


def canonicalize_retail_order_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = _RETAIL_ORDER_ID_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    return f"#W{match.group('digits')}"
