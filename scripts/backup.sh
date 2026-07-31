#!/bin/sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
backup_root=${BACKUP_OUTPUT_DIR:-}
passphrase_file=${BACKUP_PASSPHRASE_FILE:-}
qdrant_url=${QDRANT_BACKUP_URL:-http://127.0.0.1:6333}
qdrant_alias=${QDRANT_BACKUP_ALIAS:-hedge_apps_current}

case "$backup_root" in
    /*) ;;
    *) echo "BACKUP_OUTPUT_DIR must be an absolute path" >&2; exit 2 ;;
esac
case "$backup_root" in
    /|/home|/var|/tmp) echo "BACKUP_OUTPUT_DIR is too broad" >&2; exit 2 ;;
esac
if [ ! -f "$passphrase_file" ] || [ ! -s "$passphrase_file" ]; then
    echo "BACKUP_PASSPHRASE_FILE must identify a non-empty secret file" >&2
    exit 2
fi

umask 077
mkdir -p "$backup_root"
staging=$(mktemp -d "$backup_root/.hedge-backup.XXXXXX")
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
final_dir="$backup_root/$timestamp"
workers_paused=false

cleanup() {
    if [ "$workers_paused" = true ]; then
        (cd "$repo_dir" && docker compose unpause metadata-worker metadata-scheduler) >/dev/null 2>&1 || true
    fi
    if [ -d "$staging" ]; then
        rm -rf -- "$staging"
    fi
}
trap cleanup EXIT HUP INT TERM

encrypt_file() {
    source_file=$1
    encrypted_file="$source_file.enc"
    openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
        -pass "file:$passphrase_file" -in "$source_file" -out "$encrypted_file"
    rm -- "$source_file"
}

cd "$repo_dir"
docker compose exec -T postgres sh -c \
    'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
    >"$staging/postgres.dump"
catalogue_count=$(docker compose exec -T postgres sh -c \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM catalog_apps WHERE active"' \
    | tr -d '\r')
encrypt_file "$staging/postgres.dump"

alias_response=$(curl -fsS "$qdrant_url/aliases")
qdrant_collection=$(printf '%s' "$alias_response" | jq -er \
    --arg alias "$qdrant_alias" '.result.aliases[] | select(.alias_name == $alias) | .collection_name')
snapshot_response=$(curl -fsS -X POST \
    "$qdrant_url/collections/$qdrant_collection/snapshots")
snapshot_name=$(printf '%s' "$snapshot_response" | jq -er '.result.name')
snapshot_checksum=$(printf '%s' "$snapshot_response" | jq -er '.result.checksum')
curl -fsS \
    "$qdrant_url/collections/$qdrant_collection/snapshots/$snapshot_name" \
    -o "$staging/qdrant.snapshot"
printf '%s  %s\n' "$snapshot_checksum" "$staging/qdrant.snapshot" | sha256sum -c - >/dev/null
qdrant_count=$(curl -fsS \
    "$qdrant_url/collections/$qdrant_collection/points/count" \
    -H 'Content-Type: application/json' -d '{"exact":true}' | jq -er '.result.count')
curl -fsS -X DELETE \
    "$qdrant_url/collections/$qdrant_collection/snapshots/$snapshot_name" >/dev/null
encrypt_file "$staging/qdrant.snapshot"

running_services=$(docker compose ps --status running --services)
if printf '%s\n' "$running_services" | grep -qx metadata-worker; then
    docker compose pause metadata-worker >/dev/null
    workers_paused=true
fi
if printf '%s\n' "$running_services" | grep -qx metadata-scheduler; then
    docker compose pause metadata-scheduler >/dev/null
    workers_paused=true
fi
docker compose exec -T valkey-queue valkey-cli SAVE >/dev/null
valkey_keys=$(docker compose exec -T valkey-queue valkey-cli DBSIZE | tr -d '\r')
docker compose exec -T valkey-queue tar -C /data -cf - . >"$staging/valkey-queue.tar"
encrypt_file "$staging/valkey-queue.tar"

jq -n \
    --arg created_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg qdrant_collection "$qdrant_collection" \
    --arg qdrant_snapshot "$snapshot_name" \
    --argjson catalogue_count "$catalogue_count" \
    --argjson qdrant_count "$qdrant_count" \
    --argjson valkey_keys "$valkey_keys" \
    '{schema_version:"1.0", created_at:$created_at, encryption:"AES-256-CBC/PBKDF2-SHA256/200000", PostgreSQL:{active_catalogue_count:$catalogue_count}, Qdrant:{collection:$qdrant_collection,snapshot:$qdrant_snapshot,point_count:$qdrant_count}, Valkey:{queue_key_count:$valkey_keys}}' \
    >"$staging/manifest.json"
(cd "$staging" && sha256sum manifest.json postgres.dump.enc qdrant.snapshot.enc valkey-queue.tar.enc >SHA256SUMS)

if [ -e "$final_dir" ]; then
    echo "backup destination already exists: $final_dir" >&2
    exit 1
fi
mv -- "$staging" "$final_dir"
staging=
echo "encrypted backup completed: $final_dir"
