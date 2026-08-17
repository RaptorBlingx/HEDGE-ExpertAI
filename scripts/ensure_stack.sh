#!/usr/bin/env bash
set -Eeuo pipefail

# Reconcile the Compose stack after Docker or the host has restarted. Docker
# can restore a container's process while leaving its network endpoint stale;
# recreating the edge gateway is safe and restores its published listener.
STACK_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose -f "$STACK_DIR/docker-compose.yml" -f "$STACK_DIR/docker-compose.e2e.yml")
DEMO_SERVICES=(
  postgres migrations qdrant discovery-ranking mock-api
  valkey-cache valkey-queue rasa chat-intent expert-recommend
  metadata-worker metadata-scheduler metadata-ingest gateway
)

cd "$STACK_DIR"
"${COMPOSE[@]}" up -d --no-build --remove-orphans "${DEMO_SERVICES[@]}"
"${COMPOSE[@]}" up -d --no-build --force-recreate gateway

for _ in $(seq 1 60); do
  status="$(docker inspect hedge-gateway --format '{{.State.Health.Status}}' 2>/dev/null || true)"
  if [[ "$status" == healthy ]]; then
    exit 0
  fi
  sleep 1
done

echo "hedge-gateway did not become healthy" >&2
docker compose -f "$STACK_DIR/docker-compose.yml" -f "$STACK_DIR/docker-compose.e2e.yml" ps gateway >&2 || true
exit 1
