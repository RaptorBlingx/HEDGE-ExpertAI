# Expert conversation over Store evidence

> **Superseded (22 October 2026).** The generative expert path, its review loop and `scripts/check_store_conversation_grounding.py` were removed; see [conversational architecture](t2-conversational-architecture.md). This page records its revision.

Local performance work on 2026-10-19 changes the default request path; see [prepared Store discovery](prepared-store-discovery.md). Routine replies now use prepared source evidence, with explicit bounded reasoning opt-in. The implementation and measurements below describe their earlier revision; the running workspace has not been changed by the local performance task.

Review branch starts at `4fa7a6e`. The private preview remains
[127.0.0.1:8098](http://127.0.0.1:8098); the frozen reference at `fa06952` was read
only. No new Jira identifier was assigned.

The [proposal](proposals/HEDGE-IoT-OC1-Proposal-HedgeExpertAI.md) calls for contextual,
useful explanations. The [integration baseline](integration-baseline.md) retains
HEDGE's replied questions and the remaining native Angular/authentication decisions.
This change improves the private conversational surface without enabling public
Store indexing or changing SCRUM-39's separate implementation.

## What caused the quality gap

The reference demo's recommendation code prompts concise, question-oriented prose
and has readable fallbacks backed by rich authored summaries. Its preserved runtime
configuration currently uses real Rasa and the deterministic E2E generation endpoint
(`OLLAMA_MODEL=deterministic-e2e`, `OLLAMA_BASE_URL=http://mock-api:9000`). This is a
useful presentation benchmark, not evidence of current real-model reasoning quality.
Only configuration/source were inspected; no requests or mutations touched the demo.

The Store baseline instead selected field names and rendered repetitive quotations.
It discarded long README evidence from generation, did not give the model conversation
history, and routed many natural questions to static help or unresolved references.
Before this change an introduction and a “main difference” follow-up each produced
1,404 characters and five quotations plus blanket caveats. A use-case follow-up
became static help; “explain that in simpler terms” failed reference resolution.

## Decision and generation boundaries

- Rasa remains the first-pass classifier. Code binds explicit names/native IDs,
  current catalogue lists, focus and the unique alternative. Existing conversation
  Apps go directly to the fact-aware expert; a thin directory classifier cannot
  reject a functional choice before seeing README evidence. A small directory
  planner handles first turns without bound Apps.
- Internal routing labels and refresh authorization stay outside the answer evidence;
  capture timestamps and source provenance remain available, and full operational
  status remains visible in the workspace.
- Both planning and answer writing use actual user/assistant turns and finish with
  the current user question. Source fields are separate context, not instructions.
- The answer returns a current-source focus alongside its prose. Distinct schema
  alternatives require a nonempty source plan for App explanations. The source plan
  can also inspect Apps in a negative answer; it is not a suitability verdict. The
  final response act follows the prose. Code validates every planned App key and
  clears returned focus/cards for abstention and clarification, independently of
  the source plan. The previous visible list is retained separately.
- A new discovery task can request one existing scoped retrieval before a final
  answer. That directive is never served as prose, persisted as an answer or turned
  into an impression; repeat directives are rejected. There is no new tool framework.
- Explicit find/search/recommend requests retain the existing application-owned
  discovery boundary and their functional constraints, removing only request boilerplate; the model cannot turn them
  into unfiltered listings. Search uses the existing PostgreSQL/E5/Qdrant implementation. Retrieval
  failures remain HTTP/SSE errors, distinct from genuine no-match responses.
- The existing local Ollama client drafts fluent prose from current source fields
  and conversation context. Usable README/embedded descriptions are whole fields;
  whole-field omissions and extraction statuses remain explicit to the model.
  Historical assistant text is context, never authority for App facts.
- Structured generation selects the App focus and source-field map, writes prose,
  then assigns the response act. Citation selection is a source plan, while the
  final act determines whether App context is displayed. A direct whole-field positive control against actual
  Store evidence passed the source reviewer.
- Evidence is an App-key-to-field-path map. The request schema preserves ownership;
  code rejects invented/duplicate references and uncited positive App explanations.
  Ordinary explanations/comparisons require inspected field references for each
  supplied App with usable evidence. Search candidates are different: only selected
  or explicitly discussed Apps require citations, so an irrelevant hit cannot force
  an unasked comparison or source footer. The writer receives an explicit
  `retrieval_complete` boundary, rather than an internal NLU label. These references
  document inspection, including why a candidate does not match; they are not endorsements. Code also checks positive-answer coverage and rejects an uncited named App. Citation labels are generated from authoritative identities. A conversational/chat
  label cannot remove attribution when a reply names a current App or declares source field references. Neutral responses may leave that map empty
  for greetings; explicit App mentions still require a valid source reference. General greetings need no source footer; source
  attribution and displayed cards are separate decisions.
- A separate source review lists concrete claim/source mismatches, including
  restrictions, prerequisites, ownership and invented commercial terms. A nonempty
  issue list blocks delivery. There are no independently generated approval/category
  fields that can contradict the critique. The prompt permits supported paraphrases,
  analogies and honest unknowns without demanding unrelated missing information.
  Zero/false fields alone never establish free use, currency or licence terms.
- Source planning, prose and response classification are distinct: the writer
  labels the completed answer. The reviewer checks facts only and cannot promote
  abstention. Combining response labeling with factual criticism reproduced false
  rejection of a simple supported paraphrase. No-match clears cards/impressions
  even when the source plan discusses specific Apps. Missing optional commercial
  metadata alone does not make an App a functional no-match.
- Blank or punctuation-only prose cannot count as an answer, even with valid
  citations and a no-match decision. It uses the same bounded revision or retry path.
- A draft rejected for source mismatches or forbidden output markup gets one bounded revision using the same current
  evidence and the review feedback, followed by a fresh review. Unknown identities/field paths are rejected immediately. A missing search citation
  can use the same revision budget; the repaired answer must still pass source review. Formatting repair
  retains the same guard: an invalid second draft is never served. There is no unbounded regeneration loop.
- Model failure, invalid output or twice-rejected grounding yields a short retry response,
  not a forced recommendation. Displayed source-context cards create the existing
  display impressions; these are not accepted recommendations or evidence of meeting
  the proposal's acceptance KPI. Legitimate no-match clears recommendation cards and
  impressions. After generation, App publication and the entire current projection
  are rechecked before any answer is delivered.
- Source-bound App focus also survives a conversational/chat label. Generic chat
  has no focus and shows no App cards; explicit abstention and clarification clear
  the cards. Missing focus never selects all retrieval candidates by default.
- The focal subject and displayed source context are separate: another uniquely named,
  cited App discussed in prose remains inspectable without becoming the subject of a
  later “it”. Duplicate names never expand source identity. Private generation metadata
  reports code-bound `focus_ids`; cards remain conversation context, not endorsements.
- Session turn advancement belongs to the Chat boundary; policy context cannot
  overwrite it. Displayed cards are stored separately from conversational bindings,
  so an honest no-match does not restore stale cards after reload. Displayed citation
  numbers survive restoration: a sole source numbered 2 is not renumbered to 1. A new search binds
  only the Apps actually displayed; hidden retrieval candidates cannot become the
  next turn’s “other App”.

This review is probabilistic quality control, not a proof of entailment. A small
model can miss errors. Human real-corpus acceptance is still required before release.
General explanatory background is allowed; it must not invent App capabilities.

## Presentation and operation

Ordinary answers no longer receive a model label, repeated quotation block or legal
footer. Relevant uncertainty belongs in the answer; timestamp/refresh state and
complete original fields remain available in workspace status and source inspection.
Technical native IDs live in expanded source details. The UI shows interpretation,
writing, source-checking and (when needed) revision stages with SSE keep-alives, never unreviewed model tokens.

Run the existing `scripts/store-workspace.sh` from this worktree. It changes only the
labelled private workspace. PostgreSQL, Qdrant, Valkey, credential mounts and read-only
Store transport are preserved. The pinned `qwen3.5:2b` model and Ollama 0.32.0 cache
are reused; no cloud service, new weights or dependency change is introduced.
The existing model-disable flag still selects the deterministic source policy.
The private runner has a 4 GiB memory limit. New conversation calls have a bounded
16K context; default client behavior for other profiles remains unchanged.

Request size includes UTF-8 field/path data, schema and output budget. Only complete
historical turns may be removed to fit context; source strings are never silently
cut. Response length is checked after parsing because the pinned model server
rejects the grammar generated by a large JSON-schema `maxLength` rule.

## Acceptance and remaining work

`tests/browser/store-expert-conversation.cjs` exercises actual authorized Store
records through multi-turn browser conversations. Its console output contains only
counts, decisions, timings and source status. Protected answers remain in the private
UI/session store; no source values, names, screenshots or credentials enter Git.
Authored evidence tests are separate from real Store validation. The actual local
model accepted a supported paraphrase and rejected authored future-capability,
cross-field environment, invented-commercial and wrong-feature-channel claims.
Run `python -m scripts.check_store_conversation_grounding` inside the private
runner to repeat those authored controls against the configured local model. The
writer is controlled and the real source review is exercised once per case.
These are bounded negative controls, not a general semantic safety guarantee.

Representative browser conversations use the authorized records, not authored demo
Apps. Protected answer text and App names stay in the private UI/session; the table
records observable outcomes. Browser verification used reload checkpoints while
fixing defects, rather than claiming one uninterrupted run.

| Question | Baseline / reproduced problem | Verified result |
| --- | --- | --- |
| What Apps are available, and what is each useful for? | 1,404 characters of quotations and blanket caveats. | Two actual Apps, a 402-character overview and four source references. |
| What is the main difference between them? | Repeated the same 1,404-character source dump. | A different 690-character comparison, two App cards and four references. |
| Which one would help with semantic models, and why? | Static help; later a chat label hid the App cards. | A 389-character explanation, one App and references including embedded Dataspace fields. |
| Explain that in simpler terms. | Unresolved reference. | A different 633-character explanation retaining context and citations. |
| What would I use this named App for? | Mechanical field quotations. | A 706-character explanation, the correct native App and inspectable original fields. |
| What about the other one? | Weak relative-reference handling. | The alternate native App, a 524-character explanation and citations after one bounded revision. |
| How do their deployment requirements differ? | A reviewed comparison discussed two Apps but displayed only one. | A 507-character comparison, both source cards, and four references covering connector, OS and README evidence; no revision. |
| Are they free, and what currency does the Store use? | Raw fields need interpretation without invented terms. | A reviewed 558-character answer citing both Apps’ raw `price`/`billable` fields, after one source-based revision. |
| Would either warn me about earthquakes? | A negative explanation retained positive display behavior; a later draft was punctuation-only. | A reviewed 463-character explanation, no cards/impression, no stale cards after reload, and explicit source inspection still available. |
| Tell me about the first App. | Relative references were unreliable. | Normal HTTP used real Rasa, selected the original first native App, retained six source references, and restored the reviewed answer/card in the browser. |

A further reproduced boundary defect rejected a valid one-App search explanation
unless every other retrieval candidate was cited. The search-only correction retains
whole source context for review, focused/named-App citation checks and strict
browsing/comparison coverage. Permanent HTTP/SSE regressions use real disposable
persistence/retrieval and verify only the selected App is displayed.

Offline verification: 799 unit tests passed (89.96% shared branch coverage),
118 disposable PostgreSQL / Qdrant / Valkey integration tests passed, Ruff and
Bash/JavaScript syntax checks passed, and all six public OpenAPI exports were
unchanged. Widget Markdown safety checks passed 11 payloads, 65 streaming prefixes
and five compatibility cases without executable content, even without CSP. The private
Store observation contains two eligible Apps, both with extracted README and embedded
metadata. Read-only probes found both native-name records and README-only terms in
PostgreSQL lexical retrieval (2/2 in each probe); actual Chat discovery also exercised
real E5 dense retrieval. These checks establish the retained source-to-index path,
not fresh upstream completeness.

For review, run `tests/browser/store-expert-conversation.cjs` with Playwright and a
local Chromium (`STORE_BROWSER_EXECUTABLE`) against the loopback preview. Its default
flow starts with browsing; `STORE_CONVERSATION_HTTP=true` starts with normal HTTP
retrieval and restores that conversation before continuing through browser SSE.
The test never prints protected prose. Run model quality controls sequentially on this
CPU workspace; parallel generations compete for the same local model slot.

The catalogue is the retained authorized API observation. Current refresh requires
renewed access; global completeness and today's upstream publication are unverified.
The prototype is not native HEDGE Angular integration, corpus training or proposal
KPI acceptance. Latency and reviewed model/corpus quality remain release work; the
inherited npm audit gate remains unchanged and unwaived.

## QA handoff

Refresh the private preview, start a conversation and try the questions in the table
in sequence. Check that a named/relative follow-up keeps its subject, comparisons
show the discussed sources, and the source inspector contains the complete retained
README. Ask a new functional search to exercise retrieval rather than only browsing.
An unsupported functional request should explain the gap without cards/impressions;
model failure should invite retry without serving an unchecked draft.

Next priorities toward proposal acceptance:

1. Obtain durable official read credentials and confirm catalogue completeness,
   visibility scope and lifecycle behavior with HEDGE. Renewed access is required
   for fresh upstream validation; a retained snapshot is not a live publication check.
2. Conduct human acceptance on representative authorized Apps, languages and
   multi-turn tasks. The local model/source reviewer remains probabilistic, and
   CPU turns take minutes. No recommendation-accuracy or response-time KPI is claimed.
3. Agree and implement the native HEDGE Angular pane/session contract, then collect
   reviewed end-user acceptance evidence and distinguish display telemetry from
   accepted recommendations.
4. Resolve the inherited dependency audit gate independently. This branch changes
   no dependency manifests, lockfiles or CI policy and grants no security waiver.

During verification, an overloaded factual review rejected supported paraphrases
and fresh discovery. The final fact-only reviewer passed both supported-positive
and all six negative authored controls. Fresh normal HTTP discovery for “semantic
data modelling” then returned both observed Apps, real Rasa/dense E5 evidence and
five source references. The restored browser inspected the complete README, then
received a reviewed 138-character no-match follow-up with no cards/impression.
Native source inspection still worked and reload did not restore stale cards.
`STORE_CONVERSATION_SEARCH_QUERY` allows additional corpus acceptance queries
without product changes. These results do not establish general language accuracy.
