"""Bind the existing Store dialogue to deployed HTTP services."""
import json
import os
from functools import lru_cache

import httpx
from fastapi import HTTPException
from hedge_shared.config import Settings

from .store_conversation import STREAM, StoreConversation

client = httpx.Client(timeout=Settings().STORE_MODEL_TIMEOUT_SECONDS + 10, trust_env=False,
                      headers={"X-API-Key": os.environ.get("GATEWAY_API_KEY", "")})


def call(service, path, body):
    try:
        response = client.post(os.environ[service] + path, json=body)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Store service unavailable") from None


def resolve(identities):
    return call("DISCOVERY_RANKING_URL", "/internal/store/catalogue", {"identities": identities})["apps"]


def compose(mode, question, rows, locale, response=None):
    return call("EXPERT_RECOMMEND_URL", "/internal/store/compose",
                {"mode": mode, "question": question, "rows": rows,
                 "locale": locale, "response": response or {}})


def present(question, response, locale):
    result = compose("present", question, [], locale, response)
    response["context"] = result["context"]
    return result["message"]


@lru_cache(maxsize=1)
def policy():
    from .routes import _recommend_v2

    def interpret(question, locale, directory, context, history):
        return call("EXPERT_RECOMMEND_URL", "/internal/store/interpret", {
            "question": question, "locale": locale, "directory": directory,
            "context": context, "history": history})

    def explain(question, rows, locale, action, history, **kwargs):
        # Progress callbacks are local; only typed conversation data crosses HTTP.
        return call("EXPERT_RECOMMEND_URL", "/internal/store/reason", {
            "question": question, "rows": rows, "locale": locale,
            "action": action, "history": history, "references": kwargs.get("references", {}),
            "nlu": kwargs.get("nlu_hint", {})})

    def explainer(act, question, apps, state, history, phrase=""):
        body = {"act": act, "question": question, "apps": apps, "state": state,
                "history": history[-6:], "phrase": phrase[:120]}
        relay = STREAM.get()
        if relay is None:
            return call("EXPERT_RECOMMEND_URL", "/internal/store/explain", body)
        # Forward checked sentences to the widget while the answer is generated.
        try:
            with client.stream("POST", os.environ["EXPERT_RECOMMEND_URL"] + "/internal/store/explain",
                               json={**body, "stream": True}) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    item = json.loads(line) if line else {}
                    if "delta" in item:
                        relay(str(item["delta"]))
                    elif "final" in item:
                        return item["final"]
        except (httpx.HTTPError, ValueError):
            pass
        raise HTTPException(503, "Store service unavailable")

    return StoreConversation(
        _recommend_v2, resolve,
        lambda q, rows, locale: compose("describe", q, rows, locale)["message"],
        interpret, explain,
        decide=lambda q, rows, locale: compose("decide", q, rows, locale),
        present=present, explainer=explainer,
    )
