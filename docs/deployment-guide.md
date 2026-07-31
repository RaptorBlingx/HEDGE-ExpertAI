# Deployment Guide

> Current status: this repository is a production-hardening candidate. Do not
> describe a deployment as production-ready until the Release 3 gates in the
> traceability matrix have retained evidence.

## Supported target

- Docker Engine 27+ with Docker Compose v2.24+
- Linux amd64 or arm64
- 8 GB RAM minimum; 16 GB recommended when Rasa and local generation run together
- 20 GB free disk plus explicit capacity for PostgreSQL backups, Qdrant snapshots,
  model caches, and retained logs
- externally managed TLS certificates and an OIDC provider for production

The production profile intentionally limits local-model concurrency to one and
keeps operational queues bounded by container resource limits. Re-run the load
and soak gates on the actual target node before changing those limits.

## Local validation stack

```bash
cp .env.example .env
docker compose config --quiet
docker compose build
docker compose up -d
docker compose exec ollama ollama pull qwen3.5:2b
curl -X POST http://127.0.0.1:8004/api/v2/ingestion/runs
docker compose ps
```

The ingestion trigger is asynchronous. A run is complete only when
`GET /api/v2/ingestion/runs/latest` reports `completed` and all derived-index
outbox operations have succeeded. `degraded` is not an acceptable readiness
state: `/ready` returns HTTP 503 whenever a required dependency is unavailable.

## Production preflight

Create a production-specific environment file outside version control. At a
minimum it must provide:

```dotenv
APP_ENV=production
CORS_ALLOWED_ORIGINS=https://apps.example.org
TRUST_PROXY_HEADERS=true
TRUSTED_PROXY_IPS=10.0.0.0/24
ENABLE_HSTS=true
ENABLE_RBAC=true
OAUTH_ENABLED=true
OAUTH_ISSUER=https://identity.example.org/realms/hedge
OAUTH_AUDIENCE=hedge-expert-api
OAUTH_CLIENT_ID=hedge-expert-api
OAUTH_JWKS_URL=https://identity.example.org/realms/hedge/protocol/openid-connect/certs
RATE_LIMIT_REQUIRED=true
POSTGRES_PASSWORD=<non-default secret>
DATABASE_URL=postgresql://hedge:<url-encoded-secret>@postgres:5432/hedge
```

`OAUTH_SHARED_SECRET`, wildcard/non-HTTPS origins, permissive rate limiting,
default database passwords, and absent JWKS configuration are rejected at
gateway startup when `APP_ENV=production`.

Validate the merged configuration before rollout:

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml config --quiet
```

The overlay removes host port publishing from PostgreSQL, Valkey, Qdrant,
Ollama, mock ingestion, and internal application services. Only the loopback
gateway remains published unless the TLS profile is enabled. Application
containers run as non-root with dropped capabilities, read-only root
filesystems, bounded process counts, and writable `/tmp` tmpfs mounts.

## TLS and renewal

For production, prefer an externally managed load balancer or ingress that
already renews certificates and forwards only to `127.0.0.1:8080`. Preserve the
client address only from a proxy range listed in `TRUSTED_PROXY_IPS`.

The optional nginx profile is suitable when certificate files are supplied to
the container by the deployment platform. The production overlay sets
`REQUIRE_EXTERNAL_TLS=true`; it will not generate a self-signed certificate.
After the platform renews a mounted certificate, reload nginx with:

```bash
docker compose exec nginx nginx -s reload
```

The v1 and v2 SSE routes have buffering disabled and a bounded 310-second proxy
timeout. Browser query-string API keys are unsupported; use same-origin OIDC or
the widget `getAccessToken` callback.

## Rollout and rollback

1. Back up PostgreSQL and create a Qdrant snapshot.
2. Apply reversible SQL migrations before starting new application containers.
3. Build immutable images and record their digests and SBOMs.
4. Start dependencies, then workers, internal APIs, gateway, and edge proxy.
5. Require HTTP 200 from every `/ready` endpoint before routing traffic.
6. Trigger a full derived-index rebuild into a new versioned collection.
7. Promote only after the indexed count matches the active PostgreSQL catalogue.

```bash
curl -X POST http://127.0.0.1:8080/api/v2/index/rebuild \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"collection_name":"hedge_apps_v2_20260731"}'
```

Rollback application containers by digest. Roll back the derived index without
rewriting data by promoting a previously validated versioned collection:

```bash
curl -X POST http://127.0.0.1:8080/api/v2/index/promote \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"collection_name":"hedge_apps_v2_previous"}'
```

Never attach a newer Qdrant image directly to an older in-place data volume.
Follow supported intermediate upgrades or rebuild the derived collection from
PostgreSQL, validate it, and atomically switch the alias.

## Backup and restore acceptance

PostgreSQL is authoritative. Use encrypted `pg_dump --format=custom` backups
with off-node retention. Qdrant snapshots reduce recovery time but do not
replace the PostgreSQL backup. Preserve the Valkey queue volume or RDB export so
unacknowledged ingestion deliveries survive a queue restart; cache/session
Valkey data is disposable.

The repository provides encrypted, fail-fast backup and isolated restore tools.
The passphrase is read from a file and is never accepted on the command line:

```bash
install -d -m 0700 /srv/hedge-backups
BACKUP_OUTPUT_DIR=/srv/hedge-backups \
BACKUP_PASSPHRASE_FILE=/run/secrets/hedge_backup_passphrase \
  ./scripts/backup.sh

