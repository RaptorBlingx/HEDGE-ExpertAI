# SCRUM-39: recommendation evidence and abstention

> Dated report. The clause grammar described here was replaced on 21 October 2026
> by requirement-level evidence matching; see
> [T2 recommendation evidence](t2-recommendation-evidence.md).

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

Re-review of `3e276bcaf5d954f3be0d7973b028136180cab6bc` reproduced three
structural defects despite those original cases passing:

- The positive warning/SMS description plus README `SMS delivery is disabled.`
  still produced `source_supported` and a recommendation impression. A restriction
  on one required component did not pass the whole-query containment check.
- `Provides earthquake warnings. Another App is required for this feature.`
  was recommended because the foreign-actor prefix deleted the prerequisite.
- `Earthquake warnings and water readings are available. Sends water readings
  via SMS.` was recommended for earthquake warnings by SMS. Group-level term
  union transferred the water readings' channel to a different feature.

All three reproduced through normal/SSE Gateway output and the disposable Store
pipeline. The retained 62-observation review probe included 22 unsupported
recommendation observations before this correction; all 62 now match expected
decisions. The new permanent Gateway cases initially reproduced 26 failures in
60 observations, including positive controls, before changing admission code.

The final review of `ec6503f` exposed two remaining structural gaps: an exclusive
MQTT restriction was treated like a prohibition of MQTT, and a negated prerequisite
discarded a later SMS prerequisite in the same sentence. A feature-wide simulation
restriction also vanished when its predicate mentioned a channel. Before this
bounded correction, the retained Gateway probe reproduced 14 unsupported decisions
in 48 observations; the disposable Store run reproduced all three source failures
(3 failed, 144 passed). The initial added Gateway regressions reproduced 30 failing
assertions before changing production code. After correction the 48 observations
all match their expected decisions, including failed-generation fallback.

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

Each bounded source assertion now retains a feature owner, its explicitly attached
attributes, qualification kind/scope, interpretation completeness, original field
path and complete original sentence/segment. Status derives from that interpretation;
source spans remain internal and the public result schema is unchanged. There
are no groups that union distinct feature terms. Coordinated subjects and objects
produce separate owned assertions through the same resolver. An unbound reference
or unresolved App-wide statement cannot supply capability evidence. Recognized
predicates and availability states establish assertions; negation, conditional/
future language and uninterpreted context cannot establish unconditional support.

Attributes compose only for the same normalized feature owner. An unambiguous
immediate reference or bounded local noun-head repeat (`warnings` referring to
`earthquake warnings`) can retain that owner within a field and paragraph.
`Provides earthquake warnings. Sends them via SMS.` therefore supports delivery
of those warnings by SMS. Coordinated owners make a following bare reference
ambiguous, regardless of whether their declaration uses an action or an
availability state. An explicit water-reading delivery statement contributes only
to water readings. `Provides earthquake warnings. Supports SMS.` does not establish
a delivery relationship. Explicit independent conjunctions can require separately
supported features. References do not cross fields; explicit repeated owners can
still carry their own attributes in another field.

Restrictions are checked against each required feature and attribute across all
available functional fields, including README and embedded descriptions. Partial
overlap retains uncertainty rather than requiring the restriction to repeat the
whole query. Thus `SMS delivery is disabled` qualifies a requested SMS channel.
An explicitly scoped `Water readings via SMS are disabled` stays on water readings;
`Earthquake warnings via MQTT are disabled` does not erase separately affirmed SMS
delivery. A qualification with unresolved scope qualifies the App rather than
vanishing. Recognizable unrelated restrictions and privacy statements remain
separate from the requested feature.

Dependencies are interpreted before other-actor assertions. Active requirements
and passive prerequisites qualify their target feature/channel; an unknown or
ambiguous target remains uncertain. Only a parsed assertion about another actor's
capability is ignored as evidence for this App. Explicit absence of a prerequisite
supplies no capability evidence and does not negate an otherwise supported
capability. These are bounded grammatical relationships, with no additional model
call, NLP framework, similarity threshold or dependency/ranking redesign.

### Qualification and completeness contract

Qualification kind is separate from grammatical scope. Feature availability and
environment/conditional restrictions retain feature-wide force despite incidental
transport text. An explicitly channel-qualified subject binds its restriction to
that feature/channel. Direct negative delivery assertions can also prohibit a
channel. Unknown or inconsistent attributes cannot narrow uncertainty and thereby
erase a restriction. Nothing attempts to prove that an installation prerequisite
or environment condition has been satisfied.

