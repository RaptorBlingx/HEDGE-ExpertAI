#!/bin/bash
# Trigger initial data ingestion
set -e
echo "Triggering metadata ingestion..."
curl -sf -X POST http://localhost:8004/api/v1/ingest/trigger | python3 -m json.tool
echo ""
echo "Ingestion triggered. Check status with:"
echo "  curl http://localhost:8004/api/v1/ingest/status"
