# T2 recommendation evidence: verified requirement-level matching

Engineering change of 21 October 2026 on `feat/t2-backend-completion`, based on
`06f24f9`, revised after an independent review of the first version (`6ef81e3`).
Controlled offline evidence against agent-authored labels; not live Store,
Angular/Rasa or proposal KPI acceptance.

## Diagnosis

Retrieval usually placed the right App first, yet users were told nothing matched.
Replaying the actual prepared dialogue path on the 32 development queries
(`evaluation/retrieval`) recommended an App for **none of the 26 positive
requests**. Three independent causes:

1. **The suitability grammar failed on ordinary READMEs.** Request terms had to be
   a literal subset of one parsed clause, and any unparsed or negative sentence
   anywhere could block an App: "flexibility bid aggregation" abstained against
   "BidRelay aggregates flexibility bids …" because of an unrelated "It does not
   forecast prices." Workaround layers (semantic recovery, function menus,
   `_related_passage`) had accumulated around it.
2. **Dialogue routing errors.** In a first request, "submit *them* to a live
   market" bound "them" to five seeded catalogue Apps; any price word ("price
   forecasting", "Does it forecast prices?") was refused as a commercial question.
3. **Presentation errors.** Summaries preferred the shortest sentence ("It does not
   forecast prices."), and quoted source vocabulary was rewritten ("bids" shown as
   "offers").

## Review of the first version