An exclusive channel assertion supplies an allowed-channel set, not a prohibition
of that set. Independently affirmed delivery can be corroborated when the requested
channel is allowed and no affirmed channel conflicts. Without an explicit requested
channel, the exclusive limitation remains uncertain. A qualified assertion alone
does not manufacture affirmative evidence.

| Source added to independently supported warning/SMS evidence | Request | Decision |
|---|---|---|
| Warnings only available via MQTT | Warning/SMS | Uncertain: exclusivity conflicts |
| Warnings only available via SMS | Warning/SMS | Supported: matching channel corroborated |
| Warnings via MQTT disabled | Warning/SMS | Supported: different channel |
| Warnings only available in simulation via SMS | Warnings, or warning/SMS | Uncertain: feature environment restriction |
| Warnings via MQTT available only in simulation | Warning/SMS | Supported: explicitly different channel |
| Another App required for SMS delivery | Warning/SMS | Uncertain: requested-channel prerequisite |
| `Earthquake warnings do not require another App, but SMS delivery requires another App.` | Warning/SMS | Uncertain: compound is not silently discarded |
| `Earthquake warnings do not require another App.` | Warning/SMS | Preserve independent positive support |
| Water readings via SMS disabled | Warning/SMS | Supported: different feature |

Only bounded atomic assertions, understood nominal lists and the existing simple
action coordination are interpreted. Unhandled contrast, parenthetical/comma
compounds, nested transports or unconsumed dependency arguments become explicit
incomplete evidence with unresolved scope. They cannot support a recommendation
or be discarded as an absent prerequisite/foreign actor. Sentence, semicolon and
paragraph boundaries remain supported; references do not cross fields/paragraphs.
The existing matching subject/predicate transport form remains valid.

Complete active/passive prerequisite interpretation is deliberately limited to the
existing external-actor forms (`another App`, `other Apps`, `an external service`)
and a simple target. Other argument structures retain uncertainty, including
negated ones. This bounds interpretation rather than expanding a noun vocabulary
or attempting general compound parsing. Ordinary substantive colon-labelled states
retain their source and owner; a colon cannot hide a tail in a discarded argument.
Unknown source language, paraphrase and unresolved relationship limitations remain.

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

SCRUM-58's fresh integration verification and explicitly bounded development-only
npm exception are recorded in [integration evidence](security/SCRUM-58-integration.md).
The original audit failure below remains historical evidence, not a clean CI claim.

- 1,058 unit tests pass with 93.58% shared-package branch coverage (80% gate).
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
- The shared authored `tests/fixtures/store-v1/suitability-ownership.json` corpus
  contains 72 cases (24 positive / 48 uncertain) through both Gateway paths and
  real Store persistence/retrieval, including 39 additional qualification and
  completeness cases. The retained sparse and coherent multi-sentence positives
  still pass; source-span tracing also protects full qualification provenance.
  It covers partial/cross-field/embedded restrictions, dependency polarity and
  scope, wrong-feature channel transfer, active/state declaration variants,
  ambiguity and sparse/coherent positives. The exclusive-channel, environment and
  compound-prerequisite failures and a matching-channel positive additionally
  exercise every existing selection/
  abstention/timeout/transport/malformed-output branch through both Gateway paths.
- 170 committed focused integration tests pass with disposable PostgreSQL 16.9, Qdrant 1.18.2
  and Valkey 8.1.3 on a unique internal network, no host ports and ephemeral storage.
  Invented Store records traverse the real normalizer, storage, indexing, lexical/
  vector search and recommender. An unrelated dense Water Meter neighbour remains
  unverified; a sparse warning description is admitted, simulation-only warnings
  remain uncertain, and current withdrawal overrides stale vector evidence.
  Existing native identity, revision, metadata, indexing and dialogue tests pass.
  Thirteen added review cases prove the record was retrieved before admission,
  preserve the original description/README, native identity, checksum and revision,
  compare stream/non-stream output, and withdraw it while its vector is stale.
  All 72 ownership/qualification cases additionally preserve raw optional fields/
  checksums and test withdrawal with a stale vector. All 16 retained independent-
  review assertions pass in that infrastructure, for 186 integration checks in
  the corrective verification run. The permanent tests include all prior cases.
- The SCRUM-38 1,254-/16,001-character README regressions retain complete omission/
  extraction-status handling and streaming parity. Legacy standalone explanation
  remains usable without inventing a missing App identity.
- Ruff and 25 frontend tests pass; all six OpenAPI exports match tracked files.
  The original branch's TypeScript/Vite build and widget syntax checks passed
  using pinned Node 20.19.4; this correction changes no frontend code or public
  schema. Frontend tests and OpenAPI comparisons were rerun for this correction.
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
