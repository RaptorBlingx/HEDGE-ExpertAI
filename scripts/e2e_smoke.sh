#!/bin/sh
set -eu

if [ -n "${GATEWAY_E2E_URL:-}" ]; then
    gateway_url="$GATEWAY_E2E_URL"
else
    gateway_bind="${GATEWAY_BIND_ADDRESS:-}"
    if [ -z "$gateway_bind" ] && [ -f .env ]; then
        gateway_bind="$(awk -F= '$1 == "GATEWAY_BIND_ADDRESS" {print $2}' .env | tail -n 1)"
    fi
    gateway_url="http://${gateway_bind:-127.0.0.1}:8080"
fi
ingest_url="${INGEST_E2E_URL:-http://127.0.0.1:8004}"
rasa_url="${RASA_E2E_URL:-http://127.0.0.1:5005}"
deadline="${E2E_DEADLINE_SECONDS:-300}"

wait_until=$(( $(date +%s) + deadline ))
while ! curl -fsS "$gateway_url/ready" >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$wait_until" ]; then
        echo "gateway did not become ready within ${deadline}s" >&2
        exit 1
    fi
    sleep 3
done

# The public demo is served with a strict script CSP. Its initialization must
# remain in a same-origin asset rather than an inline script.
curl -fsS "$gateway_url/demo.html" >/tmp/hedge-e2e-demo.html
grep -q 'src="/demo-init.js' /tmp/hedge-e2e-demo.html
if grep -Eq '<script[[:space:]]*>' /tmp/hedge-e2e-demo.html; then
    echo "demo contains an inline script blocked by the gateway CSP" >&2
    exit 1
fi
curl -fsS "$gateway_url/demo-init.js" >/dev/null
curl -fsS "$gateway_url/hedge-expert-widget.js" | grep -q 'isSyntheticAppUrl'
curl -fsS "$gateway_url/favicon.svg" >/dev/null

curl -fsS -X POST "$rasa_url/model/parse" \
    -H 'Content-Type: application/json' \
    -d '{"text":"Zeige mir Anwendungen zur Energieüberwachung"}' \
    >/tmp/hedge-e2e-rasa.json
jq -e '.intent.name == "search" and .intent.confidence >= 0.5' \
    /tmp/hedge-e2e-rasa.json >/dev/null

curl -fsS -X POST "$ingest_url/api/v2/ingestion/runs" >/tmp/hedge-e2e-ingest.json

while :; do
    status="$(curl -fsS "$ingest_url/api/v2/ingestion/runs/latest" | jq -r '.status')"
    case "$status" in
        completed) break ;;
        failed|partial)
            echo "ingestion ended with status $status" >&2
            exit 1
            ;;
    esac
    if [ "$(date +%s)" -ge "$wait_until" ]; then
        echo "ingestion did not complete within ${deadline}s" >&2
        exit 1
    fi
    sleep 2
done

curl -fsS -X POST "$gateway_url/api/v2/apps/search" \
    -H 'Content-Type: application/json' \
    -d '{"query":"energy monitoring","locale":"de","filters":{"extension_uri":"https://saref.etsi.org/saref4ener/"},"limit":2}' \
    >/tmp/hedge-e2e-search.json
jq -e '.locale == "de" and .total == 2 and (.results | length == 2)' \
    /tmp/hedge-e2e-search.json >/dev/null

curl -fsS -N -X POST "$gateway_url/api/v2/chat/stream" \
    -H 'Content-Type: application/json' \
    -d '{"message":"Find energy monitoring apps","locale":"en","filters":{}}' \
    >/tmp/hedge-e2e-stream.txt

for event in stage recommendations explanation_delta complete; do
    grep -q "event: $event" /tmp/hedge-e2e-stream.txt
done
if grep -qi '<think>' /tmp/hedge-e2e-stream.txt; then
    echo "hidden reasoning tag leaked into SSE" >&2
    exit 1
fi

echo "deterministic Docker E2E smoke passed"
