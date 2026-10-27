#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

from app.operations.sqlite_backup import create_backup


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and verify an online SQLite backup.")
    parser.add_argument("--source", default=os.getenv("ECOM_AGENT_SQLITE_PATH", "data/ecommerce_agent.db"))
    parser.add_argument("--destination", default="data/backups")
    parser.add_argument("--retain", type=int, default=14)
    parser.add_argument("--label")
    args = parser.parse_args()
    result = create_backup(Path(args.source), Path(args.destination), args.retain, args.label)
    print(result.database_path)
    print(result.metadata_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

