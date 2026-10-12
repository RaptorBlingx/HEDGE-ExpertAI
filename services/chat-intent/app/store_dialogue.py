"""Offline Store dialogue policy. Cached results bind identity, never supply facts."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

from hedge_shared.models_v2 import ChatRequestV2

from .routes import _ORDINALS

_PRICE = re.compile(r"\b(price|prices|pricing|cost|costs|cheapest|cheaper|free|paid|budget)\b", re.I)
_UNSUPPORTED_METADATA = re.compile(r"\b(supports?|capabilit\w*|compatible|protocols?|mqtt|opc[- ]?ua|versions?|licen[cs]es?|prices?|categories|translations?|certifi\w*|ratings?)\b", re.I)
# A closed browsing grammar: domain constraints/negation remain search terms.
# Compose verbs, catalogue nouns and availability qualifiers, not exact questions.
_BROWSE = re.compile(
    r"(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?"
    r"(?:show(?:\s+me)?|list|browse|display|what|which)"
    r"(?:\s+(?:all|the|available|published|currently|store|hedge))*"
    r"\s+(?:apps?|applications?|catalog(?:ue)?)"
    r"(?:\s+(?:are|do|you|have|available|published|currently|in|the|store|hedge|catalog(?:ue)?))*[?!.]*",
    re.I,
)
_REFERENCE = re.compile(r"\b(it|that app|this app|both|them|these apps|those apps)\b", re.I)


class StoreDialogue:
    """Use existing recommendation/quoting seams plus authoritative scoped resolution."""

    def __init__(self, recommend: Callable[..., Awaitable[dict]],
                 resolve: Callable[[list[str] | None], list[dict]],
                 describe: Callable[[str, list[dict], str], str]):
        self.recommend = recommend
        self.resolve = resolve
        self.describe = describe

    async def respond(self, req: ChatRequestV2, intent: str, context: dict) -> dict:
        current = self.resolve(None)
        message = req.message
        previous = [item.get("app", item)["id"] for item in context.get("last_results", [])]
        named_apps = [app for app in current
                 if any(value and re.search(rf"(?<!\w){re.escape(value)}(?!\w)", message, re.I)
                        for value in (app.get("name"), app["app_id"]))]
        named = [app["id"] for app in named_apps]
        ordinals = [index for token, index in _ORDINALS.items()
                    if re.search(rf"\b{re.escape(token)}\b", message, re.I)]
        targeted = intent in {"detail", "compare"} or bool(ordinals) or bool(_REFERENCE.search(message))
        selected = named if targeted else []
        if targeted and not selected:
            if intent == "compare" and re.search(r"\bfirst (two|three|2|3)\b", message, re.I):
                count = 3 if re.search(r"\b(three|3)\b", message, re.I) else 2
                selected = previous[:count] if len(previous) >= count else []
            elif ordinals:
                # Any unresolved ordinal fails instead of silently comparing a subset.
                selected = [previous[i] for i in sorted(set(ordinals))] if max(ordinals) < len(previous) else []
            elif _REFERENCE.search(message):
                selected = previous if intent == "compare" or re.search(r"\b(both|them|these apps|those apps)\b", message, re.I) else context.get("focused_ids", [])
        selected = list(dict.fromkeys(selected))
        unsupported = _PRICE.search(message) or _UNSUPPORTED_METADATA.search(message)
        filters = req.filters.model_dump(mode="json")
        if targeted or intent == "refine":
            filters = {**(context.get("filters") or {}),
                       **{k: v for k, v in filters.items() if v not in (None, [], "")}}
        invalid_filters = any(v not in (None, [], "") for k, v in filters.items() if k != "publisher")
        if unsupported or invalid_filters:
            return self._response(
                "The supported Store projection does not provide verified prices, structured capabilities, or the requested metadata, "
                "or the requested filter. I cannot confirm support, cost, or suitability. "
                "Ask for an App's supplied description or compare its source fields.", [], intent, context,
            )
        if _BROWSE.fullmatch(message.strip()):
            apps = current
            if filters.get("publisher"):
                apps = [a for a in apps if filters["publisher"].casefold() in (a.get("provider") or "").casefold()]
            # Stable listing order, no similarity score or claim of full Store coverage.
            apps = sorted(apps, key=lambda app: app["app_id"])[:5]
            results = [{"app": app, "rank": i + 1, "evidence_fields": ["catalogue"]}
                       for i, app in enumerate(apps)]
            text = (f"Showing {len(apps)} currently eligible Apps from this isolated snapshot (up to 5). "
                    "This snapshot may be incomplete; coverage of the entire HEDGE catalogue is not established. "
                    "Listing order is not a relevance ranking.")
            if results:
                text += "\n" + self.describe(message, results, req.locale)
            next_context = {"last_query": "", "filters": filters, "last_results": results,
                            "focused_ids": [apps[0]["id"]] if len(apps) == 1 else []}
            return self._response(text, results, "browse", next_context)

        if selected or targeted:
            apps = self.resolve(selected)
            if filters.get("publisher"):
                apps = [a for a in apps if filters["publisher"].casefold() in (a.get("provider") or "").casefold()]
            if len(apps) != len(selected) or not apps or (intent == "compare" and len(apps) < 2):
                return self._response(
                    "I cannot resolve those references to currently published Apps. "
                    "Search for Apps or provide their names; comparison needs at least two.", [], intent, context,
                )
            results = [{"app": app, "rank": i + 1, "evidence_fields": ["reference"]}
                       for i, app in enumerate(apps)]
            text = "Supplied source fields only; missing metadata cannot be confirmed.\n" + self.describe(message, results, req.locale)
            if intent == "compare":
                text = "Source-field comparison only; no superiority or suitability is inferred.\n" + text
            next_context = {**context, "filters": filters, "focused_ids": selected}
            if intent != "compare" and len(selected) == 1:
                intent = "detail"
            return self._response(text, results, intent, next_context)

        # Remove only request boilerplate, not content terms or negation. Dense
        # retrieval (when available) still receives the remaining natural query.
        query = re.sub(r"^(?:please\s+)?(?:find|search for|show me|recommend|i need|i am looking for)\s+", "", message, flags=re.I)
        query = re.sub(r"^(?:an?\s+)?(?:apps?|applications?)\s+(?:for|to|about|that)\s+", "", query, flags=re.I)
        if named:
            names = [(app["name"] or app["app_id"]).replace('"', " ") for app in named_apps]
            query = " OR ".join('"' + name + '"' for name in names)
        if intent == "refine" and context.get("last_query"):
            query = context["last_query"] + " " + query
        response = await self.recommend(query=query, locale=req.locale, filters=filters)
        next_context = {"last_query": query, "filters": filters,
                        "last_results": response["apps"][:5],
                        "focused_ids": [response["apps"][0]["app"]["id"]] if len(response["apps"]) == 1 else []}
        if not response["apps"]:
            response["message"] += " A missing match does not establish that a product lacks a feature."
        return {**response, "intent": intent, "context": next_context}

    @staticmethod
    def _response(message, apps, intent, context):
        return {"message": message, "apps": apps, "intent": intent, "context": context}