`6ef81e3` fixed recall (development 23 Pass / 6 Partial / 3 Fail) but let cosine
similarity, pool-relative scores or 75% word coverage *authorize* a
recommendation. The review reproduced unsupported recommendations ("automatically
schedule maintenance" from "Engineers review the alerts before scheduling
maintenance"; "forecast market prices and demand" from "Forecasts market
prices."), lost ownership, instruction and condition protections, an unvalidated
similarity response, and weakened adverse tests. All findings were reproduced and
are now regression tests (`test_review_probes_are_not_recommended`, run with no
and with maximal similarity).

## Design

`services/expert-recommend/app/evidence.py`; `suitability.py` is a thin boundary
(identity lookups, reviewed-support receipts, source fields).

- **Requirements.** The request is split into the functions asked for. Coordinated
  nouns and modifiers ("with encryption") stay attached and must all be evidenced;
  scaffolding and situation sentences are removed; "rather than X" and "but I
  don't need X" are not requested.
- **Nomination.** E5 similarity from Discovery (`POST /api/v2/evidence/similarity`,
  bounded, batched and clipped by the caller, scores validated as finite numbers)
  or ≥ 50% word overlap selects the sentence that best addresses a requirement.
  Nomination never establishes support.
- **Verification.** A requirement is `documented` only by a sentence that:
  is owned by this App (not another named product, `Another App …`, or people such
  as engineers, partners or users); is declarative, not an instruction or
  question; states no condition, exception or limitation ("if the customer buys
  sensors", "except in production", "pending certification", "it used to …");
  names at most one delivery channel; contains every requested term and number
  (light stemming only, no synonyms); and is not merely a purpose modifier
  ("water readings *for* earthquake warnings"). A pronoun ("Sends them via SMS",
  "Those bids are then combined …") counts only with a single, functional, owned
  antecedent in the same field. A negative requirement ("must not collect personal
  data") needs an owned statement that the App does not perform that same action.
- **Limitations** exclude or limit a requirement when they negate or qualify it,
  concern only what was requested ("SMS delivery is disabled", "Earthquake warnings
  are only available via MQTT", a condition on the requested feature), restrict a
  requested quantity, cover the part affirmative sentences leave uncovered, contradict
  the requested channel, or restrict the App as a whole ("It does not work in
  production", "Another App is required", "This feature is disabled" after a
  non-functional sentence). A requested condition ("only in simulation" when
  simulation is asked for, "only via SMS") is not a limitation; "does not require
  another App" is not one either.
- **Decision.** An App is recommended only when every requirement is documented,
  with its verbatim source sentences. A nominated but unverified sentence is a
  `related` finding: shown as the App's closest statement, never as a match ("I
  couldn't confirm an exact match, but these App descriptions come closest: …").
  Mixed results are explained per requirement. Suitability `status` is
  `source_supported`, `partial` or `uncertain`; the decision outcome for partial
  results is `abstained` with reason `partial_matches_only`, so the Angular contract
  is unchanged. Expert assesses ten retrieved candidates and returns at most the
  requested limit.
- **Unavailable or malformed similarity** removes only nominations; verification
  is identical. Unit tests run in this mode.

The unused LLM veto branch (`allow_model`) and `_related_passage` were removed.
Preparation leads with an unqualified sentence in source order and quotes source
vocabulary verbatim; `PREPARATION_VERSION` 5 re-prepares Store rows (and their
index payloads) through the existing synchronization/repair path, so a rollout
needs matching service versions and time for re-preparation.

Dialogue: pronouns route to references only once something has been discussed;
functional price wording is not a pricing question (`cost_question()`); "Which of
them can …" is decided over the displayed Apps; partial results without a focused
App skip model recovery and keep their explanation.

## Tests

- `test_suitability_original.py` is the original suitability suite, run against the
  new boundary. Changes are mechanical ("uncertain" means "not recommended"; a
  removed internal and reason name use the equivalent behaviour) except two
  marked reversals of over-restriction: "Used to publish and manage shared data
  models and mappings." (the real Store purpose sentence) and the French "Prend en
  charge MQTT." are claims; "Ne prend pas en charge MQTT." is a tested negation.
- The ownership fixture (`tests/fixtures/store-v1/suitability-ownership.json`) and
  the Gateway, Store-integration and finalization adverse cases keep their original
  labels.

## Before and after

Grades (`evaluation/recommendation`): **Pass** recommends exactly what is
supported; **Partial** recommends correctly but misses an acceptable App;
**Suggested** recommends nothing unsupported and shows a correct App as its
closest, explicitly unconfirmed statement; **Fail** recommends something
unsupported or shows no correct App.

| Set | Cases | `06f24f9` | `6ef81e3` | Now |
| --- | --- | --- | --- | --- |
| Development | 32 | 6 Pass / 26 Fail | 23 Pass / 6 Partial / 3 Fail (1 unsupported) | 8 Pass / 3 Partial / 19 Suggested / 2 Fail (0 unsupported) |
| Unseen-1 | 24 | 8 / 16 | 18 / 2 / 4 (3 unsupported) | 10 Pass / 13 Suggested / 1 Fail (0 unsupported) |
| Unseen-2 | 20 | 7 / 13 | 13 / 2 / 5 (3 unsupported) | 10 Pass / 1 Partial / 8 Suggested / 1 Fail (0 unsupported) |
| Private real-Store observation | 10 | 5 Pass / 5 Fail | 9 / 1 | 5 Pass / 4 Suggested / 1 Fail (0 unsupported) |

Unseen-1 informed the first version's rules. This revision was driven by the
review probes, the original adverse tests and the authored conversations, not by
the unseen sets; their replies were read only to check wording. Before, every
"Fail" on a positive case meant "I couldn't find a matching App for that request."

Representative replies (prepared path, no model):

- *flexibility bid aggregation* — "**BidRelay** fits what you need. BidRelay
  aggregates flexibility bids from several providers and submits a combined bid to
  the energy market operator."
- *Our departments use conflicting field names. We need one place to agree what
  those fields mean.* — "I couldn't confirm an exact match, but these App
  descriptions come closest: **MeaningHub**: Teams can agree the meaning of fields
  across their organisations. **ModelCommons**: Partner organisations discuss field
  definitions and version approved models."
- *Detect bearing failures from vibration data and automatically schedule
  maintenance* — no recommendation; TurbineWatch's closest statements are shown,
  including "Engineers review the alerts before scheduling maintenance."
- *Does it forecast prices?* (about BidRelay) — "No. BidRelay's description says:
  It does not forecast prices."

## Remaining limits

- **Paraphrases are suggested, not recommended.** Verification needs the request's
  terms in the source sentence, so "Store past flexibility bids for an audit"
  against "stores historical flexibility offers for audit" is a closest statement.
  Recommending such paraphrases needs reviewed term alignment (for example a vetted
  domain glossary or a verified entailment step), not a similarity threshold.
- **Missed entirely:** four authored cases (hard paraphrases, a homonym in the gap
  rule, a simulation-before-live request) and one real case where "common
  definitions and mappings" is read as two requirements.
- Ownership uses product-like subjects (CamelCase, multi-word capitalized names,
  acronyms) and a closed list of human roles; an unknown single-word product name
  as a subject is treated as this App.
- Thresholds and rules come from a 20-App fictional catalogue and two real Apps.
  Evaluations use dense-only candidate pools and bypass Rasa and the model-assisted
  recovery path (`STORE_SEMANTIC_ENABLED`), which still runs when nothing is nominated.
- Non-English requests keep only basic lexical behaviour.
