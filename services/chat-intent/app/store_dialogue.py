"""Offline Store dialogue policy. Cached results bind identity, never supply facts."""

from __future__ import annotations

import asyncio
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
# Explicit source-field reads are separate from capability/suitability questions.
# Full matches keep constraints such as "only free Apps" out of this path.
_SOURCE_FIELDS = {
    "readme": ("readme",),
    "embedded metadata": ("dataspaceAppDescription.",),
    "connector fields": ("builtForConnector", "connectorVersion"),
    "connector version": ("connectorVersion",),
    "versions": ("appVersionList[",),
    "billing fields": ("billable", "price"),
    "price": ("price", "billable"),
    "type": ("type",),
}
_SOURCE_READ = re.compile(
    r"(?:show|quote|list)(?: me)? (?:the )?(" + "|".join(_SOURCE_FIELDS) +
    r")(?: (?:for|of) (.+?))?[?!.]*", re.I,
)
_REFERENCE = re.compile(r"\b(it|that app|this app|both|them|these apps|those apps)\b", re.I)


def _mentions(app: dict, message: str) -> bool:
    return any(value and re.search(rf"(?<!\w){re.escape(value)}(?!\w)", message, flags)
               for value, flags in ((app.get("name"), re.I), (app["app_id"], 0)))


