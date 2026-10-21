"""Source assessment for recommendations; retrieval rank never establishes suitability.

An App is recommended for a request only when its own functional source text
documents every requested function (see ``evidence``). Partial matches keep the
per-requirement evidence so they can be explained, never presented as complete.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from . import evidence


def source_text(app: dict[str, Any], locale: str) -> dict[str, str]:
    """Original functional field paths; no rank, provider, price or inferred ontology."""
    if app.get("source_profile") == "hedge-store-v1":
        values = app.get("source_evidence")
        if isinstance(values, dict):
            return {path: value for path, value in values.items()
                    if isinstance(path, str) and isinstance(value, str) and value and (
                        path in {"description", "readme"}
                        or path == "dataspaceAppDescription.properties.description"
                        or path.startswith("dataspaceAppDescription.properties.featureList[")
                    )}
        description = app.get("description")
        return {"description": description} if isinstance(description, str) and description else {}
    values = {}
    if isinstance(app.get("description"), str) and app["description"]:
        values["description"] = app["description"]
    summary = app.get("summary")
    if isinstance(summary, dict):
        language = locale if summary.get(locale) else "en"
        if isinstance(summary.get(language), str) and summary[language]:
            values[f"summary.{language}"] = summary[language]
    capabilities = app.get("capabilities")
    for index, capability in enumerate(capabilities if isinstance(capabilities, list) else []):
        if isinstance(capability, str) and capability:
            values[f"capabilities[{index}]"] = capability
    for direction in ("inputs", "outputs"):
        contracts = app.get(direction)
        for index, contract in enumerate(contracts if isinstance(contracts, list) else []):
            if isinstance(contract, dict) and isinstance(contract.get("description"), str):
                values[f"{direction}[{index}].description"] = contract["description"]
    return values


MAX_SEMANTIC_SUPPORT_FIELDS = 20


@dataclass(frozen=True)
class ReviewedSupport:
    """Internal result of semantic grounding review, never a request contract."""
    request: str
    app_id: str
    source_digest: str
    quotes: tuple[tuple[str, str], ...]


def source_digest(app: dict, locale: str) -> str:
    return hashlib.sha256(json.dumps(source_text(app, locale), sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest()


def _names(app: dict[str, Any], locale: str) -> tuple[str, ...]:
    title = app.get("name") if app.get("source_profile") == "hedge-store-v1" else app.get("title")
    if isinstance(title, dict):
        title = title.get(locale) or title.get("en")
    return (title,) if isinstance(title, str) and title else ()


def _identity(query: str, app: dict[str, Any], locale: str) -> dict | None:
    """An exact quoted-name lookup ("MeaningHub") is an identity request."""
    title = app.get("name") if app.get("source_profile") == "hedge-store-v1" else app.get("title")
    path = "name" if app.get("source_profile") == "hedge-store-v1" else "title"
    if isinstance(title, dict):
        language = locale if title.get(locale) else "en"
        path, title = f"title.{language}", title.get(language)
    if not title and app.get("app_id"):
        path = "appId"
    names = re.findall(r'"([^"\n]+)"', query)
    identity = str(title or app.get("app_id") or "")
    if not identity or not names or not re.fullmatch(r'"[^"\n]+"(?:\s+OR\s+"[^"\n]+")*', query.strip()):
        return None
    matched = identity in names if path == "appId" else identity.casefold() in {n.casefold() for n in names}
    return {"status": "source_supported", "reason": "requested_identity", "evidence_fields": [path]} if matched else None


def _reviewed(query: str, app: dict, locale: str, receipt: ReviewedSupport | None) -> dict | None:
    """Only the expert's request-bound review receipt, with exact current quotations."""
    if not (isinstance(receipt, ReviewedSupport) and receipt.request == query
            and receipt.app_id == app.get("id") and receipt.source_digest == source_digest(app, locale)):
        return None
    fields = source_text(app, locale)
    quotes = receipt.quotes
    if not (1 <= len(quotes) <= MAX_SEMANTIC_SUPPORT_FIELDS and len(set(quotes)) == len(quotes)
            and all(len(quote.strip()) >= 16 and quote in fields.get(path, "") for path, quote in quotes)):
        return None
    return {"status": "source_supported", "reason": "semantically_reviewed_source_support",
            "evidence_fields": list(dict.fromkeys(path for path, _ in quotes)),
            "evidence_spans": list(dict.fromkeys(quote for _, quote in quotes))}


def _decision(findings: list[evidence.Finding]) -> dict[str, Any]:
    """Only verified findings support a recommendation; related ones are shown as closest statements."""
    documented = [f for f in findings if f.status == "documented"]
    if not findings:
        status, reason = "uncertain", "request_needs_clarification"
    elif len(documented) == len(findings):
        status, reason = "source_supported", "documented_requirements"
    elif documented or any(f.status in {"limited", "related"} for f in findings):
        status, reason = "partial", "partial_source_support"
    else:
        status = "uncertain"
        reason = "documented_limitation" if any(f.status == "excluded" for f in findings) else "no_documented_match"
    return {"status": status, "reason": reason,
            "evidence_fields": list(dict.fromkeys(c.path for f in documented for c in f.supporting)),
            "evidence_spans": list(dict.fromkeys(f.clause.quote for f in documented)),
            "requirements": [{"requirement": f.requirement, "status": f.status,
                              **({"field": f.clause.path, "quote": f.clause.quote} if f.clause else {})}
                             for f in findings]}


def assess_many(query: str, apps: list[dict[str, Any]], locale: str, *,
                reviewed_support: dict[str, ReviewedSupport] | None = None) -> list[dict[str, Any]]:
    """Assess candidate Apps together, so semantic matches are judged relative to the pool."""
    results: list[dict | None] = [
        _identity(query, app, locale) or _reviewed(query, app, locale, (reviewed_support or {}).get(app.get("id")))
        for app in apps]
    pending = [i for i, result in enumerate(results) if result is None]
    findings = evidence.assess_pool(query, [source_text(apps[i], locale) for i in pending],
                                    [_names(apps[i], locale) for i in pending])
    for index, found in zip(pending, findings, strict=True):
        results[index] = _decision(found)
    return results  # type: ignore[return-value]


def assess(query: str, app: dict[str, Any], locale: str, *, reviewed_support: ReviewedSupport | None = None) -> dict[str, Any]:
    return assess_many(query, [app], locale,
                       reviewed_support={app.get("id"): reviewed_support} if reviewed_support else None)[0]
