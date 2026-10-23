# T2 operation and reference boundaries

Bounded follow-up from `2cde320` on `feat/t2-backend-completion`. That clean
checkpoint was pushed normally to Forgejo and the remote SHA verified. This
follow-up remains local. No model weights, Rasa corpus, UI, dependencies,
retrieval/ranking, ingestion or existing deployment configuration changed.

## Confirmed causes and changes

The four previous final-holdout failures were reproduced at the prepared-parser
boundary against `2cde320`. Their complete actual baseline widget answers and
model/NLU traces were retained; expensive baseline model calls were not repeated.

- The source-field parser recognized direct questions but failed to compose
  request wrappers, possessive/nominal fields and complete App targets. Provider
  requests therefore reached Qwen with an unrelated previous functional need.
  The existing parser now composes these parts before catalogue resolution.
  `provider`/`supplier` identify the existing provider field; this is operation
  vocabulary, not App capability knowledge or a per-App answer table.
- Source reads could ask Qwen to re-resolve an already parsed target. A model
  reference could then discard a valid discussed App or widen an unknown target.
  Parsed source reads now retain the application-owned operation and scope.
  Exact native identity, unique focus, peer, displayed ordinal and bounded
  discussion references use the existing authorized catalogue reader. Unknown
  targets/qualifications clarify rather than being silently bound to focus.
- Current focus and the App discussed before a new search were not distinct.
  `search_origin_ids` records the prior focus in session state for both prepared
  and semantic searches. Historical references re-resolve current authorized
  source; stale identities never fall back to another App. No migration is needed.
- Rasa's coarse `compare` also covers predicate selection, so treating that label
  alone as authoritative would revive wrong comparisons. Complete purpose
  comparison frames now enter the existing comparison operation with the actual
  displayed set. Selection questions, unknown axes and extra requirements are
  not rewritten. Qwen remains available for unresolved functional understanding;
  it no longer reclassifies recognized source reads or these comparisons.

All field targets are consumed in full. Existing native-ID casing, duplicate
identity, publisher/visibility, late catalogue-revision, suitability and pending
condition checks remain in place. No source inspection establishes that an App
meets an unverified pricing or functional requirement.

## Bounded verification

Only the two authorized synchronized Store Apps were served. The approved Angular
artifact used real gateway/chat, Rasa HTTP, expert/source composition and
Discovery/E5 boundaries. An owned, capped Qwen3 4B worker was used only for the
three semantic turns; it never shared residency with the existing Ollama worker.

| Browser set | Pass / Partial / Fail |
| --- | --- |
| Known failure flows and setup, 9 turns | 9 / 0 / 0 |
| Fresh questions frozen before implementation, 8 turns | 8 / 0 / 0 |
| Targeted selection/condition regression, 7 turns | 7 / 0 / 0 |

All four formerly failing turns were correct, without inference, at 0.293–0.518 s.
The fresh eight used no inference (0.288–0.494 s). Across the bounded 24 turns,
there were no observed false abstentions, wrong-App answers, unsupported positive
claims or lost conditions. Provider lookup under a free-use condition answered
the source fact while retaining the unconfirmed requirement. Predicate selection
after comparison recommended the correct App despite Rasa's wrong `compare`
label and the model's wrong ordinal reference; discovery retained its own scope.

The single full unit run passed **1,356 tests**, with **86.62%** shared-package
branch coverage. Targeted parser/policy checks, Ruff, whitespace and secret checks
also passed. No 79-turn replay or model benchmark was run. Complete unedited
before/after conversations, frozen question hashes and separate pipeline review
are private under `~/.local/share/hedge-t2-operations/`; no Store snapshots or
runtime credentials are committed.

## Handoff

The verified basic metadata/reference/purpose-comparison flows are sufficient to
move to the separate retrieval/ranking evaluation. This is not closure of general
NLU: unrecognized source-reference phrases now clarify instead of guessing.
Unparsed operation wording and comparison axes beyond the recognized purpose
frame still reach the existing semantic path and can be misinterpreted by Qwen.
Source validation cannot repair a wrongly interpreted goal. Other-language UX
was not evaluated here.

Qwen's broader interpretation and reference choices remain fallible. The three
cold assisted turns took 81.246–89.674 s under serialized owned-worker scheduling;
this round does not solve inference performance or demonstrate warm/concurrent
serving. Settlement paraphrases and broader-catalogue recommendation quality were
not re-evaluated and are not claimed fixed. No regression was observed in this
bounded check; it does not replace a later broader acceptance evaluation.
