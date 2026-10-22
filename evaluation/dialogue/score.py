"""Score replayed conversations against implementation-agnostic expectations.

Per turn: expected subjects (cards or bold names), concepts, forbidden text,
decision outcome, and generic failures that no answerable turn may show (a
generic clarification, "Which App do you mean?" for a named App, the open-question
fallback, or a recommendation verdict where none was asked or supported).
The `act` label documents the intended interpretation; it is reported, not
scored, so the same scorer applies to any implementation.
"""
from __future__ import annotations

import json
import pathlib
import sys

GENERIC = ("narrow this down to the main function", "which task or app would you like to explore",
           "couldn't quite resolve", "couldn’t quite resolve", "which app do you mean", "cannot resolve that reference",
           "cannot resolve those references", "which app or earlier comparison")
OPEN_FALLBACK = ("don’t have a reliable answer", "don't have a reliable answer")
VERDICT = "fits what you need"
DECISION_ACTS = {"find", "check", "choose"}


def problems(expect: dict, reply: dict) -> list[str]:
    text = reply.get("reply", "")
    folded = text.casefold()
    names = [n for n in reply.get("apps", []) if n]
    shown = lambda name: name in names or f"**{name}**".casefold() in folded  # noqa: E731
    found = []
    missing = [n for n in expect.get("subject", []) if not shown(n)]
    if missing:
        found.append(f"subject missing {missing}")
    if expect.get("subject_any") and not any(shown(n) for n in expect["subject_any"]):
        found.append(f"none of subjects {expect['subject_any']}")
    if len(names) < expect.get("min_cards", 0):
        found.append(f"{len(names)} cards")
    if expect.get("concepts_any") and not any(c.casefold() in folded for c in expect["concepts_any"]):
        found.append(f"none of {expect['concepts_any']}")
    hits = [f for f in expect.get("forbid", []) if f.casefold() in folded]
    if hits:
        found.append(f"forbidden {hits}")
    outcome = (reply.get("decision") or {}).get("outcome")
    if "outcome" in expect and outcome != expect["outcome"]:
        found.append(f"outcome {outcome}")
    if not expect.get("clarify"):
        generic = [g for g in GENERIC if g in folded]
        if generic:
            found.append(f"generic reply {generic[0]!r}")
        if any(g in folded for g in OPEN_FALLBACK):
            found.append("open-question fallback")
    if VERDICT in folded and (expect.get("outcome") == "abstained" or expect.get("act") not in DECISION_ACTS):
        found.append("unrequested or unsupported recommendation verdict")
    if not text.strip():
        found.append("empty reply")
    return found


def score(scenarios: dict, results: list[dict]) -> dict:
    by_id = {c["id"]: c for c in scenarios["conversations"]}
    turns = passed = 0
    lines = []
    for conversation in results:
        expected = by_id[conversation["id"]]["turns"]
        for turn, expect in zip(conversation["turns"], expected, strict=True):
            found = problems(expect["expect"], turn)
            turn["problems"] = found
            turns += 1
            passed += not found
            lines.append(f"{conversation['id']:5} {'PASS' if not found else 'FAIL'}  {turn['message'][:70]!r}"
                         + (f"  -> {'; '.join(found)}" if found else ""))
    return {"turns": turns, "passed": passed, "lines": lines}


if __name__ == "__main__":
    scenarios = json.loads(pathlib.Path(sys.argv[1]).read_text())
    results = json.loads(pathlib.Path(sys.argv[2]).read_text())
    summary = score(scenarios, results)
    print("\n".join(summary["lines"]))
    print(json.dumps({k: summary[k] for k in ("turns", "passed")}))
