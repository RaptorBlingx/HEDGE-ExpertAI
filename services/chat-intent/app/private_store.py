"""Bind the existing Store dialogue to deployed HTTP services."""
import os
from functools import lru_cache

import httpx
from fastapi import HTTPException

from .store_conversation import StoreConversation

client = httpx.Client(timeout=30, trust_env=False,
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

    def unavailable(*args, **kwargs):
        raise RuntimeError("Optional generation is disabled in private service testing")

    return StoreConversation(
        _recommend_v2, resolve,
        lambda q, rows, locale: compose("describe", q, rows, locale)["message"],
        unavailable, unavailable,
        decide=lambda q, rows, locale: compose("decide", q, rows, locale),
        present=present,
    )
