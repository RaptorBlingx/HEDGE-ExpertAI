#!/usr/bin/env bash
# Run the offline library pipeline in disposable resources; never use Compose/.env.
set -euo pipefail
umask 077
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
browser=false
reuse_model_image=false
metadata_demo=false
real_embeddings=false
real_rasa=false
real_ollama=false
ollama_runtime=/home/ubuntu/.cache/hedge-store-ollama/0.32.0
ollama_model=qwen3.5:2b
port=8091
input_file=""
input_kind=""
store_id=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --browser) browser=true; shift ;;
        --metadata-demo) metadata_demo=true; shift ;;
        --reuse-model-image) reuse_model_image=true; shift ;;
        --embeddings) real_embeddings=true; shift ;;
        --rasa) real_rasa=true; shift ;;
        --ollama) real_ollama=true; shift ;;
        --ollama-model) ollama_model="${2:?Specify the model tag}"; shift 2 ;;
        --ollama-runtime) ollama_runtime="${2:?Specify private CPU runtime directory}"; shift 2 ;;
        --store-token-file|--apps-json)
            if [[ -n "$input_kind" ]]; then echo 'Choose one private input' >&2; exit 1; fi
            input_kind="$1"; input_file="${2:?Specify an absolute private input path}"; shift 2 ;;
        --store-id) store_id="${2:?Specify the native Store ID}"; shift 2 ;;
        --port) port="${2:?Specify a loopback port}"; shift 2 ;;
        *) break ;;
    esac
done
if ! [[ "$port" =~ ^[0-9]{4,5}$ ]] || ((port < 1024 || port > 65535)); then
    echo 'Choose a nonprivileged loopback port' >&2; exit 1
fi
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    echo "Launcher: --browser [--metadata-demo] [--port 8091] [--embeddings [--reuse-model-image]] [--rasa] [--ollama]; CLI: [--examples]; input: --store-token-file /private/token OR --apps-json /private/apps.json, with --store-id ID"
    python3 "$repo/scripts/store_v1_playground.py" --help
    exit 0
fi
if $reuse_model_image && ! $real_embeddings; then
    echo '--reuse-model-image requires --embeddings' >&2; exit 1
fi
if $metadata_demo && [[ -n "$input_kind" ]]; then
    echo 'Choose authored metadata demo OR private input' >&2; exit 1
fi
if [[ -n "$input_kind" ]]; then
    if [[ -z "$store_id" ]]; then echo 'Private input requires --store-id' >&2; exit 1; fi
    # Inspect permissions only, never read/print credentials on the host.
    python3 - "$input_file" "$repo" <<'PRIVATE'
import os, stat, sys
from pathlib import Path
try:
    path = Path(sys.argv[1])
    info = path.lstat()
    safe = (path.is_absolute() and stat.S_ISREG(info.st_mode)
            and info.st_uid == os.getuid() and not info.st_mode & 0o077
            and not path.resolve().is_relative_to(Path(sys.argv[2]).resolve()))
except OSError:
    safe = False
if not safe:
    sys.exit("Use an owned, regular mode-0600 private file outside the repository")
PRIVATE
elif [[ -n "$store_id" ]]; then
    echo '--store-id requires a private input' >&2; exit 1
fi
if $real_ollama; then
    if $real_rasa; then echo 'Run Rasa diagnostics separately from CPU generation on this host' >&2; exit 1; fi
    if [[ ! -x "$ollama_runtime/bin/ollama" ]]; then
        echo 'Prepare the pinned CPU runtime per docs/store-v1-ollama-evaluation.md' >&2; exit 1
    fi
