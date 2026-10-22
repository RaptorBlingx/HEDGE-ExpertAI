"""Answers to a known question about known Apps, from their current Store source.

The dialogue has already decided what is asked (a field, a capability, an open
question) and about which Apps; nothing here re-reads the wording to change
that. Capability answers reuse the single recommendation verifier; field
answers quote supplied values without inferring business meaning (a listed
price of 0 does not establish free use).
"""
from __future__ import annotations

import re

from . import app_guide, evidence
from .recommender import _partial_line, _quoted_store_text, decision_message
from .review import reviewed_decision

FIELDS = ("provider", "price", "access", "details")
# Extractive answers quote statements at least this similar to the question.
_EXTRACT_FLOOR = 0.80
_URL = re.compile(r"https?://[^\s<>\"\\]+")


_CONDITIONS = {"pricing": "free use or other pricing conditions", "license_spdx": "licensing",
               "capabilities": "capabilities", "protocols": "protocol support", "semantic_uri": "semantic class",
               "extension_uri": "semantic extension", "deployment_modes": "deployment modes",
               "supported_languages": "supported languages", "data_classifications": "data classifications",
               "lifecycle_status": "lifecycle status", "tags": "tags"}


def listing(apps: list[dict]) -> str:
    """Each App with the lead statement of its description."""
    lines = []
    for app in apps:
        guide = app_guide.build(app)
        lines.append(_claim(guide) if guide.lead else f"**{_name(app)}**")
    return "\n\n".join(lines)


def unverified(fields: list[str]) -> str:
    """Conditions the Store metadata cannot establish, kept for the provider to confirm."""
    if fields == ["pricing"]:
        return ("The Store metadata doesn’t establish which Apps meet your pricing requirement. "
                "A listed price of 0 doesn’t confirm free use. Check licence terms and any usage fees "
                "with the provider. I can show the listed prices or compare Apps by what they do.")
    requested = ", ".join(dict.fromkeys(_CONDITIONS.get(key, "catalogue conditions") for key in fields))
    return (f"The Store metadata doesn’t verify the requested {requested}. "
            "I can show the supplied fields for an App, or compare its documented capabilities. "
            "Keep that requirement as something to confirm with the provider.")


def _name(app: dict) -> str:
    return _quoted_store_text(app.get("name") or app["app_id"]) or "This App"


def fact_answer(field: str, apps: list[dict]) -> str:
    return "\n\n".join(_FACTS[field](app) for app in apps)


def _provider(app: dict) -> str:
    provider = _quoted_store_text(app.get("provider") or "")
    return f"**{_name(app)}** is provided by **{provider}**." if provider else f"No provider is listed for **{_name(app)}**."


def _price(app: dict) -> str:
    price = app.get("source_evidence", {}).get("price")
    try:
        zero = price is not None and float(price) == 0
    except (TypeError, ValueError):
        zero = False
    if price is None:
        return f"No price is listed for **{_name(app)}**. I’d check the cost with the provider."
    if zero:
        return (f"Pricing isn’t confirmed for **{_name(app)}**. The Store lists a price of 0, but that doesn’t "
                "establish free use. Check the terms with the provider.")
    return (f"**{_name(app)}** lists a price of {_quoted_store_text(str(price)) or '—'}; "
            "the currency and billing period aren’t specified.")


def _access(app: dict) -> str:
    guide = app_guide.build(app)
    statements = guide.by_role("access")
    urls = list(dict.fromkeys(u.rstrip(".,;)") for s in statements for u in _URL.findall(s.quote)
                              if not re.search(r"[\[\]()]", u.rstrip(".,;)"))))
    notes = [s.text for s in statements if not _URL.search(s.text)]
    if not urls and not notes:
        return (f"**{_name(app)}**’s Store entry doesn’t say how to access it. You can open its Store entry "
                "from the App card, and the provider can confirm how to get access.")
    return (f"**Access to {_name(app)}**, according to its Store entry:" + "".join(f"\n- “{_quoted_store_text(n)}”" for n in notes)
            + "".join(f"\n- [{u}]({u})" for u in urls[:3]))


def _details(app: dict) -> str:
    source = app.get("source_evidence", {})
    labels = {"type": "Type", "builtForConnector": "Built for connector", "connectorVersion": "Connector version"}
    lines = [f"- {label}: {_quoted_store_text(source[path])}" for path, label in labels.items() if source.get(path)]
    versions = [source[p] for p in source if re.fullmatch(r"appVersionList\[\d+\]\.version", p)]
    if versions:
        lines.append("- Versions, in Store order: " + ", ".join(_quoted_store_text(v) or "" for v in versions))
    if not lines:
        return f"**{_name(app)}**’s Store entry lists no technical details beyond its description."
    return f"Supplied Store details for **{_name(app)}**:\n" + "\n".join(lines)


_FACTS = {"provider": _provider, "price": _price, "access": _access, "details": _details}


