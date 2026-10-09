# Offline Store v1 search and recommendations

This slice exercises Store Apps through existing PostgreSQL, Qdrant, reciprocal-rank
fusion and recommendation code. It adds no endpoint, environment switch, migration,
dependency, scheduler, live ingestion or public Store result contract. Public
search/detail/list, indexing operations, rebuilds and outbox creation still default
to synthetic v2 only. The frozen demo is independent and was not used for testing.

## Explicit offline boundary

For **disposable test resources only**, call the existing Python functions
`discovery-ranking/app/indexer.py::apply_operations` and
`discovery-ranking/app/searcher_v2.py::search_apps_v2` with both `store_id` and
`collection_name`. The collection must be `hedge_store_offline_` followed by 32
lowercase hexadecimal characters (a test UUID). Missing scope or a live collection
name fails before I/O. Create/remove that collection in the test harness; no alias
is created or promoted. These arguments are absent from public request models and
HTTP handlers. The name guard is an accidental-use safeguard, not resource isolation:
the harness must supply an isolated database/network/Qdrant and avoid demo resources.

Scoped storage reads require the Store profile, matching native Store ID, local
active state and both explicit source publication flags. Index writes reuse current
revision/checksum checks and the App row lock through completed Qdrant writes.
Retrieval rehydrates candidates from PostgreSQL, validates native identity, and
rejects stale revisions or withdrawn/retired Apps. Local absence retirement remains
effective even when retained source flags are true. Lexical search works before
indexing or during vector failure; PostgreSQL failure fails closed. Offline search
bypasses Valkey entirely, leaving public caches untouched. Store rows still create
no production outbox work; tests supply explicit revisioned operations directly.

## Supported evidence

- Search text uses supplied `name`, `description`, and `provider`; `publisher`
  filtering matches the supplied provider. Unsupported taxonomy, capabilities,
  language, lifecycle, licence, protocol, deployment and semantic filters return
  no match. PostgreSQL derives Store text from those current payload fields so
  historical search documents containing README cannot expand the evidence.
- Results carry `source_profile`, local `id`, native `store_id`/`app_id`, original
  nullable descriptive fields and publication facts. Source profile/native identity
  preserve attribution to the source App; neither source language nor review status
  is asserted. Internal RRF orders candidates; the response exposes rank and retrieval
  channels, with no invented quality score, calibrated relevance band or v2 fields.
- Missing name/description/provider stay missing. Apps with no searchable text are
  retained in PostgreSQL but skipped for indexing/recommendations. Versions are not
  selected or invented. No canonical navigation URL is asserted.
- README (including HTML), registry paths, and embedded Dataspace descriptions are
  excluded from search, vector payloads and recommendation results. Name, description
  and provider remain untrusted strings: explanations bound and escape HTML/Markdown
  quotations and identify the actual source fields. Both ordinary and streamed v2
  recommendations use the same deterministic Store narrative, without an LLM call,
  translation, inferred capability or applicability claim. Synthetic generation and
  existing synthetic contracts remain unchanged.
- Store Apps are the entities. No Assets are fetched, joined, enriched or recommended.

## Verification and remaining gates

`tests/fixtures/store-v1/offline-recommendations.json` contains invented records
representing observed nullable/millisecond/empty-version/HTML/embedded-JSON formats,
not copied private authenticated records. The offline integration tests connect
normalization and reconciliation to PostgreSQL, actual disposable Qdrant writes,
search and the existing normal/streaming recommendation orchestrator. Only the
service transport seam and embeddings/LLM are replaced in tests; embeddings are
constant deterministic vectors, and Store explanations do not invoke generation.
These checks establish wiring and safety, not retrieval relevance or live-model KPIs.

Run with the existing guarded disposable database named `hedge_phase1_test` and
`HEDGE_TEST_QDRANT_URL=http://vectors:6333` on an isolated test network:

```sh
python -m pytest tests/integration/test_store_v1_recommendations.py \
  tests/integration/test_index_consistency.py \
  tests/integration/test_catalogue_snapshot.py \
  tests/integration/test_store_v1_persistence.py -q
```

Coverage includes native collisions across Stores, missing fields, unsupported
filters, HTML/instruction-bearing text, private/unknown publication, vector lag and
failure, authoritative database failure, stale writes, withdrawal/reappearance,
absence retirement, concurrency and public-result isolation. Tests apply migrations
only inside their temporary schema in that explicitly disposable database.

Final offline verification: **432 unit tests + 100 integration tests passed**
(including 26 new Store recommendation cases), with **97.49% shared branch
coverage**. Ruff and whitespace checks passed; all six regenerated OpenAPI
files were byte-identical. One existing Starlette/httpx deprecation warning remains.
Disposable resources used PostgreSQL 16.9 and Qdrant 1.18.2 without published ports
or demo volumes. These results do not establish Store access or quality KPIs.

Before live/public use, HEDGE still needs to confirm backend credential acquisition,
visibility/`active` semantics, catalogue coverage and corpus permissions. An approved
public result/UI/navigation contract and measured real-corpus quality remain separate
work. A single observed App/Asset `@id` match does not authorize universal enrichment.
See the [integration baseline](integration-baseline.md) for those decisions.
