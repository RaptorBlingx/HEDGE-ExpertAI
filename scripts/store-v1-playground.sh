#!/usr/bin/env bash
# Run the offline library pipeline in disposable resources; never use Compose/.env.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    python3 "$repo/scripts/store_v1_playground.py" --help
    exit 0
fi
work=$(mktemp -d)
suffix=$(basename "$work")
network="hedge-store-cli-$suffix"
postgres="${network}-database"
vectors="${network}-vectors"
sessions="${network}-sessions"
runner="${network}-runner"
image='hedge-store-cli:local'
postgres_image='postgres:16.9-alpine@sha256:7c688148e5e156d0e86df7ba8ae5a05a2386aaec1e2ad8e6d11bdf10504b1fb7'
qdrant_image='qdrant/qdrant:v1.18.2@sha256:75eab8c4ba42096724fdcfde8b4de0b5713d529dde32f285a1f86fdcb2c9e50c'
valkey_image='valkey/valkey:8.1.3-alpine@sha256:d827e7f7552cdee40cc7482dbae9da020f42bc47669af6f71182a4ef76a22773'
cleanup() {
    docker rm -f "$runner" "$sessions" "$vectors" "$postgres" >/dev/null 2>&1 || true
    docker network rm "$network" >/dev/null 2>&1 || true
    rm -rf -- "$work"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

# Only locks enter the build context, never .env, samples or runtime materials.
cp "$repo/tests/offline-store/Dockerfile" "$work/Dockerfile"
cp "$repo/shared/requirements.lock" "$work/shared.lock"
for service in chat-intent discovery-ranking expert-recommend metadata-ingest gateway mock-api; do
    cp "$repo/services/$service/requirements.lock" "$work/$service.lock"
done
for dependency_image in "$postgres_image" "$qdrant_image" "$valkey_image"; do
    docker image inspect "$dependency_image" >/dev/null 2>&1 || {
        echo "Required cached image missing: $dependency_image" >&2
        exit 1
    }
done
docker build -q -t "$image" "$work" >/dev/null

docker network create --internal "$network" >/dev/null
docker run -d --name "$postgres" --network "$network" --network-alias database \
    --memory 256m --cpus 1 --tmpfs /var/lib/postgresql/data:rw,size=384m \
    -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=hedge_phase1_test \
    "$postgres_image" >/dev/null
docker run -d --name "$vectors" --network "$network" --network-alias vectors \
    --memory 256m --cpus 1 --tmpfs /qdrant/storage:rw,size=128m \
    --tmpfs /qdrant/snapshots:rw,size=32m "$qdrant_image" >/dev/null
docker run -d --name "$sessions" --network "$network" --network-alias sessions \
    --memory 64m --cpus 0.5 --tmpfs /data:rw,size=32m \
    "$valkey_image" valkey-server --save '' --appendonly no >/dev/null
for ((attempt = 0; attempt < 30; attempt++)); do
    if docker exec "$postgres" pg_isready -U postgres -d hedge_phase1_test >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
terminal=()
if [[ -t 0 && -t 1 ]]; then terminal=(-t); fi
docker run --rm -i "${terminal[@]}" --name "$runner" --network "$network" \
    --memory 512m --cpus 1 --read-only --tmpfs /tmp:rw,size=64m \
    --mount "type=bind,source=$repo,target=/repo,readonly" \
    -e DATABASE_URL=postgresql://postgres@database/hedge_phase1_test \
    -e HEDGE_TEST_DATABASE_URL=postgresql://postgres@database/hedge_phase1_test \
    -e HEDGE_TEST_QDRANT_URL=http://vectors:6333 \
    -e VALKEY_SESSION_URL=redis://sessions:6379/0 \
    -e RASA_ENABLED=false "$image" scripts/store_v1_playground.py "$@"
