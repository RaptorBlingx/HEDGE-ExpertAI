"""Replay multi-turn conversations through the real Store dialogue.

Chat routing (regex NLU unless RASA_ENABLED), StoreConversation, Expert decisions,
presentation and explanations are the repository's own code; HTTP hops are local
calls. Candidate pools are E5 dense top-10 (as in ../recommendation). Without
--model-url no language model is called and model-assisted acts take their
prepared fallback. With --model-url, set only for an isolated, verified model
endpoint, explanation and interpretation calls use it.

Checks are coarse signals; read the transcript. Results belong outside Git.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "shared"), str(ROOT), str(ROOT / "evaluation/recommendation")]


def configure(model_url: str | None) -> None:
    os.environ.setdefault("RASA_ENABLED", "false")
    enabled = "true" if model_url else "false"
    os.environ["STORE_SEMANTIC_ENABLED"] = enabled
    os.environ["STORE_EXPLANATIONS_ENABLED"] = enabled
    if model_url:
        os.environ["OLLAMA_BASE_URL"] = model_url


def _ngrams(text: str, n: int = 5) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z0-9’']+", text.casefold())
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def repetition(reply: str, earlier: list[str]) -> float:
    """Share of this reply's 5-grams already said in an earlier reply."""
    grams = _ngrams(reply)
    if not grams or not earlier:
        return 0.0
    return max(len(grams & _ngrams(e)) / len(grams) for e in earlier)


def check(expect: dict, reply: dict, names: list[str], seconds: float, rep: float) -> list[str]:
    text = reply["message"]
    folded = text.casefold()
    problems = []
    # The conversation kept its subject if the answer shows or names the App.
    missing = [n for n in expect.get("subject", []) if n not in names and f"**{n}**" not in text]
    if missing:
        problems.append(f"subject missing {missing}")
    if expect.get("concepts_any") and not any(c.casefold() in folded for c in expect["concepts_any"]):
        problems.append(f"none of {expect['concepts_any']}")
    hits = [f for f in expect.get("forbid", []) if f.casefold() in folded]
    if hits:
        problems.append(f"forbidden {hits}")
    if "outcome" in expect and reply.get("decision", {}).get("outcome") != expect["outcome"]:
        problems.append(f"outcome {reply.get('decision', {}).get('outcome')}")
    if expect.get("model") is False and reply.get("generation", {}).get("model_completed"):
        problems.append("used the model")
    if rep > 0.6:
        problems.append(f"repeats {rep:.0%} of an earlier answer")
    return problems


class Lexical:
    """Candidate pools by word overlap, for runs that cannot afford the E5 model."""

    def __init__(self, apps, terms):
        self.apps, self.texts, self.terms = [a for a, _ in apps], [terms(t) for _, t in apps], terms

    def pool(self, query, size):
        words = self.terms(query)
        order = sorted(range(len(self.apps)), key=lambda i: -len(words & self.texts[i]))[:size]
        return [{"app": self.apps[i], "rank": r + 1, "evidence_fields": ["lexical"]} for r, i in enumerate(order)]


