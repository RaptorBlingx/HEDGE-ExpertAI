#!/usr/bin/env bash
set -Eeuo pipefail

STACK_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
expected_bind="127.0.0.1"
if [[ -f "$STACK_DIR/.env" ]]; then
  configured_bind="$(awk -F= '$1 == "GATEWAY_BIND_ADDRESS" {print $2}' "$STACK_DIR/.env" | tail -n 1)"
  [[ -n "$configured_bind" ]] && expected_bind="$configured_bind"
fi

health="$(docker inspect hedge-gateway --format '{{.State.Health.Status}}' 2>/dev/null || true)"
published="$(docker port hedge-gateway 8000/tcp 2>/dev/null || true)"
if [[ "$health" == healthy ]] && grep -Fq -- "${expected_bind}:8080" <<<"$published"; then
  exit 0
fi

exec "$STACK_DIR/scripts/ensure_stack.sh"
