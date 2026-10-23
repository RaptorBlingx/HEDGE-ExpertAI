#!/usr/bin/env bash
# Own project only. Never layer this file onto the demo/production Compose stack.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export PRIVATE_TEST_DIR="${PRIVATE_TEST_DIR:-/home/ubuntu/.local/share/hedge-private-test}"
compose=(docker compose -p expertai-private-test --env-file "$PRIVATE_TEST_DIR/runtime.env" -f docker-compose.private-test.yml)
python3 - "$PRIVATE_TEST_DIR" <<'PY'
import os
import pathlib
import sys
from urllib.parse import urlparse
root = pathlib.Path(sys.argv[1])
values = dict(line.split('=', 1) for line in (root / 'runtime.env').read_text().splitlines()
              if line and not line.startswith('#'))
url = urlparse(values['DATABASE_URL'])
assert url.hostname == 'postgres' and url.path == '/hedge_private_test', 'Wrong test database'
assert values.get('PRIVATE_STORE_ENABLED') == 'true', 'Private mode required'
assert values.get('APP_ENV') == 'private-testing', 'Private testing environment required'
for file in [root / 'runtime.env', root / 'credentials/client-secret']:
    info = file.stat()
    assert file.is_file() and not file.is_symlink() and info.st_uid == os.getuid() and info.st_mode & 0o777 == 0o600, 'Unsafe private configuration permissions'
PY
"${compose[@]}" config --quiet
case "${1:-status}" in
  start)
    python3 - <<'PY'
import shutil
assert shutil.disk_usage('/').free >= 4 * 1024**3, 'Keep at least 4 GiB disk headroom'
mem = dict((line.split(':')[0], int(line.split()[1])) for line in open('/proc/meminfo'))
assert mem['MemAvailable'] >= 700 * 1024, 'Insufficient available memory'
PY
    "${compose[@]}" up -d postgres valkey-cache valkey-queue qdrant
    "${compose[@]}" run --rm migrations
    "${compose[@]}" up -d discovery-ranking rasa expert-recommend chat-intent metadata-ingest metadata-worker metadata-scheduler gateway
    for ((attempt=0; attempt<90; attempt++)); do
      if curl -fsS http://127.0.0.1:8096/api/v2/status >/dev/null 2>&1; then
        curl -fsS -X POST http://127.0.0.1:8096/evaluation/refresh
        exit 0
      fi
      sleep 2
    done
    echo 'Private gateway did not become available; inspect only this project.' >&2
    exit 1 ;;
  stop) "${compose[@]}" stop ;;
  status) "${compose[@]}" ps ;;
  *) echo 'Usage: scripts/private-test.sh start|stop|status' >&2; exit 1 ;;
esac
