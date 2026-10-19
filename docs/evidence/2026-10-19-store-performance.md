# Store performance evaluation — 2026-10-19

Local implementation on `perf/prepared-store-discovery`, isolated from existing
workspaces and deployments. See [architecture and dependency composition](../prepared-store-discovery.md)
and [retained anonymized observations](2026-10-19-store-performance.json).

## Result and timing boundary

The measured median is below five seconds on this host, including the final
managed Store adapter with real Rasa, pinned E5, PostgreSQL, Qdrant and Valkey.
Ordinary responses use no runtime LLM generation. This establishes a local
saved-snapshot result, not production or full-catalogue quality acceptance.

Host: two logical CPUs, approximately 5.7 GiB RAM, shared with existing services.
The baseline uses the configured `qwen3.5:2b` and cached Ollama 0.32.0; the model
choice was not changed to obtain faster numbers. E5 uses the existing cached
`intfloat/multilingual-e5-small`, built from pinned revision
`614241f622f53c4eeff9890bdc4f31cfecc418b3`. Image identities and cgroup limits/peaks
are retained in JSON. No original container was restarted or reconfigured.

| HTTP profile | Responses | CPU cap | Median (s) | Mean (s) | p95 (s) | Max (s) |
|---|---:|---:|---:|---:|---:|---:|
| Existing `c6050ab`, E5 + runtime drafting/review | 12 | 2 | 169.363 | 176.189 | 353.311 | 353.311 |
| Prepared + pinned E5, regex NLU | 120 | 2 | 0.073 | 0.062 | 0.084 | 0.124 |
| Prepared + pinned E5, regex NLU | 120 | 1 | 0.073 | 0.063 | 0.089 | 0.110 |
| Final managed workspace, pinned E5 + real Rasa | 120 | 1 | **0.126** | **0.135** | **0.210** | **0.243** |
| Prepared lexical fallback, regex NLU | 120 | 1 | 0.058 | 0.065 | 0.107 | 0.141 |

p95 is the nearest-rank statistic. Twelve baseline observations make its p95 a
small-sample maximum, not a reliable population tail estimate. Each improved run
contains ten repetitions of twelve diagnostic turns, not 120 independent use
cases. Every reported improved observation returned HTTP 200; the positive cases
still returned Apps and the negative cases explicitly abstained. The final managed
run records **120/120 NLU results from Rasa**, not an assumption based on its flag.

The HTTP client waits for each complete JSON reply from a real loopback Uvicorn
server. The measured interval includes classification, dialogue, current catalogue
hydration, retrieval, source decision/rendering, Valkey session work, PostgreSQL
impressions and serialization. The managed variant also exercises the existing
workspace's observation/membership gates. Inter-service calls use the established
in-process bridges. Native Angular UI rendering, external TLS, separate service
process/network hops, concurrent production traffic and large-catalogue behavior
are outside this timing boundary. The shared host was not reserved exclusively;
brief checks ran during parts of baseline collection. These are retained local
measurements, not controlled production load-test claims.

## What the measurements changed

The baseline's reported generation stage consumed over 99% of measured reply time.
Browsing took 177.021 seconds; an English detail turn took 118.391 seconds and
fell back because the generated answer lacked source evidence. A no-match turn
repaired a rejected draft and took 353.311 seconds. Streaming would still wait for
validated text and would not remove that computation.

A restart-style managed rerun initially had a 5.203-second first discovery request:
existing vectors were reused, so no indexing operation loaded the query encoder.
The workspace now warms the same encoder before serving, as Discovery already
does. Final managed bootstrap took 5.910 seconds separately from request latency;
its request maximum became 0.243 seconds. This avoids disguising model loading as
an ordinary first-user request or excluding that outlier without a code correction.
The two fresh-snapshot E5 bootstraps took approximately 6–8 seconds. Bootstrap time
includes migrations and preparation of two Apps; it is not a large-catalogue sync benchmark.

The final one-CPU E5 runner had a 1-GiB memory limit and approximately 661 MiB cgroup
peak charge. The managed one-CPU runner had a 1.5-GiB limit; its separate Rasa process
had a 768-MiB limit. The old model-enabled runner had a 4-GiB limit and an observed
3.876-GiB charge during inference (a sample, not a retained peak). Runtime generation
and its model residency are absent from the ordinary path.

## Source and recommendation checks

The input is the existing authorized saved Store snapshot with **two eligible
Apps**. No new Store calls, token acquisition, source writes, public indexing or
production synchronization were performed. Source coverage and present-day
upstream availability remain unverified. All diagnostics used the same source
records and configured E5 weights.

The twelve cases below were inspected against the actual projected fields and
README evidence. Expected identities/order were then checked over **480 improved
observations**, with **560 served-App metadata fingerprints** matching the source
projection and **zero unexpected served Apps** for these cases. These are authored
diagnostic expectations, not jointly labelled pilot ground truth or an explanation
accuracy KPI. Full source/model prose, native identifiers and tokens are not
retained in the JSON evidence.

