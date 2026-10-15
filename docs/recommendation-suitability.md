# SCRUM-39: recommendation evidence and abstention

Implemented on `feat/SCRUM-39-recommendation-suitability`, based on integrated
SCRUM-38 commit `eddb1794d9ddc74db01c05928d69b20eb6690d99`. This is offline
engineering verification, not live Store, model-quality or pilot acceptance.

## Defects reproduced before changing code

Against that baseline, the actual recommendation orchestrator reproduced Astra
[findings 2 and 3](audits/HEDGE-ExpertAI-Astra-Independent-Audit-2026-10-13.md):

- For `Find earthquake warning apps`, a rank-one Water Meter described only as
  displaying water readings was returned in `apps`. Model abstention (`None of
  these apps meets the requested requirement.`) was rejected and replaced with
  `Start with **Water Meter** because it is the highest-ranked evidence-backed match`.
- Both title/order validators accepted a narrative claiming that Water Meter
  guarantees 90% electricity savings and is medically certified. Source metadata
  supported neither claim. This reproduced validator behavior with a model double;
  it does not measure the frequency of fabricated output from a live model.

The independent review of `bd8de291aa8ec44e9271df25487af8ac356d4576`
then reproduced three admission defects, also reproduced before this correction:

| Request and source | Reviewed behavior | Corrected behavior |
|---|---|---|
| `earthquake warnings`; `Earthquake warnings are planned for a future release.` | Recommended | Unverified candidate; future availability is not current support. |
| Same request; `Earthquake warnings. They are not supported by this App.`, or a positive description with README `This feature is disabled. It cannot be used.` | Recommended | Unverified candidate; neighboring qualifications and README uncertainty cannot be dropped. |
| Portuguese `alertas de terremoto` / `Não envia alertas de terremoto.`, or German `MQTT` / `Unterstützt MQTT nicht.` | Recommended | Unverified candidate; explicit negation applies regardless of requested locale. |
| `earthquake warnings SMS`; `Provides earthquake warnings. Sends them via SMS.` | Rejected | Source-supported; the clear local reference connects the delivery channel to the warnings. |

## Decision boundary

Retrieval and fusion are unchanged. The recommender assesses retrieved records
before creating recommendation cards, impressions or served narrative:

| Evidence/condition | Behavior |
|---|---|
| Direct functional source support | Return the App in `apps`, with original rank, identity and metadata plus `suitability.evidence_fields`. |
| Unrelated, qualified, ambiguous or insufficient evidence | Retain the record in `candidates` with `uncertain` status, quote available source facts, and explicitly label it unverified. It is not a recommendation or impression. |
| Valid structured model selection of no Apps | Preserve abstention; never replace it with a forced first candidate. |
| Invalid, fabricated, unknown-ID, duplicate-ID or unavailable model response | Serve only the independently admitted source-supported subset and code-rendered source facts. Raw model narrative never reaches the client. |
| Successful retrieval with no candidates | Return an abstained decision explaining that retrieval was empty. |
| Retrieval error/timeout/malformed result envelope | Preserve SCRUM-28 503/504 errors or terminal stream problem events; do not claim no match. |

The former one-sentence term check ignored material context and could not compose
related evidence. The correction interprets bounded source clauses as affirmed,
qualified or unresolved claims, keeping their original field paths and feature
scope. Recognized predicates and availability states establish assertions;
negation, conditional/future language, restrictions and uninterpreted context
cannot establish unconditional support. Applicable contradictions and uncertainty
are checked across all available functional fields, including README. This is a
source-claim check, not an expanded retrieval keyword score.

Evidence may compose through an explicit repeat of a feature or an unambiguous
immediate reference within a field and paragraph. `Provides earthquake warnings.
Sends them via SMS.` supports warning delivery by SMS. `Provides earthquake
warnings and water readings. Sends them via SMS.` leaves the referent ambiguous.
`Provides earthquake warnings. Supports SMS.` does not establish that relationship.
Explicit independent conjunctions can require separately supported features.
References do not cross fields; an explicit named capability in another field
can still supply its own support. Recognizable unrelated feature restrictions and
privacy statements do not automatically veto another supported capability;
unresolved scope or App-wide unavailability does. An explicitly different actor
cannot supply this App's capabilities.

Request scaffolding and simple inflections are normalized for matching; original
source text is unchanged. There is no similarity threshold, required metadata
count, minimum description length, provider/ontology admission or ranking change.
A sparse description such as `Warns about earthquakes.` remains sufficient for
`Find apps for earthquake warnings`. Bounded English, Portuguese and German forms
cover the reported cases, including affirmative counterparts; unrecognized
language or grammar remains uncertain rather than being translated or guessed.
Exact known informational annotations in the explicitly synthetic catalogue
are retained in output but do not themselves support or negate a capability.
Present-purpose statements can corroborate exact typed capability declarations;
unknown implementation context and material qualifications still remain relevant.

Functional evidence comprises Store `description`, safely extracted README and
embedded description/feature paths, or synthetic/legacy description, localized
summary, capability strings and input/output descriptions. Original source paths
are retained. Explicit quoted name-only searches establish identity lookup, not a
capability; opaque native App IDs remain case-sensitive. A name-only Store lookup
shortcut cannot discard additional request constraints.

Normal synthetic/legacy recommendation generation reuses the existing bounded
structured Ollama call (40-second request limit, existing model and client). Its
schema allows only selected admitted IDs, including an empty list. The model may
decline Apps; it cannot promote an unsupported candidate or produce served facts.
The existing opt-in Store extractive generator likewise accepts empty search/refine
selection; Store context is cleared so the declined Apps do not remain recommended
references. The existing late publication check covers candidates as well as
admitted Apps; changed or withdrawn evidence clears the response. Successful
generation retains unverified candidate evidence. Store detail, browse and
comparison remain descriptive source views.
Ordinary Store recommendation assessment does not enable a new model call.

Both normal and streamed recommendation paths decide before exposing App cards.
The response adds `candidates` and `decision: {outcome, reason}`; retrieval metadata,
source records and admitted Apps' existing keys remain intact. The existing gateway,
chat and isolated Store browser forward these fields. Card badges identify source
evidence rather than equating a retrieval relevance band with suitability.
The correction preserves this response shape and decision reasons. Functional
`suitability.reason` values now distinguish `coherent_source_support`,
`no_coherent_source_support` and `qualified_or_unresolved_source`; identity lookup,
request clarification and model-decline reasons retain their previous meaning.

## Provenance, bounded evidence and safety

SCRUM-38 normalization, PostgreSQL revisions, lexical/vector projections and source
visibility gates are preserved. No Store call, ingestion schedule, index activation,
publication policy, connector compatibility interpretation or price/currency/licence
inference is introduced. Candidates contain the same authorized projection as Apps;
this does not introduce access to raw embedded secrets or additional source fields.

Code-owned prose uses escaped complete field quotations. A field exceeding the
1,200-character prose bound is explicitly omitted in full, never cut before a
qualification. Admission examines complete available evidence up to the existing
16,000-character extraction bound; oversized unprojected fields supply no support.
Processing statuses remain distinct from missing metadata. Malformed optional
functional fields cannot supply evidence. Omitted evidence cannot cause an
unrelated candidate to become a forced fallback. The old prompt helpers also allow
abstention and omit whole over-bound fields, although recommendation serving now
uses structured selection rather than those free-form templates.

## Regression and verification evidence

- 816 unit tests pass with 93.58% shared-package branch coverage (80% gate).
  Source admission tests cover sparse positives, negation, simulation restrictions,
  unrelated limitations, README/embedded provenance, malformed optional fields,
  unsupported provider/price/ontology evidence, and constrained queries.
