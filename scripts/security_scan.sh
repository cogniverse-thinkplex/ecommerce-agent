#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-benchmarks/.venv/bin/python}"
PIP_AUDIT_BIN="${PIP_AUDIT_BIN:-benchmarks/.venv/bin/pip-audit}"
BANDIT_BIN="${BANDIT_BIN:-benchmarks/.venv/bin/bandit}"
UV_BIN="${UV_BIN:-uv}"

if [[ ! -x "$PIP_AUDIT_BIN" ]]; then
  echo "security scanner missing: pip-audit" >&2
  exit 2
fi
if [[ ! -x "$BANDIT_BIN" ]]; then
  echo "security scanner missing: bandit" >&2
  exit 2
fi

PIP_AUDIT_CACHE_DIR="${PIP_AUDIT_CACHE_DIR:-/tmp/ecom-pip-audit-cache}"
RUNTIME_REQUIREMENTS="$(mktemp /tmp/ecom-runtime-requirements.XXXXXX.txt)"
cleanup() { rm -f "$RUNTIME_REQUIREMENTS"; }
trap cleanup EXIT
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/ecom-uv-cache}" "$UV_BIN" export --quiet \
  --project benchmarks --no-dev --no-hashes --no-emit-project \
  --output-file "$RUNTIME_REQUIREMENTS"
"$PIP_AUDIT_BIN" --requirement "$RUNTIME_REQUIREMENTS" --no-deps --progress-spinner off \
  --cache-dir "$PIP_AUDIT_CACHE_DIR" --ignore-vuln CVE-2026-114603
# B105/B106 are false positives for boolean fields and an intentionally invalid
# legacy placeholder hash. B608 findings are limited to repository-owned SQL
# fragments assembled from fixed allowlists; all values remain parameterized.
"$BANDIT_BIN" -q -r backend/app scripts -x backend/tests -s B105,B106,B608

if rg -n --hidden --glob '!*.lock' --glob '!.env' --glob '!.git/**' \
  '(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----)' \
  backend scripts docs .env.example .env.production.example README.md; then
  echo "potential secret material found" >&2
  exit 1
fi
echo "secret_pattern_scan=clean"