async def main(args) -> None:
    configure(args.model_url)
    from evaluate import Dense, catalogue  # noqa: E402  (same pinned E5 pools)
    from hedge_shared.models_v2 import ChatRequestV2

    from scripts.store_v1_playground import load_service
    expert = load_service("conversation_expert", "expert-recommend")
    recommender, presenter, explainer = expert("recommender"), expert("store_conversation"), expert("explainer")
    evidence = expert("evidence")
    chat = load_service("conversation_chat", "chat-intent")
    dialogue, classifier = chat("store_conversation"), chat("classifier")

    data = json.loads(args.scenarios.read_text())
    apps = catalogue(args.catalogue)
    if args.lexical:
        # ~1 GB less memory: word-overlap pools, no similarity nominations.
        dense = Lexical(apps, evidence.terms)
    else:
        dense = Dense(apps)
        evidence.set_similarity(dense.similarity)
    by_id = {app["id"]: app for app in dense.apps}

    async def recommend(*, query, locale, filters):
        pool = dense.pool(query, recommender.ASSESSED_CANDIDATES)
        return recommender._bounded(recommender._recommendation_decision(query, pool, locale), 5)

    def resolve(ids):
        return list(by_id.values()) if ids is None else [by_id[i] for i in ids if i in by_id]

    calls = {"explain": 0, "interpret": 0}
    raw: list[str] = []
    if args.model_url:
        # Record raw model text for reading; it is never part of the reply.
        client = explainer.OllamaClient

        class Tracing(client):
            def chat_text(self, *a, **kw):
                chunks, relay = [], kw.get("on_delta")
                kw["on_delta"] = lambda chunk: (chunks.append(chunk), relay(chunk) if relay else None)
                try:
                    return super().chat_text(*a, **kw)
                finally:  # also when a sentence check stops the answer
                    raw.append("".join(chunks))

        explainer.OllamaClient = Tracing

    def interpret(question, locale, directory, context, history):
        calls["interpret"] += 1
        return presenter.plan(question, locale, directory, context, history)

    def explain(act, question, rows, state, history, phrase=""):
        calls["explain"] += 1
        return explainer.respond(act, question, rows, state, history, phrase)

    policy = dialogue.StoreConversation(
        recommend, resolve, recommender._recommendation_narrative, interpret if args.model_url else None, None,
        decide=recommender._recommendation_decision, present=presenter.prepared_answer, explainer=explain)

    out, summary, lines = [], {"turns": 0, "flagged": 0}, []
    wanted = set(args.only or [])
    for case in data["conversations"]:
        if wanted and case["id"] not in wanted:
            continue
        context, history, replies, turns = {}, [], [], []
        lines.append(f"\n## {case['id']}\n")
        for number, turn in enumerate(case["turns"]):
            req = ChatRequestV2(message=turn["message"], locale="en")
            intent = policy.route_intent(req.message, classifier.classify(req.message).intent, context)
            before = dict(calls)
            raw.clear()
            started = time.monotonic()
            reply = await policy.respond_with_history(req, intent, context, history, nlu={"intent": intent})
            seconds = time.monotonic() - started
            names = [row["app"].get("name") for row in reply["apps"]]
            # The same context update as the chat route.
            context = {**context, **reply["context"], "turn": number + 1,
                       "displayed_ids": [row["app"]["id"] for row in reply["apps"]]}
            history += [{"role": "user", "content": req.message}, {"role": "assistant", "content": reply["message"]}]
            rep = repetition(reply["message"], replies)
            problems = check(turn.get("expect", {}), reply, names, seconds, rep)
            replies.append(reply["message"])
            generation = reply.get("generation", {})
            summary["turns"] += 1
            summary["flagged"] += bool(problems)
            record = {"message": turn["message"], "reply": reply["message"], "apps": names,
                      "decision": reply.get("decision"), "generation": generation, "seconds": round(seconds, 2),
                      "repetition": round(rep, 2), "calls": {k: calls[k] - before[k] for k in calls},
                      "problems": problems, "model_text": list(raw)}
            turns.append(record)
            path = generation.get("reason") or generation.get("source")
            lines.append(f"**User:** {turn['message']}\n\n*[{path}; {reply.get('decision', {}).get('outcome')}; "
                         f"cards={names}; {seconds:.2f}s; model={bool(generation.get('model_completed'))}]*"
                         + (f" **CHECK: {'; '.join(problems)}**" if problems else "")
                         + f"\n\n{reply['message']}\n\n"
                         + "".join(f"> raw model text: {t}\n\n" for t in raw if t not in reply["message"])
                         + "---\n")
        out.append({"id": case["id"], "turns": turns})
    args.output.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    args.output.with_suffix(".md").write_text("\n".join(lines))
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=pathlib.Path, required=True)
    parser.add_argument("--catalogue", type=pathlib.Path, default=ROOT / "evaluation/retrieval/catalogue.json")
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--model-url")
    parser.add_argument("--lexical", action="store_true", help="word-overlap pools instead of E5 (less memory)")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    asyncio.run(main(parser.parse_args()))
