#!/usr/bin/env python3
from __future__ import annotations

from datetime import timedelta
import json
import os
from pathlib import Path
import urllib.request
from urllib.parse import urlparse

from app.operations.operational_checks import run_operational_checks


def _ready_probe() -> dict:
    endpoint = os.getenv("ECOM_READY_URL", "http://127.0.0.1:8000/ready")
    if urlparse(endpoint).scheme not in {"http", "https"}:
        raise ValueError("ECOM_READY_URL must use http or https")
    # Scheme is constrained above; Bandit cannot infer the urlparse guard.
    with urllib.request.urlopen(endpoint, timeout=5) as response:  # nosec B310
        return json.load(response)


def main() -> int:
    result = run_operational_checks(
        ready_probe=_ready_probe,
        backup_dir=Path(os.getenv("ECOM_BACKUP_DIR", "data/backups")),
        max_backup_age=timedelta(seconds=int(os.getenv("ECOM_MAX_BACKUP_AGE_SECONDS", "93600"))),
        min_disk_free_ratio=float(os.getenv("ECOM_MIN_DISK_FREE_RATIO", "0.20")),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

