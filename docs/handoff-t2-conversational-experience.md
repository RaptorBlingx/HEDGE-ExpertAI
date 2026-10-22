# Handoff: T2 conversational experience (21 October 2026)

Branch `feat/t2-conversational-experience` (worktree
`/home/ubuntu/hedge-t2-conversation-opus`), based on `a2a02ad`. Local commits
only; not pushed, merged or deployed. The original checkout, its branch and the
8156 deployment were not modified. Design, evaluation and limits:
[conversational experience](t2-conversational-experience.md).

## What changed

| Area | Files |
| --- | --- |
| General domain background | `shared/hedge_shared/glossary.py` |
| Source-derived App guide | `services/expert-recommend/app/app_guide.py` |
| Layered explanations, bounded model answers | `services/expert-recommend/app/explainer.py`, `/internal/store/explain` in `private_store.py`, `OllamaClient.chat_text` |
| Explanation acts and subjects | `services/chat-intent/app/conversation_acts.py`, `store_conversation.py` (`_act_response`, `discussed_ids`, planner skip/hand-off) |
| Dialogue fixes | `store_dialogue.py` ("which one"), Expert presenter (unconfirmed answers) |
| Widget streaming of checked sentences | `services/chat-intent/app/routes.py`, `private_store.py` (`STREAM`) |
| Routing metadata only | `evidence.Finding.screened`, `suitability` `screened` |
| Removed | `store_elaboration.py`, `/internal/store/elaborate`, its tests (properties re-covered) |
| Evaluation | `evaluation/conversation/` |

New setting `STORE_EXPLANATION_TOKENS` (default 220) in shared settings,
`.env.example`, the private-test Compose profile and the configuration reference.
Prepared explanations need no flag and no model.

## Verification performed

- Ruff clean; 1,548 unit tests pass (baseline 1,483; the 24 elaboration tests are
  replaced by explanation, act, streaming, routing and safety tests, including
  regression tests for the three review corrections).
- OpenAPI export regenerated: no diff (internal routes are not public).
- Integration suite against disposable PostgreSQL/Qdrant/Valkey on an internal
  network: 206 pass, 27 fail, the same 27 on `a2a02ad` (stale expectations).
- Recommendation decisions identical to `a2a02ad` on both unseen sets.
- Offline conversation sets (no model) and live Qwen runs on an isolated,
  read-only copy of the approved model; an isolated end-to-end stack with the
  unchanged Angular build in headless Chromium, prepared and streamed model
  answers. Results: [design document](t2-conversational-experience.md#live-model-and-end-to-end-validation-2122-october).

Not performed: Rasa in the loop, a real-user session, multi-user load.

## Rollout notes

- No preparation-version bump, migration or reindex: guides derive from current
  source fields.
- Deploy Chat and Expert together. Mixed versions degrade safely: a new Chat
  falls back to the existing paths if `/internal/store/explain` is missing; an old
  Chat's `/internal/store/elaborate` call fails into its prepared fallback.
- The model is used less often than at `a2a02ad`; with `STORE_EXPLANATIONS_ENABLED`
  off, open questions return an explicit prepared fallback.

## Recommended next steps

1. Independent review, especially the act grammar, the glossary text (domain
   review), the sentence checks and the routing default for conversational
   questions.
2. Before deploying to 8156: give the model service memory headroom or periodic
   recycling (the evaluation copy was OOM-killed in the same 3 GiB limit), then
   release this branch in a maintenance window and repeat the widget run with Rasa.
3. A short real-user session with a new, independent conversation set.