fi
if $real_embeddings || $real_rasa || $real_ollama; then
    required_mib=1800
    if $real_embeddings && $real_rasa; then required_mib=2600; fi
    if $real_ollama; then required_mib=3200; fi
    if $real_ollama && $real_embeddings; then required_mib=3800; fi
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
fetcher="${network}-fetch"
image='hedge-store-cli:local'
if $browser; then image='hedge-store-browser:local'; fi
postgres_image='postgres:16.9-alpine@sha256:7c688148e5e156d0e86df7ba8ae5a05a2386aaec1e2ad8e6d11bdf10504b1fb7'
qdrant_image='qdrant/qdrant:v1.18.2@sha256:75eab8c4ba42096724fdcfde8b4de0b5713d529dde32f285a1f86fdcb2c9e50c'
valkey_image='valkey/valkey:8.1.3-alpine@sha256:d827e7f7552cdee40cc7482dbae9da020f42bc47669af6f71182a4ef76a22773'
cleanup() {
    docker rm -f "$fetcher" "$runner" "$rasa" "$sessions" "$vectors" "$postgres" >/dev/null 2>&1 || true
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
if $real_embeddings && ! $reuse_model_image; then
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
# Private-input runs use the host UID; public model weights must be readable by it.
RUN mv /tmp/e5-model /opt/e5-model && chmod -R a+rX /opt/e5-model && rm -rf /tmp/e5-cache
ENV EMBEDDING_MODEL=/opt/e5-model
USER 10001
MODEL
fi
if $reuse_model_image; then
    # Explicit opt-in to the previously prepared local pinned-model image. Do
    # not rebuild large model layers merely to mount changed application source.
    image=$(docker image inspect hedge-store-models:local --format '{{.Id}}')
    docker run --rm --network none --read-only --entrypoint python "$image" -c \
        "from pathlib import Path; from importlib.util import find_spec; assert find_spec('sentence_transformers'); assert Path('/opt/e5-model/modules.json').is_file()"
    echo "Using cached developer model image: $image"
else
    docker build -q --memory 1024m --cpu-period 100000 --cpu-quota 100000 "${build_args[@]}" -t "$image" "$work" >/dev/null
fi

input_mounts=()
input_env=()
if $metadata_demo; then
    input_env=(-e STORE_PLAYGROUND_METADATA_DEMO=true)
fi
if [[ -n "$input_kind" ]]; then
    fetch_option=--apps-json
    input_network=none
    if [[ "$input_kind" == --store-token-file ]]; then
        fetch_option=--token-file; input_network=bridge
    fi
    # Only this bounded one-shot process has outbound access and the private file.
    # The chat runner receives no token, raw owner fields or Store transport settings.
    docker run --rm --name "$fetcher" --network "$input_network" --user "$(id -u):$(id -g)" \
        --memory 256m --cpus 1 --read-only --tmpfs /tmp:rw,size=32m \
        --mount "type=bind,source=$repo,target=/repo,readonly" \
        --mount "type=bind,source=$input_file,target=/input/private,readonly" \
        "$image" -m scripts.store_v1_input "$fetch_option" /input/private --store-id "$store_id" \
        > "$work/apps.json"
    input_mounts=(--user "$(id -u):$(id -g)" \
        --mount "type=bind,source=$work/apps.json,target=/input/apps.json,readonly")
    input_mode=private-json-import
    if [[ "$input_kind" == --store-token-file ]]; then input_mode=authorized-api-snapshot; fi
    input_env=(-e STORE_PLAYGROUND_INPUT=/input/apps.json -e "STORE_PLAYGROUND_ID=$store_id" \
        -e "STORE_PLAYGROUND_SOURCE=$input_mode")
fi

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
ollama_mounts=()
if $real_ollama; then
    install -d -m 700 /home/ubuntu/.cache/hedge-store-ollama/models
    ollama_mounts=(--user "$(id -u):$(id -g)" \
        --mount "type=bind,source=$ollama_runtime,target=/opt/ollama,readonly" \
        --mount "type=bind,source=/home/ubuntu/.cache/hedge-store-ollama/models,target=/ollama-models" \
        --tmpfs "/.ollama:rw,size=16m,mode=700,uid=$(id -u),gid=$(id -g)")
    model_env+=(-e STORE_PLAYGROUND_OLLAMA=true -e "OLLAMA_MODEL=$ollama_model" \
        -e OLLAMA_MODELS=/ollama-models -e OLLAMA_HOST=127.0.0.1:11434 \
        -e OLLAMA_BASE_URL=http://127.0.0.1:11434 -e OLLAMA_NUM_PARALLEL=1 \
        -e OLLAMA_MAX_LOADED_MODELS=1 -e OLLAMA_NO_CLOUD=true -e OLLAMA_DEBUG=false)
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
    echo "Isolated Chat Pane: http://127.0.0.1:$port (Ctrl-C stops and removes only this run)"
fi
if $real_ollama; then
    command=(scripts/store_v1_ollama.py "${command[@]}")
    memory=2560m
    if $real_embeddings; then memory=3072m; fi
fi
docker run --rm -i "${terminal[@]}" --name "$runner" --network "$network" \
    --memory "$memory" --memory-swap "$memory" --cpus 1 --read-only --tmpfs /tmp:rw,size=64m "${ports[@]}" \
    --mount "type=bind,source=$repo,target=/repo,readonly" \
    -e DATABASE_URL=postgresql://postgres@database/hedge_phase1_test \
    -e HEDGE_TEST_DATABASE_URL=postgresql://postgres@database/hedge_phase1_test \
    -e HEDGE_TEST_QDRANT_URL=http://vectors:6333 \
    -e VALKEY_SESSION_URL=redis://sessions:6379/0 \
    "${model_env[@]}" "${input_env[@]}" "${input_mounts[@]}" "${ollama_mounts[@]}" "$image" "${command[@]}"
