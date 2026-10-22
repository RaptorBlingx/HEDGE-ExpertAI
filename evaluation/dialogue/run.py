"""Replay natural multi-turn conversations through the repository's dialogue.

The repository under test is mounted at --repo (default: this checkout), so the
same runner, scenarios and scorer measure a baseline commit and this branch.
HTTP hops are local calls; candidate pools are E5 dense top-k as in
../recommendation. Without --model-url, every model call fails at once, the way
the 8156 planner times out; with it, calls go to that (isolated) endpoint.
Results belong outside Git.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent


def configure(model_url: str | None) -> None:
    os.environ.setdefault("RASA_ENABLED", "false")
    # The deployed flags: model-assisted paths are enabled.
    os.environ["STORE_SEMANTIC_ENABLED"] = "true"
    os.environ["STORE_EXPLANATIONS_ENABLED"] = "true"
    if model_url:
        os.environ["OLLAMA_BASE_URL"] = model_url


class Unavailable:
    """Stands in for the model client when no endpoint is given."""

    def __init__(self, *args, **kwargs):
        pass

    def chat_structured(self, *args, **kwargs):
        raise TimeoutError("no model endpoint")

    def chat_text(self, *args, **kwargs):
        raise TimeoutError("no model endpoint")

    def is_available(self):
        return False


async def main(args) -> None:
    configure(args.model_url)
    root = args.repo.resolve()
    sys.path[:0] = [str(root / "shared"), str(root), str(root / "evaluation/recommendation")]
    from evaluate import Dense, catalogue  # noqa: E402  (same pinned E5 pools)
    from hedge_shared.models_v2 import ChatRequestV2
    from scripts.store_v1_playground import load_service

    from score import score

    expert = load_service("dialogue_expert", "expert-recommend")
    recommender, presenter, explainer, evidence = (expert(m) for m in ("recommender", "store_conversation", "explainer", "evidence"))
    chat = load_service("dialogue_chat", "chat-intent")
    if not args.model_url:
        for module in (presenter, explainer):
            module.OllamaClient = Unavailable

    apps = catalogue(args.catalogue)
    dense = Dense(apps)
    evidence.set_similarity(dense.similarity)
    by_id = {app["id"]: app for app in dense.apps}

    async def recommend(*, query, locale, filters):
        pool = dense.pool(query, recommender.ASSESSED_CANDIDATES)
        return recommender._bounded(recommender._recommendation_decision(query, pool, locale), 5)

    def resolve(ids):
        return list(by_id.values()) if ids is None else [by_id[i] for i in ids if i in by_id]

    policy, turn_runner = build(chat, expert, recommender, presenter, explainer, recommend, resolve)
    data = json.loads(args.scenarios.read_text())
    out, lines = [], []
    for case in data["conversations"]:
        state = {"context": {}, "history": []}
        lines.append(f"\n## {case['id']}\n")
        turns = []
        for number, turn in enumerate(case["turns"]):
            started = time.monotonic()
            reply = await turn_runner(state, turn["message"], number)
            seconds = time.monotonic() - started
            record = {"message": turn["message"], "reply": reply["message"],
                      "apps": [row["app"].get("name") for row in reply["apps"]],
                      "decision": reply.get("decision"), "generation": reply.get("generation", {}),
                      "frame": reply.get("frame"), "seconds": round(seconds, 2)}
            turns.append(record)
            lines.append(f"**User:** {turn['message']}\n\n*[{turn['expect'].get('act')} → "
                         f"{(reply.get('frame') or {}).get('act', reply.get('intent'))}; "
                         f"{(reply.get('decision') or {}).get('outcome')}; cards={record['apps']}; {seconds:.2f}s]*"
                         f"\n\n{reply['message']}\n\n---\n")
        out.append({"id": case["id"], "turns": turns})
    summary = score(data, out)
    args.output.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    args.output.with_suffix(".md").write_text("\n".join(lines) + "\n\n## Score\n\n" + "\n".join(summary["lines"]))
    print(json.dumps({"turns": summary["turns"], "passed": summary["passed"]}))


def build(chat, expert, recommender, presenter, explainer, recommend, resolve):
    """The dialogue under test, driven the way the chat route drives it."""
    classifier = chat("classifier")
    try:
        assistant = chat("assistant")
    except ImportError:
        assistant = None
    if assistant is None:
        # Baseline (86fa782 and earlier): StoreConversation behind route_intent.
        dialogue = chat("store_conversation")
        policy = dialogue.StoreConversation(
            recommend, resolve, recommender._recommendation_narrative,
            lambda q, l, d, c, h: presenter.plan(q, l, d, c, h), None,
            decide=recommender._recommendation_decision, present=presenter.prepared_answer,
            explainer=lambda act, q, apps, s, h, phrase="": explainer.respond(act, q, apps, s, h, phrase))
        from hedge_shared.models_v2 import ChatRequestV2

        async def run(state, message, number):
            req = ChatRequestV2(message=message, locale="en")
            context = state["context"]
            intent = policy.route_intent(message, classifier.classify(message).intent, context)
            reply = await policy.respond_with_history(req, intent, context, state["history"], nlu={"intent": intent})
            state["context"] = {**context, **reply["context"], "turn": number + 1,
                                "displayed_ids": [row["app"]["id"] for row in reply["apps"]]}
            state["history"] += [{"role": "user", "content": message}, {"role": "assistant", "content": reply["message"]}]
            return reply
        return policy, run
    return assistant.evaluation_runner(chat, expert, recommend, resolve)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=pathlib.Path, required=True)
    parser.add_argument("--catalogue", type=pathlib.Path, required=True)
    parser.add_argument("--repo", type=pathlib.Path, required=True)
    parser.add_argument("--model-url")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    sys.path.insert(0, str(HERE))
    asyncio.run(main(parser.parse_args()))
