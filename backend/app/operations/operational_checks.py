from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
from typing import Any


@dataclass(frozen=True)
class OperationalCheck:
    code: str
    status: str
    message: str
    value: float | str | None = None


@dataclass(frozen=True)
class OperationalCheckResult:
    ok: bool
    checked_at: str
    checks: list[OperationalCheck]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "checked_at": self.checked_at, "checks": [asdict(item) for item in self.checks]}


def run_operational_checks(
    *,
    ready_probe: Callable[[], dict[str, Any]],
    backup_dir: Path | str,
    max_backup_age: timedelta = timedelta(hours=26),
    min_disk_free_ratio: float = 0.2,
    now: datetime | None = None,
    disk_usage: Callable[[Path], Any] = shutil.disk_usage,
) -> OperationalCheckResult:
    checked_at = now or datetime.now(timezone.utc)
    checks: list[OperationalCheck] = []
    try:
        readiness = ready_probe()
        ready = readiness.get("status") == "ready"
        checks.append(OperationalCheck(
            "service_ready" if ready else "service_not_ready",
            "ok" if ready else "error",
            "API dependencies are ready" if ready else "API dependencies are not ready",
        ))
    except Exception as exc:
        checks.append(OperationalCheck("service_not_ready", "error", f"Readiness probe failed: {type(exc).__name__}"))

    directory = Path(backup_dir)
    backups = sorted(directory.glob("*.db"), key=lambda item: item.stat().st_mtime, reverse=True) if directory.exists() else []
    if not backups:
        checks.append(OperationalCheck("backup_missing", "error", "No SQLite backup is available"))
    else:
        age_seconds = max(0.0, checked_at.timestamp() - backups[0].stat().st_mtime)
        stale = age_seconds > max_backup_age.total_seconds()
        checks.append(OperationalCheck(
            "backup_stale" if stale else "backup_fresh",
            "error" if stale else "ok",
            "Latest backup is stale" if stale else "Latest backup is fresh",
            round(age_seconds, 3),
        ))

    directory.mkdir(parents=True, exist_ok=True)
    total, _used, free = disk_usage(directory)
    free_ratio = free / total if total else 0.0
    low = free_ratio < min_disk_free_ratio
    checks.append(OperationalCheck(
        "disk_space_low" if low else "disk_space_ok",
        "error" if low else "ok",
        "Disk free space is below threshold" if low else "Disk free space is sufficient",
        round(free_ratio, 4),
    ))
    return OperationalCheckResult(
        ok=all(item.status == "ok" for item in checks),
        checked_at=checked_at.astimezone(timezone.utc).isoformat(),
        checks=checks,
    )

