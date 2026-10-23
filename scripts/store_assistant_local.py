"""The Store assistant wired in-process, for playgrounds and offline evaluation.

The deployed wiring (chat-intent/app/private_store.py) reaches Expert, Discovery
and Rasa over HTTP; here the same components are called directly. Act
classification uses the given E5 similarity function and, when RASA_URL is set,
a Rasa server.
"""
from __future__ import annotations

import os

import httpx


def local_assistant(chat, expert, *, recommend, resolve, semantic, rasa_url: str | None = None,
                    arbitrate: bool = False):
    """chat/expert are load_service() module loaders; semantic(text, examples) -> scores."""
    assistant, understanding = chat("assistant"), chat("understanding")
    answers, explainer, recommender = expert("answers"), expert("explainer"), expert("recommender")
    rasa_url = rasa_url if rasa_url is not None else os.environ.get("RASA_URL", "")

    def rasa(text):
        if not rasa_url:
            return None
        parsed = httpx.post(rasa_url.rstrip("/") + "/model/parse", json={"text": text}, timeout=10).json()
        return [(r["name"], r["confidence"]) for r in parsed.get("intent_ranking", [])]

    def compose(mode, question, rows, locale, fields=()):
        if mode == "check":
            return answers.capability_answer(question, rows, locale)
        if mode == "review":
            return answers.search_answer(question, rows, locale)
        if mode == "decide":
            return recommender._recommendation_decision(question, rows, locale)
        if mode == "list":
            return {"message": answers.listing([r["app"] for r in rows])}
        return {"message": answers.unverified(list(fields))}

    def choose(message, options, context):
        return expert("interpretation").choose(message, [o["gloss"] for o in options], context.get("history", []))

    return assistant.Assistant(
        recommend=recommend, resolve=resolve, compose=compose,
        explainer=lambda act, q, apps, state, history, phrase="": explainer.respond(act, q, apps, state, history, phrase),
        interpreter=understanding.Interpreter(rasa=rasa, semantic=semantic, arbitrate=choose if arbitrate else None),
        static=lambda intent, locale: chat("routes")._static_message(intent, locale))
