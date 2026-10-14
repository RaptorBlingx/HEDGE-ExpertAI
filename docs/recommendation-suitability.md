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

The deterministic admission baseline requires all content terms in one functional
source sentence, with simple plural/verb normalization. Request scaffolding is
removed; restrictions and negation are retained. Qualified or negative support is
uncertain. Explicit general production limitations also qualify otherwise positive
fields. Unrelated feature restrictions and privacy statements do not automatically
veto positive evidence for another topic. Requests with unresolved constraints
remain uncertain. There is no similarity threshold, required metadata count,
minimum description length, provider/ontology admission or ranking-policy change.
A single sparse description such as `Warns about earthquakes.` can support
`Find apps for earthquake warnings`.

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

- 710 unit tests pass with 93.58% shared-package branch coverage (80% gate).
  Source admission tests cover sparse positives, negation, simulation restrictions,
  unrelated limitations, README/embedded provenance, malformed optional fields,
  unsupported provider/price/ontology evidence, and constrained queries.
- Real Discovery → Expert → Chat → Gateway HTTP routes exercise positive,
  unrelated and qualified earthquake requests, structured model abstention,
  stream/non-stream decisions, source-only prose and absence of recommendation
  impressions on abstention. Existing SCRUM-28 error regressions remain passing.
- 85 focused integration tests pass with disposable PostgreSQL 16.9, Qdrant 1.18.2
  and Valkey 8.1.3 on a unique internal network, no host ports and ephemeral storage.
  Invented Store records traverse the real normalizer, storage, indexing, lexical/
  vector search and recommender. An unrelated dense Water Meter neighbour remains
  unverified; a sparse warning description is admitted, simulation-only warnings
  remain uncertain, and current withdrawal overrides stale vector evidence.
  Existing native identity, revision, metadata, indexing and dialogue tests pass.
- The SCRUM-38 1,254-/16,001-character README regressions retain complete omission/
  extraction-status handling and streaming parity. Legacy standalone explanation
  remains usable without inventing a missing App identity.
- Ruff passes; 25 frontend tests pass; TypeScript/Vite build and widget syntax
  checks pass using pinned Node 20.19.4. All six OpenAPI exports match tracked files.
- `npm audit --audit-level=high` fails with 8 high and 4 moderate advisories in
  the unchanged baseline dependency lockfile. Dependency remediation is separate
  from this issue; the branch cannot be represented as fully green CI.

## Limits and owner acceptance still required

Direct textual support is a conservative baseline, not semantic entailment or a
calibrated suitability classifier. Paraphrases, multilingual requests, capabilities
requiring several sentences, implicit constraints and conflicting/complex source
claims may remain unverified. They remain visible for inspection; abstention does
not establish that an App lacks a feature. Source assertions are attributed claims,
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