| Diagnostic turn | Old seconds | Final managed median seconds | Served Apps: old → new | Check |
|---|---:|---:|---:|---|
| English catalogue listing | 177.021 | 0.082 | 2 → 2 | Stable native identities and bounded-coverage caveat |
| Details of second listed App | 118.391 | 0.203 | 0 → 1 | Correct reference; previous model draft had failed validation |
| Compare named Apps | 175.350 | 0.102 | 2 → 2 | Same source metadata, no invented winner |
| Find Apps for shared data models | 144.128 | 0.129 | 1 → 1 | Same App, supported by its actual README |
| Turkish equivalent discovery | 102.241 | 0.127 | 1 → 1 | Same App, Turkish request normalization/prose |
| Production earthquake warnings via SMS | 158.447 | 0.128 | 0 → 0 | No unsupported capability recommendation |
| Satellite crop disease prediction | 353.311 | 0.122 | 2 → 0 | Unsupported request now abstains; candidates remain unverified |
| Cost of named App | 165.574 | 0.205 | 0 → 1 | Raw source-field inspection, not a price/free-use recommendation |
| Turkish catalogue listing | 181.468 | 0.085 | 2 → 2 | Explicit browse intent and stable catalogue order |
| Turkish second-App details | 173.153 | 0.202 | 1 → 1 | Resolves the second card in the current visible list |
| Turkish comparison follow-up | 246.834 | 0.102 | 2 → 2 | Current reference set, correct Store identities |
| Publisher-filtered listing | 118.353 | 0.083 | 1 → 1 | Supplied provider filter only |

The old Turkish browse reused an earlier retrieval order; the corrected browse
uses stable catalogue order. Its subsequent ordinal is checked against the new
visible list, not blindly required to return the old list's second identity.
Cost/detail/browse/comparison cards are source context, not evidence that a product
meets a requested functional or deployment requirement.

The first deterministic experiment missed the README's shared-data-model purpose.
The correction extends **the existing SCRUM-39 assessor**, rather than adding a
second suitability engine. It recognizes complete purpose/provenance headings,
coordinated predicates with their whole shared object, short acronym annotations
and scoped deployment restrictions. Complete source spans and qualifications stay
in evidence. Authored positive/negative controls include historical wording,
simulation, disabled features, external prerequisites, container restrictions and
feature/channel ownership. Unknown predicates and unparsed relationships still
abstain. Named capability questions call the same Expert decision function on the
resolved Apps; names alone cannot establish support.

Further checks cover English/Turkish controls, conjunctions, strict/negative
requirements, unknown Turkish terms, explicit source reads, ambiguous references,
wrong-case native IDs, metadata/quote limits, malformed evidence, injection,
normal/SSE decisions, database errors, publication withdrawal and late revisions.
The relevant SCRUM-28/38/39 regressions remain active.

## Optional reasoning and contention

With the configured real model and an eight-second combined drafting/review budget,
explicit deep comparison returned its prepared source fallback in **8.123 seconds**.
No model answer completed or was served. The two App projections remained exactly
unchanged. During that request, another session's real discovery response completed
in **0.178 seconds**, returning its source-supported App. Session turns now serialize
per session, so model reasoning does not hold an unrelated chat's turn lock.
Background catalogue/index preparation likewise uses a separate refresh lock.

A transport regression also verifies cancellation of a delayed model request under
one wall-clock deadline. Structured generation has no retry/repair loop in this
path, and a reviewed model abstention can only veto existing source support.
This is bounded-fallback evidence, **not** successful complex reasoning quality
acceptance at the eight-second budget. On this CPU host the configured model may
frequently fall back; a longer unbounded wait is not hidden in routine requests.
The overlap probe is one concrete contention check, not a full load benchmark.

## Verification and retained exclusions

- **1,220 unit tests passed**, with **90.24% shared-package branch coverage**
  (80% gate enforced).
- **202 relevant isolated integration tests passed** against actual PostgreSQL,
  Qdrant and Valkey; fixture embeddings/model seams are deterministic in those
  regressions. Real E5/Rasa/Ollama execution is the separately retained HTTP work above.
- **25 frontend tests passed** and the TypeScript/Vite production build passed
  after `npm ci --offline` using the unchanged lockfile.
- Pinned Ruff passed over shared/services/tests/scripts/evaluation/database;
  Bash syntax and `git diff --check` passed.
- All six OpenAPI exports were regenerated/reviewed. Only Expert's health
  description changed; request schemas and source metadata contracts did not.
- Persistence tests prove unchanged preparation/vector reuse, source/version/model
  invalidation, repair without inventing a source revision, current hydration,
  withdrawal and index loss/recovery. Concurrency checks retain same-session
  ordering while allowing unrelated chats and background preparation to proceed.

The earlier shared disposable test database exhausted its 256-MiB temporary storage
while integration schemas were being exercised. The nine affected HTTP 503s are
retained under `excluded_harness_faults`; they are not counted as fast successful
answers. The first three complete baseline observations were retained, all nine
affected cases were rerun, and the replacement disposable database used a 512-MiB
cap with bounded WAL/checkpoint settings. A separate initial model run under a
smaller memory cap produced model HTTP errors and was excluded from successful
model-performance evidence. Existing services remained separate and running.

## Limits and necessary next action

No material regression was observed in the retained source-reviewed cases and
existing regressions. Broader recommendation quality is **not established** by two
Apps, repeated queries, exact source fingerprints or passing structural tests.
Complex prose, novel paraphrases and unsupported Turkish forms can remain
unverified. Ordinary explanations are complete bounded source quotations, not
free-form expert paraphrases. Optional reasoning has demonstrated safe timeout
recovery, not successful completion for complex requests at the chosen budget.

The implementation is local and undeployed. The next necessary acceptance work is
review of the explicit dependency composition and a broader approved, jointly
labelled Store corpus on the intended deployment topology, including concurrent
load and human explanation review. The daily polling default also needs owner
alignment with the proposal's stricter two-hour freshness commitment. No new
production-readiness, HitRate, explanation-accuracy or pilot-acceptance KPI is claimed.
