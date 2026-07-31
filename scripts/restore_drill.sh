#!/bin/sh
set -eu

backup_dir=${1:-}
passphrase_file=${BACKUP_PASSPHRASE_FILE:-}
case "$backup_dir" in
    /*) ;;
    *) echo "usage: BACKUP_PASSPHRASE_FILE=/absolute/secret $0 /absolute/backup" >&2; exit 2 ;;
esac
if [ ! -d "$backup_dir" ] || [ ! -f "$backup_dir/SHA256SUMS" ]; then
    echo "backup directory or checksum manifest is missing" >&2
    exit 2
fi
if [ ! -f "$passphrase_file" ] || [ ! -s "$passphrase_file" ]; then
    echo "BACKUP_PASSPHRASE_FILE must identify a non-empty secret file" >&2
    exit 2
fi

umask 077
work_dir=$(mktemp -d)
suffix=$(date +%s)-$$
postgres_name="hedge-restore-postgres-$suffix"
qdrant_name="hedge-restore-qdrant-$suffix"
valkey_name="hedge-restore-valkey-$suffix"
postgres_image='postgres:16.9-alpine@sha256:7c688148e5e156d0e86df7ba8ae5a05a2386aaec1e2ad8e6d11bdf10504b1fb7'
qdrant_image='qdrant/qdrant:v1.18.2@sha256:75eab8c4ba42096724fdcfde8b4de0b5713d529dde32f285a1f86fdcb2c9e50c'
valkey_image='valkey/valkey:8.1.3-alpine@sha256:d827e7f7552cdee40cc7482dbae9da020f42bc47669af6f71182a4ef76a22773'

cleanup() {
    for container_name in "$postgres_name" "$qdrant_name" "$valkey_name"; do
        case "$container_name" in
            hedge-restore-*) docker rm -f "$container_name" >/dev/null 2>&1 || true ;;
        esac
    done
    rm -rf -- "$work_dir"
}
trap cleanup EXIT HUP INT TERM

(cd "$backup_dir" && sha256sum -c SHA256SUMS)
for artifact in postgres.dump qdrant.snapshot valkey-queue.tar; do
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
        -pass "file:$passphrase_file" \
        -in "$backup_dir/$artifact.enc" -out "$work_dir/$artifact"
done

expected_catalogue=$(jq -er '.PostgreSQL.active_catalogue_count' "$backup_dir/manifest.json")
expected_qdrant=$(jq -er '.Qdrant.point_count' "$backup_dir/manifest.json")
expected_valkey=$(jq -er '.Valkey.queue_key_count' "$backup_dir/manifest.json")

docker run -d --name "$postgres_name" \
    -e POSTGRES_DB=hedge_restore -e POSTGRES_USER=hedge_restore \
    -e POSTGRES_PASSWORD=restore-drill-only "$postgres_image" >/dev/null
attempt=0
until docker exec "$postgres_name" pg_isready -U hedge_restore -d hedge_restore >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    [ "$attempt" -lt 60 ] || { echo "isolated PostgreSQL did not start" >&2; exit 1; }
    sleep 1
done
docker exec -i "$postgres_name" pg_restore -U hedge_restore -d hedge_restore \
    --no-owner --no-privileges <"$work_dir/postgres.dump"
restored_catalogue=$(docker exec "$postgres_name" psql -U hedge_restore -d hedge_restore \
    -Atc 'SELECT count(*) FROM catalog_apps WHERE active')
[ "$restored_catalogue" = "$expected_catalogue" ] || {
    echo "PostgreSQL catalogue count mismatch" >&2; exit 1;
}

docker run -d --name "$qdrant_name" -p 127.0.0.1::6333 "$qdrant_image" >/dev/null
qdrant_port=$(docker port "$qdrant_name" 6333/tcp | awk -F: 'NR==1 {print $NF}')
attempt=0
until curl -fsS "http://127.0.0.1:$qdrant_port/readyz" >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    [ "$attempt" -lt 60 ] || { echo "isolated Qdrant did not start" >&2; exit 1; }
    sleep 1
done
curl -fsS -X POST \
    "http://127.0.0.1:$qdrant_port/collections/restore_drill/snapshots/upload?priority=snapshot" \
    -F "snapshot=@$work_dir/qdrant.snapshot" >/dev/null
restored_qdrant=$(curl -fsS \
    "http://127.0.0.1:$qdrant_port/collections/restore_drill/points/count" \
    -H 'Content-Type: application/json' -d '{"exact":true}' | jq -er '.result.count')
[ "$restored_qdrant" = "$expected_qdrant" ] || {
    echo "Qdrant point count mismatch" >&2; exit 1;
}

mkdir "$work_dir/valkey-data"
tar -C "$work_dir/valkey-data" -xf "$work_dir/valkey-queue.tar"
docker run -d --name "$valkey_name" --user "$(id -u):$(id -g)" \
    -v "$work_dir/valkey-data:/data" \
    "$valkey_image" valkey-server --appendonly yes >/dev/null
attempt=0
until docker exec "$valkey_name" valkey-cli ping >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    [ "$attempt" -lt 30 ] || { echo "isolated Valkey did not start" >&2; exit 1; }
    sleep 1
done
restored_valkey=$(docker exec "$valkey_name" valkey-cli DBSIZE | tr -d '\r')
[ "$restored_valkey" = "$expected_valkey" ] || {
    echo "Valkey queue key count mismatch" >&2; exit 1;
}

echo "isolated restore drill passed: PostgreSQL=$restored_catalogue Qdrant=$restored_qdrant Valkey=$restored_valkey"
