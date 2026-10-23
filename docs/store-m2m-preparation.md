# Store M2M authentication and automatic English preparation

Latest: [finalization and integration handoff](integration-handoff-prepared-store.md) supersedes the earlier regression limitations below.

Local implementation on `perf/prepared-store-discovery`, based on `84f93fe`,
19 October 2026. No push, merge, deployment, upstream mutation or Jira change.
English is the current evaluation language; Turkish improvements are deferred.

## Actual access

The supplied `AAMST` client successfully obtained a Bearer token from the
provisioned realm using its advertised client-credentials/client-secret-post flow.
The issuer matched; issued token lifetime was 1,500 seconds. Cached reuse and a
forced local cache-expiry renewal both succeeded against real Keycloak; Store
catalogue reads succeeded before and after renewal. This was early renewal, not
waiting for a naturally expired token. Both observed App detail endpoints also succeeded. No users or asset endpoints
were accessed.

**Two Apps synchronized from the real Store on 19 October:** both current records
normalized successfully, replacing the dated bootstrap projections (two updated,
zero quarantined). Native Store/App identities were retained. Both are active and
visible. The index reached zero pending work. Subsequent automatic polls returned
two unchanged Apps without incrementing their source revisions. The public Store
OpenAPI remains version 1.0 with its previously recorded SHA-256.

The response is the service client's authorized observation, not proof of global
catalogue completeness, owner-only visibility semantics or upstream deletion.
The retained ingestion status is `partial` because completeness is unproven, not
because either record failed: fetched=2, quarantined=0.

An initial local credential-import mistake selected a configuration-note word
instead of the secret from the supplied email. Those initial 401s were invalid-input
checks, not evidence of a HEDGE credential problem. The import was corrected and
live token/catalogue access revalidated. The earlier local commit's rejection
finding is superseded by these successful observations. The actual supplied secret
was absent from the committed diff and remains in private configuration only.

Private credentials, source-bearing records, screenshots, complete conversations
and receipts stay under `/home/ubuntu/.local/share/hedge-store-m2m`. The original
private workspace, integration branches and preserved demo are untouched.

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
60-second interval was used temporarily to observe repeated successful live polls.
Unchanged polls do not measure publication-to-search delay or resolve the proposal's
two-hour freshness target. Native Angular integration and deployed service hops remain untested.

## New/updated App explanations

Preparation version 3 automatically creates **English extractive explanations**
during the existing normalization/upsert, including embedded descriptions and a
structured-feature fallback for Apps without prose. No per-App file, prompt, service, API,
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
Valkey; ordinary requests make no Ollama call. A fresh task database first bootstrapped the authorized dated source, then synchronized
both current records from the real Store. **No manually prepared explanations** were imported. Complete raw
answers, cards/decisions, diagnostics and screenshots are retained privately.
The adapter uses existing in-process service bridges, so measured response times
are not deployed-service or production-load measurements.

Browser evaluation exposed poor purpose selection, missed English comparison/setup
phrasing and an unrelated-annotation veto in the richer live metadata. Unknown flat
structured feature labels now retain topic-scoped uncertainty in the existing sole
assessor; negative, conditional, relational and sentence-shaped fields retain their
full restriction checks. Explicit source reads and displayed comparison order also
retain their proper references. This does not promote unknown labels into matches. General purpose ranking and existing control grammars were adjusted;
no App names or question-specific answer tables were added. Final transcripts and
measurements are in the private evaluation report. Important limitations remain:
compound, qualified aggregation requirements can return a relevant complete source
passage with no confirmed recommendation card; generic how-it-works answers can
repeat descriptive lists; automatic text is less fluent than reviewed paraphrases.
These outcomes are retained, not scored away.

Synthetic preparation scaling measures code/payload cost only. It cannot establish
recommendation quality on hundreds of real Apps. Real upstream lifecycle changes, authorized corpus breadth beyond two observed Apps,
jointly labelled retrieval quality and native Store UI acceptance remain unverified.
There is no remaining credential/access blocker in the local integration.

Final automated verification and actual live-widget measurements are retained in
the private evaluation report alongside complete raw conversations and the real
synchronization/renewal receipts. Synthetic 100/300/1,000-App preparation timings
exclude HTTP, database writes, embedding/indexing and chat. They establish no
recommendation-quality KPI.

Final checks: **1,253 unit tests**, **87.49% shared branch coverage**, **148 disposable
integration tests**, focused source/explanation checks, Ruff, shell syntax and
whitespace checks passed. Existing deprecation/tokenizer warnings and the widget's
missing-resource 404 diagnostic remain retained.

The final **21-turn current-live widget** run measured median **0.292 s**, mean
**0.264 s**, p95 **0.315 s**, maximum **0.320 s**, with no runtime LLM calls. A separate
run during concurrent automated verification measured median 0.562 s / p95 0.752 s
and is retained too. Synthetic preparation alone on one CPU (five runs): median
0.0134 s for 100 Apps, 0.0365 s for 300 Apps, 0.2552 s for 1,000 Apps. These latter
timings exclude HTTP, persistence, embedding/indexing and chat, and provide no
real recommendation-quality evidence.
