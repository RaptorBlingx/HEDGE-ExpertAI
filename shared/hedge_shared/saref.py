"""SAREF ontology class inference from tags and text.

SAREF (Smart Applications REFerence) ontology provides a shared model for IoT.
This module maps keywords to SAREF classes for ranking boost.

CRITICAL: infer_saref_class() MUST accept both str and list[str] as the tags
parameter, because different callers pass different types.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .models_v2 import AppMetadataV2, SemanticAnnotation

SAREF_CORE_VERSION = "4.1.1"
SAREF_CORE_URI = "https://saref.etsi.org/core/"
SAREF_EXTENSION_URIS: dict[str, str] = {
    "SAREF4ENER": "https://saref.etsi.org/saref4ener/",
    "SAREF4ENVI": "https://saref.etsi.org/saref4envi/",
    "SAREF4BLDG": "https://saref.etsi.org/saref4bldg/",
    "SAREF4CITY": "https://saref.etsi.org/saref4city/",
    "SAREF4INMA": "https://saref.etsi.org/saref4inma/",
    "SAREF4AGRI": "https://saref.etsi.org/saref4agri/",
    "SAREF4AUTO": "https://saref.etsi.org/saref4auto/",
    "SAREF4EHAW": "https://saref.etsi.org/saref4ehaw/",
    "SAREF4WEAR": "https://saref.etsi.org/saref4wear/",
    "SAREF4WATR": "https://saref.etsi.org/saref4watr/",
    "SAREF4LIFT": "https://saref.etsi.org/saref4lift/",
    "SAREF4GRID": "https://saref.etsi.org/saref4grid/",
}
SAREF_EXTENSION_VERSIONS: dict[str, str] = {
    name: "2.1.1" for name in SAREF_EXTENSION_URIS
}
SAREF_CORE_TERMS = {
    f"{SAREF_CORE_URI}Command",
    f"{SAREF_CORE_URI}Device",
    f"{SAREF_CORE_URI}FeatureOfInterest",
    f"{SAREF_CORE_URI}Function",
    f"{SAREF_CORE_URI}Property",
    f"{SAREF_CORE_URI}State",
}


def is_allowed_saref_uri(uri: str) -> bool:
    """Return whether a term or ontology URI belongs to the pinned profile."""
    parsed = urlparse(uri)
    if parsed.scheme != "https" or parsed.netloc != "saref.etsi.org":
        return False
    if uri in SAREF_CORE_TERMS or uri == SAREF_CORE_URI:
        return True
    return any(
        uri == extension or uri.startswith(extension)
        for extension in SAREF_EXTENSION_URIS.values()
    )


def validate_annotation(annotation: SemanticAnnotation) -> list[str]:
    """Validate an assertion against the reviewed URI registry."""
    errors: list[str] = []
    term_uri = str(annotation.term_uri)
    ontology_uri = str(annotation.ontology_uri)
    if not is_allowed_saref_uri(term_uri):
        errors.append(f"unsupported SAREF term URI: {term_uri}")
    if ontology_uri not in {SAREF_CORE_URI, *SAREF_EXTENSION_URIS.values()}:
        errors.append(f"unsupported SAREF ontology URI: {ontology_uri}")
    if annotation.relation == "domain" and term_uri not in SAREF_EXTENSION_URIS.values():
        errors.append("domain annotations must reference a registered extension URI")
    if annotation.relation != "domain" and term_uri in SAREF_EXTENSION_URIS.values():
        errors.append("extension roots are valid only as domain annotations")
    return errors


def validate_app_semantics(app: AppMetadataV2) -> list[str]:
    """Return all semantic validation errors for an application."""
    errors: list[str] = []
    for index, annotation in enumerate(app.semantic_annotations):
        errors.extend(
            f"semantic_annotations[{index}]: {error}"
            for error in validate_annotation(annotation)
        )
    return errors


def app_to_jsonld(app: AppMetadataV2) -> dict[str, Any]:
    """Serialize an app as compact JSON-LD without claiming RDF conformance."""
    payload = app.model_dump(mode="json", exclude={"checksum"})
    payload["@context"] = {
        "@vocab": "https://schema.org/",
        "saref": SAREF_CORE_URI,
        "hedge": "https://w3id.org/hedge/catalogue/",
        "semanticAnnotations": "hedge:semanticAnnotations",
        "termUri": {"@id": "hedge:termUri", "@type": "@id"},
        "ontologyUri": {"@id": "hedge:ontologyUri", "@type": "@id"},
    }
    payload["@id"] = f"https://w3id.org/hedge/catalogue/apps/{app.id}"
    payload["@type"] = "SoftwareApplication"
    return payload

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
