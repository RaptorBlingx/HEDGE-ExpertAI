# SCRUM-38 follow-through: metadata in browser Chat

This review branch starts at integration `eddb179`. It makes preserved Store App
metadata usable in the existing isolated Chat workflow. It does not incorporate
or modify SCRUM-39. Source records and retrieval order are not suitability decisions.

## Open the preview

On this development host, open **http://127.0.0.1:8096**. It binds only loopback.
For a remote browser, forward that port over SSH; do not expose it publicly.

Reproduce from this worktree, with cached repository-pinned dependency images:

```sh
bash scripts/store-v1-playground.sh --browser --metadata-demo --embeddings --reuse-model-image --port 8096
```

`--reuse-model-image` explicitly uses the existing local `hedge-store-models:local`
image, resolving its immutable image ID before use. This avoids rebuilding large
model layers on this nearly full development disk. The retained verification used
`sha256:e02493fccbbf67c15c6abf52e25695963795cb9f588f99b7e1fd75db475b41cb`.
Omit `--reuse-model-image` to build the existing locked developer/model environment;
that fresh model build was not verified in this delivery because it exhausted disk
space. Omit both embedding options for the real PostgreSQL lexical-only mode.
Neither mode uses fabricated vectors. No dependency/model pins changed.

The launcher creates its own uniquely named database, Qdrant, Valkey and runner.
It does not read `.env`, contact Store, use demo volumes or start Compose. Ctrl-C
cleans only this run. Preview data is disposable. The existing private JSON import
and optional model modes remain available; see [browser evaluation](store-v1-browser-evaluation.md).
`--metadata-demo` cannot be combined with private input.

## Try the complete flow

The prompt buttons fill Chat; press **Send**. All records in this scenario are
explicitly **authored Store v1 examples**, not verified HEDGE product claims.

1. **Find apps for district heat measurements**. That phrase occurs only in the
   Telemetry App's README, not its name/description. Inspect `source_evidence.readme`
   and lexical/dense retrieval channels on the returned record.
2. **Show README for Demo Telemetry Bridge**. The answer retains the complete
   simulator-only MQTT qualification. Expand **Source evidence** on its card for
   original Store field paths, native Store/App identity and extraction statuses.
3. **Show embedded metadata for it**, **Show connector fields for it**,
   **Show billing fields for it**, **Show versions for it**. Values are quoted;
   no connector compatibility, currency, licence terms or latest version is inferred.
4. **Show README for Demo Sparse Catalogue**, **Show embedded metadata for Demo
   Sparse Catalogue**, **Show README for Demo Long Documentation**. Missing,
   malformed and too-large evidence remain distinct.
5. Use **Update demo App**, then request the Telemetry README again. The fixed
   authored source transition goes through snapshot reconciliation, revision/checksum
   persistence, lexical-document refresh and scoped E5 reindexing. Chat reads the
   new CSV-export quotation from current PostgreSQL metadata.
6. Use **Withdraw demo App**, then **Show README for it** and search again. Current
   results exclude it, and its vector point is deleted. **Restore demo App** returns
   its original evidence under the same native/local identity, with a new revision.
   Historical messages remain historical; they are not rewritten as current facts.
7. Browse Apps, compare the first two, reload the tab, and inspect context. On
   mobile, close the source pane to return to Chat.

The page status includes actual eligible-row revisions and an exact Qdrant point
count. Initially four eligible Apps produce four vectors with E5; the fifth,
unpublished authored App never enters result projections. The fixed publisher
controls are absent for private snapshots. They accept no arbitrary source payload,
make no Store writes and do not enable public indexing. Failed source/index steps
are reported as failures; PostgreSQL and Qdrant are not a distributed transaction.
Retry or restore this disposable scenario before evaluating its state.

## What changed

Previously, a README question could silently return only the generic description;
connector/version requests hit a blanket metadata refusal despite SCRUM-38 retaining
those fields. Explicit full-match source reads (`Show/Quote/List <field> for <exact
name/native ID/reference>`) now select retained evidence paths and reuse the
SCRUM-38 complete-quotation renderer. Reads without a target require a focused App.
Additional constraints are not interpreted as field reads. Capability, free-price
filters and suitability questions retain the existing limitations.

Source-field answers are deterministic even when the optional extractive generator
is enabled: it cannot drop billing/version caveats or replace a requested field with
another excerpt. Long quotations are omitted whole. Missing projected evidence is
not described as proof that a capability is absent. Results retain their complete
authoritative App projection and source identity; context still binds identities.

Widget cards expose escaped plain-text source evidence, never raw HTML/embedded
JSON. Long card descriptions direct readers to complete evidence rather than
cutting off qualifications. Keyboard focus reaches evidence summaries. The mobile open-panel selector also
now takes precedence over the smaller-screen transition rule, avoiding a scaled,
inset Chat pane. Store cards
use **Store source records**, with retrieval rank rather than a suitability badge.
Normal browser failures now return a sanitized 503; SSE retains its terminal problem
without successful completion. Production API schemas/routes are unchanged.

## Verification and limits

Retained local evidence: `/home/ubuntu/.codex/artifacts/HEDGE-browser-metadata-flow`.
New source-read regressions produced **12 failures on the original policy**, then
passed with the correction. The full unit suite passed (693 tests, shared branch
coverage 93.58%); 87 focused disposable PostgreSQL/Qdrant/Valkey integration tests
passed, including current-evidence updates and withdrawal. The actual Playwright
browser flow covers HTTP/SSE parity, source paths, real lexical/dense retrieval,
safe rendering, source update/withdrawal/restore, history and desktop/mobile layout.
Ruff, shell/JavaScript syntax and whitespace checks passed; six regenerated
production OpenAPI files were byte-identical.
No live Store, real-model quality, production service mesh or native Angular
integration is established by these checks. The developer E5 tokenizer emits an
existing regex compatibility warning; corpus-quality acceptance remains pending.
The inherited frontend npm audit failure is unchanged and is not waived here.

## Next priorities toward the proposal

1. Independently review this change and resolve the separate CI/security gate.
   Then coordinate integration with the reviewed SCRUM-39 work; this branch's
   disclosure labels do not implement its suitability/abstention policy.
2. Agree a representative, authorized Store corpus and at least 50 jointly labelled
   queries. Validate multilingual dialogue, sparse metadata, no-match behavior and
   HitRate@2 before claiming retrieval quality. Dense neighbours remain weak on this
   tiny authored corpus; regex NLU is explicitly labelled.
3. Validate useful expert explanations with the existing optional model seam,
   source restrictions and human review. Deterministic quotations prove grounding
   and wiring, not expert reasoning, <5-second model response or 80% explanation
   accuracy. Retain real sessions and define qualified acceptance events.
4. Agree HEDGE's existing Angular pane contract, navigation and incoming access
   policy; this widget is a browser validation surface. No canonical detail links
   or user-specific recommendations are invented.
5. Confirm approved credential/corpus scope, metadata/billing/connector semantics,
   publication/access rules and polling cadence before live ingestion/indexing.
   Local simulated revision changes do not prove the proposal's two-hour freshness
   commitment. See the [integration baseline](integration-baseline.md) and original
   [proposal](proposals/HEDGE-IoT-OC1-Proposal-HedgeExpertAI.md).
