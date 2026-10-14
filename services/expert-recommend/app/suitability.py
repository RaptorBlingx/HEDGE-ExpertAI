"""Source-supported admission, independent of retrieval rank or similarity scores.

Direct textual support is a bounded baseline, not a semantic relevance benchmark.
Unresolved paraphrases/constraints remain visible as unverified candidates.
"""
from __future__ import annotations

import re
from typing import Any

# Request scaffolding only; retain content verbs and all restriction/negation words.
_REQUEST_WORDS = set("a an the app apps application applications please find search show me for to "
                     "that can could you i need looking recommend about with support supports does "
                     "do give want some available in on and".split())
_LIMITATION = re.compile(
    r"\b(not|no|never|cannot|unsupported|unavailable|unimplemented|lacks|without|except|only|unless|unlike|simulation|simulated|prototype)\b|"
    r"\b(?:can|doesn|don|isn|aren|won)[\x27’]t\b|"
    r"\b(ignore|disregard)\s+(all\s+|previous\s+)?instructions\b|\?", re.I,
)
_OPERATING_LIMITATION = re.compile(
    r"\b(?:this\s+(?:app|application)|it)\s+(?:"
    r"(?:does|will)\s+not\s+(?:work|operate)\s+in\s+production|"
    r"(?:is|works?|operates?|runs?)\s+only\s+(?:in|for)\s+(?:simulation|testing|demonstrations?))\b|"
    r"(?:^|[.!?]\s+)only\s+(?:in|for)\s+(?:simulation|testing|demonstrations?)\b", re.I,
)
_REQUEST_LIMITATION = re.compile(r"\b(not|without|except|only|cheapest|best|better)\b", re.I)


def _terms(text: str) -> set[str]:
    terms = set()
    for word in re.findall(r"[^\W_]+", text.casefold()):
        if word in _REQUEST_WORDS:
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us")):
            word = word[:-1]
        if len(word) > 5 and word.endswith("ing"):
            word = word[:-3]
        terms.add(word)
    return terms


def source_text(app: dict[str, Any], locale: str) -> dict[str, str]:
    """Original functional field paths; no rank, provider, price or inferred ontology."""
    if app.get("source_profile") == "hedge-store-v1":
        evidence = app.get("source_evidence")
        if isinstance(evidence, dict):
            return {path: value for path, value in evidence.items()
                    if isinstance(path, str) and isinstance(value, str) and value and (
                        path in {"description", "readme"}
                        or path == "dataspaceAppDescription.properties.description"
                        or path.startswith("dataspaceAppDescription.properties.featureList[")
                    )}
        description = app.get("description")
        return {"description": description} if isinstance(description, str) and description else {}
    evidence = {}
    if isinstance(app.get("description"), str) and app["description"]:
        evidence["description"] = app["description"]
    summary = app.get("summary")
    if isinstance(summary, dict):
        language = locale if summary.get(locale) else "en"
        if isinstance(summary.get(language), str) and summary[language]:
            evidence[f"summary.{language}"] = summary[language]
    capabilities = app.get("capabilities")
    for index, capability in enumerate(capabilities if isinstance(capabilities, list) else []):
        if isinstance(capability, str) and capability:
            evidence[f"capabilities[{index}]"] = capability
    for direction in ("inputs", "outputs"):
        contracts = app.get(direction)
        for index, contract in enumerate(contracts if isinstance(contracts, list) else []):
            if isinstance(contract, dict) and isinstance(contract.get("description"), str):
                evidence[f"{direction}[{index}].description"] = contract["description"]
    return evidence


def assess(query: str, app: dict[str, Any], locale: str) -> dict[str, Any]:
    """Admit direct, unqualified source support; uncertainty never means exclusion.

    All content terms must occur in one source sentence. A name can establish an
    identity lookup, not a capability. The LLM may decline these admissions but
    cannot promote an unsupported candidate or generate factual claims.
    """
    title = app.get("name") if app.get("source_profile") == "hedge-store-v1" else app.get("title")
    identity_path = "name" if app.get("source_profile") == "hedge-store-v1" else "title"
    if isinstance(title, dict):
        language = locale if title.get(locale) else "en"
        identity_path = f"title.{language}"
        title = title.get(language)
    if not title and app.get("app_id"):
        identity_path = "appId"
    names = re.findall(r'"([^"\n]+)"', query)
    identity_query = bool(names) and re.fullmatch(r'"[^"\n]+"(?:\s+OR\s+"[^"\n]+")*', query.strip())
    identity = str(title or app.get("app_id") or "")
    identity_match = identity in names if identity_path == "appId" else identity.casefold() in {name.casefold() for name in names}
    if identity and identity_query and identity_match:
        return {"status": "source_supported", "reason": "requested_identity",
                "evidence_fields": [identity_path]}
    terms = _terms(query)
    fields = source_text(app, locale)
    if not terms or _REQUEST_LIMITATION.search(query):
        return {"status": "uncertain", "reason": "request_needs_clarification", "evidence_fields": []}
    support = []
    limited = []
    operating_limit = any(_OPERATING_LIMITATION.search(text) for text in fields.values())
    for path, text in fields.items():
        # No truncation or removal of qualifications. Oversized input cannot admit a match.
        if len(text) > 16000:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if terms <= _terms(sentence):
                (limited if _LIMITATION.search(sentence) or operating_limit
                 else support).append(path)
    if limited:
        return {"status": "uncertain", "reason": "qualified_or_negative_source",
                "evidence_fields": list(dict.fromkeys(limited))}
    return {"status": "source_supported" if support else "uncertain",
            "reason": "direct_source_support" if support else "no_direct_source_support",
            "evidence_fields": list(dict.fromkeys(support))}
