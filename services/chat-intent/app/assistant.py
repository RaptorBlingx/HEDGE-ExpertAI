"""The Store assistant: understand the turn once, execute it from sources, keep the state.

``understanding.Interpreter`` decides what the user wants and about which Apps.
This module executes that frame with the existing grounded components and owns
the dialogue state; it never re-interprets the wording.

- explanations, facts and open questions: Expert's explainer, from App guides;
- capability checks and choices: Expert's verifier (only documented support
  recommends an App);
- searches: Discovery retrieval plus the same verifier;
- listings: the current authorized catalogue.

Every App shown is resolved from the current catalogue and checked again after
any slow step; text streamed to the widget is released only while its Apps are
unchanged. Conditions the Store cannot verify (prices, typed filters) stay
pending until the user drops them and keep recommendations from being made.
"""
from __future__ import annotations

import asyncio
import re
import time
from contextvars import ContextVar
from copy import deepcopy

from hedge_shared.store_language import cost_question

from .understanding import EXPLANATION_ACTS, SMALL_TALK, Frame, Interpreter

# Set by the streaming chat route for one request: receives text the widget
# shows before the reply completes. Only _guarded_explain wraps it for release.
STREAM: ContextVar = ContextVar("store_explanation_stream", default=None)
_CHANGED = "The catalogue changed while preparing this reply. Please search again."
_LISTED = 5
# Frame acts answered by Expert's explainer, by its act names.
_EXPLAINER = {"describe": "overview", "simple": "simple", "example": "example", "analogy": "analogy", "how": "how",
              "differently": "differently", "meaning": "meaning", "audience": "audience", "provider": "provider",
              "price": "price", "access": "access", "details": "details", "ask": "ask", "compare": "compare",
              "choose": "choose", "term": "term"}
_INTENTS = {"list": "browse", "find": "search", "compare": "compare", "choose": "compare", "clarify": "clarify",
            "remove_constraint": "conversation", "term": "conversation"}


def _rows(apps: list[dict]) -> list[dict]:
    return [{"app": app, "rank": i + 1, "evidence_fields": ["reference"]} for i, app in enumerate(apps)]


def _names(apps: list[dict]) -> str:
    names = [f"**{a.get('name') or a['app_id']}**" for a in apps]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


