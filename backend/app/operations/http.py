from __future__ import annotations

import json
import logging
import os
import re
from time import monotonic
from uuid import uuid4


REQUEST_LOGGER = logging.getLogger("ecommerce_agent.http")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def normalize_request_id(value: str | None) -> str:
    return value if value and _REQUEST_ID.fullmatch(value) else str(uuid4())


def security_headers() -> dict[str, str]:
    headers = {
        "x-content-type-options": "nosniff",
        "referrer-policy": "strict-origin-when-cross-origin",
        "permissions-policy": "camera=(), microphone=(), geolocation=()",
        "content-security-policy": (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'"
        ),
    }
    if os.getenv("ECOM_ENV", "development").strip().lower() == "production":
        headers["strict-transport-security"] = "max-age=31536000; includeSubDomains"
    return headers


def request_timer() -> float:
    return monotonic()


def log_request(*, request_id: str, method: str, path: str, status_code: int, started: float) -> None:
    REQUEST_LOGGER.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": request_id,
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round((monotonic() - started) * 1000, 3),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )

