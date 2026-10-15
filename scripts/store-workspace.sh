#!/usr/bin/env bash
# Private, durable development workspace. Never uses Compose, .env or demo resources.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
prefix=expertai-store-private
label=expertai.workspace=store-private
store_id=${HEDGE_STORE_ID:-56779afa-bdcc-4abe-a8b0-d306dc07bed1}
private_dir=/home/ubuntu/.local/share/hedge-store-live
command=${1:-status}
check_owner() {
  [[ $(docker inspect "$1" --format '{{index .Config.Labels "expertai.workspace"}}') == store-private ]] || {
    echo 'Resource ownership mismatch; refusing operation' >&2; exit 1;
  }
}
case "$command" in
  stop)
    for role in runner sessions vectors database; do
      if docker container inspect "$prefix-$role" >/dev/null 2>&1; then
        check_owner "$prefix-$role"; docker stop "$prefix-$role" >/dev/null
      fi
    done
    echo 'Private workspace stopped; data retained'; exit 0 ;;
  status)
    docker ps -a --filter "label=$label" --format '{{.Names}} {{.Status}} {{.Ports}}'; exit 0 ;;
  restart)
    if docker container inspect "$prefix-runner" >/dev/null 2>&1; then
      check_owner "$prefix-runner"; docker rm -f "$prefix-runner" >/dev/null
    fi ;;
  start) ;;
  *) echo 'Usage: bash scripts/store-workspace.sh start|restart|stop|status' >&2; exit 1 ;;
esac
umask 077
mkdir -p "$private_dir"; chmod 700 "$private_dir"
# A dedicated directory permits atomic token replacement without stale bind inodes.
credential_dir="$private_dir/credentials"
mkdir -p "$credential_dir"; chmod 700 "$credential_dir"
previous_token=/home/ubuntu/.config/hedge/store-access-token
if [[ ! -f "$credential_dir/token" && -f "$previous_token" && -O "$previous_token" && $(stat -c %a "$previous_token") == 600 ]]; then
  cp "$previous_token" "$credential_dir/token"; chmod 600 "$credential_dir/token"
fi
if [[ -e "$credential_dir/token" ]] && [[ ! -f "$credential_dir/token" || ! -O "$credential_dir/token" || $(stat -c %a "$credential_dir/token") != 600 ]]; then
  echo 'Workspace token must be an owned mode-0600 file' >&2; exit 1
fi
image=$(docker image inspect hedge-store-models:local --format '{{.Id}}')
for net in private ui; do
  if ! docker network inspect "$prefix-$net" >/dev/null 2>&1; then
    options=(); if [[ "$net" == private ]]; then options=(--internal); fi
    docker network create --label "$label" "${options[@]}" "$prefix-$net" >/dev/null
  elif [[ $(docker network inspect "$prefix-$net" --format '{{index .Labels "expertai.workspace"}}') != store-private ]]; then
    echo 'Network ownership mismatch' >&2; exit 1
  fi
done
ensure() {
  local role=$1; shift
  if docker container inspect "$prefix-$role" >/dev/null 2>&1; then
    check_owner "$prefix-$role"; docker start "$prefix-$role" >/dev/null
  else
    docker run -d --name "$prefix-$role" --label "$label" "$@" >/dev/null
  fi
}
# Volumes are uniquely scoped and are deliberately not removed by stop.
for volume in postgres qdrant sessions; do
  if ! docker volume inspect "$prefix-$volume" >/dev/null 2>&1; then
    docker volume create --label "$label" "$prefix-$volume" >/dev/null
  elif [[ $(docker volume inspect "$prefix-$volume" --format '{{index .Labels "expertai.workspace"}}') != store-private ]]; then
    echo 'Volume ownership mismatch' >&2; exit 1
  fi
done
ensure database --network "$prefix-private" --network-alias database --memory 256m --cpus 1 \
  --mount "type=volume,source=$prefix-postgres,target=/var/lib/postgresql/data" \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=hedge_store_workspace \
  postgres:16.9-alpine@sha256:7c688148e5e156d0e86df7ba8ae5a05a2386aaec1e2ad8e6d11bdf10504b1fb7
ensure vectors --network "$prefix-private" --network-alias vectors --memory 256m --cpus 1 \
  --mount "type=volume,source=$prefix-qdrant,target=/qdrant/storage" \
  qdrant/qdrant:v1.18.2@sha256:75eab8c4ba42096724fdcfde8b4de0b5713d529dde32f285a1f86fdcb2c9e50c
ensure sessions --network "$prefix-private" --network-alias sessions --memory 64m --cpus 0.5 \
  --mount "type=volume,source=$prefix-sessions,target=/data" \
  valkey/valkey:8.1.3-alpine@sha256:d827e7f7552cdee40cc7482dbae9da020f42bc47669af6f71182a4ef76a22773 \
  valkey-server --appendonly yes
for ((attempt=0; attempt<30; attempt++)); do
  if docker exec "$prefix-database" pg_isready -U postgres -d hedge_store_workspace >/dev/null 2>&1; then break; fi
  sleep 1
done
ensure runner --network "$prefix-private" --network "$prefix-ui" -p 127.0.0.1:8098:8091 \
  --user "$(id -u):$(id -g)" --memory 1280m --cpus 1 --read-only --tmpfs /tmp:rw,size=64m \
  --mount "type=bind,source=$repo,target=/repo,readonly" \
  --mount "type=bind,source=$credential_dir,target=/credentials,readonly" \
  --mount "type=bind,source=$private_dir,target=/bootstrap,readonly" \
  -e DATABASE_URL=postgresql://postgres@database/hedge_store_workspace \
  -e VALKEY_SESSION_URL=redis://sessions:6379/0 -e RASA_ENABLED=false \
  -e "HEDGE_STORE_ID=$store_id" \
  -e STORE_PLAYGROUND_E5=true -e EMBEDDING_MODEL=/opt/e5-model \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 -e OMP_NUM_THREADS=1 -e TOKENIZERS_PARALLELISM=false \
  "$image" -m uvicorn scripts.store_v1_workspace:app --host 0.0.0.0 --port 8091
printf '%s\n' 'Private durable Store workspace: http://127.0.0.1:8098 (startup may take a moment)'