class Assistant:
    def __init__(self, *, recommend, resolve, compose, explainer, interpreter: Interpreter, static):
        self.recommend, self.resolve, self.compose = recommend, resolve, compose
        self.explainer, self.interpreter, self.static = explainer, interpreter, static
        self.progress = lambda stage: None

    async def reply(self, req, context: dict, history: list[dict]) -> dict:
        started = time.monotonic()
        state = deepcopy(context.get("dialogue", {}))
        catalogue = self.resolve(None)
        clicked = None
        if req.app_action:
            action = req.app_action
            clicked = [a["id"] for a in catalogue if a["store_id"] == action.store_id and a["app_id"] == action.app_id]
        frame = await asyncio.to_thread(self.interpreter.interpret, req.message, state, catalogue,
                                        history=history, clicked=clicked)
        filters = {k: v for k, v in req.filters.model_dump(mode="json").items() if v not in (None, "", [])}
        reply = await self._execute(frame, req, state, history, catalogue, filters)
        reply = self._hold(reply, state, frame)
        reply = self._recheck(reply)
        reply["frame"] = frame.summary()
        reply.setdefault("timings", {})["complete_seconds"] = time.monotonic() - started
        reply["context"] = {"dialogue": self._next_state(state, frame, reply), "filters": filters}
        return reply

    # --- execution -----------------------------------------------------------

    async def _execute(self, frame: Frame, req, state: dict, history: list[dict], catalogue: list[dict],
                       filters: dict) -> dict:
        act = frame.act
        if act in SMALL_TALK:
            return self._small_talk(act, req.locale, catalogue)
        if act == "clarify":
            return self._clarify(frame, catalogue, state.get("shown", []))
        if act == "remove_constraint":
            return await self._remove_constraint(req, state, history, catalogue, filters)
        if any(k != "publisher" for k in filters):
            # Typed catalogue filters cannot be verified from Store metadata.
            state["pending_filters"] = list(dict.fromkeys([*state.get("pending_filters", []), *filters]))
            return self._unverified(state, act)
        if act == "list":
            return self._list(catalogue, filters)
        apps = self.resolve(frame.subjects)
        if len(apps) != len(frame.subjects):
            return self._clarify(Frame("clarify", problem="unavailable_subject"), catalogue)
        if filters.get("publisher"):
            apps = [a for a in apps if filters["publisher"].casefold() in (a.get("provider") or "").casefold()]
            if not apps and frame.subjects:
                return self._reply("None of those Apps is from that provider.", [], "clarify",
                                   {"outcome": "abstained", "reason": "publisher_filter"})
        if act in {"find", "check", "choose"} and frame.need and cost_question(req.message):
            # "A free app that ..." – a pricing condition the Store cannot confirm.
            state["pending_filters"] = list(dict.fromkeys([*state.get("pending_filters", []), "pricing"]))
            state["constraint_request"] = req.message
            return self._unverified(state, act)
        if act == "find":
            return await self._find(frame, req, state, filters)
        if act in {"check", "choose"} and frame.need:
            return await self._check(frame, req, state, apps)
        return await self._explain(frame, req, state, history, apps)

    async def _explain(self, frame, req, state, history, apps) -> dict:
        self.progress("explanation")
        answer, released, changed = await self._guarded_explain(
            _EXPLAINER[frame.act], req.message, apps, state, history, frame.phrase)
        if changed:
            return {**self._reply((released + "\n\n" if released else "") + _CHANGED, [], "clarify",
                                  {"outcome": "abstained", "reason": "catalogue_changed"}), "changed": True}
        state["explanations"] = answer.get("state", state.get("explanations", {}))
        rows = _rows(apps) if frame.act != "term" else []
        intent = _INTENTS.get(frame.act, "detail")
        return {**self._reply(answer.get("message") or "", rows, intent,
                              {"outcome": "not_applicable", "reason": "source_explanation"}),
                "generation": answer.get("generation", {"source": "prepared"})}

    async def _check(self, frame, req, state, apps) -> dict:
        self.progress("explanation")
        decision = await asyncio.to_thread(self.compose, "check", frame.need, _rows(apps), req.locale)
        # Cards are recommendations; the Apps asked about stay the subject either way.
        return {"message": decision["message"], "apps": decision["apps"], "intent": "detail",
                "decision": decision["decision"], "candidates": decision.get("candidates", []),
                "presented": [a["id"] for a in apps], "generation": {"source": "prepared", "reason": "source_evidence"}}

    async def _find(self, frame, req, state, filters) -> dict:
        self.progress("retrieval")
        found = await self.recommend(query=frame.need, locale=req.locale, filters=filters)
        if not found.get("apps") and found.get("candidates"):
            # No sentence states every requested word: review paraphrased matches.
            # All candidates: review spends its budget on the most relevant reviewable ones.
            reviewed = await asyncio.to_thread(self.compose, "review", frame.need, found["candidates"], req.locale)
            if reviewed.get("apps"):
                found = {**found, **{k: reviewed[k] for k in ("apps", "candidates", "decision", "message")}}
        apps = found.get("apps", [])
        # Closest unconfirmed Apps are described, not shown as recommendations.
        partial = [r for r in found.get("candidates", []) if r.get("suitability", {}).get("status") == "partial"]
        return {"message": found.get("message", ""), "apps": apps, "intent": "search",
                "presented": [r["app"]["id"] for r in (apps or partial[:3])],
                "decision": found.get("decision", {"outcome": "abstained", "reason": "insufficient_evidence"}),
                "candidates": found.get("candidates", []), "timings": found.get("timings", {}),
                "generation": {"source": "prepared", "reason": "source_evidence"}}

    def _list(self, catalogue: list[dict], filters: dict) -> dict:
        apps = [a for a in catalogue if not filters.get("publisher")
                or filters["publisher"].casefold() in (a.get("provider") or "").casefold()]
        if not apps:
            return self._reply("I can’t see any Apps in this catalogue right now. That doesn’t mean the Store has none; "
                               "please try again later.", [], "browse", {"outcome": "not_applicable", "reason": "catalogue_browse"})
        apps = sorted(apps, key=lambda a: (a.get("name") or a["app_id"]).casefold())
        rows = [{"app": a, "rank": i + 1, "evidence_fields": ["catalogue"]} for i, a in enumerate(apps[:_LISTED])]
        body = self.compose("list", "", rows, "en")["message"]
        count = len(apps)
        lead = (f"There {'is' if count == 1 else 'are'} {count} App{'s' if count != 1 else ''} in the Store"
                + (":" if count <= _LISTED else f". Here are {_LISTED}; tell me what you need and I’ll find the right ones."))
        return self._reply(lead + "\n\n" + body, rows, "browse", {"outcome": "not_applicable", "reason": "catalogue_browse"})

    def _small_talk(self, act: str, locale: str, catalogue: list[dict]) -> dict:
        intent = "conversation" if act == "thanks" else act
        if locale != "en" and act != "thanks":
            return self._reply(self.static(act, locale), [], intent, {"outcome": "not_applicable", "reason": act})
        example = next((a.get("name") for a in catalogue if a.get("name")), "an App")
        message = {
            "greeting": "Hello! I can help you explore the Apps in the HEDGE Store: ask what an App does, "
                        "find one for a task, or compare a few.",
            "help": (f"I can tell you what the {len(catalogue)} App{'s' if len(catalogue) != 1 else ''} in the Store do, "
                     "find one for a task you describe, check whether an App can do something, and compare them. "
                     f"For example: “What does {example} do?” or “Is there an App for flexibility trading?”"),
            "thanks": "You’re welcome. Come back any time you want to explore more Apps.",
            "out_of_scope": "I can only help with the Apps in the HEDGE Store. You can ask what an App does, "
                            "look for one for a task, or compare them.",
            "reset": self.static("reset", locale),
        }[act]
        return self._reply(message, [], intent, {"outcome": "not_applicable", "reason": act})

    def _clarify(self, frame: Frame, catalogue: list[dict], shown: list[str] = ()) -> dict:
        names = {a["id"]: a.get("name") or a["app_id"] for a in catalogue}
        # Offer the Apps just shown first: "it" after two results means one of them.
        offered = [names[i] for i in shown if i in names] or list(names.values())
        listed = " or ".join(f"**{n}**" for n in offered[:3])
        if frame.problem == "two_readings":
            readings = [o["gloss"] for o in frame.options]
            message = "Do you want me to " + ", or ".join(readings) + "?"
        elif frame.problem == "id_case":
            message = "App IDs are case-sensitive. Please use the exact ID or the App’s name."
        elif frame.problem == "ambiguous_name":
            message = ("Several Apps have that name. Please choose one from its App card, or use its exact native ID.")
        elif frame.problem in {"no_subject", "no_comparison_pair", "unavailable_subject"}:
            need = "two Apps to compare" if frame.problem == "no_comparison_pair" else "which App you mean"
            message = (f"Tell me {need}" + (f", for example {listed}" if listed else "") + ".")
            if frame.problem == "unavailable_subject":
                message = "That App is no longer available. " + message
        elif frame.problem == "unavailable_action":
            message = "That App is no longer available. Please browse the current Apps."
        elif frame.problem == "no_need":
            message = "What should the App do? Describe the task, and I’ll look for Apps whose descriptions cover it."
        elif frame.problem == "no_term":
            message = "Which word or idea would you like me to explain?"
        else:
            message = "I didn’t quite follow. You can ask what an App does, look for an App for a task, or ask me to list the Apps."
        return self._reply(message, [], "clarify", {"outcome": "not_applicable", "reason": frame.problem or "clarification"})

    def _unverified(self, state: dict, act: str) -> dict:
        message = self.compose("unverified", "", [], "en", state["pending_filters"])["message"]
        return {**self._reply(message, [], "search" if act == "find" else "detail",
                              {"outcome": "abstained", "reason": "unverified_filters"}),
                "unverified_filters": state["pending_filters"]}

    async def _remove_constraint(self, req, state, history, catalogue, filters) -> dict:
        pending = state.get("pending_filters", [])
        if not pending:
            return self._reply("There’s no earlier condition to drop. What would you like to look for?", [],
                               "conversation", {"outcome": "not_applicable", "reason": "constraint_update"})
        state["pending_filters"], state["constraint_request"] = [], ""
        need = state.get("need", "")
        if need and cost_question(need):
            need = " ".join(re.sub(r"\b(?:free|paid|cheap\w*|budget|pricing|cost\w*|price\w*)\b", " ", need, flags=re.I).split())
        if state.get("last", {}).get("act") == "find" and need:
            state["need"] = need
            return await self._find(Frame("find", need=need), req, state, filters)
        return self._reply("I’ve dropped that condition. What would you like to explore next?", [], "conversation",
                           {"outcome": "not_applicable", "reason": "constraint_update"})

    async def _guarded_explain(self, act, message, apps, state, history, phrase=""):
        """Run the explainer; release streamed text only while its Apps are unchanged.

        Every sentence is re-checked against the current authorized catalogue
        before the widget sees it, so no later validation can reject text that
        was already shown. Returns the answer, the released text, and whether
        the Apps changed.
        """
        relay, ids, released, changed = STREAM.get(), [a["id"] for a in apps], [], []

        def release(text):
            if changed or self.resolve(ids) != apps:
                changed.append(True)
                return
            released.append(text)
            relay(text)

        token = STREAM.set(release if relay else None)
        try:
            answer = await asyncio.to_thread(self.explainer, act, message, apps,
                                             deepcopy(state.get("explanations", {})), history[-6:], phrase)
        finally:
            STREAM.reset(token)
        return answer, "".join(released), bool(changed) or self.resolve(ids) != apps

    def _hold(self, reply: dict, state: dict, frame: Frame) -> dict:
        """No path recommends while a condition the Store cannot verify is pending.

        One gate after execution, so search, capability checks, choices and model
        review are all covered, whichever of them produced the recommendation.
        """
        recommended = reply.get("apps") and (reply.get("decision") or {}).get("outcome") == "recommended"
        if state.get("pending_filters") and recommended:
            return {**self._unverified(state, frame.act), "candidates": reply["apps"] + reply.get("candidates", []),
                    "presented": [r["app"]["id"] for r in reply["apps"]]}
        return reply

    def _recheck(self, reply: dict) -> dict:
        """A slow step must not show withdrawn or modified Apps."""
        if reply.get("changed"):
            return reply
        visible = [*reply.get("apps", []), *reply.get("candidates", [])]
        fresh = {a["id"]: a for a in self.resolve([r["app"]["id"] for r in visible])}
        if any(fresh.get(r["app"]["id"]) != r["app"] for r in visible):
            return {**reply, "message": _CHANGED, "apps": [], "candidates": [],
                    "decision": {"outcome": "abstained", "reason": "catalogue_changed"}, "changed": True}
        return reply

    # --- state ---------------------------------------------------------------

    def _next_state(self, state: dict, frame: Frame, reply: dict) -> dict:
        shown = reply.get("presented") or [r["app"]["id"] for r in reply.get("apps", [])]
        if reply.get("changed"):
            return {k: v for k, v in state.items() if k in {"pending_filters", "constraint_request", "need"}}
        if frame.act in SMALL_TALK | {"clarify"}:
            return {**state, "shown": state.get("shown", [])} if frame.act != "reset" else {}
        state["shown"] = shown
        if frame.act in EXPLANATION_ACTS | {"provider", "price", "access", "details", "ask", "check"}:
            state["focus"] = frame.subjects[:1] if len(frame.subjects) == 1 else state.get("focus", [])
        elif frame.act == "find":
            state["focus"] = shown[:1] if len(shown) == 1 else []
        elif frame.act in {"compare", "choose"}:
            state["focus"] = [i for i in state.get("focus", []) if i in frame.subjects]
        elif frame.act == "list":
            state["focus"] = shown[:1] if len(shown) == 1 else []
        if len(shown) > 1 or frame.act in {"compare", "choose"}:
            state["compared"] = shown if len(shown) > 1 else frame.subjects
        if frame.need:
            state["need"] = frame.need
        state["discussed"] = list(dict.fromkeys([*state.get("discussed", []), *frame.subjects, *shown[:1]]))[-5:]
        state["last"] = {"act": frame.act, "subjects": frame.subjects, "need": frame.need}
        return state

    @staticmethod
    def _reply(message, rows, intent, decision) -> dict:
        return {"message": message, "apps": rows, "intent": intent, "decision": decision,
                "generation": {"source": "prepared"}}
