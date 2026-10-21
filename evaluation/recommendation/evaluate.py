"""Replay discovery requests through the real prepared Store dialogue path.

Decision, presentation and dialogue code are the repository's own; Rasa is
replaced by the intent each case names and no language model is called.
Candidate pools are E5 dense top-10 over prepared index text, an approximation of
hybrid retrieval. Requires the pinned CPU E5 model image (see README.md).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys

os.environ.setdefault("STORE_SEMANTIC_ENABLED", "false")
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "shared"), str(ROOT)]

import numpy as np  # noqa: E402
from hedge_shared.models_v2 import ChatRequestV2  # noqa: E402
from hedge_shared.store_knowledge import prepare  # noqa: E402
from hedge_shared.store_v1 import StoreAppMetadata  # noqa: E402

from scripts.store_v1_playground import load_service  # noqa: E402

expert = load_service("evaluation_expert", "expert-recommend")
recommender, presenter, evidence = expert("recommender"), expert("store_conversation"), expert("evidence")
dialogue = load_service("evaluation_chat", "chat-intent")("store_conversation")


def catalogue(path: pathlib.Path) -> list[tuple[dict, str]]:
    apps = []
    for raw in json.loads(path.read_text())["apps"]:
        prepared = prepare(StoreAppMetadata.model_validate(raw))
        projection = {**prepared["projection"], "prepared_explanation": prepared["explanation"]}
        if projection.get("active") and projection.get("visible"):
            apps.append((projection, prepared["index_text"]))
    return apps


class Dense:
    def __init__(self, apps: list[tuple[dict, str]]):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(os.environ.get("EMBEDDING_MODEL", "/opt/e5-model"))
        self.apps = [app for app, _ in apps]
        self.passages = self.encode([text for _, text in apps], "passage")

    def encode(self, texts: list[str], prefix: str) -> np.ndarray:
        return np.array(self.model.encode([f"{prefix}: {t}" for t in texts],
                                          normalize_embeddings=True, show_progress_bar=False))

    def pool(self, query: str, size: int) -> list[dict]:
        order = np.argsort(-(self.passages @ self.encode([query], "query")[0]))[:size]
        return [{"app": self.apps[i], "rank": rank + 1, "evidence_fields": ["dense"]} for rank, i in enumerate(order)]

    def similarity(self, queries: list[str], passages: list[str]) -> list[list[float]]:
        return (self.encode(queries, "query") @ self.encode(passages, "passage").T).tolist()


def conversation(dense: Dense, trace: dict):
    by_id = {app["id"]: app for app in dense.apps}

    async def recommend(*, query, locale, filters):
        pool = dense.pool(query, recommender.ASSESSED_CANDIDATES)
        trace["pool"] = [row["app"]["app_id"] for row in pool]
        return recommender._bounded(recommender._recommendation_decision(query, pool, locale), 5)

    def resolve(ids):
        return list(by_id.values()) if ids is None else [by_id[i] for i in ids if i in by_id]

    return dialogue.StoreConversation(
        recommend, resolve, recommender._recommendation_narrative, None, None,
        decide=recommender._recommendation_decision, present=presenter.prepared_answer)


def grade(case: dict, recommended: list[str], closest: list[str]) -> str:
    """Pass: only complete/acceptable Apps recommended, including every complete one.

    Suggested: nothing unsupported is recommended, and a complete App is offered as
    the closest unconfirmed statement rather than recommended.
    """
    complete = set(case.get("complete", case.get("relevant_native_ids", [])))
    acceptable = complete | set(case.get("acceptable", []))
    chosen = set(recommended)
    if chosen & set(case.get("forbidden", [])) or chosen - acceptable:
        return "Fail(unsupported)"
    if complete and not chosen:
        return "Suggested" if complete & set(closest) else "Fail(abstained)"
    return "Partial(missed)" if not complete <= chosen else "Pass"


def _closest(reply: dict) -> list[str]:
    """Candidates presented as unconfirmed closest statements (every finding documented or related)."""
    return [row["app"]["app_id"] for row in reply.get("candidates", [])[:3]
            if row.get("suitability", {}).get("status") == "partial"
            and {r["status"] for r in row["suitability"].get("requirements", [])} <= {"documented", "related"}]


async def run(args) -> None:
    dense = Dense(catalogue(args.catalogue))
    evidence.set_similarity(dense.similarity)
    out, summary = [], {}
    for path in args.queries or []:
        for case in json.loads(path.read_text())["queries"]:
            trace = {}
            reply = await conversation(dense, trace).respond_with_history(
                ChatRequestV2(message=case["query"], locale="en"), "search", {}, [])
            recommended = ([row["app"]["app_id"] for row in reply["apps"]]
                           if reply.get("decision", {}).get("outcome") == "recommended" else [])
            result = {"id": case["id"], "query": case["query"], "pool": trace.get("pool"),
                      "recommended": recommended, "decision": reply.get("decision"),
                      "closest": _closest(reply), "message": reply["message"],
                      "grade": grade(case, recommended, _closest(reply))}
            summary[result["grade"].split("(")[0]] = summary.get(result["grade"].split("(")[0], 0) + 1
            out.append(result)
            print(f"{case['id']:4} {result['grade']:18} recommended={recommended}")
    for path in args.conversations or []:
        for case in json.loads(path.read_text())["conversations"]:
            context, turns = {}, []
            for number, turn in enumerate(case["turns"]):
                reply = await conversation(dense, {}).respond_with_history(
                    ChatRequestV2(message=turn["message"], locale="en"), turn["intent"], context, [])
                context = {**context, **reply["context"], "turn": number + 1}
                turns.append({"message": turn["message"], "expect": turn["expect"], "reply": reply["message"]})
                print(f"--- {case['id']} > {turn['message']}\n{reply['message']}\n")
            out.append({"id": case["id"], "turns": turns})
    args.output.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    if summary:
        print(summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=pathlib.Path, default=ROOT / "evaluation/retrieval/catalogue.json")
    parser.add_argument("--queries", type=pathlib.Path, nargs="+")
    parser.add_argument("--conversations", type=pathlib.Path, nargs="+")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    asyncio.run(run(parser.parse_args()))
