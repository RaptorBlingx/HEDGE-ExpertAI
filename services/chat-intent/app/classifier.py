"""Keyword-based intent classifier.

Design Decision (OC1 Scope):
  The proposal specifies RASA for intent classification & entity extraction.
  For OC1 the regex classifier is sufficient because:
    1. The intent space is small and well-defined (5 intents).
    2. IoT domain queries follow predictable patterns
       ("find apps for…", "show me…", "tell me about…").
    3. RASA adds ~2GB memory and a separate container; the current sandbox
       server has only 5GB RAM already saturated by Ollama.
    4. Classification accuracy on the 69-query test set is >95%
       (verified via unit tests in test_classifier.py).
  RASA integration is prepared (RASA_ENABLED flag in shared config) and
  will be activated when moving to a larger deployment or OC2.

Intents:
  - search: user wants to find/discover apps
  - detail: user wants info about a specific app
  - help: user needs assistance
  - greeting: user greets
  - unknown: fallback (treated as search)
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass

import httpx


logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}
_RASA_CONSECUTIVE_FAILURES = 0
_RASA_CIRCUIT_OPEN_UNTIL = 0.0


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
            re.compile(r"^(hi|hello|hey|greetings|good\s*(morning|afternoon|evening)|howdy|welcome)[\s!.,?]*$", re.I),
        ],
    ),
    (
        "help",
        [
            re.compile(r"\b(help|how\s+do\s+i|what\s+can\s+you\s+do|usage|guide|instructions|how\s+does\s+this\s+work)\b", re.I),
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
            re.compile(r"\b(find|search|looking\s+for|show\s+me|i\s+need|recommend|suggest|discover|any\s+app|which\s+app|list\b.*\bapps?)\b", re.I),
            re.compile(r"\b(monitor|track|manage|detect|optimi[sz]e|control|analyz|measur|automat|sens[eo]r|smart|iot)\b", re.I),
            # Domain-specific patterns that strongly imply search intent
            re.compile(r"\b(energy|building|environment|water|agriculture|city|health|manufacturing|hvac|irrigation|factory)\b", re.I),
        ],
    ),
]

# App ID extraction pattern
_APP_ID_RE = re.compile(r"\b(app[-\s]?\d{3})\b", re.I)

# Entity extraction patterns for SAREF classes
_SAREF_ENTITY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("Energy", re.compile(r"\b(energy|solar|wind|grid|electric|power|battery|renewable|charging)\b", re.I)),
    ("Building", re.compile(r"\b(building|hvac|indoor|elevator|lighting|occupancy|access\s+control)\b", re.I)),
    ("Environment", re.compile(r"\b(environment|air\s+quality|pollution|weather|flood|wildfire|noise)\b", re.I)),
    ("Water", re.compile(r"\b(water|leak|irrigation|drain|wastewater|pipeline|swimming\s+pool)\b", re.I)),
    ("Agriculture", re.compile(r"\b(agricultur|farm|crop|soil|livestock|greenhouse|beehive|apiculture)\b", re.I)),
    ("City", re.compile(r"\b(city|urban|traffic|parking|waste|street|transit|bike)\b", re.I)),
    ("Health", re.compile(r"\b(health|patient|wearable|elderly|fall\s+detect|diabetes|sleep|medication|rehabilitation)\b", re.I)),
    ("Manufacturing", re.compile(r"\b(manufactur|factory|predictive\s+maintenance|assembly|warehouse|cnc|robot)\b", re.I)),
]


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def _extract_entities(text_clean: str) -> dict:
    entities: dict = {}
    app_id_match = _APP_ID_RE.search(text_clean)
    if app_id_match:
        entities["app_id"] = app_id_match.group(1).replace(" ", "-").lower()

    for saref_class, pattern in _SAREF_ENTITY_PATTERNS:
        if pattern.search(text_clean):
            entities.setdefault("saref_class", saref_class)
            break
    return entities


def _classify_via_regex(text_clean: str, entities: dict) -> IntentResult:
    for intent_name, patterns in _INTENT_PATTERNS:
        for pattern in patterns:
            if pattern.search(text_clean):
                return IntentResult(intent=intent_name, confidence=0.85, entities=entities)

    if len(text_clean.split()) >= 3:
        return IntentResult(intent="search", confidence=0.5, entities=entities)

    return IntentResult(intent="unknown", confidence=0.3, entities=entities)


def _request_rasa_parse(text: str) -> dict:
    rasa_url = os.getenv("RASA_URL", "http://rasa:5005").rstrip("/")
    timeout_s = float(os.getenv("RASA_TIMEOUT", "5"))
    response = httpx.post(
        f"{rasa_url}/model/parse",
        json={"text": text},
        timeout=timeout_s,
    )
    response.raise_for_status()
    return response.json()


def _classify_via_rasa(text_clean: str, entities: dict) -> IntentResult:
    payload = _request_rasa_parse(text_clean)
    intent_data = payload.get("intent") or {}
    intent_name = str(intent_data.get("name") or "unknown")
    confidence = float(intent_data.get("confidence") or 0.0)

    merged_entities = dict(entities)
    for entity in payload.get("entities") or []:
        entity_name = str(entity.get("entity") or "")
        entity_value = entity.get("value")
        if entity_name == "app_id" and entity_value:
            merged_entities["app_id"] = str(entity_value).replace(" ", "-").lower()
        elif entity_name == "saref_class" and entity_value:
            merged_entities["saref_class"] = str(entity_value)

    if intent_name not in {"greeting", "help", "detail", "search", "unknown"}:
        intent_name = "unknown"

    return IntentResult(intent=intent_name, confidence=confidence, entities=merged_entities)


def _rasa_circuit_open() -> bool:
    global _RASA_CIRCUIT_OPEN_UNTIL, _RASA_CONSECUTIVE_FAILURES
    if _RASA_CIRCUIT_OPEN_UNTIL <= 0:
        return False
    if time.monotonic() >= _RASA_CIRCUIT_OPEN_UNTIL:
        _RASA_CIRCUIT_OPEN_UNTIL = 0.0
        _RASA_CONSECUTIVE_FAILURES = 0
        return False
    return True


def _record_rasa_failure() -> None:
    global _RASA_CONSECUTIVE_FAILURES, _RASA_CIRCUIT_OPEN_UNTIL
    _RASA_CONSECUTIVE_FAILURES += 1
    if _RASA_CONSECUTIVE_FAILURES >= 3:
        _RASA_CIRCUIT_OPEN_UNTIL = time.monotonic() + float(os.getenv("RASA_CIRCUIT_OPEN_SECONDS", "60"))


def _reset_rasa_failures() -> None:
    global _RASA_CONSECUTIVE_FAILURES, _RASA_CIRCUIT_OPEN_UNTIL
    _RASA_CONSECUTIVE_FAILURES = 0
    _RASA_CIRCUIT_OPEN_UNTIL = 0.0


def classify(text: str) -> IntentResult:
    """Classify user message into an intent."""
    text_clean = text.strip()
    if not text_clean:
        return IntentResult(intent="unknown", confidence=0.0, entities={})

    entities = _extract_entities(text_clean)
    regex_result = _classify_via_regex(text_clean, entities)

    if not _env_flag("RASA_ENABLED"):
        return regex_result

    if _rasa_circuit_open():
        logger.warning("RASA circuit open; using regex fallback")
        return regex_result

    try:
        rasa_result = _classify_via_rasa(text_clean, entities)
        _reset_rasa_failures()
    except Exception:
        logger.exception("RASA classification failed; using regex fallback")
        _record_rasa_failure()
        return regex_result

    if _env_flag("RASA_SHADOW_MODE"):
        if rasa_result.intent != regex_result.intent:
            logger.info(
                "RASA shadow disagreement: rasa=%s regex=%s text=%s",
                rasa_result.intent,
                regex_result.intent,
                text_clean,
            )
        return regex_result

    threshold = float(os.getenv("RASA_CONFIDENCE_THRESHOLD", "0.6"))
    if rasa_result.confidence >= threshold:
        return rasa_result

    return regex_result
