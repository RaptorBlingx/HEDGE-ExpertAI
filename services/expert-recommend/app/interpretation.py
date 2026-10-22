"""Choose between two readings of a message when the act classifiers disagree.

The model sees only the conversation's last exchange, the message and the
candidate readings in plain English, and returns the number of one of them. It
never sees source text and cannot add an App, a need or a fact. The fixed
instructions come first so the server can reuse their processed prompt across
calls: on CPU, reading the prompt dominates latency.
"""
from __future__ import annotations

import json
import time

from hedge_shared.config import Settings

from .llm_client import OllamaClient

SYSTEM = (
    "You help an App Store assistant understand its user. Given the last exchange and the user's new "
    "message, decide which reading of the message is what the user wants. Answer with the number of "
    "that reading only. Readings in bold name Apps from the Store."
)


def choose(message: str, options: list[str], history: list[dict]) -> int | None:
    previous = [f"{m.get('role')}: {' '.join(str(m.get('content', '')).split())[:240]}" for m in history[-2:]]
    readings = "\n".join(f"{i + 1}. {text}" for i, text in enumerate(options))
    prompt = (("Last exchange:\n" + "\n".join(previous) + "\n\n" if previous else "")
              + f"New message: {message}\n\nReadings:\n{readings}")
    schema = {"type": "object", "properties": {"reading": {"type": "integer", "enum": list(range(1, len(options) + 1))}},
              "required": ["reading"], "additionalProperties": False}
    settings = Settings()
    budget = settings.STORE_INTERPRETATION_SECONDS
    raw = OllamaClient().chat_structured(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], schema,
        timeout=budget, max_tokens=12, context_tokens=settings.STORE_MODEL_CONTEXT_TOKENS,
        deadline=time.monotonic() + budget)
    reading = json.loads(raw).get("reading")
    return reading - 1 if isinstance(reading, int) and 1 <= reading <= len(options) else None
