# T2 recommendation evidence: requirement-level matching

Engineering change of 21 October 2026 on `feat/t2-backend-completion`, based on
`06f24f9`. Controlled offline evidence against agent-authored labels; not live
Store, Angular/Rasa or proposal KPI acceptance.

## Diagnosis

Retrieval usually placed the right App first, yet users were told nothing matched.
Replaying the actual prepared dialogue path on the 32 development queries
(`evaluation/retrieval`) recommended an App for **none of the 26 positive
requests**. Three independent causes:

1. **Suitability was a hand-written entailment grammar.** `assess()` required
   the request's terms to be a literal subset of one parsed source clause, and
   any unparsed or negative sentence anywhere in an App could block it. BidRelay's
   README says "BidRelay aggregates flexibility bids from several providers", yet
   "flexibility bid aggregation" abstained because of an unrelated "It does not
   forecast prices." Paraphrases could never pass. Much of the grammar was
   special-cased to the two real Store READMEs; other layers (semantic recovery,
   function menus, `_related_passage`) had been added to work around it.
2. **Dialogue routing errors.** In a first request, "submit *them* to a live
   market" bound "them" to five seeded catalogue Apps and answered with their
   descriptions. Any price word ("day ahead electricity price forecasting",
   "Does it forecast prices?") was refused as a commercial-terms question.
3. **Presentation errors.** The extractive preparer preferred the shortest
   sentence, so BidRelay's summary was "It does not forecast prices.", and the
   presenter rewrote quoted source vocabulary ("bids" became "offers").

## Design

`services/expert-recommend/app/evidence.py` replaces the grammar; `suitability.py`
is now a thin boundary (identity lookups, reviewed-support receipts, source fields).

- **Requirements.** The request is split into the functions asked for
  ("combine bids, submit them to a live market and calculate settlement" → three).
  Coordinated nouns and modifiers stay attached, scaffolding is removed, situation
  sentences ("Our departments use conflicting field names.") are context, and
  "rather than X" / "but I don't need X" are not requested.
- **Source sentences.** Whole sentences per functional field, plus contrastive
  parts and coordinated predicates. Referring sentences ("Sends them via SMS",
  "Those bids are then combined …") are assessed and quoted with their antecedent
  in the same field. Instructions, questions and other actors' statements are not
  App claims.
- **Matching.** Each requirement is scored against every candidate sentence with
  the pinned E5 model (new Discovery route `POST /api/v2/evidence/similarity`)
  plus normalized lexical coverage. E5-small cosine scores sit in a narrow band,
  so a semantic match must be very close (≥ 0.87) or stand out from the pool's
  sentences for that requirement (z ≥ 2.0, ≥ 0.83), and low-overlap matches must
  share at least one term with the App's own wording; short titles need shared
  vocabulary; numbers must appear in the source. Negated sentences are matched on
  their topic ("forecast prices"), because E5 under-rates negations; polarity is
  read separately.
