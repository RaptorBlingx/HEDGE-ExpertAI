"""Confirm a paraphrased match: does this App's own sentence say it does what was asked?

The verifier documents a requirement only when one sentence states every
requested word, so "manage vocabularies" is not confirmed by "a vocabulary hub
used to publish and manage shared data models". When no requirement is
excluded or limited, the model is asked whether the App's related sentences (or,
if none was nominated, its own statements closest to the need) state that the
App does what was requested. A
yes becomes the existing request-bound ``ReviewedSupport`` receipt: tied to
this request, this App's current source digest, and quotations present in its
source. Quantities, absences, conditions and limitations never reach review.
"""
from __future__ import annotations

import json
import time

from hedge_shared.config import Settings
from hedge_shared.store_language import search_language

from . import app_guide, evidence
from .llm_client import OllamaClient
from .recommender import _recommendation_decision
from .suitability import ReviewedSupport, source_digest, source_text

MAX_REVIEWED = 2
MAX_QUOTES = 3
SYSTEM = (
    "You check App Store descriptions. For each App, decide whether its quoted statements say that the App "
    "itself does what the request asks. Different wording counts. A related topic, a plan, a condition, a "
    "simulation or doing only part of the request does not. Answer with one true or false per App, in order."
)


def _reviewable(row: dict, need: str, locale: str) -> list[tuple[str, str]]:
    """Exact quotations to review: the verifier's related sentences, else the App's most relevant ones.

    Nothing is reviewed once the verifier found an absence or a limitation.
    """
    findings = row.get("suitability", {}).get("requirements", [])
    if not findings or any(f["status"] not in {"documented", "related", "not_documented"} for f in findings) \
            or all(f["status"] == "documented" for f in findings):
        return []
    fields = source_text(row["app"], locale)
    quotes = list(dict.fromkeys((f["field"], f["quote"]) for f in findings if f.get("quote")))
    if any(f["status"] == "not_documented" for f in findings):
        # No sentence was nominated: offer the App's own statements closest to the need.
        quotes += [(s.path, s.quote) for s in _statements(row["app"], need) if (s.path, s.quote) not in quotes]
    quotes = [(p, q) for p, q in quotes if q in fields.get(p, "")][:MAX_QUOTES]
    return quotes


def reviewed_decision(need: str, rows: list[dict], locale: str) -> dict:
    """The verifier's decision, extended by model review of related sentences when enabled."""
    decision = _recommendation_decision(need, rows, locale)
    settings = Settings()
    if (decision["apps"] or not (settings.STORE_SEMANTIC_ENABLED and settings.STORE_EXPLANATIONS_ENABLED)
            or _strict(need)):
        return decision
    pending = [(row, quotes) for row in decision["candidates"]
               if (quotes := _reviewable(row, need, locale))][:MAX_REVIEWED]
    if not pending:
        return decision
    try:
        verdicts = _ask(need, pending)
    except Exception:
        return {**decision, "review": "unavailable"}
    request = search_language(need, locale)
    receipts = {row["app"]["id"]: ReviewedSupport(request=request, app_id=row["app"]["id"],
                                                  source_digest=source_digest(row["app"], locale), quotes=tuple(quotes))
                for (row, quotes), supported in zip(pending, verdicts, strict=True) if supported}
    if not receipts:
        return {**decision, "review": "not_supported"}
    reviewed = _recommendation_decision(need, rows, locale, reviewed_support=receipts)
    return {**reviewed, "review": "supported"}


def _strict(need: str) -> bool:
    """Quantities, absences, conditions and exclusions stay with the lexical verifier."""
    folded = evidence._fold(need)
    return bool(evidence._NUMBER.search(folded) or evidence._NEGATIVE.search(folded)
                or evidence._WITHOUT.search(folded) or evidence._LIMITED.search(folded))


def _statements(app: dict, need: str):
    """The App's own capability statements at least as relevant to the need as the verifier requires.

    Two signals must agree before a paraphrase is confirmed: E5 relevance here
    (the verifier's GAP_MATCH floor) and the model's review. Without similarity,
    nothing beyond the verifier's own nominations is reviewed.
    """
    statements = [s for s in app_guide.build(app).statements
                  if s.owned and s.role in {"purpose", "capability", "scheme"}]
    scores = evidence._similarity([need], [evidence._topic(s.text) for s in statements]) if statements else None
    if not scores:
        return []
    ranked = sorted(zip(scores[0], statements, strict=True), key=lambda pair: -pair[0])
    return [s for score, s in ranked if score >= evidence.GAP_MATCH][:2]


def _ask(need: str, pending: list[tuple[dict, list[tuple[str, str]]]]) -> list[bool]:
    apps = "\n\n".join(f"App {i + 1}: {row['app'].get('name') or row['app']['app_id']}\n"
                       + "\n".join(f"- “{quote}”" for _, quote in quotes)
                       for i, (row, quotes) in enumerate(pending))
    schema = {"type": "object", "properties": {"supported": {
        "type": "array", "items": {"type": "boolean"}, "minItems": len(pending), "maxItems": len(pending)}},
        "required": ["supported"], "additionalProperties": False}
    settings = Settings()
    budget = settings.STORE_MODEL_TIMEOUT_SECONDS
    raw = OllamaClient().chat_structured(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"Request: {need}\n\n{apps}"}], schema,
        timeout=budget, max_tokens=24, context_tokens=settings.STORE_MODEL_CONTEXT_TOKENS,
        deadline=time.monotonic() + budget)
    verdicts = json.loads(raw)["supported"]
    if len(verdicts) != len(pending) or not all(isinstance(v, bool) for v in verdicts):
        raise ValueError("Malformed review")
    return verdicts