BACKUP_PASSPHRASE_FILE=/run/secrets/hedge_backup_passphrase \
  ./scripts/restore_drill.sh /srv/hedge-backups/20260731T122028Z
```

Each set contains AES-256-CBC/PBKDF2-encrypted PostgreSQL, Qdrant, and Valkey
artifacts, a privacy-safe manifest, and SHA-256 checksums. The restore script
verifies the checksums, decrypts into a mode-0700 temporary directory, restores
all three stores into disposable isolated containers, compares authoritative
catalogue/vector/queue counts, and removes those containers afterward. Qdrant
must use the same supported minor release as the snapshot.

A restore drill passes only when it uses isolated temporary instances and
verifies:

- schema migration versions and row counts;
- active catalogue payload checksums and revision history;
- pending/failed outbox entries can be replayed;
- the Qdrant snapshot count matches the active searchable catalogue;
- search succeeds after rebuilding Qdrant solely from PostgreSQL;
- no live volume, alias, or database was overwritten during the drill.

Repository tooling and a local 120-record restore drill are implemented.
Scheduling, off-node replication, encryption-key custody/rotation, backup
retention, alerting, and retained target-environment drill evidence remain
deployment responsibilities and Release 3 gates.

## Operational checks

```bash
docker compose ps
curl -fsS http://127.0.0.1:8080/live
curl -fsS http://127.0.0.1:8080/ready
curl -fsS http://127.0.0.1:8080/metrics
docker compose logs --since=15m gateway chat-intent expert-recommend discovery-ranking
```

Logs must not include message text, access tokens, raw session identifiers, or
quarantined source payloads. Retain event-level pseudonymous KPI data for no
more than 30 days and aggregates thereafter. Consented qualitative transcripts
require a separate consent record, encryption, restricted access, expiry, and
deletion support.

The daily `apply-data-retention` Celery task transactionally aggregates expired
KPI events without session hashes or App IDs, deletes their raw impressions and
cascaded events, and hard-deletes expired consented transcripts. PostgreSQL
migrations run once under an advisory lock before database-dependent services
start.

## Troubleshooting

| Symptom | Required check |
|---|---|
| Discovery remains unready | PostgreSQL reachability, Qdrant alias, model-cache permissions, pinned model revision |
| Ingestion retries forever | quarantine errors, outbox `last_error`, worker queue health, derived-index readiness |
| Admin route returns 401/403 | issuer, audience, JWKS reachability, token expiry, configured role mapping |
| Public route returns 503 | Valkey fail-closed rate limiter or a required downstream dependency |
| SSE arrives in one block | edge buffering for both `/api/v1/chat/stream` and `/api/v2/chat/stream` |
| Qdrant cannot open a volume | restore the old image and perform supported intermediate upgrades, or rebuild from PostgreSQL |
