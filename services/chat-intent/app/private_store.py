"""Bind the Store assistant to the deployed HTTP services."""
import json
import logging
import os
import threading
import time
from functools import lru_cache

import httpx
from fastapi import HTTPException
from hedge_shared.config import Settings

from .assistant import STREAM, Assistant
from .classifier import rasa_acts
from .understanding import Interpreter, acts

logger = logging.getLogger(__name__)
client = httpx.Client(timeout=Settings().STORE_MODEL_TIMEOUT_SECONDS + 10, trust_env=False,
                      headers={"X-API-Key": os.environ.get("GATEWAY_API_KEY", "")})
# Discovery's similarity route accepts this many example utterances per call.
_EXAMPLES_PER_CALL = 400


def call(service, path, body):
    try:
        response = client.post(os.environ[service] + path, json=body)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Store service unavailable") from None


def resolve(identities):
    return call("DISCOVERY_RANKING_URL", "/internal/store/catalogue", {"identities": identities})["apps"]


def compose(mode, question, rows, locale, fields=()):
    return call("EXPERT_RECOMMEND_URL", "/internal/store/compose",
                {"mode": mode, "question": question, "rows": rows, "locale": locale, "fields": list(fields)})


def semantic(text: str, examples: list[str]) -> list[float] | None:
    """E5 similarity of a message to each example utterance; None if Discovery cannot answer."""
    try:
        scores: list[float] = []
        for start in range(0, len(examples), _EXAMPLES_PER_CALL):
            scores += call("DISCOVERY_RANKING_URL", "/api/v2/evidence/similarity", {
                "queries": [text], "passages": examples[start:start + _EXAMPLES_PER_CALL], "symmetric": True})["scores"][0]
        return scores
    except (HTTPException, KeyError, IndexError, TypeError):
        logger.warning("Semantic act classification unavailable")
        return None


def warm(attempts: int = 30, pause: float = 10.0) -> None:
    """Have Discovery embed the example utterances before the first user turn needs them."""
    examples = [e for act in acts().values() for e in act["examples"]]

    def run():
        for _ in range(attempts):
            if semantic("hello", examples) is not None:
                return
            time.sleep(pause)

    threading.Thread(target=run, daemon=True, name="act-examples-warmup").start()


def arbitrate(message: str, options: list[dict], context: dict) -> int | None:
    if not Settings().STORE_SEMANTIC_ENABLED:
        return None
    try:
        choice = call("EXPERT_RECOMMEND_URL", "/internal/store/arbitrate", {
            "message": message, "options": [o["gloss"] for o in options],
            "history": context.get("history", [])[-2:]})["choice"]
    except (HTTPException, KeyError, TypeError):
        return None
    return choice if isinstance(choice, int) else None


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


@lru_cache(maxsize=1)
def policy() -> Assistant:
    from .routes import _recommend_v2, _static_message

    return Assistant(recommend=_recommend_v2, resolve=resolve, compose=compose, explainer=explainer,
                     interpreter=Interpreter(rasa=rasa_acts, semantic=semantic, arbitrate=arbitrate),
                     static=_static_message)
