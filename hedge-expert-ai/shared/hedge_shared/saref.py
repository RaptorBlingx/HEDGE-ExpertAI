"""SAREF ontology class inference from tags and text.

SAREF (Smart Applications REFerence) ontology provides a shared model for IoT.
This module maps keywords to SAREF classes for ranking boost.

CRITICAL: infer_saref_class() MUST accept both str and list[str] as the tags
parameter, because different callers pass different types.
"""

from __future__ import annotations

# Mapping of keywords to SAREF ontology classes
# Based on SAREF core + SAREF4ENER, SAREF4BLDG, SAREF4ENVI, SAREF4AGRI, SAREF4CITY
SAREF_KEYWORDS: dict[str, list[str]] = {
    "Energy": [
        "energy", "power", "electricity", "solar", "wind", "battery",
        "consumption", "generation", "grid", "meter", "photovoltaic",
        "renewable", "efficiency", "watt", "kwh", "voltage", "current",
        "inverter", "charging", "ev", "heat", "thermal",
        "thermostat", "demand", "load",
    ],
    "Building": [
        "building", "room", "floor", "door", "window", "elevator",
        "lighting", "light", "occupancy", "ventilation", "air",
        "conditioning", "smart home", "home automation", "bms",
        "facility", "space", "zone", "ceiling", "wall",
        "hvac", "heating", "cooling",
    ],
    "Environment": [
        "environment", "weather", "temperature", "humidity", "co2",
        "pollution", "air quality", "noise", "radiation", "pressure",
        "climate", "forecast", "wind speed", "rainfall", "uv",
        "particulate", "pm2.5", "pm10", "ozone", "emission",
    ],
    "Water": [
        "water", "irrigation", "flood", "moisture", "leak",
        "wastewater", "reservoir", "pump", "flow", "pipe",
        "hydro", "rain", "drainage", "sewage",
    ],
    "Agriculture": [
        "agriculture", "farm", "crop", "soil", "livestock",
        "greenhouse", "precision farming", "fertilizer", "harvest",
        "plant", "garden", "irrigation", "pest",
    ],
    "City": [
        "city", "traffic", "parking", "street", "public transport",
        "waste", "bin", "recycling", "urban", "municipal",
        "infrastructure", "road", "pedestrian", "bike",
    ],
    "Health": [
        "health", "medical", "patient", "hospital", "wearable",
        "fitness", "heart rate", "blood pressure", "glucose",
        "wellness", "elderly", "care",
    ],
    "Manufacturing": [
        "manufacturing", "factory", "production", "machine",
        "industrial", "assembly", "quality", "predictive maintenance",
        "vibration", "motor", "conveyor", "robot",
    ],
}

# Flattened reverse lookup: keyword -> SAREF class
_KEYWORD_TO_CLASS: dict[str, str] = {}
for _cls, _keywords in SAREF_KEYWORDS.items():
    for _kw in _keywords:
        _KEYWORD_TO_CLASS[_kw.lower()] = _cls


def infer_saref_class(tags: str | list[str]) -> str | None:
    """Infer SAREF class from tags.

    Args:
        tags: A single string (space-separated) or a list of strings.

    Returns:
        The best-matching SAREF class name, or None if no match.
    """
    if isinstance(tags, str):
        words = tags.lower().split()
    elif isinstance(tags, list):
        words = " ".join(str(t) for t in tags).lower().split()
    else:
        return None

    # Count matches per class
    class_scores: dict[str, int] = {}
    text = " ".join(words)

    for keyword, saref_class in _KEYWORD_TO_CLASS.items():
        if keyword in text:
            class_scores[saref_class] = class_scores.get(saref_class, 0) + 1

    if not class_scores:
        return None

    return max(class_scores, key=class_scores.get)  # type: ignore[arg-type]


def get_saref_class_for_query(query: str) -> str | None:
    """Infer SAREF class from a user query string."""
    return infer_saref_class(query)
