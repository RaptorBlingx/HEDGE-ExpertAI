# HEDGE-ExpertAI Architecture

## Authority and derived state

PostgreSQL is the sole durable authority for catalogue revisions, ingestion runs, indexing outbox records, corpus manifests, recommendation impressions/events and consented research records. Qdrant is a rebuildable dense index. Valkey cache holds 30-minute dialogue sessions, cache entries and distributed limiter buckets; the separate Valkey queue uses AOF for Celery delivery.

```text
Widget / validation console
          |
      Gateway v2  ---- OIDC roles (administration/analytics only)
          |
      Chat Intent ---- Valkey session state ---- PostgreSQL impressions/events
          |
   Expert Recommend ---- Ollama/Qwen (validated output only)
          |
  Discovery & Ranking ---- PostgreSQL FTS (independent candidates)
          |              \\ Qdrant/E5 (independent candidates)
          |                 -> weighted reciprocal-rank fusion
          |
  PostgreSQL catalogue <---- transactional ingestion API/worker/scheduler
          |                              |
     indexing outbox --------------------+
```

## Ingestion invariants

1. Every source record is parsed as strict `AppMetadataV2` and its ontology URIs are checked against the reviewed registry. Invalid records go to quarantine with structured errors.
2. The current catalogue revision and indexing outbox entry are committed in one PostgreSQL transaction. A checksum never suppresses a failed outbox retry.
3. The worker sends revisioned upsert/delete operations to Qdrant. Only successful delivery sets `searchable_at`.
4. Complete snapshots retire missing apps and enqueue tombstone deletes. Qdrant can be rebuilt entirely from active PostgreSQL rows.
5. New physical collections are populated and count-validated before `hedge_apps_current` is atomically promoted. Existing volumes are never opened in-place across unsupported upgrade gaps.

Rasa is an NLU-only dependency in the production and deterministic acceptance
profiles. It performs multilingual intent/entity parsing; `chat-intent` retains
deterministic dialogue policy, context merge/reset behavior, and a circuit-broken
local fallback. The fallback is not counted as multilingual KPI evidence.

## Search and explanation

PostgreSQL full-text search and Qdrant dense search retrieve candidates independently. Weighted reciprocal-rank fusion combines ranks, avoiding the false assumption that lexical and cosine scores are probabilities. Typed filters apply to both branches; semantic boosts are bounded and provenance-aware. Public responses expose only `high`, `medium` or `low` relevance.

The E5 model uses `query:` and `passage:` prefixes and is pinned to an audited repository revision. The explanation layer receives only ordered retrieval results. It treats the query and metadata as untrusted delimited data, removes hidden-reasoning tags across stream chunks, verifies all titles and ordering, and falls back to deterministic localized evidence text on any validation failure.

## Conversation and streaming

Rasa is NLU-only. Application code owns deterministic policy and authoritative state: locale, intent, concepts, filters, recent impression/results and turn number. Refinements merge filters; new searches and resets clear prior topic context intentionally.

SSE v2 events are `stage`, `recommendations`, `explanation_delta`, `complete` and `problem`. Ranked results are emitted immediately after retrieval. Explanation deltas begin only after the full narrative has passed grounding validation; no chain of thought or fabricated client stage is emitted.

## Deployment profiles

The development Compose file binds internal dependencies to loopback and includes explicitly synthetic fixtures. `docker-compose.production.yml` adds read-only application filesystems, dropped capabilities, non-root images, bounded processes and fail-closed gateway configuration. Liveness checks process survival; readiness returns HTTP 503 when required dependencies or first ingestion state are unavailable.

The target remains an 8–16 GB single node. Production readiness is not claimed until the retained gates in `docs/traceability-matrix.md` pass.
