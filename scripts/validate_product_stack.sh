#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
curl -fsS "$BASE_URL/health" >/dev/null
cookie_file="$(mktemp)"
trap 'rm -f "$cookie_file"' EXIT
./scripts/seed_demo_customers.sh >/dev/null
email="${SUPPORT_TEST_EMAIL:-ivan.santos3158@example.com}"
password="${SUPPORT_TEST_PASSWORD:-DemoCustomer@123}"
curl -fsS -c "$cookie_file" -X POST \
  -H 'content-type: application/json' \
  --data "{\"email\":\"$email\",\"password\":\"$password\"}" \
  "$BASE_URL/api/v1/auth/login" | benchmarks/.venv/bin/python -c \
  'import json,sys; user=json.load(sys.stdin)["user"]; assert user["role"] == "customer"; assert user["retail_account_linked"] is True' >/dev/null
curl -fsS -b "$cookie_file" "$BASE_URL/support/" | grep -q "sidebar-account-name"
curl -fsS -b "$cookie_file" "$BASE_URL/account/" | grep -q "address-list"
curl -fsS -b "$cookie_file" "$BASE_URL/api/v1/auth/addresses" | benchmarks/.venv/bin/python -c \
  'import json,sys; rows=json.load(sys.stdin); assert isinstance(rows,list) and rows; assert rows[0]["is_default"] is True' >/dev/null
curl -fsS -b "$cookie_file" "$BASE_URL/api/v1/auth/spending?period=month" | benchmarks/.venv/bin/python -c \
  'import json,sys; body=json.load(sys.stdin); assert body["period"] == "month"; assert body["demo_data"] is True; assert len(body["series"]) == 12' >/dev/null
conversation_id="$(curl -fsS -b "$cookie_file" -X POST "$BASE_URL/api/v1/support/conversations" | \
  benchmarks/.venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["conversation_id"])')"
test -n "$conversation_id"
curl -fsS "$BASE_URL/health" | benchmarks/.venv/bin/python -c \
  'import json,sys; assert "mcp" in json.load(sys.stdin)["tool_backend"]'
echo "Product stack validation passed: $conversation_id"
