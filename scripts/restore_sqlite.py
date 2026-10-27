#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from app.operations.sqlite_backup import restore_backup


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify and restore a SQLite backup.")
    parser.add_argument("source")
    parser.add_argument("target")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    result = restore_backup(Path(args.source), Path(args.target), args.replace)
    print(result.target_path)
    if result.safety_backup_path:
        print(f"safety_backup={result.safety_backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

