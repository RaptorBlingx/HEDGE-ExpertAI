# Store M2M authentication and automatic English preparation

Local implementation on `perf/prepared-store-discovery`, based on `84f93fe`,
19 October 2026. No push, merge, deployment, upstream mutation or Jira change.
English is the current evaluation language; Turkish improvements are deferred.

## Actual access

The supplied realm's public OIDC discovery returned 200 with the matching issuer,
client-credentials grant and client-secret-post/basic methods. Both advertised
client-secret methods, using the supplied `AAMST` credential, returned **401**:
`unauthorized_client`, `Invalid client or Invalid client credentials`.
The implemented backend provider independently reproduced 401. No access token
was issued, so no current authorized Store catalogue or detail fetch was achieved.
This does not establish missing Store roles: token issuance failed before Store
permissions could be tested. HEDGE must verify the client/secret in this exact realm
and backend service-account grant, then catalogue access can be revalidated.
The supplied JSON is public realm metadata, not a token or client secret.

**Zero Apps freshly synchronized.** The isolated local workspace imported the
previously authorized 12 October two-App observation, retaining its file-time
provenance. It is not today's catalogue and proves neither scope nor completeness.
Failed startup, manual and timed authentication attempts preserve that observation,
its native identities and index. Private payloads, credentials, screenshots and
complete conversations stay outside Git under
`/home/ubuntu/.local/share/hedge-store-m2m`; the earlier workspace and demo are untouched.

## Authentication and automatic synchronization

The existing read-only `HedgeApiClient` accepts exactly one authentication source:
a supplied Bearer token, externally rotated token file, or `StoreClientCredentials`.
Incoming ExpertAI user OIDC is separate. No user-list endpoint is accessed.

Client credentials use TLS-verified OIDC discovery with exact issuer matching and
a same-authority HTTPS token endpoint. Secrets are read from an owned private
regular file (symlinks rejected), sent only to the token endpoint and reread at
renewal. Access tokens stay in backend memory. A lock avoids concurrent grants;
expiry uses monotonic time with an early-renewal margin. A Store 401 invalidates
the rejected cached token and permits exactly one renewal within the original
operation budget. A 403 or failed client grant stops; no login/retry loop.
Responses are bounded, redirects/proxies disabled, and operational errors omit
bodies, credentials and chained transport errors. No refresh token is needed for
the client-credentials grant.

Reuse the existing private workspace polling/refresh, PostgreSQL reconciliation,
membership, source revisions and incremental Qdrant repair. Successful observations
prepare new/changed records; unchanged records reuse preparation and vectors.
Publication/withdrawal gates, quarantine, source-scoped availability and lexical
fallback remain. A successful array still does not establish catalogue completeness
or authorize upstream deletion. The generic synthetic Celery ingestion job/public
Store activation stays disabled; this task enables no production pipeline.

Backend settings, all empty by default:

- `HEDGE_STORE_ISSUER`: provisioned HTTPS realm issuer.
- `HEDGE_STORE_CLIENT_ID`: backend client identifier.
- `HEDGE_STORE_CLIENT_SECRET_FILE`: absolute owned mode-0600 secret file.
- Leave `HEDGE_STORE_TOKEN_FILE` empty when using client credentials.

The existing launcher supports an explicitly named isolated local workspace with
`STORE_WORKSPACE_NAME`, `STORE_WORKSPACE_DIR`, `STORE_WORKSPACE_PORT`. Default names,
labels and paths remain compatible. Only task-owned labelled resources were used.
Mount the credential directory read-only; the secret is never an environment value.
Example (contains no credential):

```sh
STORE_WORKSPACE_NAME=expertai-store-m2m \
STORE_WORKSPACE_DIR=/home/ubuntu/.local/share/hedge-store-m2m \
STORE_WORKSPACE_PORT=8094 \
HEDGE_STORE_ISSUER=https://idp.haslab-dataspace.pt/realms/hedgeiot \
HEDGE_STORE_CLIENT_ID=AAMST \
HEDGE_STORE_CLIENT_SECRET_FILE=/credentials/client-secret \
bash scripts/store-workspace.sh start
```

