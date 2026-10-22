# Handoff: T2 conversational architecture (22 October 2026)

Branch `feat/t2-conversational-architecture` (worktree
`/home/ubuntu/hedge-t2-architecture`), based on the deployed `86fa782`. Local
commits only; not pushed, merged or deployed. 8156, the original checkout and the
earlier branches were not modified. Design and results:
[conversational architecture](t2-conversational-architecture.md).

## What changed

| Area | Files |
| --- | --- |
| App identity | `shared/hedge_shared/app_linker.py` |
| Dialogue acts (one dataset for Rasa and E5) | `shared/hedge_shared/dialogue_acts.json`, `scripts/generate_rasa_nlu.py`, `services/rasa/` (`hedge-expertai-nlu-v3`) |
| Interpretation | `services/chat-intent/app/understanding.py`; Rasa acts in `classifier.py`; E5 symmetric similarity in Discovery |
| Execution and dialogue state | `services/chat-intent/app/assistant.py`, `private_store.py`, `routes.py` (`_store_turn`) |
| Answers | `services/expert-recommend/app/answers.py`, `review.py`, `interpretation.py`, `private_store.py`; explainer field acts and extractive fallback |
| Verifier | `evidence.py`: light verbs; fully covering negations exclude |
| Removed | `chat-intent`: `store_conversation.py`, `store_dialogue.py`, `conversation_acts.py`; `expert-recommend`: `store_conversation.py` (planner, generative review, presenter), `store_answers.py`; `/internal/store/interpret`, `/internal/store/reason`; `STORE_REASONING_*`, `STORE_MODEL_OUTPUT_TOKENS`; `scripts/check_store_conversation_grounding.py` |
| Evaluation | `evaluation/dialogue/` (sealed sets, runner, scorer, leakage check); `scripts/store_assistant_local.py` |

New setting `STORE_INTERPRETATION_SECONDS` (default 30): shared settings,
`.env.example`, the private-test Compose profile, the configuration reference.

## Rollout notes

- **Rebuild Rasa** (new corpus; model name `hedge-expertai-nlu-v3`) and deploy it
  with Chat, Expert and Discovery together: Chat calls Discovery's symmetric
  similarity and Expert's new compose modes and `/arbitrate`.
- No migration, preparation-version bump or reindex. Old sessions keep their
  legacy context keys; the assistant reads only `context["dialogue"]`, so an old
  session starts with empty dialogue state.
- Discovery embeds the ~400 example utterances on first use; Chat warms this at
  startup.

## Verification performed

- Ruff clean; 1,285 unit tests; generated Rasa corpus check; sealed-set leakage check.
- Recommendation decisions on the unseen query sets: unchanged from `86fa782`
  except one case improved (Fail to Suggested).
- Integration suite against disposable PostgreSQL/Qdrant/Valkey: 3 failures, all
  inherited from `86fa782`.
- Natural conversations offline, with an isolated Qwen copy, and through an
  isolated stack of this branch's services with real Rasa and E5: see
  [results](t2-conversational-architecture.md#evaluation). Final sealed set:
  baseline 9/27 offline and 12/27 with Qwen; branch 15/27 offline, 22/27 with
  Qwen and through the stack.
- All evaluation containers and networks were removed. 8156 was only observed read-only (logs, container stats and environment); no requests were sent to it and nothing was changed.

Not performed: the Angular widget in a browser, a real-user session, multi-user
load, Turkish conversations.

## Recommended next steps

1. Independent review, especially `review.py` (model review of paraphrased
   evidence is the main recommendation-safety change) and the act dataset.
2. Broaden `dialogue_acts.json` with varied, need-marked examples from real
   sessions, keeping a sealed set unseen.
3. Before deploying: rebuild Rasa, measure on 8156-equivalent load, and settle
   model memory sizing; then a short real-user session.
