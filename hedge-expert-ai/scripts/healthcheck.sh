#!/bin/bash
# Check health of all HEDGE-ExpertAI services
echo "=== HEDGE-ExpertAI Health Check ==="
echo ""
for svc in "Gateway:8000" "Chat-Intent:8001" "Expert-Recommend:8002" "Discovery-Ranking:8003" "Metadata-Ingest:8004" "Mock-API:9000"; do
  name="${svc%%:*}"
  port="${svc##*:}"
  status=$(curl -sf "http://localhost:${port}/health" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "DOWN")
  printf "  %-20s %s\n" "$name" "$status"
done
