# Configuration Reference

The checked-in `.env.example` is the authoritative development template.
Production values belong in a deployment-managed secret/environment source and
must never be committed.

## Authoritative and operational stores

| Variable | Development default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql://hedge:hedge-dev-only@postgres:5432/hedge` | PostgreSQL catalogue, revisions, outbox, provenance, impressions, events, consent records |
| `POSTGRES_DB` | `hedge` | Bootstrap database name |
| `POSTGRES_USER` | `hedge` | Bootstrap database role |
| `POSTGRES_PASSWORD` | `hedge-dev-only` | Development-only bootstrap password; rejected in production |
| `VALKEY_SESSION_URL` | `redis://valkey-cache:6379/0` | 30-minute dialogue state |
| `VALKEY_CACHE_URL` | `redis://valkey-cache:6379/1` | Revision-namespaced search cache |
| `VALKEY_RATE_LIMIT_URL` | `redis://valkey-cache:6379/2` | Distributed public rate-limit buckets |
| `VALKEY_QUEUE_URL` | `redis://valkey-queue:6379/0` | Persistent Celery broker/result transport |
| `REDIS_URL` | cache DB 0 | One-release compatibility alias only |

PostgreSQL is authoritative. Qdrant is a rebuildable derived index. Cache and
session Valkey data may be discarded; the queue uses AOF persistence.

## Retrieval and generation

| Variable | Default | Purpose |
|---|---|---|
| `QDRANT_HOST` / `QDRANT_PORT` | `qdrant` / `6333` | Derived vector service |
| `QDRANT_COLLECTION_VERSION` | `v2` | Bootstrap physical collection version |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | Eight-language dense encoder |
| `EMBEDDING_MODEL_REVISION` | `614241f622f53c4eeff9890bdc4f31cfecc418b3` | Audited model revision; do not use `main` |
| `RRF_K` | `60` | Reciprocal-rank constant |
| `RRF_DENSE_WEIGHT` | `0.55` | Dense rank contribution; requires evaluation approval before change |
| `RRF_LEXICAL_WEIGHT` | `0.45` | PostgreSQL FTS rank contribution |
| `SEMANTIC_BOOST_MAX` | `0.05` | Maximum bounded semantic boost |
| `SEARCH_CACHE_TTL_SECONDS` | `300` | Derived search-cache TTL |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Local generation endpoint |
| `OLLAMA_MODEL` | `qwen3.5:2b` | Deployment model identifier |
| `OLLAMA_TIMEOUT` | `180` | Generation timeout in seconds |
| `OLLAMA_THINK` | `false` | Hidden reasoning is disabled and stripped defensively |

Every E5 query and passage is encoded with the model-required prefix. Changing
the model or revision requires a complete new collection and alias promotion.

## Multilingual NLU

| Variable | Default | Purpose |
|---|---|---|
| `RASA_ENABLED` | `false` locally / `true` in production and E2E overlays | Use Rasa for NLU only |
| `RASA_URL` | `http://rasa:5005` | Rasa parse endpoint |
| `RASA_TIMEOUT` | `5` | Parse timeout |
| `RASA_CONFIDENCE_THRESHOLD` | `0.60` | Minimum accepted Rasa confidence |
| `RASA_SHADOW_MODE` | `false` | Compare without selecting Rasa output |
| `RASA_CIRCUIT_OPEN_SECONDS` | `60` | Backoff after repeated NLU failure |

The application owns dialogue policy and session context. Supported locales are
fixed to `en`, `de`, `fr`, `es`, `it`, `nl`, `pt`, and `tr`.

## Ingestion and service routing

| Variable | Default | Purpose |
|---|---|---|
| `MOCK_API_URL` | `http://mock-api:9000` | Synthetic fixture source |
| `HEDGE_API_URL` | empty | Future real-store endpoint; real calls remain out of scope |
| `INGEST_INTERVAL_SECONDS` | `7200` | Scheduler interval |
| `CHAT_INTENT_URL` | `http://chat-intent:8001` | Gateway chat target |
| `EXPERT_RECOMMEND_URL` | `http://expert-recommend:8002` | Recommendation target |
| `DISCOVERY_RANKING_URL` | `http://discovery-ranking:8003` | Retrieval/index target |
| `METADATA_INGEST_URL` | `http://metadata-ingest:8004` | Administrative ingestion target |

`HEDGE_API_URL` does not enable a guessed legacy mapping. The adapter accepts
only the provisional v2 fixture contract until the real API schema and data
rights are approved.

## Public security boundary

| Variable | Development default | Production rule |
|---|---|---|
| `APP_ENV` | development | Must be `production` to enable fail-closed startup validation |
| `CORS_ALLOWED_ORIGINS` | `*` | Explicit HTTPS origins only |
| `TRUST_PROXY_HEADERS` | `false` | Enable only with `TRUSTED_PROXY_IPS` set to actual proxy CIDRs |
| `ENABLE_HSTS` | `false` | Must be true behind validated TLS |
| `ENABLE_RBAC` | `false` | Must be true |
| `RATE_LIMIT_REQUIRED` | `false` | Must be true; Valkey failure then returns 503 |
| `OAUTH_ENABLED` | `false` | Must be true |
| `OAUTH_ISSUER` | empty | HTTPS issuer required |
| `OAUTH_AUDIENCE` | `hedge-expert-api` | Expected token audience |
| `OAUTH_CLIENT_ID` | `hedge-expert-api` | Client-specific role mapping |
| `OAUTH_JWKS_URL` | empty | HTTPS JWKS required |
| `OAUTH_SHARED_SECRET` | empty | Test-only and forbidden in production |
| `RBAC_ADMIN_ROLES` | `admin,administrator` | Ingestion/reindex authority |
| `RBAC_ANALYST_ROLES` | `analyst,admin` | Analytics/quarantine authority |

Anonymous chat, search, catalogue detail, event submission, and session deletion
remain public and rate-limited. Ingestion, reindex, quarantine, and analytics are
role protected. Browser query-string API keys are not supported.

## Production validation

At gateway startup, `APP_ENV=production` rejects default passwords, permissive
origins, disabled HSTS/RBAC/OIDC/rate limiting, non-HTTPS issuer/JWKS URLs, and
shared-secret JWT verification. Validate both Compose files before rollout:

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml config --quiet
```

The production overlay removes host publishing for internal services and adds
non-root/read-only/capability/process hardening to application containers. See
the deployment guide and traceability matrix for gates that still require
target-environment evidence.