class StoreDialogue:
    """Use existing recommendation/quoting seams plus authoritative scoped resolution."""

    def __init__(self, recommend: Callable[..., Awaitable[dict]],
                 resolve: Callable[[list[str] | None], list[dict]],
                 describe: Callable[[str, list[dict], str], str],
                 generate: Callable[..., dict] | None = None, *, catalogue_references: bool = False):
        self.recommend = recommend
        self.resolve = resolve
        self.describe = describe
        self.generate = generate
        self.catalogue_references = catalogue_references

    def route_intent(self, message: str, intent: str) -> str:
        """Explicit Store entities/references outrank statistical small-talk labels."""
        if not self.catalogue_references or intent == "reset":
            return intent
        if re.match(r"^(?:please\s+)?compare\b", message, re.I):
            return "compare"
        if _BROWSE.fullmatch(message.strip()):
            return "search"
        if not _SOURCE_READ.fullmatch(message.strip()) and re.match(
            r"^(?:please\s+)?(?:find|search|recommend|show me)\b", message, re.I
        ):
            return "search"
        known = any(_mentions(app, message) for app in self.resolve(None))
        reference = bool(re.search(r"\b(?:first|second|third|fourth|fifth) app\b", message, re.I) or
                         _REFERENCE.search(message))
        if known or reference or _SOURCE_READ.fullmatch(message.strip()):
            return "compare" if re.search(r"\bcompare\b", message, re.I) else "detail"
        return intent

    async def respond(self, req: ChatRequestV2, intent: str, context: dict) -> dict:
        response = await self._respond(req, intent, context)
        if self.generate and response.get("intent") != "source_fields":
            rendered = await asyncio.to_thread(self.generate, req.message, response["apps"],
                                               req.locale, response["intent"], response["message"])
            # A slow model must not expose facts from a withdrawn/changed App.
            fresh = {app["id"]: app for app in self.resolve([r["app"]["id"] for r in response["apps"]])}
            if any(fresh.get(r["app"]["id"]) != r["app"] for r in response["apps"]):
                response.update(message="The local snapshot changed while preparing this reply. Please search again.", apps=[])
                response["context"].update(last_results=[], focused_ids=[])
                response["generation"] = {"source": "deterministic", "reason": "catalogue_changed"}
            else:
                response.update(message=rendered["message"], generation=rendered["generation"])
                label = (("Model-assisted source selection" if self.catalogue_references else "Validated Ollama source excerpts")
                         if rendered["generation"]["source"] == "ollama"
                         else "Deterministic source fallback")
                response["message"] = f"*{label}.*\n" + response["message"]
        return response

    async def _respond(self, req: ChatRequestV2, intent: str, context: dict) -> dict:
        current = self.resolve(None)
        message = req.message
        source_read = _SOURCE_READ.fullmatch(message.strip())
        source_target = source_read[2] if source_read else None
        seeded = self.catalogue_references and not context.get("turn") and not context.get("last_results")
        if seeded:
            context = {**context, "last_results": [{"app": app, "rank": i + 1}
                       for i, app in enumerate(sorted(current, key=lambda a: a["app_id"])[:5])]}
        previous = [item.get("app", item)["id"] for item in context.get("last_results", [])]
        named_apps = [app for app in current if _mentions(app, message)]
        named = [app["id"] for app in named_apps]
        ordinals = [index for token, index in _ORDINALS.items()
                    if re.search(rf"\b{re.escape(token)}\b", message, re.I)]
        targeted = bool(source_read) or intent in {"detail", "compare"} or bool(ordinals) or bool(_REFERENCE.search(message))
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
        if self.catalogue_references and selected and _PRICE.search(message) and not source_read:
            # A cost question asks for supplied values, never a free/paid verdict.
            # Unsupported filters still fail closed below; this does not rank by price.
            source_read = _SOURCE_READ.fullmatch("Show billing fields")
            source_target = None
            context = {**context, "focused_ids": selected}
        if source_read and not invalid_filters:
            # Resolve the complete target, not names/ordinals occurring elsewhere
            # in the question. Native IDs are opaque and case-sensitive; duplicate
            # names require an explicit ID rather than silently selecting both.
            selected = context.get("focused_ids", [])
            if source_target:
                exact_ids = [a["id"] for a in current if a["app_id"] == source_target]
                exact_names = [a["id"] for a in current
                               if (a.get("name") or "").casefold() == source_target.casefold()]
                ordinal = next((index for token, index in _ORDINALS.items()
                                if source_target.casefold() == f"the {token} app"), None)
                if exact_ids:
                    selected = exact_ids
                elif len(exact_names) == 1:
                    selected = exact_names
                elif source_target.casefold() in {"both", "both apps", "these apps", "those apps"}:
                    selected = previous
                elif ordinal is not None:
                    selected = [previous[ordinal]] if ordinal < len(previous) else []
                elif source_target.casefold() not in {"it", "this app", "that app"}:
                    selected = []
            apps = self.resolve(selected)
            if filters.get("publisher"):
                apps = [a for a in apps if filters["publisher"].casefold() in (a.get("provider") or "").casefold()]
            if not selected or len(apps) != len(selected):
                return self._response("Choose a currently published App by exact name/native ID or an existing reference; "
                                      "source-field reads do not apply additional constraints.",
                                      [], "source_fields", context)
            field = source_read[1].casefold()
            prefixes = _SOURCE_FIELDS[field]
            results = [{"app": app, "rank": i + 1, "evidence_fields": ["reference"]}
                       for i, app in enumerate(apps)]
            lines = ["Supplied Store source values only; these do not establish suitability or compatibility."]
            if field in {"price", "billing fields"}:
                lines.append("Currency, billing period, taxes and licence terms are unspecified. "
                             "billable=false or price=0 does not establish that an App is free.")
            if field == "versions":
                lines.append("Versions are in source order; no current or latest version is inferred.")
            for result in results:
                evidence = {path: value for path, value in result["app"].get("source_evidence", {}).items()
                            if any(path == prefix or
                                   (prefix.endswith((".", "[")) and path.startswith(prefix))
                                   for prefix in prefixes)}
                # Reuse the SCRUM-38 whole-quotation and escaping boundary. The
                # complete authoritative projection stays in the result/card.
                if evidence:
                    view = {**result["app"], "source_evidence": evidence,
                            "readme_status": None, "dataspace_description_status": None}
                    lines.append(self.describe(f"Show {field}", [{**result, "app": view}], req.locale))
                else:
                    status_key = {"readme": "readme_status", "embedded metadata": "dataspace_description_status"}.get(field)
                    status = result["app"].get(status_key) if status_key else "missing"
                    # Statuses are normalized enums, never raw publisher strings.
                    status = status if status in {"missing", "too_large", "malformed", "unsupported_shape",
                                                   "no_supported_text", "not_projected", "extracted"} else "unavailable"
                    lines.append(f"App {result['rank']}: requested source evidence is {status}. "
                                 "Missing projected evidence does not establish absence of a capability.")
            next_context = {**context, "filters": filters, "focused_ids": selected}
            return self._response("\n".join(lines), results, "source_fields", next_context)
        if (unsupported and not (self.catalogue_references and selected and not _PRICE.search(message))) or invalid_filters:
            limitation = ("This snapshot has no verified price information. I cannot confirm what it costs. "
                          if _PRICE.search(message) else
                          "The supplied Store fields do not verify that capability, metadata or filter. "
                          "I cannot confirm support or suitability. ")
            return self._response(limitation + "I can describe an App's supplied fields or compare the source descriptions.",
                                  [], intent, context)
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
            if seeded and named:
                next_context["last_results"] = results
            if seeded and not named:
                text = "References use the observed catalogue order shown on this page.\n" + text
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
        if response["apps"]:
            response["message"] = ("Retrieved source records; order does not establish suitability.\n"
                                   + response["message"])
        if not response["apps"]:
            response["message"] += " A missing match does not establish that a product lacks a feature."
        return {**response, "intent": intent, "context": next_context}

    @staticmethod
    def _response(message, apps, intent, context):
        return {"message": message, "apps": apps, "intent": intent, "context": context}
