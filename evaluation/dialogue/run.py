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
    from score import score

    from scripts.store_v1_playground import load_service

    expert = load_service("dialogue_expert", "expert-recommend")
    recommender, explainer, evidence = (expert(m) for m in ("recommender", "explainer", "evidence"))
    chat = load_service("dialogue_chat", "chat-intent")
    if not args.model_url:
        # Every module that calls the model, in whichever commit is mounted.
        for name in ("store_conversation", "explainer", "interpretation", "review"):
            try:
                expert(name).OllamaClient = Unavailable
            except ImportError:
                pass

    apps = catalogue(args.catalogue)
    dense = Dense(apps)
    DENSE_MODEL.append(dense.model)
    evidence.set_similarity(dense.similarity)
    by_id = {app["id"]: app for app in dense.apps}

    async def recommend(*, query, locale, filters):
        pool = dense.pool(query, recommender.ASSESSED_CANDIDATES)
        return recommender._bounded(recommender._recommendation_decision(query, pool, locale), 5)

    def resolve(ids):
        return list(by_id.values()) if ids is None else [by_id[i] for i in ids if i in by_id]

    policy, turn_runner = build(chat, expert, recommender, explainer, recommend, resolve)
    data = json.loads(args.scenarios.read_text())
    out, lines = [], []
    for case in data["conversations"]:
        state = {"context": {}, "history": []}
        lines.append(f"\n## {case['id']}\n")
        turns = []
        for number, turn in enumerate(case["turns"]):
            started = time.monotonic()
            reply = await turn_runner(state, turn["message"], number, case.get("locale", "en"))
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


def build(chat, expert, recommender, explainer, recommend, resolve):
    """The dialogue under test, driven the way the chat route drives it."""
    classifier = chat("classifier")
    try:
        assistant = chat("assistant")
    except ImportError:
        assistant = None
    if assistant is None:
        # Baseline (86fa782 and earlier): StoreConversation behind route_intent.
        dialogue, presenter = chat("store_conversation"), expert("store_conversation")
        policy = dialogue.StoreConversation(
            recommend, resolve, recommender._recommendation_narrative,
            lambda q, locale, d, c, h: presenter.plan(q, locale, d, c, h), None,
            decide=recommender._recommendation_decision, present=presenter.prepared_answer,
            explainer=lambda act, q, apps, s, h, phrase="": explainer.respond(act, q, apps, s, h, phrase))
        from hedge_shared.models_v2 import ChatRequestV2

        async def run(state, message, number, locale="en"):
            req = ChatRequestV2(message=message, locale=locale)
            context = state["context"]
            intent = policy.route_intent(message, classifier.classify(message).intent, context)
            reply = await policy.respond_with_history(req, intent, context, state["history"], nlu={"intent": intent})
            state["context"] = {**context, **reply["context"], "turn": number + 1,
                                "displayed_ids": [row["app"]["id"] for row in reply["apps"]]}
            state["history"] += [{"role": "user", "content": message}, {"role": "assistant", "content": reply["message"]}]
            return reply
        return policy, run
    from evaluate import Dense  # noqa: E402

    from scripts.store_assistant_local import local_assistant

    model = Dense.__new__(Dense)
    model.model = DENSE_MODEL[0]
    cache: dict[str, object] = {}

    def semantic(text, examples):
        import numpy as np
        key = "\n".join(examples)
        if key not in cache:
            cache[key] = model.encode(examples, "query")
        return (np.asarray(cache[key]) @ model.encode([text], "query")[0]).tolist()

    policy = local_assistant(chat, expert, recommend=recommend, resolve=resolve, semantic=semantic,
                             arbitrate=bool(os.environ.get("ARBITRATE")))
    from hedge_shared.models_v2 import ChatRequestV2

    async def run(state, message, number, locale="en"):
        reply = await policy.reply(ChatRequestV2(message=message, locale=locale), state["context"], state["history"])
        state["context"] = {**state["context"], **reply["context"], "turn": number + 1}
        state["history"] += [{"role": "user", "content": message}, {"role": "assistant", "content": reply["message"]}]
        return reply
    return policy, run


DENSE_MODEL: list = []


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=pathlib.Path, required=True)
    parser.add_argument("--catalogue", type=pathlib.Path, required=True)
    parser.add_argument("--repo", type=pathlib.Path, required=True)
    parser.add_argument("--model-url")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    sys.path.insert(0, str(HERE))
    asyncio.run(main(parser.parse_args()))
