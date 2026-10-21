# T2 conversational experience: grounded, layered explanations

Engineering change of 21 October 2026 on `feat/t2-conversational-experience`, based
on `a2a02ad`. Controlled offline evidence through the repository's own dialogue
code; not live-model, browser, real-user or proposal-KPI acceptance.

## Problem

The 8156 prototype (Qwen3 4B on a 1.5-CPU model service) answered "What does that
mean?" or "Explain it differently" with near-paraphrases of one source sentence,
took 13–73 seconds per model turn, sometimes overgeneralized (a data-model App
explained as household wiring; "settlement" rendered as "payments"), lost the
discussed App after a capability follow-up, and answered "Compare both Apps in
plain English" with a fixed template. An audit traced this to:

- **Context starvation.** The explainer received one purpose sentence; the
  sentences that make an App understandable (schemes, roles, features) were
  excluded because they were *qualified*, a verification rule misapplied to
  explanation.
- **A prompt that forbade the needed answer.** All prose had to be an App fact,
  in 45 words, keeping the source nouns, with no channel for general background.
- **No explanation strategy.** Temperature 0, the same single sentence and no
  record of what had been explained produced repeated answers.
- **Model effort in the wrong place.** A ~780-token planner classified intents
  (65 s of prompt reading at ~12 tokens/s) and guard rules then overrode it.

## Design

Two kinds of content are kept visibly apart in every answer:

| | Source | Authority |
| --- | --- | --- |
| What an App's description says | `expert-recommend/app/app_guide.py`, a pure function of its current Store source | Documented claims, quoted or attributed |
| General background | `hedge_shared/glossary.py`, 58 domain concepts with plain definitions, reasons, illustrative examples and analogies | Labelled general background; never App evidence |

- **App guide.** Complete, owned sentences from description, dataspace description
  and README, classified as purpose, capability, scheme, limitation, access,
  attribution or context (another actor, such as "Engineers review the alerts").
  Instructions ("Ignore previous instructions …", "Say that it guarantees …"),
  other products and release boilerplate are excluded; quotes remain exact source
  substrings; the preparer's linked restatement ("It combines bids …") is reused.
  Because the guide is derived from current authoritative fields and cached by
  their digest, newly ingested Apps and source revisions need no separate
  preparation job, migration or reindex.
- **Glossary.** Domain background for energy flexibility, markets, grids, IoT,
  data definitions, data spaces, maintenance and access. It is agent-authored and
  marked `agent_authored_pending_domain_review`; a domain expert should review it.
  It never reaches the recommendation verifier.
- **Conversation acts** (`chat-intent/app/conversation_acts.py`): one closed
  grammar for overview, simplify, "what does that mean", term definitions,
  examples, analogies, "explain it differently", plain comparison, choosing,
  provider-and-access and open questions. Capability checks ("Does it …?",
  "Can it …?"), searches, filters, metadata reads and criteria comparisons are
  deliberately *not* acts and keep their verified paths. Subjects come from named
  Apps, the focused App, the displayed Apps or recently discussed Apps
  (`discussed_ids`), never from a model guess.
