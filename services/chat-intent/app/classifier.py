"""Keyword-based intent classifier.

Intents:
  - search: user wants to find/discover apps
  - detail: user wants info about a specific app
  - help: user needs assistance
  - greeting: user greets
  - unknown: fallback (treated as search)
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class IntentResult:
    intent: str
    confidence: float
    entities: dict


# Patterns ordered by priority (first match wins within each intent)
_INTENT_PATTERNS: list[tuple[str, list[re.Pattern]]] = [
    (
        "greeting",
        [
            re.compile(r"^(hi|hello|hey|greetings|good\s*(morning|afternoon|evening))[\s!.,?]*$", re.I),
        ],
    ),
    (
        "help",
        [
            re.compile(r"\b(help|how\s+do\s+i|what\s+can\s+you\s+do|usage|guide|instructions)\b", re.I),
        ],
    ),
    (
        "detail",
        [
            re.compile(r"\b(tell\s+me\s+(more\s+)?about|details?\s+(of|about|for)|what\s+does\b.*\bdo|explain|describe)\b", re.I),
            re.compile(r"\bapp[-\s]?\d{3}\b", re.I),  # explicit app ID reference
        ],
    ),
    (
        "search",
        [
            re.compile(r"\b(find|search|looking\s+for|show\s+me|i\s+need|recommend|suggest|discover|any\s+app|which\s+app)\b", re.I),
            re.compile(r"\b(monitor|track|manage|detect|optimi[sz]e|control|analyz|measur|automat)\b", re.I),
        ],
    ),
]

# App ID extraction pattern
_APP_ID_RE = re.compile(r"\b(app[-\s]?\d{3})\b", re.I)


def classify(text: str) -> IntentResult:
    """Classify user message into an intent."""
    text_clean = text.strip()
    if not text_clean:
        return IntentResult(intent="unknown", confidence=0.0, entities={})

    # Extract potential app IDs
    entities: dict = {}
    app_id_match = _APP_ID_RE.search(text_clean)
    if app_id_match:
        entities["app_id"] = app_id_match.group(1).replace(" ", "-").lower()

    for intent_name, patterns in _INTENT_PATTERNS:
        for pattern in patterns:
            if pattern.search(text_clean):
                return IntentResult(intent=intent_name, confidence=0.85, entities=entities)

    # Fallback: if text is long enough, assume search intent
    if len(text_clean.split()) >= 3:
        return IntentResult(intent="search", confidence=0.5, entities=entities)

    return IntentResult(intent="unknown", confidence=0.3, entities=entities)