- Real Discovery → Expert → Chat → Gateway HTTP routes exercise positive,
  unrelated and qualified earthquake requests, structured model abstention,
  stream/non-stream decisions, source-only prose and absence of recommendation
  impressions on abstention. Existing SCRUM-28 error regressions remain passing.
  Permanent normal/SSE Gateway cases now cover all reported review defects,
  coherent and ambiguous references, related/unrelated restrictions, Portuguese
  and German affirmative/negative evidence, and unknown-language contradictions.
  Timeout, transport failure, malformed/fabricated generation, valid selection
  and structured abstention are each tested with supported and unsupported Apps.
  Unsupported Apps never invoke selection or create recommendation impressions;
  source-supported fallback never serves raw fabricated/private model output.
  Exclusions such as `without SMS`, material real-time requirements and unknown
  implementation context cannot disappear from the admission decision.
- 98 focused integration tests pass with disposable PostgreSQL 16.9, Qdrant 1.18.2
  and Valkey 8.1.3 on a unique internal network, no host ports and ephemeral storage.
  Invented Store records traverse the real normalizer, storage, indexing, lexical/
  vector search and recommender. An unrelated dense Water Meter neighbour remains
  unverified; a sparse warning description is admitted, simulation-only warnings
  remain uncertain, and current withdrawal overrides stale vector evidence.
  Existing native identity, revision, metadata, indexing and dialogue tests pass.
  Thirteen added review cases prove the record was retrieved before admission,
  preserve the original description/README, native identity, checksum and revision,
  compare stream/non-stream output, and withdraw it while its vector is stale.
- The SCRUM-38 1,254-/16,001-character README regressions retain complete omission/
  extraction-status handling and streaming parity. Legacy standalone explanation
  remains usable without inventing a missing App identity.
- Ruff and 25 frontend tests pass; all six OpenAPI exports match tracked files.
  The original branch's TypeScript/Vite build and widget syntax checks passed
  using pinned Node 20.19.4; this correction changes no frontend code or public
  schema. Frontend tests were rerun on that same pinned Node version.
- `npm audit --audit-level=high` fails with 8 high and 4 moderate advisories in
  the unchanged baseline dependency lockfile. Dependency remediation is separate
  from this issue; the branch cannot be represented as fully green CI.
  Source and integration baseline have identical manifests, lockfile and audit
  gate. Pinned Node 20.19.4/npm 10.8.2 returns exit 1 for the CI audit command on
  both. Affected high-severity package entries are `braces`, `micromatch`,
  `fast-glob`, `chokidar`, `tailwindcss`, `browserslist`, `nanoid` and `source-map-js`;
  moderate entries are `baseline-browser-mapping`, `postcss-selector-parser`,
  `vitest` and `@vitest/mocker`. These are development/build/test dependencies;
  the production-only audit reports zero. The inspected serving paths do not feed
  chat or Store input into these tooling APIs; that is not a blanket security
  waiver. The existing CI failure still requires a maintainer decision.

## Limits and owner acceptance still required

Bounded claim interpretation is a conservative baseline, not general semantic
entailment, full multilingual understanding or a calibrated suitability classifier.
Paraphrases, unknown predicates, implicit constraints, distant/ambiguous references
and complex source claims may remain unverified. Multi-sentence support is admitted
only when the relationship is explicit or locally unambiguous. Conflicting claims
remain uncertain rather than choosing a preferred field. Candidates remain visible
for inspection; abstention does not establish that an App lacks a feature.
Source assertions are attributed claims,
not certification of real-world capabilities, deployment compatibility or safety.
The model can decline direct support but cannot rescue a paraphrase without that
support. This trades recommendation recall for explicit uncertainty and needs
held-out real-corpus acceptance, particularly for sparse Apps.

Owners still need to agree labelled positive/ambiguous/no-match queries, supported
languages, suitability expectations and the native UI presentation of unverified
candidates. Measure real-model accuracy/latency and corpus precision/recall before
claiming quality targets. The 40-second bounded model selection can delay the first
recommendation event; no live latency or proposal KPI is newly established here.
The unchanged evaluator's structural explanation checks are not factual validation.
Store access/redistribution authorization, publication semantics, connector/billing
field meaning and public-index activation remain the outstanding decisions recorded
in the integration baseline and SCRUM-38 notes. No protected Store data or live
model was accessed for this implementation.
