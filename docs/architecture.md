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

1. Synthetic records use strict `AppMetadataV2` and reviewed ontology validation. Store v1 uses its separate sparse, offline profile; see [mapping and reconciliation notes](store-v1-phase1.md). Invalid records go to quarantine.
2. Snapshot projection, revisions, quarantine and run statistics commit in one PostgreSQL transaction; synthetic changes also enqueue indexing operations. A checksum never suppresses a failed outbox retry.
3. The worker sends revisioned upsert/delete operations through the current-revision PostgreSQL row lock. Interrupted claims are reclaimed, late acknowledgements are fenced, and exhausted work is retained for explicit recovery. Only successful current-revision upsert delivery sets `searchable_at`; lexical retrieval does not depend on it.
4. A source lock spans fetch through reconciliation. Only complete, unquarantined snapshots retire missing Apps within that source; empty snapshots require explicit approval. Synthetic retirement/reappearance enqueue revisioned delete/upsert operations. Store rows remain outside public v2 reads/indexing.
5. New physical collections are populated and count-validated before `hedge_apps_current` is atomically promoted. Existing volumes are never opened in-place across unsupported upgrade gaps.

Rasa is an NLU-only dependency in the production and deterministic acceptance
profiles. It performs multilingual intent/entity parsing; `chat-intent` retains
deterministic dialogue policy, context merge/reset behavior, and a circuit-broken
local fallback. The fallback is not counted as multilingual KPI evidence.

## Search and explanation

PostgreSQL full-text search and Qdrant dense search retrieve candidates independently. Ranked vector/cache references are checked against current PostgreSQL eligibility, revision, metadata and filters before fusion; vector failure leaves lexical retrieval usable. See [outbox and retrieval consistency](outbox-retrieval-consistency.md). Weighted reciprocal-rank fusion combines ranks, avoiding the false assumption that lexical and cosine scores are probabilities. Typed filters apply to both branches; semantic boosts are bounded and provenance-aware. Public responses expose only `high`, `medium` or `low` relevance.

The E5 model uses `query:` and `passage:` prefixes and is pinned to an audited repository revision. Recommendation assessment is separate from retrieval: direct functional source evidence admits Apps; unresolved candidates remain explicitly unverified. Optional structured model selection can decline admitted Apps, including all of them, but cannot promote unsupported candidates or supply served factual prose. Code renders escaped, complete source quotations and retains source paths. Store extractive generation also permits search/refine abstention. See [recommendation suitability](recommendation-suitability.md) for the conservative textual boundary and acceptance limits.

## Conversation and streaming

Rasa is NLU-only. Application code owns deterministic policy and authoritative state: locale, intent, concepts, filters, recent impression/results and turn number. Refinements merge filters; new searches and resets clear prior topic context intentionally.

SSE v2 events are `stage`, `recommendations`, `explanation_delta`, `complete` and `problem`. Recommendation events are emitted after the evidence decision, with admitted `apps`, unverified `candidates` and the `decision`. Explanation deltas contain the completed source-rendered response; no unvalidated model prose or chain of thought is emitted. Retrieval failures remain terminal problem events, distinct from abstention.

## Deployment profiles

The development Compose file binds internal dependencies to loopback and includes explicitly synthetic fixtures. `docker-compose.production.yml` adds read-only application filesystems, dropped capabilities, non-root images, bounded processes and fail-closed gateway configuration. Liveness checks process survival; readiness returns HTTP 503 when required dependencies or first ingestion state are unavailable.

The target remains an 8–16 GB single node. Production readiness is not claimed until the retained gates in `docs/traceability-matrix.md` pass.
