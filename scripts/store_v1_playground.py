#!/usr/bin/env python3
"""Manual isolated Store pipeline harness; use store-v1-playground.sh for isolation."""

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
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
STORE = "Manual-Store-Fixture"
BANNER = """OFFLINE AUTHORED FIXTURES — not a live Store or verified product demonstration.
Real: normalization/reconciliation, PostgreSQL, Store dialogue policy, Valkey sessions,
recommendation orchestration, RRF and escaped source quotations.
Replaced: inter-service HTTP calls with local Python bridges.
Default: regex NLU and lexical fallback; no model or fake-vector simulation.
Optional real pinned E5: launcher --embeddings. Experimental real Rasa: --rasa.
Default replies: prepared source evidence. Optional --ollama: bounded reasoning for explicit deep requests.
Details/comparisons resolve current published Apps; absent metadata stays absent.
Commands: :mode chat | :mode search | :filters JSON | :records | :help | :quit
Default: chat. 'reset' clears context. Filters persist until :filters {}.
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
    def __init__(self, chat, recommender, models, records, policy):
        self.chat = chat
        self.recommender = recommender
        self.models = models
        self.records = records
        self.session_id = None
        self.trace = None
        self.policy = policy
        self.source = os.getenv("STORE_PLAYGROUND_SOURCE", "authored-fixtures")

    async def converse(self, request):
        return await self.chat.run_chat_v2(request, assistant=self.policy)

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
            response = asyncio.run(self.converse(self.models.ChatRequestV2(
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
    store_id = os.getenv("STORE_PLAYGROUND_ID", STORE)
    input_path = os.getenv("STORE_PLAYGROUND_INPUT")
    fixture = ("browser-metadata-apps.json" if os.getenv("STORE_PLAYGROUND_METADATA_DEMO") == "true"
               else "manual-apps.json")
    raw = json.loads((Path(input_path) if input_path else ROOT / "tests/fixtures/store-v1" / fixture).read_text())
    ingested = ingest("snapshot").reconcile_catalogue_snapshot(
        "isolated-evaluation", lambda: raw, store_id=store_id, snapshot_complete=False,
    )
    if ingested["quarantined"]:
        raise ValueError("Evaluation input failed normalization")
    normalized = [normalize(row, store_id=store_id) for row in raw]
    snapshot_ids = [app.id for app in normalized]
    records = [app.recommendation_projection() for app in normalized if app.public_eligible]
    discovery = load_service("manual_store_discovery", "discovery-ranking")
    recommend = load_service("manual_store_expert", "expert-recommend")("recommender")
    chat = load_service("manual_store_chat", "chat-intent")("routes")
    with ExitStack() as stack:
        # Explicit model unavailability exercises the real lexical fallback;
        # constant test embeddings would give misleading manual rankings.
        def unavailable(*args, **kwargs):
            raise RuntimeError("Offline models unavailable; no generation or fabricated vectors")

        real_embeddings = os.getenv("STORE_PLAYGROUND_E5") == "true"
        if not real_embeddings:
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
        if real_embeddings:
            rows = storage.get_catalogue_apps([r["id"] for r in records], store_id=store_id)
            discovery("indexer").apply_operations(client, [
                {"app_id": identity, "revision": row["revision"], "operation": "upsert",
                 "app": row["payload"]} for identity, row in rows.items()
            ], store_id=store_id, collection_name=collection)

        def search(query, *, locale, filters, limit):
            return searcher.search_apps_v2(
                client, query=query, locale=locale,
                filters=models_v2.SearchFilters.model_validate(filters), limit=limit,
                store_id=store_id, collection_name=collection,
            )

        stack.enter_context(patch.object(recommend, "_search_apps_v2", search))
        if os.getenv("STORE_PLAYGROUND_OLLAMA") != "true":
            stack.enter_context(patch.object(recommend, "OllamaClient", unavailable))
        from hedge_shared.store_knowledge import project
        from hedge_shared.store_v1 import StoreAppMetadata

        def resolve(identities):
            identities = snapshot_ids if identities is None else identities
            rows = storage.get_catalogue_apps(identities, store_id=store_id)
            apps = []
            for identity in identities:
                if identity in rows:
                    app = StoreAppMetadata.model_validate(rows[identity]["payload"])
                    if app.id == identity and app.store_id == store_id and app.public_eligible:
                        apps.append(project(rows[identity]))
            return apps

        async def policy_search(**kwargs):
            return playground.recommend(**kwargs)

        from scripts.store_assistant_local import local_assistant

        def semantic(text, examples):
            # Act classification needs E5 (or Rasa via RASA_URL); without it, the
            # assistant asks the user to rephrase rather than guessing.
            return discovery("embeddings").similarity([text], examples, symmetric=True)[0] if real_embeddings else None

        policy = local_assistant(lambda m: importlib.import_module(f"{chat.__package__}.{m}"),
                                 lambda m: importlib.import_module(f"{recommend.__package__}.{m}"),
                                 recommend=policy_search, resolve=resolve, semantic=semantic)
        playground = Playground(chat, recommend, models_v2, records, policy)

        # Retain counts/revisions from actual persistence and index operations,
        # not claims inferred from source fixture presence. No raw payload leaks.
        persisted = storage.get_catalogue_apps([r["id"] for r in records], store_id=store_id)
        playground.pipeline = {
            "normalization": "Store v1 normalizer and snapshot reconciliation",
            "snapshot_complete": False,
            "eligible_records": len(persisted),
            "revisions": {identity: row["revision"] for identity, row in persisted.items()},
            "vector_points": client.count(collection_name=collection, exact=True).count,
            "vector_mode": "real pinned E5" if real_embeddings else "not indexed; real lexical retrieval only",
            "service_transport": "in-process Python bridges; browser HTTP/SSE is real",
            "public_indexing": False,
        }
        if os.getenv("STORE_PLAYGROUND_METADATA_DEMO") == "true" and not input_path:
            original = deepcopy(raw)

            def simulate(action):
                # Only fixed authored source transitions are accepted. Private
                # snapshots have no mutation callback; no external Store writes.
                if action not in {"update", "withdraw", "restore"}:
                    raise ValueError("Unknown authored scenario")
                row = deepcopy(original[0])
                if action == "update":
                    row["readme"] = ("<p>Updated authored fixture: district heat measurements "
                                     "can be exported as CSV. MQTT input remains simulator-only; "
                                     "production compatibility has not been validated.</p>")
                elif action == "withdraw":
                    row["visible"] = False
                receipt = ingest("snapshot").reconcile_catalogue_snapshot(
                    "isolated-evaluation", lambda: [row], store_id=store_id, snapshot_complete=False,
                )
                app = normalize(row, store_id=store_id)
                with storage.connection() as conn:
                    revision = conn.execute(
                        "SELECT revision FROM catalog_apps WHERE id = %s AND source_store_id = %s",
                        (app.id, store_id),
                    ).fetchone()["revision"]
                if real_embeddings:
                    discovery("indexer").apply_operations(client, [{
                        "app_id": app.id, "revision": revision,
                        "operation": "upsert" if app.public_eligible else "delete",
                        "app": app.model_dump(mode="json", exclude={"id", "checksum", "public_eligible"})
                        if app.public_eligible else None,
                    }], store_id=store_id, collection_name=collection)
                playground.records = resolve(None)
                current = storage.get_catalogue_apps(snapshot_ids, store_id=store_id)
                playground.pipeline.update(
                    eligible_records=len(current),
                    revisions={identity: item["revision"] for identity, item in current.items()},
                    vector_points=client.count(collection_name=collection, exact=True).count,
                )
                return {"scenario": action, "revision": revision,
                        "ingestion": {key: receipt[key] for key in ("created", "updated", "unchanged", "quarantined")},
                        "pipeline": playground.pipeline}

            playground.simulate = simulate
        yield playground


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", action="store_true", help="run a fixed diagnostic conversation")
    args = parser.parse_args()
    banner = (BANNER if not os.getenv("STORE_PLAYGROUND_INPUT") else
              "PRIVATE STORE SNAPSHOT — incomplete, isolated, no further Store calls.\n"
              "Actual PostgreSQL/dialogue/retrieval; source grounding, optional --ollama generation.")
    print(banner)
    print("Configured models:", {"E5": os.getenv("STORE_PLAYGROUND_E5") == "true",
                                 "Rasa": os.getenv("RASA_ENABLED") == "true"})
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
                    print(banner)
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
