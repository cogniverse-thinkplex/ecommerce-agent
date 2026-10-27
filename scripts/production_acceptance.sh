#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-benchmarks/.venv/bin/python}"

PYTHONPATH=backend "$PYTHON_BIN" -c 'import os; from app.operations.config import validate_runtime_config; validate_runtime_config(os.environ); print("runtime_config=valid")'
"$PYTHON_BIN" -m compileall -q backend/app scripts/backup_sqlite.py scripts/restore_sqlite.py
scripts/test_backend.sh backend/tests/operations backend/tests/ops backend/tests/api/test_operational_api.py backend/tests/api/test_login_rate_limit.py -q

ACCEPTANCE_DIR="$(mktemp -d /tmp/ecom-acceptance.XXXXXX)"
trap 'rm -rf "$ACCEPTANCE_DIR"' EXIT
PYTHONPATH=backend "$PYTHON_BIN" -c 'import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute("create table proof(value text)"); c.execute("insert into proof values (?)",("ok",)); c.commit(); c.close()' "$ACCEPTANCE_DIR/source.db"
PYTHONPATH=backend "$PYTHON_BIN" scripts/backup_sqlite.py --source "$ACCEPTANCE_DIR/source.db" --destination "$ACCEPTANCE_DIR/backups" --label acceptance
PYTHONPATH=backend "$PYTHON_BIN" scripts/restore_sqlite.py "$ACCEPTANCE_DIR/backups/acceptance.db" "$ACCEPTANCE_DIR/restored.db"
PYTHONPATH=backend "$PYTHON_BIN" -c 'import sqlite3,sys; assert sqlite3.connect(sys.argv[1]).execute("select value from proof").fetchone()[0] == "ok"' "$ACCEPTANCE_DIR/restored.db"

scripts/security_scan.sh
PYTHONPATH=backend "$PYTHON_BIN" scripts/check_operations.py
echo "production_acceptance=passed"

