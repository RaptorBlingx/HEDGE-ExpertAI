# T2 functional core: contextual Store understanding

The supplied approved proposal defines T2 as a working Rasa + LLM conversational
layer, automatic Store ingestion/indexing, hybrid retrieval/ranking and concise
source-grounded answers through containerized services and a minimal frontend.
It is a commitment baseline, not the Store API specification. This change is
prototype engineering and evaluation; it is not D2.2 or a Mid-Term Report.

## Functional gaps reproduced at the deployed baseline

At `f891831`, both real Apps were retrieved for the reported natural requests,
but literal word coverage rejected useful matches. The keyword channel used an
AND over every request word; normal requests frequently contributed no lexical
candidates. The private service policy explicitly disabled model interpretation.
Rasa's high-confidence labels confused discovery and functional follow-ups with
comparison/help. Prepared synopsis composition could not reliably resolve unfamiliar
requests or explain next steps after no match. Earlier unit counts and two-App
subsecond timings did not establish the promised semantic core.

## Implementation

- Keep the existing gateway → chat-intent → Expert → Discovery HTTP boundaries,
  Rasa, Ollama, PostgreSQL, Qdrant and incremental source preparation. No second
  recommendation engine, provider dependency or migration is added.
- The proven prepared path still handles supported simple searches, explicit source
  inspection, browsing and its existing simplification flow. With the explicit
  semantic flag, uncertain English turns use the existing contextual interpreter
  and Expert writer/reviewer. Rasa intent/entities are passed as fallible NLU
  hints. A first discovery turn retrieves directly; follow-ups use actual history,
  native identity bindings and a standalone resolved query. Explicit constrained
  search cannot become an unfiltered catalogue browse.
- Sparse Store retrieval matches independent request terms instead of requiring
  every word. Dense E5 retrieval and reciprocal-rank fusion remain unchanged.
  Original constraints remain available to Expert; candidate ranking is not proof
  of suitability. The interpreter does not receive an entire large catalogue's
  source fields; Discovery still searches the complete scoped index.
- The model distinguishes business context from explicit requirements, reasons over
  complete available source fields, and selects supplied source-reference IDs. Code
  binds those IDs to exact original fields; the model does not generate quotations
  or field paths. At most 20 distinct functional fields may support a turn. Application validation checks identities, quotations,
  required attribution and incomplete descriptive context. A separate model review
  checks the whole request and prose, including compound constraints, qualifications,
  unsupported automation and unjustified abstention. At most one correction/review
  pair is permitted. This is probabilistic semantic review, not a factual guarantee.
- Only that reviewed result can create an internal typed support receipt for the
  existing sole suitability assessor. Receipts bind the exact request, App identity
  and functional-source digest. A fresh catalogue read still checks all visible
  records before serving the answer. Unreviewed network dictionaries, stale source,
  invented quotations or changed membership cannot confer support. Zero price does
  not establish free use; production eligibility and native identities are retained.
- New/changed Apps use the same automatic preparation and current source extraction.
  The semantic layer reads their source evidence directly; it has no App-specific
  answers or curated synonym lists. All authored catalogues belong to evaluation.

Configuration and inference budgets are documented in
[configuration reference](configuration-reference.md#contextual-english-store-reasoning).
Semantic recovery is off by default; this local change does not activate it on 8096.
The model endpoint/choice, context, output budget, thinking mode, timeout and CPU
thread count are configurable
for suitable private inference infrastructure. No CPU-specific response shortcuts
replace the semantic quality requirement.

## Evaluation and acceptance boundary

The [evaluation protocol and inputs](../evaluation/t2/README.md) distinguish raw
retrieval, complete-request recommendation relevance, quotation integrity, reviewed
semantic correctness, dialogue continuity and latency. Actual browser transcripts
and protected Store observations stay outside Git. Live Store observations and
realistic authored catalogues are separate, explicitly labelled evidence sources.
A model approving itself is not a human quality score. The original private
service deployment is preserved; disposable evaluation services exercise the real
widget and HTTP/SSE boundaries without the old in-process adapter.

T2 acceptance still requires reviewing the retained complete conversations and
failure cases, selecting/calibrating a suitable real model and proving the supported
English flows on the target inference infrastructure. Two authorized Apps and
agent-authored fixtures cannot establish the proposal's jointly labelled pilot
relevance, explanation-accuracy, adoption or scalability KPIs. Turkish refinement
and native App Store UI adaptation remain deferred under the user's current scope.

The available CPU-only VM's cached 2B model is for limited protocol integration
only. It has not demonstrated reliable complete-request source assessments or
acceptable contextual English answers. No stronger private inference endpoint is
available. Completing hardware-independent implementation is not completion of
T2 quality acceptance: the frozen scenarios must be rerun and independently read
with an appropriately capable configured model, including unseen paraphrases,
compound requirements, follow-ups and failures. Do not enable semantic recovery on
the existing private environment on the basis of contract tests or fixture IR.

## Local engineering verification, 19 October 2026

- Baseline browser failures were reproduced against unchanged services on 8096.
  Separate HTTP/SSE evaluation services used a saved authorized observation of the
  two real Apps. No new Store credentials, production deployment or live migration
  were needed. The authored catalogue occupied a different Store scope.
- Actual E5/PostgreSQL/Qdrant retrieval over 12 authored scenarios (7 positive)
  achieved HitRate@2 7/7, recall@5 7/7, precision@2 0.50 and MRR 0.929. The sparse
  channel contributed to 12/12 queries versus 0/12 under the old AND query. Dense
  retrieval already found the relevant real Apps before this change; these figures
  do not prove a corresponding recommendation-quality improvement.
- A separate authored lifecycle exercised automatic preparation and the real
  Discovery HTTP index reconciler: creation revision 1, unchanged revision 1,
  changed metadata revision 2, withdrawal revision 3. Qdrant retained one point
  for the first three steps and zero after withdrawal; index pending was zero.
- Full unit verification: 1,278 passed, shared branch coverage 85.84% (80% gate).
  Lint and public OpenAPI export passed. A 30 ms deadline test failed under a
  throttled test container, then passed individually and in the full rerun with
  normal scheduling; the test and its assertions were not weakened.
- Actual prepared widget turns (recommendation, simplification, price) completed
  in 0.388–0.561 seconds, median 0.400, with semantic mode enabled and no inference.
  This is a three-turn observation, not a load-test percentile or proposal KPI.
- Limited real 2B calls exercised the writer, independent review, repair, contextual
  planner and fallback through the widget. Planning resolved the existing App
  reference correctly. Rejected reviews prevented generated answers from serving;
  one draft also invented settlement details. The original natural discovery and
  follow-up weaknesses remain unresolved in served 2B answers. Recovery examples
  took approximately 285–358 seconds, while planner-only clarifications took
  27–31 seconds. These are failure observations, not final model-quality benchmarks.
- Stronger-model held-out recommendation, factual accuracy, dialogue, negative/
  compound-request and latency acceptance remains pending. No jointly labelled
  pilot KPI, large-real-catalogue scalability or T2 quality completion is claimed.

Complete rendered conversations, raw SSE, timings, model traces, source checksums
and lifecycle results are retained in the private local evaluation evidence
folder, outside Git. Contract tests with mocked model replies establish guard and
service behavior only; they do not replace those actual conversations. The
existing AGENTS.md conversational guidance and the original deployment are kept.
