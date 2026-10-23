#!/bin/bash
# Trigger initial data ingestion
set -e
: "${GATEWAY_API_KEY:?Provide the configured administrative key in the environment}"
echo "Triggering metadata ingestion..."
printf 'X-API-Key: %s\n' "$GATEWAY_API_KEY" |
    curl -sf --header @- -X POST http://localhost:8004/api/v1/ingest/trigger | python3 -m json.tool
echo ""
echo "Ingestion triggered. Check status with:"
echo "  curl http://localhost:8004/api/v1/ingest/status"