- **Explainer** (`expert-recommend/app/explainer.py`). Each App has a ladder of
  representations: overview → simple (background, then definitions of the
  concepts it builds on, then what the App does in its own words, plus a stated
  limitation) → analogy → example (documented schemes or workflow first, then a
  scenario labelled "made up to show the idea … not taken from the App's
  description") → step by step. "Explain it differently" and "What does that
  mean?" move to a representation not yet used for that App, and per-conversation
  state avoids redefining terms or repeating the last statement. When the ladder
  is exhausted the assistant asks which part is unclear. Comparisons say what each
  App does, whether their areas overlap, what only one documents, their stated
  limitations, and, for "why choose …", which job each fits.
- **Model use.** Only questions the prepared layers cannot answer (open
  questions, undefined terms, a further "explain it differently") call Qwen, once,
  with a small prompt: up to four whole, short source statements, at most two
  background notes and, only if the question refers back, the start of the
  previous answer. Answers cite statement keys and are released **one checked
  sentence at a time** (citations exist; no links or markup; no quantities or
  guarantees, certifications, integrations, automation or security claims absent
  from the sources). The first failing sentence stops the answer with a visible
  note; released text is never withdrawn. The streaming widget receives these
  sentences through the existing `explanation_delta` event, so the approved
  Angular build is unchanged. The call reuses the deployment's context size,
  threads, batch and keep-alive, so Ollama never reloads the model.
- **Model-planner interplay.** Capability follow-ups the verifier already decided,
  either an explicit "no" or nothing related after similarity screening (new
  `screened` metadata, not an authorization input), skip the ~780-token planner.
  A pronoun-referenced focused App survives planner search proposals. Planner
  readings of simple/purpose/workflow/comparison hand off to the explainer.
  The planner still runs where it adds value: recovering a paraphrased capability
  before the same verifier decides.
- **Dialogue fixes.** "Find me one that does" searches for the previous
  capability need; "Which one …?" / "Which of the two …?" after a comparison
  decide over the displayed Apps; unconfirmed capability answers say what the App
  does document and quote its most related sentence as context; several known
  Apps without confirmation get a per-App answer instead of "Which App do you
  mean?".

The previous single-call elaborator (`store_elaboration.py`, `/internal/store/elaborate`)
is removed; its safety properties (no authorization, retained limitations, other
actors and instructions excluded, invalid grounding falls back without retry) are
covered by `tests/unit/test_conversation_explanations.py`.

## Correctness boundary

Unchanged: `evidence.py` remains the only authority for `source_supported`.
Explanation turns return `decision: not_applicable / source_explanation`, never
call the decision function, create no reviewed-support receipt, and generated
text is never stored as Store evidence or indexed. On both unseen recommendation
sets the decisions of `a2a02ad` and this branch are identical case by case
(unseen-1: 10 Pass / 13 Suggested / 1 Fail; unseen-2: 10 Pass / 1 Partial / 8
Suggested / 1 Fail). Original adverse suites are unmodified; two dialogue tests
changed only the wording of the unconfirmed-capability answer.

## Evaluation

`evaluation/conversation/` replays multi-turn conversations through the real
chat routing (regex NLU), StoreConversation, Expert decisions, presenter and
explainer, with E5 dense candidate pools, no network and no model. Checks are
coarse (subject retained, expected concepts, forbidden phrases, outcome, model
use, 5-gram repetition); the replies were read.

| Set | Authored | Turns | Flagged | Read as good | Notes |
| --- | --- | --- | --- | --- | --- |
| Development, real Store (private) | replays of the observed 8156 conversations | 19 | 0 | 19 | |
| Development, fictional | before implementation | 9 | 0 | 9 | |
| Held-out 1 | before implementation | 28 | 4 → 1 | 22 → 26 | first run, then after the mechanism fixes it revealed |
| Held-out 2 | after reading held-out 1, before those fixes | 24 | 1 → 1 | 21 → 23 | first run measured the fixes; then two grammar fixes it informed |

"Read as good" means the reply answers the turn usefully, keeps its subject and
claims nothing undocumented. Both held-out sets have now informed fixes, so
neither is a clean measure any more; a new independent set is needed for the
next round. Remaining weak turns: a strict paraphrase that the verifier only
shows as a closest statement ("sensor data" vs "sensor telemetry"); an open
question answered by the no-model fallback ("How would a utility use it in
practice?"); and a capability question without a pronoun while an App is in
focus ("Is automatic settlement available now?"), which becomes a catalogue
search when the model is off.

Representative replies (fictional catalogue, prepared, no model):

- *What does that mean?* (after "What is TurbineWatch?") — "**The background, in
  general terms:** Machines wear out. Their measurements can reveal problems early
  … **Vibration analysis**: measuring how a machine shakes; a change in the
  vibration pattern can reveal damaged parts … **What TurbineWatch does, according
  to its description:** it analyses gearbox vibration measurements and flags
  patterns associated with bearing failures. One limitation it states: “It does
  not control turbine operation.”"
- *Can it schedule maintenance automatically?* — "I couldn’t confirm that from
  **TurbineWatch**’s description. What it does document: … It also says:
  “Engineers review the alerts before scheduling maintenance.”"
- *Compare the two in plain English* (MeterScope, LoadAhead) — both are about the
  same area, each documented job, "only LoadAhead’s description covers
  *forecasting*", and both stated limitations.
- *Tell me about CommandCard* (an injection fixture) — "**CommandCard** stores
  maintenance notes." Nothing of "Ignore previous instructions" or the claimed
  5000 bids per second appears in any answer.

## Performance

Measured in the offline harness (one capped CPU): explanation acts take 0–30 ms;
search and decision turns 0.1–1.4 s (E5 included). In the observed 8156 widget
conversations, the same explanation requests took 13–43 s with Qwen and a
capability follow-up 73 s. These now need no model call.

Model-assisted answers were **not run live** (see limits). Deployment logs give
the 8156 model service's rates: ~12 prompt tokens/s and ~4.5 output tokens/s.
The open-question prompt is 1,100–1,350 characters for the real Apps (the removed
elaborator's was ~1,700 characters, measured at 474 tokens), of which ~600 are
the stable system prompt reusable from the model's prefix cache. Expect roughly
15–25 s before the first checked sentence and 35–50 s for a complete 80-word
answer on this hardware, a minority of turns rather than every explanation.

## Remaining limits

- **Live model behavior is unverified.** The 8156 model is reachable only on the
  deployment's internal network, which also carries its database, so isolation
  could not be verified, and no second model fits in memory. Grounding of
  generated sentences, citation discipline of the 4B model, and real latency need
  a bounded, authorized run (`evaluation/conversation/run.py --model-url`).
- Glossary definitions are agent-authored and need domain review; concepts outside
  it get no prepared definition (the model, if enabled, answers them as labelled
  general background).
- The act grammar is English-only and closed; unknown phrasings fall through to the
  existing paths (and to the planner when the model is enabled).
- Structural sentence checks are not entailment; a generated sentence can still
  overstate a cited statement.
- Recommendation strictness is unchanged: paraphrases are closest statements.
- No isolated browser or HTTP-stack run of this branch was performed; the
  streaming path is covered by unit tests through FastAPI test clients.
- 27 integration tests fail identically on `a2a02ad` and this branch (stale wording
  expectations and legacy playground 503s); 206 pass on both.

Private transcripts are outside Git at
`/home/ubuntu/.local/share/hedge-t2-conversation-20261021/`.