Default private polling remains daily (`STORE_SYNC_INTERVAL_SECONDS=86400`). A
60-second interval was used temporarily to observe failed-refresh preservation.
This is not successful freshness evidence or resolution of the proposal's two-hour
freshness target. Native Angular integration and deployed service hops remain untested.

## New/updated App explanations

Preparation version 2 automatically creates **English extractive explanations**
during the existing normalization/upsert. No per-App file, prompt, service, API,
manual authoring or LLM call is required. It selects complete purpose/capability
sentences, retains adjacent qualifications (including paragraph boundaries), and
binds every fact to its exact original field and quotation. An explicit purpose
statement can supply a task phrase and a short plain grammatical introduction;
unknown wording keeps the complete source sentence rather than inventing meaning.
Comparisons use those task phrases when available. Source content is not executed
as instructions. Heading/link/instruction-like passages are excluded from prose.

Provenance is `source_extraction`, **not human or model semantic review**. The
reader reproduces automatic preparation from current evidence before accepting it;
arbitrary prose cannot be relabelled as validated extraction. The existing sole
suitability assessor still checks source/request coverage, restrictions, negatives
and uncertainty. Explanation prose is never indexed as new evidence or used to
invent native identity, eligibility or unsupported features.

Source checksum changes replace stale prose automatically. Unchanged preparations
are reused. Startup upgrades outdated derived preparation from retained source
under row locks, without changing source revisions or observation timestamps.
Previously reviewed prose is preserved only while its source checksum and exact
quotes remain valid; subsequent source updates get automatic preparation.
Preparation-version upgrades trigger the existing scoped vector rebuild once.

This removes manual preparation as an operational dependency. It **does not match
the full paraphrasing quality of the two hand-reviewed explanations**: technical
terms remain technical; long capability lists can remain long; simple explanations
are shallow when a source supplies no explicit task boundary. Sparse/non-English
or poor source descriptions still limit useful English answers. No general semantic
translation or expert reasoning is claimed. An offline generator remains a future
quality option; the failed earlier bilingual prototype is not presented as solved.

## Practical evaluation

Actual Chromium widget, HTTP/SSE, real Rasa and pinned E5, PostgreSQL, Qdrant,
Valkey; ordinary requests make no Ollama call. A fresh task database imported only
the authorized dated source, **no manually prepared explanations**. Complete raw
answers, cards/decisions, diagnostics and screenshots are retained privately.
The adapter uses existing in-process service bridges, so measured response times
are not deployed-service or production-load measurements.

First browser pass exposed poor purpose selection and missed English comparison/
setup phrasing. General purpose ranking and existing control grammars were adjusted;
no App names or question-specific answer tables were added. Final transcripts and
measurements are in the private evaluation report. Important limitations remain:
compound, qualified aggregation requirements can return a relevant complete source
passage with no confirmed recommendation card; generic how-it-works answers can
repeat descriptive lists; automatic text is less fluent than reviewed paraphrases.
These outcomes are retained, not scored away.

Synthetic preparation scaling measures code/payload cost only. It cannot establish
recommendation quality on hundreds of real Apps. Successful live synchronization,
real lifecycle changes, authorized corpus breadth, jointly labelled retrieval
quality, and native Store UI acceptance remain blocked/unverified.

Final verification: **1,244 unit tests**, **87.50% shared branch coverage**, and
**148 disposable integration tests** passed; Ruff, shell syntax and whitespace
checks passed. An existing Starlette/httpx deprecation warning and E5 tokenizer
warning remain visible. Mocked successful client grants plus real PostgreSQL verify
new/changed automatic preparation and observation preservation after auth failure;
this is explicitly separate from the rejected live credential.

Final 13-turn actual-widget timing: median **0.282 s**, mean **0.274 s**, p95/max
**0.345 s** (request-to-render, two dated Apps, no runtime LLM). Synthetic preparation
alone, five runs per size on one CPU: median **0.0126 s / 100 Apps**, **0.0375 s /
300 Apps**, **0.2644 s / 1,000 Apps**. These latter timings exclude HTTP, database
writes, embedding/indexing and chat; they establish no recommendation-quality KPI.
