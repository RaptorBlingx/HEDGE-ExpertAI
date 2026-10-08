# Store v1 transport and outbound authentication

Implemented locally on 2026-10-08; tested with mocked HTTP and disposable
PostgreSQL. No request was made to the live Store, and no credentials were
provisioned. External facts remain those in the [integration baseline](integration-baseline.md).

## Contract and boundary

[`HedgeApiClient`](../services/metadata-ingest/app/client.py) replaces the guessed
`/api/apps` transport with the baseline's `getAllApps`, `getApp` and `getAssets`
paths. Its configured base must be credential-free HTTPS ending in `/api/v1`,
normally `https://store.haslab-dataspace.pt/backend/api/v1`; it appends only
relative endpoint paths. Native IDs are encoded as single path segments;
literal `.`/`..` segments cannot be safely addressed and are rejected.

App arrays and detail objects are validated by the existing Store normalizer,
including endpoint Store context, strict publication flags, versions and known
optional fields. Any malformed or duplicate App fails the entire transport
response rather than returning a partial list. Returned records preserve the
raw object shape for subsequent reconciliation. Detail 404 returns `None`;
200/null, wrong identities and other invalid shapes fail. Assets remain raw
object arrays without an inferred join, enrichment or public eligibility.

The client always reports `snapshot_complete=False`, including for valid nonempty
and empty arrays. HTTP success and structural validation do not prove authorization scope,
visibility coverage or completeness. Use the [reconciler](../services/metadata-ingest/app/snapshot.py)
inside its source lock; do not fetch outside the lock or override completeness
from an unverified response. Store projection/indexing separation remains as
documented in [Phase 1](store-v1-phase1.md).

## Credentials and failure handling

HEDGE's inline answer confirms a client/token supplied through its Store
Keycloak instance for backend Bearer access. It does **not** establish a grant,
token URL, issuer/audience/scopes, expiry or refresh contract. Those details
remain pending; no token acquisition, discovery or refresh flow was invented.
Store authentication is independent of incoming ExpertAI/user OIDC.

The explicit factory reads a backend token file; see the
[configuration reference](configuration-reference.md#ingestion-and-service-routing)
for settings and defaults. Token contents stay outside configuration/source;
provision a restricted file and, when deployed later, a read-only mount only into
the authorized backend. The file is reread for each HTTP attempt, allowing
external rotation. Direct backend callers may alternatively supply a string or
`SecretStr` constructor token. Exactly one source is required. Missing, oversized
or invalid tokens fail before a request; the client never exposes a token in
its representation or sanitized errors.

- TLS verification stays enabled; redirects and ambient proxy configuration
  are disabled. Credentials go only in the Authorization header, never URLs,
  frontend configuration or reused user credentials.
- 401/403 stop immediately without retry/refresh. Detail 404 is local to that
  request; it authorizes no catalogue retirement. Other terminal statuses,
  including redirects, 204 and partial-content 206, fail closed.
- Transport failures and 429/500/502/503/504 can retry within the configured
  attempt cap and shared operation time budget. Backoff is bounded. A server's
  `Retry-After` stops automatic retry with a deferred-retry error; the caller can
  retry later without this client guessing a delay or waiting indefinitely.
  Interrupted bodies are discarded before retry.
- Remaining time limits each I/O timeout, with deadline checks before attempts,
  after headers and between incoming body chunks. This is synchronous timeout
  enforcement, not a promise of exact wall-clock cancellation during DNS/TLS
  or JSON parsing. Responses require JSON media types and at most 10 MiB of
  decoded body. Duplicate object keys, NaN/Infinity literals and invalid content
  decoding fail closed; limits need review against authorized catalogue sizes.
- Exceptions include a safe category and optional HTTP status, without server
  bodies, header values or chained transport messages. Malformed responses are
  not retried or silently converted to empty arrays.

## Enablement and remaining evidence

The synthetic client remains available. The scheduled/API-triggered ingestion
task processes only the synthetic source. A nonempty `HEDGE_API_URL` returns
`status=disabled` before client creation, fetch, database work or index delivery.
There is no scheduled live Store ingestion, absence authority, public Store
indexing, frontend integration or credential mount in this slice.

Offline tests cover exact routes, headers, encoding, payload/identity contracts,
auth failures, external rotation, bounded retries, interrupted/slow responses,
size limits, credential/error safety and the job guard. Mocked transport through
isolated PostgreSQL reconciliation verifies that valid unverified arrays and
empty responses cannot retire existing Apps, and failed responses preserve data.
Verification passed: 329 unit tests (including 91 focused transport cases),
31 PostgreSQL cases (including four new HTTP/reconciliation bridge cases), and
nine existing adapter tests. Shared branch coverage was 93.87% against the 80%
gate. Ruff, whitespace, base/production Compose configuration checks and all six
byte-identical OpenAPI exports passed. One existing Starlette/httpx warning
remains. Verification used Python 3.11.15 and isolated PostgreSQL 16.9; the
preserved demo was not a test resource.

Still required from HEDGE: provisioned backend credentials, token issuance and
renewal details, access permissions, representative authenticated Apps/assets,
publication semantics, response sizes and demonstrable full catalogue coverage.
MockTransport does not validate deployed TLS, routing, actual Keycloak behavior
or a live catalogue. The separate outbox/retrieval safety gate still precedes
public Store results. No production readiness or proposal KPI is claimed.

Run focused offline transport checks with:

```sh
python -m pytest tests/unit/test_store_v1_transport.py tests/unit/test_snapshot_task.py \
  tests/integration/test_ingest_pipeline.py -q
```

The PostgreSQL bridge tests are in `tests/integration/test_catalogue_snapshot.py`;
use only the explicitly disposable database setup described in the Phase 1 notes.