- **Limitations.** A requirement is *excluded* or *limited* when the matched or an
  equally strong sentence negates or qualifies it; when a limitation concerns only
  what was requested ("SMS delivery is disabled", "Earthquake warnings are only
  available via MQTT"); when a limitation covers the part no affirmative sentence
  covers ("does not forecast market prices" for a demand forecaster asked for
  prices); or when it restricts the App as a whole ("It does not work in
  production", "Another App is required"). "Does not require another App" and a
  requested condition ("only in simulation" when simulation is asked for) are
  not limitations. Unrelated limitations no longer veto.
- **Decision.** Complete Apps (every requirement documented) are recommended with
  their verbatim source sentences. Otherwise suitability `status` is `partial`
  (with per-requirement `requirements` findings) or `uncertain`; the decision
  outcome stays `abstained` with reason `partial_matches_only`, so the Angular
  contract is unchanged (`source_supported` remains the only recommended status).
  Expert assesses ten retrieved candidates and returns at most the requested limit.
- **Unavailable similarity.** Without `DISCOVERY_RANKING_URL`, or after a failed
  call (30 s back-off), matching is lexical-only and more conservative. Unit tests
  run in this mode.

The unused LLM veto branch (`allow_model`) and `_related_passage` were removed.
Preparation now leads with an unqualified sentence in source order and quotes
source vocabulary verbatim; `PREPARATION_VERSION` 5 re-prepares Store rows on the
next synchronization or `/internal/store/repair`.

Dialogue: pronouns route to references only once something has been discussed;
functional price wording is not a pricing question (`cost_question()`); "Which of
them can …" is decided over the displayed Apps; partial results skip semantic
recovery and keep their explanation.

## Before and after

| Set | Cases | Before (`06f24f9`) | After |
| --- | --- | --- | --- |
| Development (frozen + holdout) | 32 | 6 Pass / 26 Fail; all 26 positives abstained | 23 Pass / 6 Partial / 3 Fail (1 unsupported, 2 abstained) |
| Unseen-1 (informed rule changes) | 24 | 8 Pass / 16 Fail | 18 Pass / 2 Partial / 4 Fail (3 unsupported, 1 abstained) |
| Unseen-2, rules frozen | 20 | 7 Pass / 13 Fail | 13 Pass / 2 Partial / 5 Fail (3 unsupported, 2 abstained) |
| Unseen-2 after one post-hoc parsing fix | 20 | — | 13 Pass / 3 Partial / 4 Fail (3 unsupported, 1 abstained) |
| Private real-Store observation (2 Apps) | 10 | 5/10 | 9/10 |

Before passed only cases where nothing should be recommended. "Partial" means a
correct recommendation that missed an acceptable alternative.

Representative replies (prepared path, no model):

- *flexibility bid aggregation* — before: "I couldn't find a matching App for that
  request." After: "**BidRelay** fits what you need. BidRelay aggregates
  flexibility bids from several providers and submits a combined bid to the energy
  market operator."
- *One App must publish shared vocabularies and transform incoming JSON payloads* —
  before: no match. After: "No single App documents everything you asked for",
  then per App what it covers and, e.g., "It doesn't cover 'transform incoming JSON
  payloads'; its description says: Payload transformation is not performed by this
  application."
- *Does it forecast prices?* (about BidRelay) — before: "No price is listed for
  BidRelay." After: "No. BidRelay's description says: It does not forecast prices."
- *Show me all available apps* — summaries now lead with what each App does
  instead of its limitations.

## Remaining failures and limits

- **Domain-adjacent false recommendations** (the main residual risk; 7 of 76
  authored cases): the domain matches but the requested function differs, which
  E5-small cannot separate — demand vs price forecasting (U5), "manual library"
  vs vibration analysis (U19), "stop command" vs alerts (U12), "automatically
  schedule maintenance" vs "engineers review the alerts before scheduling
  maintenance" (V9), "SMS alerts" (V17), "maintenance manuals" vs "maintenance
  notes" (V16), rainfall vs weather inputs (N4). Lexical rules that caught these
  also rejected genuine paraphrases. The quoted sentence makes the mismatch
  visible, but these are still wrong recommendations. A stronger embedding or
  cross-encoder, or verification of low-overlap matches, is the next step.
- **Missed matches:** hard paraphrases ("common dictionary for exchanged
  information"), a homonym in the gap rule ("*field* devices" vs "*field*
  meanings", V3), and noun coordination read as two requirements ("common
  definitions and mappings", real R4, still answered as an honest partial).
- Thresholds were chosen on 32 development queries over a 20-App fictional
  catalogue; two real Apps are far too few to validate them.
- Candidate pools in the evaluation are dense-only, and the model-assisted
  semantic recovery path (`STORE_SEMANTIC_ENABLED`) was not exercised: it still
  runs, with its latency, when nothing matches.
- Non-English requests keep only the previous lexical behaviour.
