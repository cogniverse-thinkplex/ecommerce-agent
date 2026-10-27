#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import time

from app.operations.sqlite_backup import create_backup


def run_once() -> None:
    result = create_backup(
        Path(os.getenv("ECOM_AGENT_SQLITE_PATH", "data/ecommerce_agent.db")),
        Path(os.getenv("ECOM_BACKUP_DIR", "data/backups")),
        retain=int(os.getenv("ECOM_BACKUP_RETENTION", "14")),
    )
    print(f"backup_completed path={result.database_path} sha256={result.sha256}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run verified SQLite backups periodically.")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    interval = int(os.getenv("ECOM_BACKUP_INTERVAL_SECONDS", "86400"))
    if interval < 60 and not args.once:
        raise ValueError("ECOM_BACKUP_INTERVAL_SECONDS must be at least 60")
    while True:
        run_once()
        if args.once:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())

