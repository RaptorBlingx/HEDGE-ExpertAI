# SCRUM-28: v2 search errors and genuine no-match results

Implemented on the issue branch from integration commit `0e33de4`. Astra audit
finding #13 describes an earlier revision; offline route-chain tests reproduced
its defects against this integration baseline before implementation.

## Contract

Chat message, recommendation query and Discovery search query accept 1–2,000
characters. Discovery previously limited queries to 500; increasing that limit
preserves existing Chat inputs without truncating or rewriting their meaning.
Dialogue-generated queries (including refinement concatenation) remain bounded
by the recommendation request validator. A derived query exceeding 2,000
characters is rejected explicitly, rather than truncated or treated as no-match.
Ranking, filtering, metadata and dialogue query construction are unchanged.

| Outcome | Non-streaming v2 response | Streaming v2 response |
|---|---|---|
| Successful retrieval, no results | 200, existing no-match message and empty Apps | Existing empty `recommendations`, no-match text, then `complete` |
| Invalid request at receiving boundary | 422, existing FastAPI validation detail | 422 before stream starts |
| Derived or downstream rejected search input | 422, safe error detail | Terminal `problem` with `status: 422` once stream starts |
| Retrieval/dependency unavailable or invalid Discovery result envelope | 503, safe error detail | Terminal `problem` with `status: 503` |
| Recommendation/Discovery HTTP request timeout, or upstream 504 | 504, safe error detail | Terminal `problem` with `status: 504` |
| Upstream stream ends without `complete` | N/A | Terminal `problem` with `status: 503` |

Established SSE framing is preserved. Once SSE headers have been sent, the HTTP
status remains 200: clients must treat a `problem` event as failure, not success.
A failure produces no subsequent `complete` and does not save a successful
assistant answer or update dialogue context. Error text does not echo upstream
response bodies. The gateway already forwards statuses and SSE events; its
existing gateway-transport failures still use 502. Service JSON errors retain
FastAPI's `detail` envelope; the gateway retains its existing error media type.

Successful search/recommendation payloads and no-match wording are unchanged.
Search input acceptance is widened; failures previously masked as successful
absence now intentionally return errors. OpenAPI exports record the new search
limit and non-streaming service availability responses. Legacy `/api/v1` routes
are unchanged; this fix targets the current `/api/v2` pipeline identified in #13.

Existing lexical fallback during vector/cache outages remains available. A
healthy authoritative lexical search can still legitimately return zero results
when vector retrieval is unavailable; loss of the authoritative catalogue path
is reported as unavailable. This change does not tune retrieval quality.

## Regression evidence and review/QA

`tests/unit/test_search_error_boundaries.py` executes FastAPI requests through
Gateway → Chat → Recommendation → Discovery, using ASGI/TestClient transports.
Discovery's real search orchestration runs with disposable catalogue/vector/cache
adapters. No running server, Store, models, database or demo is contacted.

Coverage includes the 501- and 2,000-character success boundaries, empty/2,001-
character validation, derived refinement overflow, genuine no-match, normal
nonempty results/impressions, unavailable connections, HTTP 503/504, transport
timeouts, rejected input, malformed result envelopes, catalogue failure/recovery,
vector fallback, truncated SSE and retry recovery. Both JSON and SSE paths are
checked, including public gateway forwarding. Timeouts are injected HTTPX
transport exceptions, not live network latency measurements.

For formal QA, use an approved isolated environment with controlled dependency
faults. Verify a long search is accepted; a genuine zero-result query succeeds;
a disabled Discovery or catalogue dependency yields an error; a timeout yields
504/a terminal problem; retry after recovery succeeds. Check both JSON and SSE,
and confirm failures do not appear as saved no-match answers. Do not fault the
preserved stakeholder demo or the running SCRUM-27 synthetic widget preview.
Real infrastructure/load behavior and search relevance remain outside this
retained offline evidence. Internal review and Tolga's formal QA are pending;
this document does not mark acceptance or close the Jira issue.
