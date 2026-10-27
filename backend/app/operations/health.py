from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import sqlite3
from typing import Any


class ReadinessChecker:
    def __init__(self, list_tools: Callable[[], list[Any]]) -> None:
        self._list_tools = list_tools

    def check(self) -> dict[str, Any]:
        checks = {
            "database": self._database_check(),
            "tools": self._tool_check(),
        }
        ready = all(item["status"] == "ok" for item in checks.values())
        return {"status": "ready" if ready else "not_ready", "checks": checks}

    def _database_check(self) -> dict[str, str]:
        if os.getenv("ECOM_AGENT_STORE", "memory").strip().lower() != "sqlite":
            return {"status": "ok", "detail": "memory"}
        path = Path(os.getenv("ECOM_AGENT_SQLITE_PATH", "data/ecommerce_agent.db"))
        try:
            connection = sqlite3.connect(path, timeout=2)
            connection.execute("SELECT 1").fetchone()
            connection.execute("SELECT 1 FROM schema_migrations LIMIT 1").fetchone()
            connection.close()
            return {"status": "ok", "detail": "sqlite"}
        except sqlite3.Error as exc:
            return {"status": "error", "detail": type(exc).__name__}

    def _tool_check(self) -> dict[str, str]:
        try:
            tools = self._list_tools()
            if not tools:
                return {"status": "error", "detail": "empty_catalog"}
            return {"status": "ok", "detail": f"{len(tools)} tools"}
        except Exception as exc:
            return {"status": "error", "detail": type(exc).__name__}

