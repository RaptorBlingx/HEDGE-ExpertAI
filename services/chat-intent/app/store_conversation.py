"""Application-owned Store dialogue with context-aware model interpretation.

The model proposes selections; current catalogue membership, identities, filters,
publication, context updates and late revision checks remain application decisions.
"""
from __future__ import annotations

import asyncio
import json
import re
import time

from hedge_shared.config import Settings
from hedge_shared.models_v2 import ChatRequestV2

from .store_dialogue import _BROWSE, _SOURCE_READ, StoreDialogue, _mentions, _search_query

# Preserve the existing application's explicit discovery boundary. A generative
# planner must not turn a constrained search command into an unfiltered listing.
_COMPLEX = re.compile(r"^(?:reason in depth|analyze in depth|ayrıntılı değerlendir):\s*", re.I)
_NEW_SEARCH = re.compile(r"^(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?(?:find|search|recommend)\b", re.I)


class StoreConversation(StoreDialogue):
    def __init__(self, recommend, resolve, describe, interpret, explain, observation=None, *, routine=True, decide=None):
        super().__init__(recommend, resolve, describe, catalogue_references=True, assess_requirements=routine, decide=decide if routine else None)
        self.routine = routine
        self.settings = Settings()
        self.interpret = interpret
        self.explain = explain
        self.observation = observation
        self.progress = lambda stage: None

    def route_intent(self, message: str, intent: str) -> str:
        if self.routine:
            return "conversation" if _COMPLEX.match(message) else super().route_intent(message, intent)
        return "reset" if intent == "reset" else "conversation"

    async def respond(self, req: ChatRequestV2, intent: str, context: dict) -> dict:
        return await self.respond_with_history(req, intent, context, [])

    async def _prepared_response(self, req, intent, context, history, *, nlu=None):
        started = time.monotonic()
        complex_request = _COMPLEX.match(req.message)
        request = req.model_copy(update={"message": req.message[complex_request.end():]}) if complex_request else req
        routed = super().route_intent(request.message, (nlu or {}).get("intent", intent))
        fallback = await super().respond(request, routed, context)
        if not fallback["apps"]:
            fallback.setdefault("decision", {"outcome": "abstained", "reason": "insufficient_evidence"})
        fallback["generation"] = {"source": "prepared", "reason": "source_evidence", "model_completed": False}
        if complex_request and self.settings.STORE_REASONING_ENABLED and fallback["apps"]:
            # A single budget covers drafting and review. The expert checks the
            # remaining budget before every model call; no repair loops here.
            rows = fallback["apps"]
            self.progress("explanation")
            budget = self.settings.STORE_REASONING_SECONDS
            try:
                answer = await asyncio.wait_for(asyncio.to_thread(
                    self.explain, request.message, rows, req.locale,
                    "compare" if routed == "compare" else "answer", history,
                    allow_repair=False, deadline=time.monotonic() + budget,
                ), timeout=budget + 0.1)
                if answer["generation"].get("source") == "ollama":
                    # Optional prose never changes the routine evidence decision,
                    # identity, order, focus or abstention.
                    if rows and answer.get("decision") == "answer":
                        fallback.update(message=answer["message"], generation=answer["generation"])
                    elif answer.get("decision") == "no_match":
                        fallback.update(message=answer["message"], apps=[],
                            candidates=[*fallback.get("candidates", []), *[
                                {**r, "suitability": {**r.get("suitability", {}), "status": "uncertain",
                                                      "reason": "model_declined"}} for r in rows]],
                            decision={"outcome": "abstained", "reason": "model_abstention"},
                            generation=answer["generation"])
                        fallback["context"].update(last_results=[], focused_ids=[])
                else:
                    fallback["generation"]["reason"] = "reasoning_fallback"
            except Exception:
                fallback["generation"]["reason"] = "reasoning_fallback"
        elif complex_request:
            fallback["generation"]["reason"] = ("reasoning_disabled" if not self.settings.STORE_REASONING_ENABLED
                                                 else "insufficient_evidence")
        visible = [*fallback["apps"], *fallback.get("candidates", [])]
        fresh = {a["id"]: a for a in self.resolve([r["app"]["id"] for r in visible])}
        if any(fresh.get(r["app"]["id"]) != r["app"] for r in visible):
            fallback.update(message=("Yanıt hazırlanırken katalog değişti. Lütfen yeniden arayın." if req.locale == "tr"
                                     else "The catalogue changed while preparing this reply. Please search again."),
                            apps=[], candidates=[], decision={"outcome": "abstained", "reason": "catalogue_changed"})
            fallback["context"].update(last_results=[], focused_ids=[])
        fallback.setdefault("timings", {})["complete_seconds"] = time.monotonic() - started
        return fallback

    async def respond_with_history(self, req, intent, context, history, *, nlu=None):
        if self.routine:
            return await self._prepared_response(req, intent, context, history, nlu=nlu)
        # Explicit inspection remains a source read, not generative paraphrasing.
        if _SOURCE_READ.fullmatch(req.message.strip()):
            return await super().respond(req, "detail", context)
        filters = {**context.get("filters", {}),
                   **{k: v for k, v in req.filters.model_dump(mode="json").items()
                      if v not in (None, "", [])}}
        if any(v not in (None, "", []) for k, v in filters.items() if k != "publisher"):
            return self._response("I can't reliably apply those catalogue filters yet. What function do you need?",
                                  [], "clarify", context)
        current = sorted(self.resolve(None), key=lambda app: app["app_id"])
        for app in current:
            native = rf"(?<!\w){re.escape(app['app_id'])}(?!\w)"
            name = app.get("name")
            if re.search(native, req.message, re.I) and not re.search(native, req.message) and not (
                name and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", req.message, re.I)
            ):
                return self._response("App IDs are case-sensitive. Please use the exact ID or the App's name.",
                                      [], "clarify", context)
        # The complete catalogue remains searchable. Large directories provide
        # only referenced/named entries to the planner; discovery still sees all.
        previous_ids = [r["app"]["id"] for r in context.get("last_results", [])]
        focus = context.get("focused_ids", [])
        directory_apps = current if len(current) <= 100 else [a for a in current
                            if a["id"] in previous_ids + focus or _mentions(a, req.message)]
        bindings = {str(i + 1): app["id"] for i, app in enumerate(directory_apps)}
        keys = {identity: key for key, identity in bindings.items()}
        directory = [{"key": key, "name": app.get("name"), "native_id": app["app_id"],
                      "description": app.get("description")}
                     for key, app in zip(bindings, directory_apps, strict=True)]
        if len(json.dumps(directory, ensure_ascii=False).encode()) > 6000:
            for app in directory:
                app.pop("description", None)
        if len(json.dumps(directory, ensure_ascii=False).encode()) > 6000:
            needed = set(previous_ids + focus) | {a["id"] for a in current if _mentions(a, req.message)}
            directory = [a for a in directory if bindings[a["key"]] in needed or a["key"] in list(bindings)[:5]]
        plan_context = {"previous": [keys[i] for i in previous_ids if i in keys],
                        "focus": [keys[i] for i in focus if i in keys], "nlu": nlu,
                        "unavailable_reference": any(i not in keys for i in previous_ids + focus)}
        self.progress("intent")
        try:
            named = [a["id"] for a in current if _mentions(a, req.message)]
            known = list(dict.fromkeys(previous_ids + focus))
            if _NEW_SEARCH.search(req.message.strip()):
                plan = {"action": "search", "apps": [], "query": req.message}
            elif _BROWSE.fullmatch(req.message.strip()):
                plan = {"action": "browse", "apps": [], "query": req.message}
            elif named or (known and not plan_context["unavailable_reference"]):
                # A known App set is evidence for the expert, not a request for
                # a thin classifier to guess the final subject without the facts.
                scope = list(dict.fromkeys(named + [i for i in known if i in keys]))[:5]
                plan = {"action": "compare" if len(scope) > 1 and (nlu or {}).get("intent") == "compare" else "answer",
                        "apps": [keys[i] for i in scope], "query": req.message}
            elif known and plan_context["unavailable_reference"]:
                return self._response("An earlier App is no longer available in this catalogue. Please name a current App or browse again.",
                                      [], "clarify", context)
            else:
                plan = await asyncio.to_thread(self.interpret, req.message, req.locale, directory, plan_context, history)
            chosen = [bindings[key] for key in plan["apps"]]
        except Exception:
            return {**self._response("I couldn't quite resolve that turn. Please try again, or name the App you mean.",
                                     [], "clarify", context),
                    "generation": {"source": "deterministic", "reason": "interpretation_unavailable"}}
        action = plan["action"]
        timings = {}
        async def retrieve(query):
            # Do not catch search failures as no-match: preserve SCRUM-28 errors.
            self.progress("retrieval")
            retrieved = await self.recommend(query=_search_query(query), locale=req.locale, filters=filters)
            return retrieved["apps"][:5], retrieved.get("timings", {})
        if action == "search":
            results, timings = await retrieve(plan["query"] or req.message)
        elif action == "browse":
            apps = current
            if filters.get("publisher"):
                apps = [a for a in apps if filters["publisher"].casefold() in (a.get("provider") or "").casefold()]
            results = [{"app": app, "rank": i + 1, "evidence_fields": ["catalogue"]}
                       for i, app in enumerate(apps[:5])]
        elif action in {"answer", "compare"}:
            apps = self.resolve(chosen)
            if filters.get("publisher"):
                apps = [a for a in apps if filters["publisher"].casefold() in (a.get("provider") or "").casefold()]
            if not chosen or len(apps) != len(chosen) or (action == "compare" and len(apps) < 2):
                return self._response("Which Apps should I compare? You can name them or browse the catalogue first.",
                                      [], "clarify", context)
            by_id = {a["id"]: a for a in apps}
            results = [{"app": by_id[identity], "rank": i + 1, "evidence_fields": ["reference"]}
                       for i, identity in enumerate(chosen)]
        elif action == "clarify":
            return self._response("Which App or earlier comparison do you mean? You can name an App, or ask me to list them.",
                                  [], "clarify", context)
        else:
            results = []
        for attempt in range(2):
            result_keys = {r["app"]["id"]: str(r["rank"]) for r in results}
            focused = [result_keys[i] for i in focus if i in result_keys]
            alternatives = [result_keys[i] for i in previous_ids if i in result_keys and i not in focus]
            references = {"named": [result_keys[i] for i in named if i in result_keys], "focus": focused, "previous": [result_keys[i] for i in previous_ids if i in result_keys],
                          "other": alternatives if len(focused) == 1 and len(alternatives) == 1 else [],
                          "unavailable_reference": plan_context["unavailable_reference"]}
            self.progress("explanation")
            answer = await asyncio.to_thread(self.explain, req.message, results, req.locale, action, history,
                                             progress=self.progress,
                                             observation=self.observation() if self.observation else None, references=references)
            if answer["decision"] != "search":
                break
            if action == "search" or attempt:
                return {**self._response("I couldn't complete that search. Please try again.", [], "clarify", context),
                        "generation": {"source": "deterministic", "reason": "repeated_search_directive"}}
            action = "search"
            plan["query"] = req.message
            results, timings = await retrieve(req.message)
        fresh = {a["id"]: a for a in self.resolve([r["app"]["id"] for r in results])}
        if any(fresh.get(r["app"]["id"]) != r["app"] for r in results):
            return {**self._response("The catalogue changed while I was answering. Please ask again so I can use the updated information.",
                                    [], "clarify", {**context, "last_results": [], "focused_ids": []}),
                    "generation": {"source": "deterministic", "reason": "catalogue_changed"}}
        next_context = {**context, "filters": filters}
        if named and action not in {"search", "browse"}:
            next_context["focused_ids"] = named
        if action in {"search", "browse"} or not previous_ids:
            next_context.update(last_results=results, last_query=plan["query"] or req.message)
        selected = answer.get("focus", [])
        focal = [r for r in results if str(r["rank"]) in selected]
        shown = answer.get("display", selected)
        results = [r for r in results if str(r["rank"]) in shown]
        if action in {"answer", "compare"} and answer["decision"] in {"answer", "chat"} and focal:
            next_context["focused_ids"] = [r["app"]["id"] for r in focal]
        elif action in {"browse", "search"}:
            next_context["focused_ids"] = [focal[0]["app"]["id"]] if len(focal) == 1 else []
        # Source context can include other Apps discussed in a comparison without
        # changing the focal subject used by a later "it" or "other one".
        if answer["decision"] in {"no_match", "clarify"}:
            results = []
            if action == "search" and answer["decision"] == "no_match":
                next_context.update(last_results=[], focused_ids=[])
        if action in {"search", "browse"}:
            # A new discovery list is the visible conversation, not the hidden
            # retrieval pool. Unshown hits cannot bind "the other App" later.
            next_context["last_results"] = results
        return {**self._response(answer["message"], results, "conversation" if answer["decision"] == "chat" else
                                "clarify" if answer["decision"] == "clarify" else
                                "detail" if action == "answer" else
                                "conversation" if action == "chat" else action, next_context),
                "timings": timings, "generation": {**answer["generation"], "focus_ids": [r["app"]["id"] for r in focal] if answer["decision"] in {"answer", "chat"} else []}}