def capability_answer(need: str, rows: list[dict], locale: str) -> dict:
    """Whether these Apps document a need: the verifier's decision, said plainly."""
    decision = reviewed_decision(need, rows, locale)
    selected, candidates = decision["apps"], decision["candidates"]
    if selected:
        message = decision_message(selected, [], direct=len(rows) == 1)
        # When choosing between named Apps, say what the others' descriptions state.
        chosen = {r["app"]["id"] for r in selected}
        for row in [r for r in candidates if r["app"]["id"] not in chosen]:
            stated = next((f for f in row.get("suitability", {}).get("requirements", [])
                           if f["status"] in {"excluded", "limited"} and f.get("quote")), None)
            message += (f"\n\n**{_name(row['app'])}**’s description says: “{_quoted_store_text(stated['quote'])}”"
                        if stated else f"\n\n**{_name(row['app'])}**’s description doesn’t document that.")
    elif len(rows) == 1:
        message = _single_gap(need, (candidates or rows)[0])
    elif any(r.get("suitability", {}).get("status") == "partial" for r in candidates):
        message = decision_message([], candidates)
    else:
        lines = ["I couldn’t confirm that from the descriptions of "
                 + ", ".join(f"**{_name(r['app'])}**" for r in rows[:-1]) + f" or **{_name(rows[-1]['app'])}**."]
        for row in rows:
            nearby = _nearby(row["app"], need)
            if nearby:
                lines.append(f"- **{_name(row['app'])}** says: “{_quoted_store_text(nearby)}”")
        message = "\n\n".join([lines[0], "\n".join(lines[1:])] if len(lines) > 1 else lines)
    return {**decision, "message": message}


def search_answer(need: str, rows: list[dict], locale: str) -> dict:
    """A search's candidates, with paraphrased matches reviewed when the verifier found none."""
    decision = reviewed_decision(need, rows, locale)
    return {**decision, "message": decision_message(decision["apps"], decision["candidates"])}


def _single_gap(need: str, row: dict) -> str:
    name = _name(row["app"])
    findings = row.get("suitability", {}).get("requirements", [])
    stated = next((f for f in findings if f["status"] == "excluded"), None)
    if stated:
        return f"No. **{name}**’s description says: “{_quoted_store_text(stated['quote'])}”"
    related = [f for f in findings if f["status"] == "related"]
    if related and len(related) == len(findings):
        # Related wording is not partial support.
        return (f"I can’t confirm that from **{name}**’s description. The closest statement is: "
                f"“{_quoted_store_text(related[0]['quote'])}”")
    if row.get("suitability", {}).get("status") == "partial":
        return "Partly. " + _partial_line(row)
    guide = app_guide.build(row["app"])
    message = f"I couldn’t confirm that from **{name}**’s description."
    if guide.lead:
        message += " What it does document: " + _claim(guide)
        nearby = _nearby(row["app"], need, exclude=guide.lead.text)
        if nearby:
            message += f"\n\nIt also says: “{_quoted_store_text(nearby)}”"
    return message


def _claim(guide: app_guide.Guide) -> str:
    from .explainer import _claim
    return _claim(guide, guide.lead)


def _nearby(app: dict, question: str, exclude: str = "") -> str:
    statements = [s for s in _ranked(app_guide.build(app), question) if s.text != exclude]
    return statements[0].text if statements else ""


def _ranked(guide: app_guide.Guide, question: str) -> list[app_guide.Statement]:
    """The guide's statements most related to a question: E5 when available, else shared words."""
    candidates = [s for s in guide.statements if s.role not in {"attribution"}]
    if not candidates:
        return []
    # Embeddings under-rate negated sentences; compare what each statement is about
    # ("does not control turbine operation" is about controlling turbines).
    scores = evidence._similarity([question], [evidence._topic(s.text) for s in candidates])
    asked = evidence.terms(question)
    if scores:
        # Like the verifier's nominations: very close, or close and sharing the question's wording.
        ranked = sorted(zip(scores[0], candidates, strict=True), key=lambda pair: -pair[0])
        return [s for score, s in ranked if score >= evidence.DENSE_MATCH
                or score >= _EXTRACT_FLOOR and asked & evidence.terms(s.text)][:2]
    ranked = sorted(candidates, key=lambda s: -len(asked & evidence.terms(s.text)))
    return [s for s in ranked if len(asked & evidence.terms(s.text)) >= max(1, len(asked) // 2)][:2]


def extractive_answer(question: str, apps: list[dict]) -> str:
    """The source statements that bear on an open question, quoted, without generation."""
    lines = []
    for app in apps:
        guide = app_guide.build(app)
        statements = _ranked(guide, question)
        if statements:
            lines.append(f"From **{_name(app)}**’s description:" + "".join(
                f"\n- “{_quoted_store_text(s.text)}”" for s in statements))
    if lines:
        return "\n\n".join(lines)
    documented = "\n".join(f"- {_claim(g)}" for g in map(app_guide.build, apps) if g.lead)
    return ("The description" + ("s don’t" if len(apps) > 1 else " doesn’t") + " say that directly."
            + (f" What {'they' if len(apps) > 1 else 'it'} document{'' if len(apps) > 1 else 's'}:\n{documented}" if documented else "")
            + "\n\nThe provider can answer questions the Store entry doesn’t cover.")
