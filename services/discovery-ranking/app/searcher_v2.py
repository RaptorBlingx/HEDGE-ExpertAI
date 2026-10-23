"""Independent lexical+dense retrieval with reciprocal-rank fusion."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import redis
from hedge_shared.models_v2 import (
    AppMetadataV2,
    RelevanceBand,
    SearchFilters,
)
from hedge_shared.storage import get_catalogue_apps, lexical_search
from hedge_shared.store_knowledge import project
from hedge_shared.store_v1 import StoreAppMetadata, validate_offline_store_scope
from qdrant_client import QdrantClient

from .embeddings import encode_single
from .indexer import COLLECTION_ALIAS

logger = logging.getLogger(__name__)

RRF_K = int(os.getenv("RRF_K", "60"))
DENSE_WEIGHT = float(os.getenv("RRF_DENSE_WEIGHT", "0.55"))
LEXICAL_WEIGHT = float(os.getenv("RRF_LEXICAL_WEIGHT", "0.45"))
SEMANTIC_BOOST_MAX = float(os.getenv("SEMANTIC_BOOST_MAX", "0.05"))
CACHE_TTL = int(os.getenv("SEARCH_CACHE_TTL_SECONDS", "300"))


def _cache() -> redis.Redis:
    return redis.from_url(
        os.getenv("VALKEY_CACHE_URL", "redis://valkey-cache:6379/1"),
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )


def _matches_filters(payload: dict[str, Any], filters: SearchFilters) -> bool:
    """Apply the same typed filters to dense candidates."""
    if payload.get("source_profile") == "hedge-store-v1":
        if any(value for key, value in filters.model_dump().items() if key != "publisher"):
            return False
        return not filters.publisher or filters.publisher.casefold() in str(
            payload.get("provider") or ""
        ).casefold()
    publisher = payload.get("publisher") or {}
    lifecycle = payload.get("lifecycle") or {}
    trust = payload.get("trust") or {}
    deployment = payload.get("deployment") or {}
    annotations = payload.get("semantic_annotations") or []
    contracts = [*(payload.get("inputs") or []), *(payload.get("outputs") or [])]

    def includes_all(field: str, expected: list[str]) -> bool:
        actual = {str(item).casefold() for item in payload.get(field, [])}
        return all(value.casefold() in actual for value in expected)

    if (
        filters.publisher
        and filters.publisher.casefold() not in str(publisher.get("name", "")).casefold()
    ):
        return False
    if filters.lifecycle_status and lifecycle.get("status") != filters.lifecycle_status.value:
        return False
    if filters.license_spdx and trust.get("license_spdx") != filters.license_spdx:
        return False
    if not includes_all("tags", filters.tags):
        return False
    if not includes_all("capabilities", filters.capabilities):
        return False
    if not includes_all("protocols", filters.protocols):
        return False
    if not includes_all("supported_languages", list(filters.supported_languages)):
        return False
    if filters.deployment_modes:
        modes = {str(item).casefold() for item in deployment.get("modes", [])}
        if not all(mode.casefold() in modes for mode in filters.deployment_modes):
            return False
    if filters.semantic_uri and not any(
        item.get("term_uri") == str(filters.semantic_uri) for item in annotations
    ):
        return False
    if filters.extension_uri and not any(
        item.get("ontology_uri") == str(filters.extension_uri) for item in annotations
    ):
        return False
    if filters.data_classifications:
        classifications = {item.get("data_classification") for item in contracts}
        if not all(value in classifications for value in filters.data_classifications):
            return False
    return True


def _dense_candidates(
    client: QdrantClient,
    query: str,
    *,
    filters: SearchFilters,
    limit: int,
    store_id: str | None = None,
    collection_name: str | None = None,
) -> list[dict[str, Any]]:
    response = client.query_points(
        collection_name=collection_name or COLLECTION_ALIAS,
        query=encode_single(query),
        limit=min(max(limit * 8, 40), 160),
        with_payload=True,
    )
    candidates = []
    for point in response.points:
        payload = point.payload or {}
        profile_matches = (
            payload.get("source_profile") == "hedge-store-v1" and payload.get("store_id") == store_id
            if store_id is not None else payload.get("schema_version") == "2.0"
        )
        if (
            not profile_matches
            or not isinstance(payload.get("id"), str)
            or type(payload.get("_index_revision")) is not int
        ):
            continue
        candidates.append(
            {
                "id": str(payload["id"]),
                "revision": payload["_index_revision"],
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


def _semantic_boost(payload: dict[str, Any], filters: SearchFilters) -> float:
    """Return a bounded, provenance-aware semantic boost."""
    if not filters.semantic_uri and not filters.extension_uri:
        return 0.0
    annotations = payload.get("semantic_annotations") or []
    best = 0.0
    for annotation in annotations:
        if filters.semantic_uri and annotation.get("term_uri") != str(filters.semantic_uri):
            continue
        if filters.extension_uri and annotation.get("ontology_uri") != str(filters.extension_uri):
            continue
        provenance = annotation.get("provenance")
        review = annotation.get("review_status")
        factor = 1.0 if provenance in {"publisher", "curated"} and review == "approved" else 0.5
        best = max(best, SEMANTIC_BOOST_MAX * factor)
    return best


def reciprocal_rank_fusion(
    dense: list[dict[str, Any]],
    lexical: list[dict[str, Any]],
    *,
    filters: SearchFilters,
    limit: int,
) -> list[dict[str, Any]]:
    """Fuse independent rankings without treating raw scores as comparable."""
    fused: dict[str, dict[str, Any]] = {}
    for source, weight in ((dense, DENSE_WEIGHT), (lexical, LEXICAL_WEIGHT)):
        for rank, candidate in enumerate(source, start=1):
            app_id = str(candidate.get("id") or candidate["payload"]["id"])
            row = fused.setdefault(
                app_id,
                {
                    "app": candidate["payload"],
                    "prepared_projection": candidate.get("prepared_projection"),
                    "fusion_score": 0.0,
                    "sources": [],
                },
            )
            row["fusion_score"] += weight / (RRF_K + rank)
            row["sources"].append("dense" if source is dense else "lexical")

    for row in fused.values():
        row["fusion_score"] += _semantic_boost(row["app"], filters)
    ordered = sorted(
        fused.values(),
        key=lambda item: (-item["fusion_score"], str(item["app"]["id"])),
    )[:limit]

    results: list[dict[str, Any]] = []
    for rank, row in enumerate(ordered, start=1):
        public_payload = {
            key: value for key, value in row["app"].items() if not key.startswith("_index_")
        }
        relevance = (
            RelevanceBand.HIGH
            if rank <= 2 and len(row["sources"]) == 2
            else RelevanceBand.MEDIUM
            if rank <= 5
            else RelevanceBand.LOW
        )
        if public_payload.get("source_profile") == "hedge-store-v1":
            app = row.get("prepared_projection") or StoreAppMetadata.model_validate(
                {key: value for key, value in public_payload.items()
                 if key not in {"id", "public_eligible", "checksum"}}
            ).recommendation_projection()
            results.append({"app": app, "rank": rank, "evidence_fields": row["sources"]})
            continue
        results.append(
            {
                "app": AppMetadataV2.model_validate(public_payload).model_dump(
                    mode="json",
                    exclude={"checksum"},
                ),
                "rank": rank,
                "relevance": relevance.value,
                "evidence_fields": row["sources"],
            }
        )
    return results


def _resolve_rankings(
    rankings: dict[str, list[dict[str, Any]]], filters: SearchFilters,
    *, store_id: str | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], bool]:
    """Treat vectors/cache as ranked references, never publication or metadata authority."""
    if set(rankings) != {"dense", "lexical"}:
        raise ValueError("Invalid cached rankings")
    for candidates in rankings.values():
        if not isinstance(candidates, list) or len(candidates) > 160:
            raise ValueError("Invalid cached candidates")
        for item in candidates:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("id"), str)
                or type(item.get("revision")) is not int
            ):
                raise ValueError("Invalid candidate identity/revision")
    scope = {"store_id": store_id} if store_id is not None else {}
    rows = get_catalogue_apps(
        [item["id"] for items in rankings.values() for item in items], **scope
    )
    if store_id is not None:
        for key, row in list(rows.items()):
            try:
                app = StoreAppMetadata.model_validate(row["payload"])
            except ValueError:
                del rows[key]
                continue
            prepared = project(row)
            if (
                app.store_id != store_id or app.id != key
                or not app.public_eligible or not any(path not in {"billable", "price"}
                    for path in prepared.get("source_evidence", {}))
            ):
                del rows[key]
            else:
                # Keep the authoritative source until final fusion projects safe evidence.
                row["payload"] = app.model_dump(mode="json", exclude={"checksum"})
                row["prepared_projection"] = prepared
    resolved = {"dense": [], "lexical": []}
    changed = False
    for source, candidates in rankings.items():
        seen = set()
        for item in candidates:
            row = rows.get(item["id"])
            if (
                row is None
                or row["revision"] != item["revision"]
                or not _matches_filters(row["payload"], filters)
            ):
                changed = True
                continue
            if item["id"] not in seen:
                resolved[source].append({**item, "payload": row["payload"],
                                         **({"prepared_projection": row["prepared_projection"]} if store_id is not None else {})})
                seen.add(item["id"])
    return resolved, changed


def search_apps_v2(
    client: QdrantClient,
    *,
    query: str,
    locale: str,
    filters: SearchFilters,
    limit: int,
    catalogue_revision: str = "current",
    store_id: str | None = None,
    collection_name: str | None = None,
) -> list[dict[str, Any]]:
    """Fuse ranked references using current PostgreSQL eligibility and payloads."""
    validate_offline_store_scope(store_id, collection_name)
    scope = {"store_id": store_id} if store_id is not None else {}
    vector_scope = {**scope, "collection_name": collection_name} if scope else {}
    cache_key = "hedge:search:v3:" + json.dumps(
        {
            "q": query.casefold().strip(),
            "locale": locale,
            "filters": filters.model_dump(mode="json"),
            "limit": limit,
            "revision": catalogue_revision,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    try:
        cached = _cache().get(cache_key) if store_id is None else None
        rankings = json.loads(cached) if cached else None
    except Exception:
        logger.warning("Search cache unavailable; continuing without cache")
        rankings = None
    if rankings is not None:
        try:
            resolved, changed = _resolve_rankings(rankings, filters)
        except (ValueError, TypeError):
            logger.warning("Invalid search cache entry; recomputing rankings")
        else:
            if not changed:
                return reciprocal_rank_fusion(**resolved, filters=filters, limit=limit)

    lexical = lexical_search(query, locale=locale, filters=filters, limit=min(limit * 8, 160), **scope)
    vector_ok = True
    try:
        dense = _dense_candidates(client, query, filters=filters, limit=min(limit * 8, 160), **vector_scope)
    except Exception:
        logger.warning("Vector retrieval unavailable; using PostgreSQL lexical candidates")
        dense = []
        vector_ok = False
    rankings = {
        "dense": dense,
        "lexical": [{"id": row["id"], "revision": row["revision"]} for row in lexical],
    }
    resolved, changed = _resolve_rankings(rankings, filters, **scope)
    results = reciprocal_rank_fusion(**resolved, filters=filters, limit=limit)
    # Do not freeze degraded or outdated rankings while the vector index recovers.
    if store_id is None and vector_ok and not changed and results:
        try:
            _cache().setex(cache_key, CACHE_TTL, json.dumps(rankings))
        except Exception:
            logger.warning("Search cache unavailable; result was not cached")
    return results
