# Response composition and dialogue — 19 October 2026

Local follow-up on `perf/prepared-store-discovery`, based on `0ed1533` and the
[earlier UX pass](2026-10-19-conversational-ux.md). The existing AGENTS.md guidance
is retained. No source catalogue, demo, integration branch, deployment or Jira state
was changed.

## Product changes

The fast source-excerpt path repeated descriptions when comparing and barely
simplified technical prose. The composer now distinguishes purpose, workflow,
practical task comparison and genuinely plain-language explanation. Direct access,
pricing and provider questions receive relevant answers without routine internal
validation prefaces. Explicit source inspection retains the complete quotation.

Reusable bilingual preparation lives beside the existing authoritative projection.
The [source-review importer](../../scripts/prepare_store_explanations.py) requires
current identity/checksum, exact quotation bindings and recorded review provenance.
Source changes invalidate it; compare-and-set publication prevents stale writes.
Original metadata and indexes remain unchanged. The existing assessor can interpret
coherent reviewed passages only with request coverage in both original source and
explanation, preserving negative/strict-request and applicable restriction checks.
No new selector, model, service, dependency or ordinary runtime generation is added.

Dialogue retains a comparison group separately from the current focus and result
list. Narrowing to one App or failing a search no longer discards the unique
alternative or earlier comparison identities. Current publication/revision checks
remain. Older dialogue behavior is preserved outside the current catalogue mode.

## Actual widget evidence

Four complete EN/TR conversations were replayed with identical questions: 15 turns
before and 15 after. Five fresh sessions added 18 turns; four further turns verified
negative/numeric/production requirements, offline uncertainty and complete source
inspection. All answers were captured from actual widget bubbles, with raw SSE,
NLU, decisions and screenshots retained.

| Sample | Turns | Median | p95 | Max |
| --- | ---: | ---: | ---: | ---: |
| Paired before | 15 | 0.141 s | 0.228 s | 0.228 s |
| Paired after | 15 | 0.143 s | 0.197 s | 0.197 s |
| All after | 37 | 0.150 s | 0.198 s | 0.199 s |

All after turns used real Rasa; none invoked runtime generation. PostgreSQL,
Qdrant, pinned E5 and Valkey were real, with the existing local Python service
bridges and actual browser HTTP/SSE. This is a saved two-App snapshot, not complete
live-Store or separately deployed service-hop acceptance. Timings include completed
DOM response, exclude reading/animation pause, and use nearest-rank p95.

Full unedited conversations, screenshots, source-review records and replay steps:
`/home/ubuntu/.local/share/hedge-ux-refinement-2026-10-19/` (`conversations.md`,
`evaluation.md`, `measurements.json`, raw captures). Source-bearing artifacts remain
private and outside Git.

## Scale and remaining limits

A separate 300-App synthetic fixture included 2.30 MB of simulated prepared prose.
Twenty HTTP requests: median 0.190 s, p95 0.214 s, max 0.223 s; one CPU/1 GiB runner,
708.5 MiB peak runner memory. Bootstrap/index/cache-fixture import took 23.526 s.
It used real pinned E5 and regex NLU, with no concurrent load. Repeated language
text and simulated review provenance size the payload only. This is not evidence
of real recommendation or translation quality at 300 Apps.

Accepted real preparation was authored and source-reviewed by Codex, with explicit
agent provenance. Local-model preparation attempts failed quotation/semantic
checks; rejected output was not imported, and the unsuccessful writer is not part
of the committed implementation. Reliable unattended preparation remains open.
Import time is not authoring/review time. New/changed Apps without preparation retain
source-excerpt fallback. Query interpretation remains bounded, some widget controls
are English, and quality evidence remains two real Apps. Nuanced comparisons among
overlapping real alternatives require a larger held-out corpus.

## Verification

- Full unit suite: 1,230 passed; 88.53% shared branch coverage (80% gate).
- Disposable Store integration selection: 146 passed, including reuse, invalidation,
  stale review rejection, concurrent source-change/withdrawal guards and legacy mode.
- Ruff and `git diff --check` passed. Existing favicon/model-loader/test-client
  warnings were retained; chat requests succeeded.
- Model/image/dependency pins, public API contracts and production checks unchanged.
  No claim of remote CI or production readiness. SCRUM-39 ancestry was preserved.
