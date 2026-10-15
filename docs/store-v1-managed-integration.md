# Private durable Store integration

Started from SCRUM-38 browser-flow commit `b5f2df0`. This advances the authorized
Store workaround into a persistent private workspace. No new Jira issue/reference
was assigned. SCRUM-39, integration, main, the frozen demo and public Store indexing
remain unchanged.

## Verified access and official contract — 15 October 2026

Read the official [documentation](https://store.haslab-dataspace.pt/docs/index.html),
[architecture](https://store.haslab-dataspace.pt/docs/architecture.html),
[App lifecycle](https://store.haslab-dataspace.pt/docs/app-lifecycle.html), account/FAQ
pages, [Swagger UI](https://store.haslab-dataspace.pt/backend/api/v1/swagger-ui/index.html)
and [OpenAPI](https://store.haslab-dataspace.pt/backend/api/v1/api-docs).
These returned HTTP 200. The OpenAPI hash is unchanged:
`f5090c9cad06ea314a70ca1676dc433d97006ddbd7a65f9273058480239793a3`.

- HTTPS base: `https://store.haslab-dataspace.pt/backend/api/v1`.
- `GET /store/{appStoreId}/app/all` returns an App array; `GET
  /store/{appStoreId}/app/{appId}` returns one App. Both require Authorization.
  No pagination/completeness marker or deployed last-update guarantee is supplied.
- Native identity is the opaque Store ID/App ID pair. App metadata includes HTML
  README, connector/type/billing fields, versions and embedded Dataspace description.
  Declarations do not establish populated values, connector compatibility, currency
  or licence semantics. The original replied integration questions override generic
  certification documentation: HEDGE does not apply the certification routine.
- Documentation describes editing README and Dataspace metadata, publishing visibility,
  versions and removal. No Store mutation is needed or performed by this integration.
- Assets are a separate protected endpoint. Their App join/permissions are unconfirmed;
  no Asset fetch, registry/login-secret operation or inferred enrichment was added.

The previously supplied authorized short-lived token now returns **401** from the
real catalogue endpoint. No fresh protected catalogue/detail success is claimed.
No browser cookies, refresh tokens, automated login or alternate authentication were
used. The existing authorized JSON workaround is usable: the earlier private
`getAllApps` observation contains **two actual Store Apps**. That saved file dates
to **12 October 2026**. It is reused locally, with file timestamp provenance, rather
than replaced with authored records. Its pre-SCRUM-38 reduction omitted some fields;
missing connector/billing/embedded fields cannot be reconstructed without a new
approved response. Two observed records do not prove today's full catalogue count.

## Run and use

The current browser workspace is **http://127.0.0.1:8098**, loopback only. Use an SSH
port forward if needed; do not publish this private service.

```sh
bash scripts/store-workspace.sh start
bash scripts/store-workspace.sh status
bash scripts/store-workspace.sh restart
bash scripts/store-workspace.sh stop
```

`restart` replaces only the labelled private runner, preserving storage. `stop`
preserves all data. No command removes volumes or operates on demo resources.
Containers/networks/volumes have the `expertai-store-private` prefix and explicit
ownership labels. PostgreSQL, Qdrant and Valkey use separate persistent volumes;
no data service exposes a host port. The existing pinned local E5 developer image
is used by immutable image ID, with source mounted read-only and bounded resources.
No dependency/model/image pins or Compose/.env configuration were changed.
The launcher defaults `HEDGE_STORE_ID` to the supplied HEDGE Store ID; an explicitly
approved alternative may be selected through that existing environment variable
and `restart`. Bootstrap data must belong to that Store. One workspace is active
at a time; PostgreSQL identity/state and derived collections remain Store-scoped.

The launcher optionally seeds its private credential directory once from the
previously authorized mode-0600 token file. Future manually approved access tokens
or the official backend token belong in:

`/home/ubuntu/.local/share/hedge-store-live/credentials/token` (owned, mode 0600).

The directory is mounted read-only into the backend. Atomic replacement is supported;
the client rereads it on every attempt. Do not put credentials in Git, frontend
configuration, shell arguments or logs. A token is not needed to browse an explicitly
imported saved observation. With no observation and no working credential, catalogue
and Chat return unavailable/terminal-error outcomes, not a successful empty catalogue.
The existing [authorized input guide](store-v1-authorized-evaluation.md) describes
manual permitted token export/JSON saving; it does not authorize credential extraction.

Optional first bootstrap uses the owned private files `bootstrap-apps.json` (the
whole authorized getAllApps array) and `bootstrap-provenance.json`, containing
`captured_file_mtime` as epoch seconds, under `/home/ubuntu/.local/share/hedge-store-live`.
They stay outside Git. Import is bounded like the API transport, rejects duplicate
JSON keys/non-finite constants, and normalizes/quarantines records individually.
Bootstrap is used only before the first retained observation. It never replaces a
subsequent successful API observation, including a genuinely empty response.

Use the catalogue panel to page through **all locally available observed Apps**;
click an App to request its README by exact native ID. Chat can browse, retrieve by
name/concept, show README/embedded/connector/billing/version source fields, and
compare supplied fields with preserved native identity. Source cards are escaped
plain text. Search/cards remain bounded to five results; catalogue pagination is
independent (25 per page, maximum 50). It is not a selected-sample ingestion limit.

**Refresh from Store** requests the entire documented array through the real HTTPS
client. The private workspace also attempts refresh every two hours, under the same
turn lock. An expired/missing credential reports `authorization_required`; there is
no retry/login loop, fixture fallback or automatic refresh-token handling. This local
interval is not a measured freshness KPI or an approved production polling policy.

## Lifecycle, consistency and durability

Migration `0004_store_sync` adds private observation/membership state without changing
existing synthetic rows, Store source payloads, revisions or the public outbox policy.
Apply migrations before using this branch's Store projections; the workspace does
so only in its own `hedge_store_workspace` database.

- The new client array transport leaves per-record metadata validation to the existing
  transaction-scoped reconciler. Legacy strict `fetch_all_apps` behavior remains.
  Valid withdrawals therefore survive malformed neighbours. A malformed record for
  the withdrawn App itself cannot leave its old projection locally available.
- An observation and its available-membership set commit atomically with normalized
  payloads/revisions/quarantine. Publication requires the existing conservative
  `active && visible` gate. Duplicates/malformed records are unavailable locally.
- Absence from a later successful array, even an empty one, suspends local availability.
  It does **not** assert upstream deletion or completeness; raw normalized history is
  retained and a later positive observation can restore the same identity. Network,
  JSON and authorization failures preserve the prior dated observation instead.
- Managed membership gates lexical results, dense/cache hydration, catalogue reads
  and identity follow-ups. Legacy offline Store projections preserve their behavior.
  Every data-bearing managed Chat answer states snapshot provenance and refresh state.
  File time is explicitly distinguished from local API response time and neither is
  a Store last-update timestamp. Quarantined observations report partial processing.
- Scoped index reconciliation compares actual vector revision/identity with current
  PostgreSQL state, writes changed/new Apps, deletes unavailable points and records
  completed revisions only after successful writes. Pending work survives failures;
  startup/manual/poll refresh repairs missing points or a lost collection. Lexical
  retrieval remains available during vector lag. This is not a distributed transaction.

The workspace reuses actual normalization/reconciliation, PostgreSQL, E5/Qdrant,
retrieval, recommendation, dialogue, Valkey and widget implementations. Browser
HTTP/SSE and Store HTTPS are real. Internal service calls still use the established
in-process evaluation bridges; this is not validation of the deployed production
service mesh, gateway authentication or native HEDGE Angular pane. Generation is
currently deterministic source quotation; no expert-LLM reasoning/KPI is claimed.

## Verification and remaining decisions

Retained evidence is under `/home/ubuntu/.codex/artifacts/HEDGE-live-contract`, with
counts/status only for protected records. Actual browser checks cover the two real
saved Apps through ingestion, real lexical/dense retrieval, source reads, comparison,
HTTP/SSE parity, refresh rejection and history. Runner recreation preserves records,
observation time and index state. No live lifecycle mutations were attempted.

Disposable authored tests cover 63-App pagination, malformed-neighbour/self withdrawal,
duplicates, empty/subset observations, disappearance/reappearance, source revisions,
index-write failure/retry, lost collection recovery, native identity and unavailable
source HTTP/SSE outcomes. These prove implementation behavior, not live Store changes.
Relevant existing SCRUM-28/38 and catalogue/publication tests remain in the run.
Verification passed: 694 unit tests (89.96% shared branch coverage), 93 disposable
integration tests, actual managed-browser checks, runner recreation, Ruff,
shell/JavaScript syntax and whitespace checks. All six regenerated production
OpenAPI schemas were byte-identical. The baseline malformed-neighbour failure was
also reproduced using the original `b5f2df0` client and mocked transport.

Required to establish a **current live** end-to-end catalogue: a renewed approved
user access token, or HEDGE's backend client/token. Install it in the private path
and refresh; no new application authentication code is required for a supplied
Bearer token. HEDGE still needs to confirm scope/completeness, active/visibility and
withdrawal semantics, credential renewal/operations, corpus reuse rights, connector/
billing/embedded metadata semantics, cadence and the native Angular contract.

The current two-record saved observation cannot establish today's App count, current
publication, two-hour freshness, retrieval HitRate@2, expert explanation accuracy,
multilingual quality or accepted-recommendation KPIs. SCRUM-39 remains separate;
nearest neighbours are labelled source records, not confirmed suitable Apps. The
existing tokenizer warning and inherited npm audit/CI failure remain unresolved and
unwaived. Next work is fresh authorized validation, coordinated suitability/security
integration, and jointly labelled real-corpus/model/native-UI acceptance against the
[proposal](proposals/HEDGE-IoT-OC1-Proposal-HedgeExpertAI.md).
