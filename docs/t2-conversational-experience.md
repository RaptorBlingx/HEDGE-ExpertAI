# T2 conversational experience: grounded, layered explanations

> **Superseded for dialogue policy (22 October 2026).** Store turns are now interpreted and executed by the [conversational architecture](t2-conversational-architecture.md); the dialogue modules named below were removed. The explainer, App guide, glossary and verifier described here remain.

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

## Live-model and end-to-end validation (21–22 October)

**Isolation.** A separate container ran the approved Ollama binary and Qwen3 4B
Q4_K_M files, mounted read-only exactly as the 8156 model service mounts them, on
its own internal network with the same limits (3 GiB, 1.5 CPU, one parallel
request, q8_0 KV cache, 2048-token context). A watchdog stopped *only* this
container whenever the 8156 model loaded (a real user) or host memory fell below
its floor; it fired twice for memory, never for user activity. Nothing in the 8156
project was restarted or contacted; all evaluation resources were removed.

**Conversations.** `live.json` (written before the first live run: open
questions, an exhausted explanation ladder, unknown terms, planner-only phrasing)
and the model-dependent turns of the development and held-out sets were run
through the dialogue with the live model, and every answer was read.

The first live run exposed defects the offline harness could not:
questions outside the act grammar ("Can I rely on its forecasts for trading?",
"Could you break that down?", "What has the weather got to do with it?") reached
the ~780-token planner, took 63–88 s and were turned into capability checks
answered "fits what you need"; "So who gets paid in the end?" was read as a
pricing filter; the model invented a negative claim ("OfferBridge itself does not
handle payments") and audiences ("data engineers or domain experts"). Fixes:
conversational questions about an App in the conversation go to the cited
explainer; capability follow-ups reinterpret only when the verifier found nothing
without similarity; statements are chosen by glossary concept as well as by word;
App-subject negations need a stated limitation; answers do not open with a bare
verdict; "who is it for?" is a prepared answer from documented roles; an
exhausted ladder asks which part is unclear (a generated rephrase took 39 s and
was worse than the prepared analogies).

After the fixes: in the live set, 13 model turns, median 18 s and at most 32 s,
no planner calls and no recommendation from an explanation turn; checks stopped
3 answers at a failing sentence, with a visible note. Answers were useful and
mostly well hedged ("The statements do not say how accurate PriceLens is",
"Automatic settlement is not available now. It is planned for a future
release."). The 4B model still adds small unstated specifics ("devices like wind
turbines", "supply chain partners"), framed as reasoning; these remain a risk.

**End to end.** This branch's Gateway, Chat, Expert and Discovery ran from
read-only source in hardened containers with disposable PostgreSQL and Valkey and
a copy of the two authorized Apps; the approved Angular build was served unchanged
by a loopback copy of the deployment adapter and driven by headless Chromium.
Prepared pass (E5, no model): 19 turns over four conversations all completed, a
typical turn ~0.25 s, the first search 9.5 s (E5 cold start); badges appeared only
on the documented match. Model pass (Discovery without E5): streamed answers
arrived as 3–5 checked sentences; first sentence after 6.6–16.3 s, complete in
15–28 s; with the model stopped, an open question received the prepared fallback
in 0.23 s. The only browser console errors were `/api/v2/status` 503s because
metadata-ingest was not started.

## Review corrections (22 October)

An independent review accepted the branch with three confirmed defects, each
reproduced here by a failing test before the fix:

- **A clicked card answered about the previously focused App.** The inspection
  action now resolves its own native `(store_id, app_id)` against the current
  catalogue; if that does not resolve, the explanation path declines and the
  existing prepared path reports the App as unavailable.
- **User wording could ground a generated claim.** The sentence checks allowed
  quantities and guarantee/integration words that appeared in the question or an
  earlier answer. Only source statements and the curated glossary notes ground
  claims now; a number the user mentions is no longer repeatable as an App fact.
- **Withdrawal was checked only after streaming.** Every streamed sentence is now
  released only if the App's current authorized record still equals the one being
  explained, the same comparison a completed reply gets. After a change nothing
  more is released, and the stored reply is the released text followed by the
  catalogue-changed notice, so no later validation rejects text already shown.
  The planner hand-off uses the same guard.

## Performance

| Turn | Before (observed 8156) | Now |
| --- | --- | --- |
| Explanation acts (simple, meaning, example, compare, term, audience) | 13–43 s with Qwen | 0–30 ms prepared |
| Decided capability follow-up | 73 s (planner) | 0.1–0.4 s |
| Open question, widget | not available | first sentence 6.6–16.3 s, complete 15–28 s |
| Search | 0.4 s | 0.1–1.4 s (9.5 s cold E5) |

Prompt reading dominates CPU latency: ~14 prompt tokens/s and ~5 output tokens/s
were measured on the evaluation copy. Open-question prompts are 260–380 tokens;
the planner's are ~780.

## Remaining limits

- The model can still embellish with unstated specifics; sentence checks catch
  links, quantities, guarantees, integrations and unsupported negations, not
  entailment. Read-before-release is not possible while streaming.
- Without Discovery similarity (degraded mode), an undocumented capability
  follow-up still reaches the planner (72–74 s observed).
- **Operational risk for 8156:** the evaluation copy was OOM-killed inside its
  3 GiB limit after ~25 minutes of varied prompts, with no model reload; memory
  grows with Ollama's prompt cache. The deployed model service has the same
  version and limit (2.89 GiB observed earlier) and may need more headroom or
  periodic recycling under varied traffic. Not changed here.
- Glossary definitions are agent-authored and need domain review.
- The act grammar is English-only; Rasa was not in the loop; no real-user session.
- Recommendation strictness is unchanged: paraphrases are closest statements.
- 27 integration tests fail identically on `a2a02ad` and this branch (stale wording
  expectations and legacy playground 503s); 206 pass on both.

Private transcripts, browser results, screenshots and model timings are outside
Git at `/home/ubuntu/.local/share/hedge-t2-conversation-20261021/`.
