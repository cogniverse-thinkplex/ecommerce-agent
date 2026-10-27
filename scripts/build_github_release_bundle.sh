#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DIST_DIR="$ROOT_DIR/dist"
BUNDLE_DIR="$DIST_DIR/e-commerce-agent-github-$STAMP"
ARCHIVE_PATH="$BUNDLE_DIR.tar.gz"

mkdir -p "$DIST_DIR"

rsync -a \
  --exclude '/.git/' \
  --exclude '/.env' \
  --exclude '/.env.production' \
  --exclude '/.idea/' \
  --exclude '/.superpowers/' \
  --exclude '/.pytest_cache/' \
  --exclude '**/.pytest_cache/' \
  --exclude '/dist/' \
  --exclude '/data/' \
  --exclude '/Adaptive_Ecommerce_Agent_Fullstack_Observability_Development_Plan.docx' \
  --exclude '.DS_Store' \
  --exclude '**/__pycache__/' \
  --exclude '**/*.pyc' \
  --exclude '/benchmarks/.venv/' \
  --exclude '/benchmarks/web/' \
  --include '/benchmarks/data/' \
  --include '/benchmarks/data/tau2/' \
  --include '/benchmarks/data/tau2/domains/' \
  --include '/benchmarks/data/tau2/domains/retail/***' \
  --exclude '/benchmarks/data/***' \
  "$ROOT_DIR/" "$BUNDLE_DIR/"

cp "$ROOT_DIR/docs/operations/upload-manifest-template.md" \
  "$BUNDLE_DIR/UPLOAD_MANIFEST.md"

"$ROOT_DIR/benchmarks/.venv/bin/python" \
  "$ROOT_DIR/scripts/verify_public_bundle.py" "$BUNDLE_DIR" "$ROOT_DIR"

tar -C "$DIST_DIR" -czf "$ARCHIVE_PATH" "$(basename "$BUNDLE_DIR")"

printf 'bundle=%s\n' "$BUNDLE_DIR"
printf 'archive=%s\n' "$ARCHIVE_PATH"
du -sh "$BUNDLE_DIR" "$ARCHIVE_PATH"

