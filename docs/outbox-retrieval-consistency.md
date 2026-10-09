# Outbox recovery and authoritative retrieval

Implemented on the local Store v1 integration branch. This slice reuses the
existing schema, outbox, services and stable vector IDs; no migration or dependency
was added. It does not enable Store v1 ingestion, public indexing, or retrieval.

## Delivery and recovery

- The worker claims one operation immediately before sending it. PostgreSQL
  `FOR UPDATE SKIP LOCKED` prevents simultaneous claims; abandoned `processing`
  claims become reclaimable after **180 seconds**. Completion/failure must match
  the claim's `updated_at` token, so late workers cannot acknowledge a new lease.
- Automatic delivery stops after **10 attempts**. Payloads and errors remain in
  the existing outbox. A final-attempt crash becomes an exhausted `failed` row
  when its lease expires and the next replay scans it. No failed work is deleted.
- Latest-ingestion status includes `outbox.outstanding` and `outbox.exhausted`;
  replay task results include these counts too. Exhaustion logs an error and
  subsequent ingestion reports partial completion. Monitor exhausted work and
  backlog age; lexical availability does not mean the vector index is healthy.
- Inspect retained `indexing_outbox` IDs, App revisions and errors through your
  approved database administration workflow. After fixing the underlying fault,
  an administrator can release one exhausted
  row through the existing endpoint:
  `POST /api/v2/ingestion/outbox/replay?outbox_id=ID`. It returns 409 unless that
  row is an exhausted failure. Without the query parameter, replay processes
  only due/reclaimable work. Explicit recovery resets its retry budget but keeps
  its payload/error until successful delivery; timestamp fencing survives resets.

Recovery HTTP access is always administrative, including with RBAC disabled.
Use an admin-role Bearer token or `X-API-Key` at the gateway. The existing
`GATEWAY_API_KEY` must also be provisioned to metadata-ingest for the internal
hop; direct ingestion/replay requests require that key. An empty key disables
these HTTP mutations with 503. Keep metadata-ingest private (the production
overlay removes its host port) and treat the shared key as an administrative
credential. Scheduled Celery recovery remains independent of HTTP authentication.

Delivery is at least once. A completed Qdrant write followed by worker loss or
lost acknowledgement is replayed. A successful HTTP status alone is insufficient:
only an integer `applied` acknowledgement of 0 or 1 completes the single operation.
Zero means an obsolete/nonapplicable operation was safely skipped.

## Index and publication boundary

The indexer checks current PostgreSQL revision, synthetic profile, publication
state and payload checksum. Encoding happens outside the lock; the indexer
rechecks under the App row lock and holds it through the synchronous Qdrant write.
Catalogue mutation and index writes for that App therefore serialize. Old/future
operations cannot replace the current revision, and an old delete cannot remove
an App that has reappeared. Upserts and deletes request `wait=True`, strong write
ordering, and require a completed result. Qdrant client timeout is 10 seconds;
App lock acquisition is bounded to 5 seconds. Lock/retry values remain simple
internal limits rather than new tuning configuration.

Unversioned live-alias batch writes are refused. The legacy index route accepts
only registered, active synthetic v2 Apps and uses the same revisioned boundary;
legacy search/detail routes also resolve current PostgreSQL metadata. Rebuilds
write actual catalogue revisions instead of inventing revision 1.

Store source rows remain excluded by profile from the outbox, public reads,
lexical retrieval, index operations and rebuilds. Their future public model and
publication contract still require the gates in the [baseline](integration-baseline.md).

## Retrieval during lag or failure

PostgreSQL lexical retrieval no longer waits for `searchable_at`, which now
records vector delivery only. Vector/embedding failures leave lexical results
usable, including before the first successful vector delivery. Vector startup
failure does not prevent process startup; readiness requires PostgreSQL and
reports `qdrant: false` while keeping service status `ok`/HTTP 200 when PostgreSQL
is healthy. This also keeps gateway health aggregation from excluding usable
lexical retrieval. PostgreSQL failure still returns HTTP 503. Cache I/O has a
one-second connection/read timeout.

Vectors and caches supply ranked ID/revision references. One PostgreSQL read
hydrates current eligible synthetic records, rechecks typed filters, and rejects
missing, withdrawn or mismatched revisions before fusion. Cached payloads are
never returned. Changed cache references cause fresh retrieval; malformed entries
are ignored. The new cache namespace avoids old payload-cache formats. Degraded,
stale or empty rankings are not cached, so recovery can take effect immediately.

The consistency boundary is the final PostgreSQL read, not an indefinite promise
about publication after a response or throughout an explanation stream. PostgreSQL
failure fails closed. Vector recall can temporarily fall back to lexical recall;
this is not a search-quality KPI claim. Candidate overfetch remains bounded and
normal ranking caches retain their existing TTL. Alias promotion/rollback remains
count-validated administration, not an atomic catalogue-wide snapshot or a
multi-node recovery drill. Stale derived entries after manual rollback or uncertain
remote completion are still rejected by the authoritative retrieval check; replay
or rebuild restores vector coverage. Production operator/alerting ownership and
fault/load validation remain pending.

## Verification

Focused regressions use disposable PostgreSQL 16.9 and Qdrant 1.18.2 with no host
ports or demo volumes. Embeddings are deterministic test vectors, not downloaded
E5 models or evidence of LLM/retrieval quality. They cover abandoned/final claims,
claim races and late acknowledgements, explicit recovery, worker loss and lost
acknowledgement after actual Qdrant writes, revision ordering, publication
withdrawal/reappearance, row-lock serialization, stale vectors/caches, current
metadata before vector delivery, and lexical fallback. Unit tests cover malformed
acknowledgements/cache entries, fail-closed authority, legacy guards and degraded
startup/readiness. Run the new integration file with the existing guarded database
fixtures and explicit isolated `HEDGE_TEST_QDRANT_URL=http://vectors:6333`.

Final offline run: **358 unit tests**, **53 integration tests** (44 guarded
PostgreSQL/Qdrant cases plus nine existing adapter cases), and **94.10% shared
branch coverage** against the 80% gate. Ruff passed. The existing Starlette/httpx
deprecation warning remains. All six OpenAPI specifications were regenerated;
the recovery query parameter at gateway/ingestion and corrected legacy detail
description are the intentional contract deltas.
The preserved demo was not used for verification. No live migration or deployment
was performed; these checks do not establish authenticated Store acceptance.
