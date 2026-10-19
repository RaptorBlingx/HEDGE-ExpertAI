"""Versioned, rebuildable Store knowledge. Source metadata remains authoritative."""
from __future__ import annotations

from typing import Any

from .store_v1 import StoreAppMetadata

# Bump whenever source extraction/projection semantics change. No generated claims.
PREPARATION_VERSION = 1


def prepare(app: StoreAppMetadata) -> dict[str, Any]:
    projection = app.recommendation_projection()
    return {
        "version": PREPARATION_VERSION,
        "checksum": app.checksum,
        "projection": projection,
        "evidence_paths": list(projection["source_evidence"]),
        "index_text": " . ".join(value for path, value in projection["source_evidence"].items()
                                 if path not in {"billable", "price"}),
    }


def project(row: dict[str, Any]) -> dict[str, Any]:
    """Use only preparation bound to this authoritative row; old rows still work.

    These documents are internal ingestion output, never request-supplied data.
    Availability/Store scope must already have been checked by the storage read.
    """
    knowledge = row.get("prepared_knowledge")
    if (isinstance(knowledge, dict) and knowledge.get("version") == PREPARATION_VERSION
            and knowledge.get("checksum") == row.get("checksum")
            and isinstance(knowledge.get("projection"), dict)
            and isinstance(knowledge["projection"].get("source_evidence"), dict)
            and knowledge["projection"].get("id") == row["id"]
            and all(knowledge["projection"].get(field) == row["payload"].get(field)
                    for field in ("source_profile", "store_id", "app_id", "active", "visible"))):
        projection = dict(knowledge["projection"])
        evidence = projection.get("source_evidence", {})
        # JSONB object order is not source order. Keep paths separately so
        # deterministic explanations remain stable across persistence.
        projection["source_evidence"] = {path: evidence[path]
            for path in knowledge.get("evidence_paths", evidence) if path in evidence}
        return projection
    return StoreAppMetadata.model_validate(row["payload"]).recommendation_projection()
