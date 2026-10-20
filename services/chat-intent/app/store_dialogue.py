"""Offline Store dialogue policy. Cached results bind identity, never supply facts."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable

from hedge_shared.models_v2 import ChatRequestV2
from hedge_shared.store_language import (
    catalogue_question,
    control_words,
    dialogue_language,
    factual_question,
    inspection_target,
    localize_prose,
    search_language,
)

from .routes import _ORDINALS

_PRICE = re.compile(r"\b(price|prices|pricing|cost|costs|cheapest|cheaper|free|paid|budget)\b", re.I)
_UNSUPPORTED_METADATA = re.compile(r"\b(supports?|capabilit\w*|compatible|protocols?|mqtt|opc[- ]?ua|versions?|licen[cs]es?|prices?|categories|translations?|certifi\w*|ratings?)\b", re.I)
# Explicit source-field reads are separate from capability/suitability questions.
# Full matches keep constraints such as "only free Apps" out of this path.
_SOURCE_FIELDS = {
    "provider": ("provider",),
    "purpose": ("description", "readme"),
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
    r"(?:(?:show|quote|list)(?: me)?|(?:can|could|may) (?:i|we) (?:see|read)) (?:the |its )?(" + "|".join(_SOURCE_FIELDS) +
    r")(?: (?:for|of) (.+?))?[?!.]*", re.I,
)
_REFERENCE = re.compile(r"\b(it|that app|this app|that one|this one|both|them|these apps|those apps|the other (?:app|one)|bu uygulama|bunu)\b", re.I)


def _mentions(app: dict, message: str) -> bool:
    return any(value and re.search(rf"(?<!\w){re.escape(value)}(?!\w)", message, flags)
               for value, flags in ((app.get("name"), re.I), (app["app_id"], 0)))


def _search_query(message: str) -> str:
    """Remove request boilerplate, retaining functional terms and negation."""
    query = re.sub(r"^(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?(?:find|search(?: for)?|show me|recommend|i need|i am looking for)\s+", "", message, flags=re.I)
    return re.sub(r"^(?:an?\s+)?(?:apps?|applications?)\s+(?:for|to|about|that)\s+", "", query, flags=re.I)


def _comparison_criterion(message: str, apps: list[dict]) -> str:
    """Retain an explicit criterion separately from resolved comparison subjects."""
    arguments = message
    identities = {value for app in apps for value in (app.get("name"), app["app_id"]) if value}
    for value in sorted(identities, key=len, reverse=True):
        arguments = re.sub(rf"(?<!\w){re.escape(value)}(?!\w)", "", arguments, flags=re.I)
    criterion = re.search(r"\b(?:for|in terms of)\s+(.+)", arguments, re.I)
    if not criterion:
        return ""
    scaffolding = {"please", "can", "could", "would", "you", "compare", "and", "with", "the", "app", "apps", "one", "ones", "two", "three",
                   "it", "that", "this", "both", "them", "these", "those", "other", *_ORDINALS}
    if not set(control_words(arguments[:criterion.start()]).split()) <= scaffolding:
        # Unknown modifiers before the criterion may be constraints. Keep the
        # whole operand rather than silently approving a narrower requirement.
        return arguments.strip()
    return criterion[1].strip().rstrip("?!.,")


class StoreDialogue:
    """Use existing recommendation/quoting seams plus authoritative scoped resolution."""

    def __init__(self, recommend: Callable[..., Awaitable[dict]],
                 resolve: Callable[[list[str] | None], list[dict]],
                 describe: Callable[[str, list[dict], str], str],
                 generate: Callable[..., dict] | None = None, *, catalogue_references: bool = False,
                 assess_requirements: bool = False, decide: Callable[..., dict] | None = None):
        self.recommend = recommend
        self.resolve = resolve
        self.describe = describe
        self.generate = generate
        self.catalogue_references = catalogue_references
        self.assess_requirements = assess_requirements
        self.decide = decide

    def route_intent(self, message: str, intent: str) -> str:
        """Explicit Store entities/references outrank statistical small-talk labels."""
        message = dialogue_language(message, "tr")
        if not self.catalogue_references or intent == "reset":
            return intent
        if re.match(r"^(?:please\s+)?compare\b|^how do (?:these|those|they|the apps) differ[?!.]*$", message, re.I):
            return "compare"
        if catalogue_question(message):
            return "search"
        if re.fullmatch(r"(?:please\s+)?show me (?:the )?(?:first|second|third|fourth|fifth|[1-5]) app[?!.]*", message, re.I):
            return "detail"
        if not _SOURCE_READ.fullmatch(message.strip()) and re.match(
            r"^(?:please\s+)?(?:find|search|recommend|show me)\b", message, re.I
        ):
            return "search"
        if re.search(r"\buygulama(?:ları)? (?:bul|öner)[?!.]*$", message, re.I):
            return "search"
        known = any(_mentions(app, message) for app in self.resolve(None))
        reference = bool(re.search(r"\b(?:first|second|third|fourth|fifth) (?:app|one)\b", message, re.I) or
                         _REFERENCE.search(message))
        if known or reference or _SOURCE_READ.fullmatch(message.strip()):
            return "compare" if re.search(r"\bcompare\b", message, re.I) else "detail"
        return intent

    async def respond_with_history(self, req, intent, context, history, *, nlu=None):
        return await self.respond(req, intent, context)

    async def respond(self, req: ChatRequestV2, intent: str, context: dict) -> dict:
        normalized = dialogue_language(req.message, req.locale)
        if re.fullmatch(r"how do (?:these|those|they|the apps) differ[?!.]*", normalized, re.I):
            normalized = "Compare both"
        # Route the normalized control grammar, retaining the actual request locale.
        routed = self.route_intent(normalized, intent)
        response = await self._respond(req.model_copy(update={"message": normalized}), routed, context)
        response["message"] = localize_prose(response["message"], req.locale)
        if self.generate and response.get("intent") != "source_fields":
            rendered = await asyncio.to_thread(self.generate, req.message, response["apps"],
                                               req.locale, response["intent"], response["message"])
            # A slow model must not expose facts from a withdrawn/changed App.
            visible_rows = [*response["apps"], *response.get("candidates", [])]
            fresh = {app["id"]: app for app in self.resolve([r["app"]["id"] for r in visible_rows])}
            if any(fresh.get(r["app"]["id"]) != r["app"] for r in visible_rows):
                response.update(message="The local snapshot changed while preparing this reply. Please search again.", apps=[], candidates=[])
                response["context"].update(last_results=[], focused_ids=[])
                response["generation"] = {"source": "deterministic", "reason": "catalogue_changed"}
                response["decision"] = {"outcome": "abstained", "reason": "catalogue_changed"}
            else:
                prior_candidates = response.get("candidates", [])
                if rendered.get("abstained") and response["intent"] in {"search", "refine"}:
                    response["candidates"] = [*response.get("candidates", []),
                        *[{**row, "suitability": {**row.get("suitability", {}), "status": "uncertain", "reason": "model_declined"}}
                          for row in response["apps"]]]
                    response["apps"] = []
                    response["context"].update(last_results=[], focused_ids=[])
                    response["decision"] = {"outcome": "abstained", "reason": "model_abstention"}
                message = rendered["message"]
                if prior_candidates and rendered["generation"]["source"] == "ollama":
                    message += "\nUnverified retrieval candidates; they are not confirmed matches:\n"
                    message += self.describe(req.message, prior_candidates, req.locale)
                response.update(message=message, generation=rendered["generation"])
                label = ("Validated Ollama source excerpts" if rendered["generation"]["source"] == "ollama"
                         else "Deterministic source fallback")
                if rendered["generation"].get("reason") == "model_abstention":
                    label = "Validated model abstention"
                response["message"] = f"*{label}.*\n" + response["message"]
        return response

    async def _respond(self, req: ChatRequestV2, intent: str, context: dict) -> dict:
        current = self.resolve(None)
        message = req.message
        factual = factual_question(message) if req.locale == "en" else None
        target = inspection_target(message) if req.locale == "en" else None
        if target and (any(target == a["app_id"] or target.casefold() == (a.get("name") or "").casefold()
                           for a in current) or _REFERENCE.fullmatch(target) or
                       any(target.casefold() == f"the {token} app" for token in _ORDINALS)):
            factual = ("purpose", target)
        # Closed catalogue composition takes precedence over an inspection
        # clause inside it. Neither operation is a capability recommendation.
        browsing = catalogue_question(message)
        if browsing:
            factual = None
        source_read = _SOURCE_READ.fullmatch(
            f"Show {factual[0]} for {factual[1]}" if factual else message.strip())
        source_target = source_read[2] if source_read else None
        seeded = self.catalogue_references and not context.get("turn") and not context.get("last_results")
        if seeded:
            context = {**context, "last_results": [{"app": app, "rank": i + 1}
                       for i, app in enumerate(sorted(current, key=lambda a: a["app_id"])[:5])]}
            context["comparison_ids"] = [r["app"]["id"] for r in context["last_results"]]
        previous = [item.get("app", item)["id"] for item in context.get("last_results", [])]
        comparison = previous if len(previous) > 1 else context.get("comparison_ids", previous)
        for app in current:
            native = rf"(?<!\w){re.escape(app['app_id'])}(?!\w)"
            if (re.search(native, message, re.I) and not re.search(native, message)
                    and not (app.get("name") and re.search(
                        rf"(?<!\w){re.escape(app['name'])}(?!\w)", message, re.I))):
                return {**self._response("App IDs are case-sensitive. Please use the exact ID or the App's name.",
                                      [], "clarify", context),
                        "decision": {"outcome": "abstained", "reason": "invalid_native_reference"}}
        named_apps = [app for app in current if _mentions(app, message)]
        named = [app["id"] for app in named_apps]
        ordinals = [index for token, index in _ORDINALS.items()
                    if (intent in {"detail", "compare"} or source_read)
                    and re.search(rf"\b{re.escape(token)}\b", message, re.I)]
        targeted = bool(source_read) or intent in {"detail", "compare"} or bool(ordinals) or bool(_REFERENCE.search(message))
        if targeted and len(named_apps) > 1 and not any(
            app["app_id"] in message for app in named_apps
        ) and len({(app.get("name") or "").casefold() for app in named_apps}) < len(named_apps):
            return self._response("Multiple Apps have that name. Please use the exact native App ID.", [], intent, context)
        selected = named if targeted else []
        if intent == "compare" and len(named) == 1 and len(context.get("focused_ids", [])) == 1:
            # An explicit comparison with a named peer includes the current
            # subject; the named App must not displace that resolved reference.
            selected = list(dict.fromkeys(context["focused_ids"] + named))
        if targeted and not selected:
            if intent == "compare" and re.search(r"\bfirst (two|three|2|3)\b", message, re.I):
                count = 3 if re.search(r"\b(three|3)\b", message, re.I) else 2
                selected = comparison[:count] if len(comparison) >= count else []
            elif ordinals:
                # Any unresolved ordinal fails instead of silently comparing a subset.
                selected = [previous[i] for i in sorted(set(ordinals))] if max(ordinals) < len(previous) else []
            elif re.search(r"\bthe other (?:app|one)\b", message, re.I):
                group = context.get("comparison_ids") or previous
                alternatives = [i for i in group if i not in context.get("focused_ids", [])]
                selected = alternatives if len(context.get("focused_ids", [])) == 1 and len(alternatives) == 1 else []
                if selected and intent == "compare":
                    selected = context["focused_ids"] + selected
            elif _REFERENCE.search(message):
                selected = comparison if intent == "compare" or re.search(r"\b(both|them|these apps|those apps)\b", message, re.I) else context.get("focused_ids", [])
        selected = list(dict.fromkeys(selected))
        criterion = _comparison_criterion(message, [a for a in current if a["id"] in selected]) if intent == "compare" else ""
        price_question = _PRICE.search(message) if not criterion else None
        unsupported = price_question or (
            _UNSUPPORTED_METADATA.search(message) if not self.assess_requirements else False)
        # Price *words* also occur in functional needs such as forecasting.
        # Only an explicit commercial condition is a definitive filter refusal;
        # other substantive requests must retain semantic interpretation.
        pricing_filter = any(match[0].casefold() in {"free", "paid", "cheapest", "cheaper"}
                             for match in _PRICE.finditer(message))
        filters = req.filters.model_dump(mode="json")
        if targeted or intent == "refine":
            filters = {**(context.get("filters") or {}),
                       **{k: v for k, v in filters.items() if v not in (None, [], "")}}
        invalid_filters = any(v not in (None, [], "") for k, v in filters.items() if k != "publisher")
        if (self.catalogue_references and selected and price_question and not source_read
                and not re.search(r"\b(?:only|free|without|instead|not)\b", message, re.I)):
            # A cost question asks for supplied values, never a free/paid verdict.
            # Unsupported filters still fail closed below; this does not rank by price.
            source_read = _SOURCE_READ.fullmatch("Show billing fields")
            source_target = None
            context = {**context, "focused_ids": selected}
        if (self.catalogue_references and selected and not source_read and re.fullmatch(
            r"(?:how do (?:we|i) (?:get started with|start using) (?:it|this app|that app)|"
            r"(?:could|can) (?:we|i) (?:use|start using) (?:it|this app|that app) without installing (?:a )?container)[?!.]*",
            message, re.I,
        )):
            # This asks for documented access/setup information, not a new
            # capability recommendation. Other deployment constraints stay searches.
            source_read = _SOURCE_READ.fullmatch("Show readme")
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
                if len(exact_ids) > 1 or len(exact_names) > 1 and not exact_ids:
                    return self._response("Multiple Apps have that identity. Choose an App card or use a unique native ID.",
                                          [], "source_fields", context)
                if exact_ids:
                    selected = exact_ids
                elif len(exact_names) == 1:
                    selected = exact_names
                elif source_target.casefold() in {"both", "both apps", "them", "these apps", "those apps"}:
                    selected = comparison
                elif source_target.casefold() in {"the other app", "the other one"}:
                    group = context.get("comparison_ids") or previous
                    alternatives = [i for i in group if i not in context.get("focused_ids", [])]
                    selected = alternatives if len(context.get("focused_ids", [])) == 1 and len(alternatives) == 1 else []
                elif ordinal is not None:
                    selected = [previous[ordinal]] if ordinal < len(previous) else []
                elif not _REFERENCE.fullmatch(source_target):
                    selected = []
            apps = self.resolve(selected)
            if filters.get("publisher"):
                apps = [a for a in apps if filters["publisher"].casefold() in (a.get("provider") or "").casefold()]
            if not selected or len(apps) != len(selected):
                return self._response("I cannot resolve that reference. Choose a currently published App by exact name/native ID or an existing reference; "
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
                    lines.append((f"Uygulama {result['rank']}: istenen kaynak kanıtının durumu: {status}. "
                                  "Eksik kaynak kanıtı, özelliğin bulunmadığını kanıtlamaz.") if req.locale == "tr" else
                                 (f"App {result['rank']}: requested source evidence is {status}. "
                                  "Missing projected evidence does not establish absence of a capability."))
            next_context = {**context, "filters": filters, "focused_ids": selected}
            if seeded and named:
                next_context["last_results"] = results
            if seeded and ordinals and not named:
                lines.insert(1, "References use the observed catalogue order shown on this page.")
            return {**self._response("\n".join(lines), results, "source_fields", next_context),
                    "source_field": field,
                    "decision": {"outcome": "not_applicable", "reason": "source_inspection"}}
        if (unsupported and not (self.catalogue_references and selected and not price_question)) or invalid_filters or pricing_filter:
            if pricing_filter or invalid_filters:
                # Keep the reason through composition and semantic recovery.
                # Rejection is an authoritative filter decision, not a failed
                # capability search which a model should try to broaden.
                fields = (["pricing"] if pricing_filter else []) + [
                    key for key, value in filters.items()
                    if key != "publisher" and value not in (None, [], "")]
                fields = list(dict.fromkeys([*context.get("pending_filters", []), *fields]))
                return {**self._response("I cannot confirm those catalogue filters. I can show an App's supplied fields instead.", [], intent,
                                        {**context, "filters": filters, "pending_filters": list(dict.fromkeys(fields)),
                                         "constraint_request": message}),
                        "unverified_filters": list(dict.fromkeys(fields)),
                        "decision": {"outcome": "abstained", "reason": "unverified_filters"}}
            limitation = ("This snapshot has no verified price information. I cannot confirm what it costs. "
                          if _PRICE.search(message) else
                          "The supplied Store fields do not verify that capability, metadata or filter. "
                          "I cannot confirm support or suitability. ")
            return self._response(limitation + "I can describe an App's supplied fields or compare the source descriptions.",
                                  [], intent, context)
        if browsing:
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
            if self.catalogue_references:
                next_context["comparison_ids"] = [app["id"] for app in apps]
            return {**self._response(text, results, "browse", next_context),
                    "decision": {"outcome": "not_applicable", "reason": "catalogue_browse"}}

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
            functional_question = search_language(message, req.locale)
            if (self.decide and re.search(r"^(?:does|can|could)\b|\b(?:supports?|sends?|delivers?|compatible)\b", functional_question, re.I)
                    and not re.match(r"^can you (?:show|list|describe|explain|tell|find|search)\b", functional_question, re.I)):
                # Reuse Expert's exact decision/abstention boundary, with only
                # identity scaffolding removed. No second suitability checker.
                for app in apps:
                    for value in (app.get("name"), app["app_id"]):
                        if value:
                            functional_question = re.sub(rf"(?<!\w){re.escape(value)}(?!\w)", "", functional_question, flags=re.I)
                decision = self.decide(functional_question, results, req.locale)
                return {**decision, "intent": "detail", "context": {
                    **context, "filters": filters, "focused_ids": selected,
                    "comparison_need": functional_question}}
            text = "Supplied source fields only; missing metadata cannot be confirmed.\n" + self.describe(message, results, req.locale)
            if intent == "compare":
                text = "Source-field comparison only; no superiority or suitability is inferred.\n" + text
            next_context = {**context, "filters": filters, "focused_ids": selected}
            if self.catalogue_references and intent == "compare":
                next_context["comparison_ids"] = selected
                next_context["last_results"] = results
                if criterion:
                    next_context["comparison_need"] = criterion
            if seeded and named:
                next_context["last_results"] = results
            if seeded and not named:
                text = "References use the observed catalogue order shown on this page.\n" + text
            if intent != "compare" and len(selected) == 1:
                intent = "detail"
            return self._response(text, results, intent, next_context)

        # Remove only request boilerplate, not content terms or negation. Dense
        # retrieval (when available) still receives the remaining natural query.
        query = _search_query(search_language(message, req.locale))
        if req.locale == "tr":
            query = re.sub(r"\s+(?:for\s+)?apps?\s+(?:find|recommend)$", "", query, flags=re.I)
        # Preserve capability constraints when a request also mentions an App name.
        # Only a query consisting of names/connectors is an identity lookup.
        remainder = query
        for app in named_apps:
            for value in (app.get("name"), app["app_id"]):
                if value:
                    remainder = re.sub(rf"(?<!\w){re.escape(value)}(?!\w)", "", remainder, flags=re.I)
        identity_only = not re.sub(r'\b(?:and|or)\b|[\s,\"\']', "", remainder, flags=re.I)
        if named and identity_only:
            names = [(app["name"] or app["app_id"]).replace('"', " ") for app in named_apps]
            query = " OR ".join('"' + name + '"' for name in names)
        if intent == "refine" and context.get("last_query"):
            query = context["last_query"] + " " + query
        response = await self.recommend(query=query, locale=req.locale, filters=filters)
        references = context if self.catalogue_references else {}
        next_context = {"last_query": query, "filters": filters,
                        "comparison_need": query,
                        "last_results": response["apps"][:5] or references.get("last_results", []),
                        "explanation_topic": references.get("explanation_topic", ""),
                        "focused_ids": [response["apps"][0]["app"]["id"]] if len(response["apps"]) == 1 else (
                            [] if response["apps"] else references.get("focused_ids", []))}
        if self.catalogue_references:
            next_context["comparison_ids"] = ([r["app"]["id"] for r in response["apps"][:5]]
                if len(response["apps"]) > 1 else references.get("comparison_ids", previous))
        if response["apps"]:
            response["message"] = ("Retrieved source records; order does not establish suitability.\n"
                                   + response["message"])
        if not response["apps"]:
            response["message"] += (" Eşleşme bulunmaması ürünün bu özelliğe sahip olmadığını kanıtlamaz." if req.locale == "tr" else " A missing match does not establish that a product lacks a feature.")
        return {**response, "intent": intent, "context": next_context}

    @staticmethod
    def _response(message, apps, intent, context):
        return {"message": message, "apps": apps, "intent": intent, "context": context}
