"""Controlled Store retrieval ablation against disposable PostgreSQL and Qdrant.

No model judgments, mocked vectors, conversational routing or product endpoints
are added. Run inside the isolated evaluation container described in README.md.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import statistics
import sys
import time
import types
from pathlib import Path
from urllib.parse import urlsplit

from hedge_shared import storage, store_sync
from hedge_shared.models_v2 import SearchFilters
from hedge_shared.store_index import repair_store_index
from hedge_shared.store_language import search_language
from hedge_shared.store_v1 import StoreAppMetadata
from qdrant_client import QdrantClient

ROOT = Path(__file__).resolve().parents[2]


def service(name: str, directory: str, module: str):
    if name not in sys.modules:
        package = types.ModuleType(name)
        package.__path__ = [str(ROOT / "services" / directory / "app")]
        sys.modules[name] = package
    return importlib.import_module(f"{name}.{module}")


def require_isolation() -> None:
    db = urlsplit(os.environ["DATABASE_URL"])
    vector = urlsplit(os.environ["HEDGE_TEST_QDRANT_URL"])
    if (db.hostname != "retrieval-db" or db.path not in {
        "/hedge_retrieval_eval", "/hedge_retrieval_real"
    } or vector.hostname != "retrieval-vectors" or os.getenv("APP_ENV") != "test"):
        raise ValueError("Requires the disposable retrieval evaluation network and database")


def collection(store_id: str) -> str:
    import uuid

    return "hedge_store_offline_" + uuid.uuid5(
        uuid.NAMESPACE_URL, "private-store:" + store_id).hex


def seed(apps: list[dict], client: QdrantClient) -> None:
    require_isolation()
    with storage.connection() as conn:
        if conn.execute("SELECT count(*) AS n FROM catalog_apps").fetchone()["n"]:
            raise ValueError("Seed requires an empty disposable catalogue")
    run_id = storage.create_ingestion_run("isolated-retrieval-evaluation")
    by_store: dict[str, dict[str, bool]] = {}
    for raw in apps:
        app = StoreAppMetadata.model_validate(raw)
        storage.upsert_catalogue_app(run_id, app)
        by_store.setdefault(app.store_id, {})[app.id] = app.public_eligible
    with storage.connection() as conn:
        for store_id, available in by_store.items():
            store_sync.observe(conn, store_id, available, run_id, "authorized_snapshot")
    indexer = service("retrieval_discovery", "discovery-ranking", "indexer")
    for store_id in by_store:
        repair_store_index(store_id, client, indexer, collection(store_id))


def metrics(rows: list[dict], mode: str) -> dict:
    positives = [row for row in rows if row["relevant_native_ids"]]
    negatives = [row for row in rows if not row["relevant_native_ids"]]

    def ids(row):
        return [item["app"]["app_id"] for item in row["results"][mode]]

    def mean(values):
        values = list(values)
        return statistics.mean(values) if values else None

    return {
        "positive_queries": len(positives), "unsupported_queries": len(negatives),
        "hit_rate_at_2": mean(float(bool(set(ids(r)[:2]) & set(r["relevant_native_ids"]))) for r in positives),
        "recall_at_5": mean(len(set(ids(r)[:5]) & set(r["relevant_native_ids"])) / len(r["relevant_native_ids"]) for r in positives),
        "mrr_at_5": mean(next((1 / i for i, aid in enumerate(ids(r), 1) if aid in r["relevant_native_ids"]), 0) for r in positives),
        "false_candidates_at_2": sum(len(set(ids(r)[:2]) - set(r["relevant_native_ids"])) for r in rows),
        "returned_slots_at_2": sum(len(ids(r)[:2]) for r in rows),
        "unsupported_queries_with_candidates": sum(bool(ids(r)) for r in negatives),
        "prepared_source_supported": sum(item["suitability"]["status"] == "source_supported" for r in rows for item in r["results"][mode]),
        "prepared_false_support": sum(item["suitability"]["status"] == "source_supported" and item["app"]["app_id"] not in r["relevant_native_ids"] for r in rows for item in r["results"][mode]),
        "missed_relevant_at_5": {r["id"]: sorted(set(r["relevant_native_ids"]) - set(ids(r)[:5])) for r in positives if set(r["relevant_native_ids"]) - set(ids(r)[:5])},
    }


def evaluate(queries: list[dict], store_id: str, client: QdrantClient) -> dict:
    searcher = service("retrieval_discovery", "discovery-ranking", "searcher_v2")
    assessor = service("retrieval_expert", "expert-recommend", "suitability")
    filters = SearchFilters()
    scope = {"store_id": store_id, "collection_name": collection(store_id)}
    rows = []
    for query in queries:
        started = time.perf_counter()
        lexical = storage.lexical_search(query["query"], locale="en", filters=filters, limit=40, store_id=store_id)
        lexical_s = time.perf_counter() - started
        started = time.perf_counter()
        dense = searcher._dense_candidates(client, query["query"], filters=filters, limit=40, **scope)
        dense_s = time.perf_counter() - started
        resolved, changed = searcher._resolve_rankings({
            "dense": dense,
            "lexical": [{"id": r["id"], "revision": r["revision"]} for r in lexical]
        }, filters, store_id=store_id)
        if changed:
            raise RuntimeError("Frozen catalogue/index revisions changed")
        results = {}
        for mode in ("lexical", "semantic", "hybrid"):
            results[mode] = searcher.reciprocal_rank_fusion(
                dense=resolved["dense"] if mode != "lexical" else [],
                lexical=resolved["lexical"] if mode != "semantic" else [],
                filters=filters, limit=5)
            for result in results[mode]:
                result["suitability"] = assessor.assess(search_language(query["query"], "en"), result["app"], "en")
        rows.append({**query, "results": results, "lexical_s": lexical_s, "semantic_s": dense_s,
                     "raw_lexical": [{"id": r["id"], "score": r["lexical_score"]} for r in lexical],
                     "resolved_dense_ids": [r["id"] for r in resolved["dense"]]})
    return {"rows": rows, "metrics": {mode: metrics(rows, mode) for mode in ("lexical", "semantic", "hybrid")}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogue", type=Path)
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--queries", required=True, type=Path)
    parser.add_argument("--store-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    require_isolation()
    client = QdrantClient(url=os.environ["HEDGE_TEST_QDRANT_URL"], check_compatibility=False)
    try:
        if args.seed:
            if args.catalogue is None:
                parser.error("--seed requires --catalogue")
            raw = json.loads(args.catalogue.read_text())
            seed(raw["apps"] if isinstance(raw, dict) else raw, client)
        queries = json.loads(args.queries.read_text())["queries"]
        labels = [q["id"] for q in queries]
        if len(labels) != len(set(labels)):
            raise ValueError("Duplicate query IDs")
        rows = storage.get_catalogue_apps(
            [r["id"] for r in store_sync.members(args.store_id) if r["available"]],
            store_id=args.store_id)
        native_ids = {r["payload"]["app_id"] for r in rows.values()}
        for q in queries:
            if (len(q["relevant_native_ids"]) != len(set(q["relevant_native_ids"]))
                    or not set(q["relevant_native_ids"]) <= native_ids):
                raise ValueError("Relevance label outside the authorized evaluation catalogue")
        result = evaluate(queries, args.store_id, client)
        result["manifest"] = {
            "source": "controlled_engineering_evidence_not_HEDGE_sandbox_KPI",
            "queries_sha256": hashlib.sha256(args.queries.read_bytes()).hexdigest(),
            "catalogue_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest(),
            "authorized_apps": len(rows), "store_id": args.store_id,
            "embedding_model": os.environ.get("EMBEDDING_MODEL"),
            "embedding_revision": os.environ.get("EMBEDDING_MODEL_REVISION"),
            "fusion": {k: getattr(service("retrieval_discovery", "discovery-ranking", "searcher_v2"), k) for k in ("RRF_K", "DENSE_WEIGHT", "LEXICAL_WEIGHT")},
        }
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n")
        print(json.dumps(result["metrics"], indent=2), flush=True)
    finally:
        client.close()


if __name__ == "__main__":
    main()
