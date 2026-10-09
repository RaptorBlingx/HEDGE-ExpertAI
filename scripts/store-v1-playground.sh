#!/usr/bin/env bash
# Run the offline library pipeline in disposable resources; never use Compose/.env.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
browser=false
real_embeddings=false
real_rasa=false
port=8091
while [[ $# -gt 0 ]]; do
    case "$1" in
        --browser) browser=true; shift ;;
        --embeddings) real_embeddings=true; shift ;;
        --rasa) real_rasa=true; shift ;;
        --port) port="${2:?Specify a loopback port}"; shift 2 ;;
        *) break ;;
    esac
done
if ! [[ "$port" =~ ^[0-9]{4,5}$ ]] || ((port < 1024 || port > 65535)); then
    echo 'Choose a nonprivileged loopback port' >&2; exit 1
fi
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    echo "Launcher: --browser [--port 8091] [--embeddings] [--rasa]; CLI: [--examples]"
    python3 "$repo/scripts/store_v1_playground.py" --help
    exit 0
fi
if $real_embeddings || $real_rasa; then
    required_mib=1800
    if $real_embeddings && $real_rasa; then required_mib=2600; fi
    available_mib=$(awk '/^MemAvailable:/ {print int($2 / 1024)}' /proc/meminfo)
    if ((available_mib < required_mib)); then
        echo "Need at least $required_mib MiB available for requested model mode; use lexical mode or stop only your own evaluation run" >&2
        exit 1
    fi
fi
work=$(mktemp -d)
suffix=$(basename "$work")
network="hedge-store-cli-$suffix"
postgres="${network}-database"
vectors="${network}-vectors"
sessions="${network}-sessions"
runner="${network}-runner"
rasa="${network}-rasa"
image='hedge-store-cli:local'
if $browser; then image='hedge-store-browser:local'; fi
postgres_image='postgres:16.9-alpine@sha256:7c688148e5e156d0e86df7ba8ae5a05a2386aaec1e2ad8e6d11bdf10504b1fb7'
qdrant_image='qdrant/qdrant:v1.18.2@sha256:75eab8c4ba42096724fdcfde8b4de0b5713d529dde32f285a1f86fdcb2c9e50c'
valkey_image='valkey/valkey:8.1.3-alpine@sha256:d827e7f7552cdee40cc7482dbae9da020f42bc47669af6f71182a4ef76a22773'
cleanup() {
    docker rm -f "$runner" "$rasa" "$sessions" "$vectors" "$postgres" >/dev/null 2>&1 || true
    docker network rm "$network" "${network}-ui" >/dev/null 2>&1 || true
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
build_args=()
if $real_embeddings; then
    # Reuse the existing pinned CPU model dependencies.
    # These are image reads, with no connection to their running demo containers.
    docker image inspect hedge-discovery-ranking:latest >/dev/null
    discovery_image=hedge-discovery-ranking:latest
    build_args=(--build-arg "BASE_IMAGE=$discovery_image")
    image=hedge-store-models:local
    cat >> "$work/Dockerfile" <<'MODEL'
ENV HF_HOME=/tmp/e5-cache OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 HF_HUB_DISABLE_XET=1
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small', revision='614241f622f53c4eeff9890bdc4f31cfecc418b3').save('/tmp/e5-model')"
ENV EMBEDDING_MODEL=/tmp/e5-model HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
MODEL
    # /tmp is a runtime tmpfs, so keep the built model outside it.
    cat >> "$work/Dockerfile" <<'MODEL'
USER root
RUN mv /tmp/e5-model /opt/e5-model && rm -rf /tmp/e5-cache
ENV EMBEDDING_MODEL=/opt/e5-model
USER 10001
MODEL
fi
docker build -q --memory 1024m --cpu-period 100000 --cpu-quota 100000 "${build_args[@]}" -t "$image" "$work" >/dev/null

docker network create --internal "$network" >/dev/null
if $browser; then docker network create "${network}-ui" >/dev/null; fi
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
model_env=(-e RASA_ENABLED=false)
if $real_rasa; then
    rasa_image=$(docker image inspect hedge-rasa:latest --format '{{.Id}}')
    docker run -d --name "$rasa" --network "$network" --network-alias rasa \
        --memory 768m --cpus 1 --tmpfs /tmp:rw,size=128m \
        -e RASA_TELEMETRY_ENABLED=false "$rasa_image" >/dev/null
    for ((attempt = 0; attempt < 60; attempt++)); do
        if docker exec "$rasa" python -c "import urllib.request; urllib.request.urlopen('http://localhost:5005/status', timeout=1)" >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    docker exec "$rasa" python -c "import urllib.request; urllib.request.urlopen('http://localhost:5005/status', timeout=2)" >/dev/null || {
        echo "Isolated Rasa failed startup; retry without --rasa" >&2; exit 1
    }
    model_env=(-e RASA_ENABLED=true -e RASA_URL=http://rasa:5005)
fi
if $real_embeddings; then
    model_env+=(-e STORE_PLAYGROUND_E5=true \
        -e EMBEDDING_MODEL_REVISION=614241f622f53c4eeff9890bdc4f31cfecc418b3 \
        -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e TOKENIZERS_PARALLELISM=false)
fi
terminal=()
if [[ -t 0 && -t 1 ]]; then terminal=(-t); fi
command=(scripts/store_v1_playground.py "$@")
ports=()
memory=512m
if $real_embeddings; then memory=1024m; fi
if $browser; then
    command=(-m uvicorn scripts.store_v1_browser:app --host 0.0.0.0 --port 8091)
    ports=(--network "${network}-ui" -p "127.0.0.1:$port:8091")
    echo "Offline Chat Pane: http://127.0.0.1:$port (Ctrl-C stops and removes only this run)"
fi
docker run --rm -i "${terminal[@]}" --name "$runner" --network "$network" \
    --memory "$memory" --cpus 1 --read-only --tmpfs /tmp:rw,size=64m "${ports[@]}" \
    --mount "type=bind,source=$repo,target=/repo,readonly" \
    -e DATABASE_URL=postgresql://postgres@database/hedge_phase1_test \
    -e HEDGE_TEST_DATABASE_URL=postgresql://postgres@database/hedge_phase1_test \
    -e HEDGE_TEST_QDRANT_URL=http://vectors:6333 \
    -e VALKEY_SESSION_URL=redis://sessions:6379/0 \
    "${model_env[@]}" "$image" "${command[@]}"
