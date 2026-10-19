"""Versioned, rebuildable Store knowledge. Source metadata remains authoritative."""
from __future__ import annotations

import re
from typing import Any

from .store_explanations import extract
from .store_v1 import StoreAppMetadata

# Bump whenever source extraction/projection semantics change.
PREPARATION_VERSION = 2


def prepare(app: StoreAppMetadata) -> dict[str, Any]:
    projection = app.recommendation_projection()
    return {
        "version": PREPARATION_VERSION,
        "checksum": app.checksum,
        "projection": projection,
        "explanation": extract(projection["source_evidence"], projection.get("name", "")),
        "evidence_paths": list(projection["source_evidence"]),
        "index_text": " . ".join(value for path, value in projection["source_evidence"].items()
                                 if path not in {"billable", "price"}),
    }


def project(row: dict[str, Any]) -> dict[str, Any]:
    """Use only preparation bound to this authoritative row; old rows still work.

    These documents are internal ingestion output, never request-supplied data.
    Availability/Store scope must already have been checked by the storage read.
    """
    knowledge = row.get("prepared_knowledge")
    if (isinstance(knowledge, dict) and knowledge.get("version") == PREPARATION_VERSION
            and knowledge.get("checksum") == row.get("checksum")
            and isinstance(knowledge.get("projection"), dict)
            and isinstance(knowledge["projection"].get("source_evidence"), dict)
            and knowledge["projection"].get("id") == row["id"]
            and all(knowledge["projection"].get(field) == row["payload"].get(field)
                    for field in ("source_profile", "store_id", "app_id", "active", "visible"))):
        projection = dict(knowledge["projection"])
        evidence = projection.get("source_evidence", {})
        # JSONB object order is not source order. Keep paths separately so
        # deterministic explanations remain stable across persistence.
        projection["source_evidence"] = {path: evidence[path]
            for path in knowledge.get("evidence_paths", evidence) if path in evidence}
        if isinstance(knowledge.get("explanation"), dict):
            projection["prepared_explanation"] = knowledge["explanation"]
        return projection
    return StoreAppMetadata.model_validate(row["payload"]).recommendation_projection()


def explanation(app: dict[str, Any]) -> dict[str, Any]:
    """Read accepted preparation only while its exact quotations remain current."""
    value = app.get("prepared_explanation")
    if not isinstance(value, dict):
        return {}
    if value.get("version") == 2:
        # Machine extraction cannot be labelled a human review or carry arbitrary
        # generated claims. Reproduce it from the current authoritative evidence.
        expected = extract(app.get("source_evidence", {}), app.get("name", ""))
        return value if expected and value == expected else {}
    if value.get("version") != 1:
        return {}
    review = value.get("review", {})
    if (not isinstance(review, dict) or
            review.get("method") not in ("human_source_review", "agent_source_review") or
            any(not isinstance(review.get(key), str) or not review[key].strip()
                for key in ("reviewer", "note"))):
        return {}
    for language in ("en", "tr"):
        prose = value.get(language)
        if not isinstance(prose, dict) or any(
            not isinstance(prose.get(key), str) or not 1 <= len(prose[key]) <= 900
            or re.search(r"https?://|<|>|\[|\]", prose[key])
            for key in ("summary", "simple", "use_when")
        ):
            return {}
    facts = value.get("facts")
    if not isinstance(facts, list) or not 1 <= len(facts) <= 5:
        return {}
    source = app.get("source_evidence", {})
    for fact in facts:
        if not isinstance(fact, dict) or any(
            not isinstance(fact.get(key), str) or not fact[key]
            for key in ("path", "quote", "en", "tr")
        ):
            return {}
        if any(len(fact[lang]) > 900 or re.search(r"https?://|<|>|\[|\]", fact[lang])
               for lang in ("en", "tr")):
            return {}
        original = source.get(fact["path"])
        if not isinstance(original, str) or fact["quote"] not in original:
            return {}
    return value
