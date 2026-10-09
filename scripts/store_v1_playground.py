#!/usr/bin/env python3
"""Manual offline Store pipeline harness; use store-v1-playground.sh for isolation."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import importlib.util
import json
import os
import sys
import uuid
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
STORE = "Manual-Store-Fixture"
BANNER = """OFFLINE SANITIZED FIXTURES — not a live Store or product-capability demonstration.
Real: normalization/reconciliation, PostgreSQL, dialogue policy, Valkey sessions,
recommendation orchestration, RRF and escaped source quotations.
Replaced: inter-service HTTP calls with local Python bridges.
Unavailable: Rasa model, dense embeddings/index coverage, Ollama generation.
The real regex intent fallback runs; lexical fallback is unmodified. No test vectors.
Returned Apps are retrieval candidates, not answers about capabilities, comparisons,
prices or guaranteed follow-up resolution. The fixtures assert names only; optional
metadata stays absent. Inspect effective_query/filters/explanations, including misses.
Commands: :mode chat | :mode search | :filters JSON | :records | :help | :quit
Default: chat. 'reset' runs the existing dialogue reset. Filters persist until :filters {}.
"""
EXAMPLES = [
    ("search", 'EdgeConnect OR "Semantic Treehouse"', {}),
    ("search", "EdgeConnect", {}),
    ("search", '"Semantic Treehouse"', {}),
    ("chat", "hello", {}),
    ("chat", "EdgeConnect", {}),
    ("chat", "Tell me more about the first app", {}),
    ("search", 'EdgeConnect OR "Semantic Treehouse"', {}),
    ("chat", 'EdgeConnect OR "Semantic Treehouse"', {}),
    ("chat", "Compare the first two apps", {}),
    ("chat", "Which app supports MQTT at the edge?", {}),
    ("chat", "How much does EdgeConnect cost?", {}),
    ("chat", "Only free apps instead", {}),
    ("chat", "Find apps for energy monitoring", {}),
    ("search", "EdgeConnect", {"capabilities": ["MQTT"]}),
    ("chat", "reset", {}),
    ("chat", "EdgeConnect", {}),
]


def load_service(name: str, directory: str):
    package = ModuleType(name)
    package.__path__ = [str(ROOT / "services" / directory / "app")]
    sys.modules[name] = package
    return lambda module: importlib.import_module(f"{name}.{module}")


def require_isolation() -> None:
    """Fail before connecting; launcher supplies these disposable-only endpoints."""
    expected = {
        "DATABASE_URL": ("postgresql", "database", "/hedge_phase1_test"),
        "HEDGE_TEST_QDRANT_URL": ("http", "vectors", ""),
        "VALKEY_SESSION_URL": ("redis", "sessions", "/0"),
    }
    for key, target in expected.items():
        url = urlparse(os.getenv(key, ""))
        if (url.scheme, url.hostname, url.path) != target:
            raise ValueError("Use scripts/store-v1-playground.sh with its disposable resources")


class Playground:
    def __init__(self, chat, recommender, models, records):
        self.chat = chat
        self.recommender = recommender
        self.models = models
        self.records = records
        self.session_id = None
        self.trace = None

    def recommend(self, query, *, locale, filters):
        result = self.recommender.recommend_v2(
            query=query, locale=locale, filters=filters, limit=5,
        )
        self.trace = {
            "effective_query": query, "filters": filters, "explanations": result["explanations"],
        }
        return result

    def ask(self, message: str, mode: str, filters: dict) -> dict:
        filters = self.models.SearchFilters.model_validate(filters).model_dump(mode="json")
        self.trace = None
        if mode == "chat":
            response = asyncio.run(self.chat.chat_v2(self.models.ChatRequestV2(
                session_id=self.session_id, message=message, locale="en", filters=filters,
            )))
            self.session_id = response["session_id"]
        else:
            response = self.recommend(message, locale="en", filters=filters)
        return {"mode": mode, "input": message, "result": response, "retrieval": self.trace}


@contextmanager
def offline_playground():
    require_isolation()
    from hedge_shared import models_v2, storage
    from qdrant_client import QdrantClient, models

    # A fresh disposable database is mandatory, not merely a test-looking name.
    with storage.connection() as conn:
        if conn.execute("SELECT current_database()").fetchone()["current_database"] != "hedge_phase1_test":
            raise ValueError("Not the disposable database")
        if conn.execute("SELECT to_regclass('catalog_apps') AS existing").fetchone()["existing"]:
            raise ValueError("Playground requires a fresh disposable database")
    spec = importlib.util.spec_from_file_location("manual_store_migrate", ROOT / "database/migrate.py")
    migrate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migrate)
    migrate.main()
    ingest = load_service("manual_store_ingest", "metadata-ingest")
    normalize = ingest("client").normalize_store_v1_app
    raw = json.loads((ROOT / "tests/fixtures/store-v1/manual-apps.json").read_text())
    ingested = ingest("snapshot").reconcile_catalogue_snapshot(
        "sanitized-manual-fixtures", lambda: raw, store_id=STORE,
    )
    if ingested["quarantined"]:
        raise ValueError("Manual fixtures failed normalization")
    records = [normalize(row).recommendation_projection() for row in raw]
    discovery = load_service("manual_store_discovery", "discovery-ranking")
    recommend = load_service("manual_store_expert", "expert-recommend")("recommender")
    chat = load_service("manual_store_chat", "chat-intent")("routes")
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {"RASA_ENABLED": "false"}))
        # Explicit model unavailability exercises the real lexical fallback;
        # constant test embeddings would give misleading manual rankings.
        def unavailable(*args, **kwargs):
            raise RuntimeError("Offline models unavailable; no generation or fabricated vectors")

        stack.enter_context(patch.object(discovery("embeddings"), "encode_single", unavailable))
        searcher = discovery("searcher_v2")
        client = QdrantClient(url=os.environ["HEDGE_TEST_QDRANT_URL"], timeout=3,
                              check_compatibility=False)
        stack.callback(client.close)
        collection = "hedge_store_offline_" + uuid.uuid4().hex
        client.create_collection(
            collection, vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE),
        )
        stack.callback(client.delete_collection, collection)

        def search(query, *, locale, filters, limit):
            return searcher.search_apps_v2(
                client, query=query, locale=locale,
                filters=models_v2.SearchFilters.model_validate(filters), limit=limit,
                store_id=STORE, collection_name=collection,
            )

        stack.enter_context(patch.object(recommend, "_search_apps_v2", search))
        stack.enter_context(patch.object(recommend, "OllamaClient", unavailable))
        playground = Playground(chat, recommend, models_v2, records)

        async def bridge(*, query, locale, filters):
            return playground.recommend(query, locale=locale, filters=filters)

        stack.enter_context(patch.object(chat, "_recommend_v2", bridge))
        yield playground


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", action="store_true", help="run a fixed diagnostic conversation")
    args = parser.parse_args()
    print(BANNER)
    with offline_playground() as playground:
        if args.examples:
            for mode, question, filters in EXAMPLES:
                print(json.dumps(playground.ask(question, mode, filters), ensure_ascii=False))
            return
        mode, filters = "chat", {}
        while True:
            try:
                line = input(f"{mode}> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if line == ":quit":
                break
            if not line:
                continue
            try:
                if line in {":mode chat", ":mode search"}:
                    mode = line.split()[-1]
                elif line == ":help":
                    print(BANNER)
                elif line == ":records":
                    print(json.dumps(playground.records, indent=2, ensure_ascii=False))
                elif line.startswith(":filters "):
                    value = json.loads(line[len(":filters "):])
                    filters = playground.models.SearchFilters.model_validate(value).model_dump(mode="json")
                    print(json.dumps(filters, ensure_ascii=False))
                elif line.startswith(":"):
                    print("Unknown command; use :help")
                else:
                    print(json.dumps(playground.ask(line, mode, filters), indent=2, ensure_ascii=False))
            except ValueError as error:
                print(f"Invalid input: {error}")


if __name__ == "__main__":
    main()
