"""Application-owned Store dialogue with context-aware model interpretation.

The model proposes selections; current catalogue membership, identities, filters,
publication, context updates and late revision checks remain application decisions.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from copy import deepcopy

from hedge_shared.config import Settings
from hedge_shared.models_v2 import ChatRequestV2
from hedge_shared.store_language import catalogue_question, dialogue_language

from .store_dialogue import (
    _SOURCE_READ,
    StoreDialogue,
    _comparison_criterion,
    _mentions,
    _search_query,
)

# Preserve the existing application's explicit discovery boundary. A generative
# planner must not turn a constrained search command into an unfiltered listing.
_COMPLEX = re.compile(r"^(?:reason in depth|analyze in depth|ayrıntılı değerlendir):\s*", re.I)
_NEW_SEARCH = re.compile(r"^(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?(?:find|search|recommend)\b", re.I)
_NEXT_STEPS = ("Tell me which requirement you can change, and I can look for a partial fit. "
               "You can also ask the provider about the missing feature, or compare the available Apps "
               "to see whether part of your workflow is covered.")


class StoreConversation(StoreDialogue):
    def __init__(self, recommend, resolve, describe, interpret, explain, observation=None, *, routine=True, decide=None, present=None):
        super().__init__(recommend, resolve, describe, catalogue_references=True, assess_requirements=routine, decide=decide if routine else None)
        self.routine = routine
        self.settings = Settings()
        self.interpret = interpret
        self.explain = explain
        self.observation = observation
        self.present = present
        self.progress = lambda stage: None

    def route_intent(self, message: str, intent: str) -> str:
        if self.routine:
            if _COMPLEX.match(message):
                return "conversation"
            # Statistical labels must not discard a substantive request or reset
            # its session. Reserve those actions for explicit conversational controls.
            clean = message.strip().rstrip("?!.,").casefold()
            if re.fullmatch(r"reset|start over|new search|clear|sıfırla", clean):
                return "reset"
            if re.fullmatch(r"hi|hello|hey|merhaba|selam", clean):
                return "greeting"
            if re.fullmatch(r"(?:(?:hi|hello|merhaba)[, ]+)?(?:help|yardım|what can you (?:do|help me with)|burada neler yapabilirim)", clean):
                return "help"
            if intent == "out_of_scope" and re.search(r"write (?:me )?a poem|medical diagnosis|political advice|legal advice", clean):
                return intent
            normalized = dialogue_language(message, "tr")
            fallback = "refine" if re.match(r"^(?:only|without|instead|sadece|yalnızca)\b", normalized, re.I) else "search"
            return super().route_intent(normalized, fallback)
        return "reset" if intent == "reset" else "conversation"

    async def respond(self, req: ChatRequestV2, intent: str, context: dict) -> dict:
        return await self.respond_with_history(req, intent, context, [])

    async def _prepared_response(self, req, intent, context, history, *, nlu=None):
        started = time.monotonic()
        context = deepcopy(context)
        complex_request = _COMPLEX.match(req.message)
        request = req.model_copy(update={"message": req.message[complex_request.end():]}) if complex_request else req
        if req.app_action:
            complex_request = None
            action = req.app_action
            selected = [a for a in self.resolve(None)
                        if a["store_id"] == action.store_id and a["app_id"] == action.app_id]
            if len(selected) != 1:
                return {**self._response("That App is no longer available. Please browse the current Apps.",
                                        [], "detail", {**context, "focused_ids": []}),
                        "decision": {"outcome": "abstained", "reason": "unavailable_action_target"},
                        "generation": {"source": "prepared", "reason": "unavailable_action_target", "model_completed": False}}
            # Reuse the source-inspection path, including filters and late
            # revision checks. No generated ID/name parsing or new fact writer.
            context["focused_ids"] = [selected[0]["id"]]
            request = req.model_copy(update={"message": "Tell me about it"})
        if re.fullmatch(
            r"(?:(?:i'm|i am) not sure|i don't know)(?: where to start| what to choose)?[?!.]*|"
            r"what (?:would you|do you) (?:suggest|recommend)[?!.]*|"
            r"(?:ne önerirsin|nereden başlayacağımı bilmiyorum)[?!.]*",
            request.message.strip(), re.I,
        ):
            # Offer concrete starting points for an unspecified goal, without
            # pretending that an unfiltered list is a recommendation.
            request = request.model_copy(update={"message": (
                "Compare both" if len(context.get("last_results", [])) > 1
                else "Tell me about it" if context.get("focused_ids")
                else "Show me all available apps")})
        routed = self.route_intent(request.message, intent)
        fallback = await super().respond(request, routed, context)
        if fallback["intent"] == "compare":
            primary = context.get("focused_ids", [])
            shown_ids = {r["app"]["id"] for r in fallback["apps"]}
            fallback["context"]["focused_ids"] = [i for i in primary if i in shown_ids] if len(primary) == 1 else []
        if self.present and fallback.get("decision", {}).get("reason") != "invalid_native_reference":
            fallback["message"] = self.present(request.message, fallback, req.locale)
        if not fallback["apps"]:
            fallback.setdefault("decision", {"outcome": "abstained", "reason": "insufficient_evidence"})
        fallback["generation"] = {"source": "prepared", "reason": (
            "source_preparation" if any(r["app"].get("prepared_explanation") for r in fallback["apps"])
            else "source_evidence"), "model_completed": False}
        if (complex_request and self.settings.STORE_REASONING_ENABLED and fallback["apps"]
                and not self.settings.STORE_SEMANTIC_ENABLED):
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
        fallback["context"]["last_outcome"] = fallback.get("decision", {}).get("outcome", "not_applicable")
        return fallback

    async def respond_with_history(self, req, intent, context, history, *, nlu=None):
        if self.routine or req.app_action:
            # Run the proven low-latency route first. A synopsis is not proof that
            # an arbitrary question was understood. Uncertain substantive turns
            # get contextual semantic interpretation, not more lexical exceptions.
            fallback = await self._prepared_response(req, intent, context, history, nlu=nlu)
            if req.app_action:
                return fallback
            fast = not _COMPLEX.match(req.message) and (fallback.get("decision", {}).get("outcome") == "recommended"
                    or fallback["intent"] == "source_fields"
                    or fallback["intent"] == "browse"
                    or self.route_intent(req.message, intent) in {"greeting", "help", "reset", "out_of_scope"}
                    or fallback["intent"] == "compare" and bool(fallback["apps"])
                    or dialogue_language(req.message, req.locale) in {"Explain it simply", "How does it work?"} and bool(fallback["apps"]))
            if (not self.settings.STORE_SEMANTIC_ENABLED or req.locale != "en" or fast
                    or fallback.get("decision", {}).get("reason") in {"invalid_native_reference", "unverified_filters"}):
                return fallback
            recovery_started = time.monotonic()
            answer = await self._interpreted_response(req, intent, context, history, fallback, nlu=nlu)
            answer.setdefault("timings", {})["recovery_seconds"] = time.monotonic() - recovery_started
            answer["timings"]["complete_seconds"] = (answer["timings"]["recovery_seconds"]
                                                        + fallback.get("timings", {}).get("complete_seconds", 0))
            if not answer.get("generation", {}).get("model_completed"):
                if not fallback["apps"]:
                    fallback.update(intent="clarify", message="Could you narrow this down to the main function you need, or name an App to explore?",
                                    decision={"outcome": "abstained", "reason": "semantic_recovery_unavailable"})
                fallback["timings"] = answer["timings"]
                fallback["generation"].update(reason="semantic_recovery_unavailable",
                                             recovery=answer.get("generation", {}).get("reason"),
                                             recovery_metadata=answer.get("generation", {}))
                return fallback
            return answer
        return await self._model_response(req, intent, context, history, nlu=nlu)

    async def _interpreted_response(self, req, intent, context, history, fallback, *, nlu=None):
        """One bounded interpretation, followed by the existing evidence boundary.

        The model translates intent and vocabulary; it cannot approve an App,
        supply facts, write an answer or grant a reviewed-support receipt.
        """
        current = self.resolve(None)
        previous = [r["app"]["id"] for r in context.get("last_results", [])]
        focus = context.get("focused_ids", [])
        # Retrieval narrows large catalogues; a directory is never an independent
        # recommendation index. Discovery still searches the complete Store.
        pool = {r["app"]["id"]: r["app"] for r in [*fallback.get("apps", []), *fallback.get("candidates", [])]}
        referenced = list(dict.fromkeys([a["id"] for a in current if _mentions(a, req.message)]
                                       + focus + context.get("comparison_ids", []) + previous))
        scoped = sorted(current, key=lambda a: (referenced.index(a["id"]) if a["id"] in referenced else
                                               len(referenced) if a["id"] in pool else len(referenced) + 1,
                                               a["app_id"]))[:5]
        scoped.sort(key=lambda a: a["app_id"])  # Stable catalogue prefix enables model prompt-cache reuse.
        bindings = {str(i + 1): a["id"] for i, a in enumerate(scoped)}
        reverse = {v: k for k, v in bindings.items()}
        directory = [{"key": reverse[a["id"]], "app": a} for a in scoped]
        self.progress("intent")
        try:
            plan = await asyncio.to_thread(self.interpret, req.message, req.locale, directory,
                {"focus": [reverse[i] for i in focus if i in reverse],
                 "previous": list(dict.fromkeys(reverse[i] for i in previous + context.get("comparison_ids", []) if i in reverse)),
                 "need": context.get("explanation_topic") or context.get("last_query", ""),
                 "last_outcome": context.get("last_outcome"),
                 "task_interpretation": True}, history)
            chosen = [bindings[k] for k in plan["apps"]]
        except Exception:
            return {**fallback, "generation": {"source": "prepared", "reason": "interpretation_unavailable", "model_completed": False}}
        action, query, view = plan["action"], plan["query"], plan.get("view", "capability")
        named = [a["id"] for a in current if _mentions(a, req.message)]
        # Inspection needs an actual user reference. A model-selected App is a
        # discovery candidate, not a request to describe it instead of recommending.
        if action == "answer" and not named and (not focus and not previous or
                fallback["intent"] in {"search", "refine"} and view == "purpose"):
            action, view = "search", "capability"
        if action == "search" and fallback["intent"] == "detail" and (named or focus) and not _NEW_SEARCH.match(req.message.strip()):
            action = "answer"
        if action == "clarify" and fallback["intent"] == "detail" and len(fallback.get("candidates", [])) == 1 and (named or focus):
            # The subject is already resolved. Recheck the original capability
            # against that App; a weak interpreter cannot discard its identity.
            action, view = "answer", "capability"
        if action == "answer" and fallback["intent"] == "detail" and fallback.get("candidates"):
            view = "capability"
        if action == "compare" and not named and fallback["intent"] == "detail" and len(fallback["apps"]) == 1:
            # A resolved singular reference (including "the other App") already
            # has one subject. A weak model must not turn it into a comparison.
            action, view = "answer", "purpose"
        filters = {**context.get("filters", {}), **{k: v for k, v in req.filters.model_dump(mode="json").items() if v not in (None, "", [])}}
        generation = {"source": "interpreted_prepared", "reason": "single_interpretation", "model_completed": True,
                      "interpretation": {"action": action, "query": query, "apps": chosen, "view": view,
                                         "source_task": plan.get("source_task"), "normalization": plan.get("normalization")}, "model_calls": 1}
        next_context = {**context, "filters": filters}
        if action == "chat" or view == "next_steps":
            # Offer concrete alternatives as exploration, not as matches to the
            # previous unsupported requirement or invented external products.
            response = self._response(_NEXT_STEPS, [], "conversation", next_context)
            response["decision"] = {"outcome": "not_applicable", "reason": "next_steps"}
        elif action == "clarify" or not query.strip() and action != "browse":
            response = self._response("Which task or App would you like to explore?", [], "clarify", next_context)
            generation["reason"] = "interpreted_clarification"
        elif action == "browse":
            # An explicit constrained search cannot be broadened into a listing.
            if not catalogue_question(req.message):
                response = self._response("What would you like the App to do?", [], "clarify", next_context)
            else:
                response = await self._prepared_response(req, intent, next_context, history)
        else:
            resolved_targets = [r["app"]["id"] for r in [*fallback.get("apps", []), *fallback.get("candidates", [])]] if fallback["intent"] == "detail" else []
            selected = (named or resolved_targets or focus or chosen) if action == "answer" else chosen
            if action == "compare":
                selected = list(dict.fromkeys(focus + named + chosen + context.get("comparison_ids", previous)))[:5]
            if action in {"answer", "compare"} and (not selected or len(self.resolve(selected)) != len(selected) or action == "compare" and len(selected) < 2):
                response = self._response("Which App do you mean? You can name it or ask me to list the Apps.", [], "clarify", next_context)
            elif any(v not in (None, "", []) for k, v in filters.items() if k != "publisher"):
                response = fallback
            else:
                if action in {"answer", "compare"}:
                    apps = self.resolve(selected)
                    apps = [a for a in apps if not filters.get("publisher") or filters["publisher"].casefold() in (a.get("provider") or "").casefold()]
                    rows = [{"app": a, "rank": i + 1, "evidence_fields": ["reference"]} for i, a in enumerate(apps)]
                else:
                    self.progress("retrieval")
                    retrieved = await self.recommend(query=query, locale=req.locale, filters=filters)
                    rows = sorted([*retrieved["apps"], *retrieved.get("candidates", [])], key=lambda r: r["rank"])[:5]
                inspection = action in {"answer", "compare"} and view in {"purpose", "workflow", "simple", "pricing", "access", "comparison"}
                # Rewriting is not permission to drop explicit restrictions. Keep
                # negative, numeric, conditional and exclusive requests on the
                # original conservative assessor. This guard is grammar, not a
                # synonym list or a semantic eligibility decision.
                strict = re.search(r"\d|\b(?:no|not|never|cannot|without|only|except|must|requires?|guarantee\w*|certifi\w*|production|offline|under|at least|at most|automatic\w*|all|every|always|unlimited)\b|n't\b", req.message, re.I)
                if re.search(r"\band\b", req.message, re.I) and not re.search(r"\band\b", query, re.I):
                    strict = True
                if strict and view not in {"pricing", "comparison"}:
                    inspection = False
                decision_query = req.message if strict or action == "answer" and view == "capability" else query
                if inspection:
                    response = self._response("", rows, "compare" if action == "compare" else "detail", next_context)
                    response["decision"] = {"outcome": "not_applicable", "reason": "source_inspection"}
                else:
                    response = {**self.decide(decision_query, rows, req.locale), "intent": "search" if action == "search" else "detail", "context": next_context}
                    next_context["comparison_need"] = decision_query
                shown = response["apps"]
                if len(shown) == 1:
                    next_focus = [shown[0]["app"]["id"]]
                elif action == "compare":
                    next_focus = [i for i in focus if i in {r["app"]["id"] for r in shown}] if len(focus) == 1 else []
                else:
                    next_focus = selected if action == "answer" else []
                next_context.update(last_query=query if action == "search" else context.get("last_query", query),
                    explanation_topic=(context.get("explanation_topic") or query) if view in {"simple", "workflow"} else query if shown else context.get("explanation_topic", ""), response_view=view,
                    focused_ids=next_focus,
                    last_results=shown if action in {"search", "compare"} else context.get("last_results", shown))
                if action == "compare":
                    next_context["comparison_ids"] = [r["app"]["id"] for r in shown]
                    criterion = _comparison_criterion(req.message, [r["app"] for r in shown])
                    if criterion:
                        next_context["comparison_need"] = criterion
                elif action == "search" and shown:
                    discussed = list(dict.fromkeys((focus or previous) + [r["app"]["id"] for r in shown]))[-5:]
                    if len(discussed) > 1 or not next_context.get("comparison_ids"):
                        next_context["comparison_ids"] = discussed
                # Canonical view controls presentation only; no free model prose.
                response["interpreted_query"] = query
                presentation = {"workflow": "How does it work?", "simple": "Explain it simply", "pricing": "What does it cost?", "access": "How do I get started?"}.get(view, req.message)
                response["message"] = self.present(presentation, response, req.locale) if self.present else response["message"]
                if not shown:
                    if action != "answer" or not response.get("candidates"):
                        response["message"] = ("I haven’t found a confirmed match for that need. Which part matters most? "
                            "I can help you explore a partial fit or check a specific App’s capabilities.")
                    if (context.get("last_outcome") == "abstained" and (nlu or {}).get("source") == "rasa"
                            and (nlu or {}).get("intent") == "help" and (nlu or {}).get("confidence", 0) >= .9):
                        # Rasa can select a recovery strategy after two unmatched
                        # turns, but never change a positive suitability decision.
                        response.update(message=_NEXT_STEPS, intent="conversation")
                        generation["nlu_policy"] = "no_match_recovery"
                # The same late authoritative equality check as prepared replies.
                visible = [*shown, *response.get("candidates", [])]
                fresh = {a["id"]: a for a in self.resolve([r["app"]["id"] for r in visible])}
                if any(fresh.get(r["app"]["id"]) != r["app"] for r in visible):
                    response.update(message="The catalogue changed while preparing this reply. Please search again.", apps=[], candidates=[], decision={"outcome": "abstained", "reason": "catalogue_changed"})
                    response["context"].update(last_results=[], focused_ids=[])
        response["generation"] = generation
        response["context"]["last_outcome"] = response.get("decision", {}).get("outcome", "not_applicable")
        return response

    async def _model_response(self, req, intent, context, history, *, nlu=None):
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
        plan_started = time.monotonic()
        try:
            named = [a["id"] for a in current if _mentions(a, req.message)]
            known = list(dict.fromkeys(previous_ids + focus))
            if _NEW_SEARCH.search(req.message.strip()):
                # An explicit constrained discovery command cannot become an
                # unfiltered browse because of a planner classification error.
                plan = {"action": "search", "apps": [], "query": req.message}
            elif self.settings.STORE_SEMANTIC_ENABLED and not known and not history and not named:
                # A first substantive turn needs discovery, not a catalogue-wide
                # planner. Expert interprets the full request and Rasa hint
                # against the retrieved evidence and may still ask a clarification.
                plan = {"action": "search", "apps": [], "query": req.message}
            elif not self.settings.STORE_SEMANTIC_ENABLED:
                if catalogue_question(req.message):
                    plan = {"action": "browse", "apps": [], "query": req.message}
                elif named or (known and not plan_context["unavailable_reference"]):
                    selected_scope = list(dict.fromkeys(named + [i for i in known if i in keys]))[:5]
                    plan = {"action": "compare" if len(selected_scope) > 1 and (nlu or {}).get("intent") == "compare" else "answer",
                            "apps": [keys[i] for i in selected_scope], "query": req.message}
                elif known and plan_context["unavailable_reference"]:
                    return self._response("An earlier App is no longer available in this catalogue. Please name a current App or browse again.",
                                          [], "clarify", context)
                else:
                    plan = await asyncio.to_thread(self.interpret, req.message, req.locale, directory, plan_context, history)
            else:
                plan = await asyncio.to_thread(self.interpret, req.message, req.locale, directory, plan_context, history)
            chosen = [bindings[key] for key in plan["apps"]]
            if self.settings.STORE_SEMANTIC_ENABLED and named and plan["action"] == "answer" and len(named) == 1:
                chosen = named
        except Exception:
            return {**self._response("I couldn't quite resolve that turn. Please try again, or name the App you mean.",
                                     [], "clarify", context),
                    "generation": {"source": "deterministic", "reason": "interpretation_unavailable"}}
        action = plan["action"]
        timings = {"interpretation_seconds": time.monotonic() - plan_started}
        retrieval_trace = []
        async def retrieve(query):
            # Do not catch search failures as no-match: preserve SCRUM-28 errors.
            self.progress("retrieval")
            retrieved = await self.recommend(query=_search_query(query), locale=req.locale, filters=filters)
            pool = {r["app"]["id"]: r for r in [*retrieved["apps"], *retrieved.get("candidates", [])]}
            rows = sorted(pool.values(), key=lambda r: r["rank"])[:5]
            retrieval_trace[:] = [{"id": r["app"]["id"], "rank": r["rank"],
                                  "sources": r.get("evidence_fields", [])} for r in rows]
            return rows, {**timings, **retrieved.get("timings", {})}
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
            # A valid clarification plan makes no App claims. Distinguish it
            # from an unavailable interpreter; do not fabricate a no-match.
            return {**self._response("Which App or earlier comparison do you mean? You can name an App, or ask me to list them.",
                                    [], "clarify", context),
                    "timings": timings,
                    "generation": {"source": "ollama", "reason": "interpreted_clarification", "model_completed": True}}
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
                                             observation=self.observation() if self.observation else None, references=references,
                                             **({"nlu_hint": nlu} if self.settings.STORE_SEMANTIC_ENABLED else {}))
            if answer["decision"] != "search":
                break
            if action == "search" or attempt:
                return {**self._response("I couldn't complete that search. Please try again.", [], "clarify", context),
                        "generation": {"source": "deterministic", "reason": "repeated_search_directive"}}
            action = "search"
            plan["query"] = req.message
            results, timings = await retrieve(req.message)
        answer.setdefault("generation", {}).update(retrieval=retrieval_trace,
            interpretation={"action": action, "query": plan["query"], "apps": chosen})
        reviewed = {r["app"]["id"]: r for r in answer.get("reviewed_rows", [])}
        results = [reviewed.get(r["app"]["id"], r) for r in results]
        fresh = {a["id"]: a for a in self.resolve([r["app"]["id"] for r in results])}
        if any(fresh.get(r["app"]["id"]) != r["app"] for r in results):
            return {**self._response("The catalogue changed while I was answering. Please ask again so I can use the updated information.",
                                    [], "clarify", {**context, "last_results": [], "focused_ids": []}),
                    "generation": {"source": "deterministic", "reason": "catalogue_changed"}}
        next_context = {**context, "filters": filters, "semantic_context": True}
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
                **({"decision": answer["recommendation_decision"]} if "recommendation_decision" in answer else {}),
                "timings": timings, "generation": {**answer["generation"], "focus_ids": [r["app"]["id"] for r in focal] if answer["decision"] in {"answer", "chat"} else []}}
