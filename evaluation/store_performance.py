"""Loopback HTTP latency probe over a private snapshot or authored fixtures.

Run inside the disposable playground launcher with --benchmark. No source text,
model prose, native identifiers or tokens are retained in the JSONL output.
Inter-service calls use the existing local bridges; this is not native UI or
multi-process gateway latency acceptance. Cold preparation is measured separately.
"""

import argparse
import hashlib
import inspect
import json
import math
import os
import statistics
import threading
import time
from pathlib import Path

import httpx
import uvicorn

from scripts.store_v1_browser import create_app
from scripts.store_v1_playground import load_service, offline_playground

cases = [
    ("browse-en", "Show me all available applications", "en", {}),
    ("detail-en", "Tell me more about the second app", "en", {}),
    ("compare-en", "Compare EdgeConnect and Semantic Treehouse", "en", {}),
    ("discovery-en", "Find apps for shared data models", "en", {}),
    ("discovery-tr", "Paylaşılan veri modelleri için uygulama bul", "tr", {}),
    ("strict", "Find apps for earthquake warnings via SMS in production", "en", {}),
    ("no-match", "Find apps for satellite crop disease prediction", "en", {}),
    ("price", "How much does EdgeConnect cost?", "en", {}),
    ("browse-tr", "Tüm uygulamaları göster", "tr", {}),
    ("detail-tr", "İkinci uygulamayı açıkla", "tr", {}),
    ("compare-tr", "İkisini karşılaştır", "tr", {}),
    ("publisher", "Show me all available applications", "en", {"publisher": "TNO"}),
]


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def report(rows):
    values = sorted(r["seconds"] for r in rows)
    return {
        "samples": len(values),
        "median": statistics.median(values),
        "p95": values[max(0, math.ceil(len(values) * 0.95) - 1)],
        "mean": statistics.mean(values),
        "max": max(values),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument(
        "--legacy", action="store_true", help="Opt into the prior model path for comparison"
    )
    parser.add_argument(
        "--managed-snapshot",
        action="store_true",
        help="Exercise the existing workspace adapter with saved bootstrap files and no token",
    )
    args = parser.parse_args()
    if args.managed_snapshot and args.legacy:
        parser.error("Use the disposable snapshot mode for the legacy comparison")
    if not 1 <= args.rounds <= 100:
        parser.error("--rounds must be between 1 and 100")
    started = time.perf_counter()
    if args.managed_snapshot:
        from hedge_shared import storage
        if os.getenv('HEDGE_PERFORMANCE_DISPOSABLE') != 'true':
            parser.error('Managed measurements require explicit disposable infrastructure')
        with storage.connection() as conn:
            if conn.execute("SELECT to_regclass('catalog_apps') AS existing").fetchone()['existing']:
                parser.error('Managed measurements require a fresh empty disposable database')
        from scripts.store_v1_workspace import workspace

        context = workspace
    else:
        context = offline_playground
    with context() as pg:
        if not args.managed_snapshot:
            module = load_service("bench_policy", "chat-intent")("store_conversation")
            expert = load_service("bench_expert", "expert-recommend")("store_conversation")

            async def search(**kwargs):
                return pg.recommend(**kwargs)

            options = {}
            if 'routine' in inspect.signature(module.StoreConversation).parameters:
                options['routine'] = not args.legacy
            if not args.legacy:
                options['decide'] = pg.recommender._recommendation_decision
                if 'present' in inspect.signature(module.StoreConversation).parameters:
                    options['present'] = expert.prepared_answer
            pg.policy = module.StoreConversation(
                search,
                pg.policy.resolve,
                pg.recommender._recommendation_narrative,
                expert.plan,
                expert.respond,
                **options,
            )
            pg.catalogue = pg.policy.resolve
        # Bind an actual loopback HTTP server, including sessions, NLU, impressions and serialization.
        app = create_app(pg)
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=8199, log_level="error", access_log=False)
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started:
            if not thread.is_alive() or time.monotonic() >= deadline:
                raise RuntimeError("Benchmark HTTP server did not start")
            time.sleep(0.05)
        print(
            json.dumps(
                {
                    "preparation_seconds": round(time.perf_counter() - started, 6),
                    "eligible_records": len(
                        pg.catalogue(None) if hasattr(pg, "catalogue") else pg.records
                    ),
                    "vectors": getattr(pg, "pipeline", {}).get("vector_points"),
                    "managed_snapshot": args.managed_snapshot,
                    "legacy": args.legacy,
                    "rounds": args.rounds,
                }
            ),
            flush=True,
        )
        outputs = []
        with httpx.Client(
            base_url="http://127.0.0.1:8199", timeout=1200, trust_env=False
        ) as client:
            count = args.rounds
            for repeat in range(count):
                session = None
                for name, question, locale, filters in cases:
                    start = time.perf_counter()
                    resp = client.post(
                        "/api/v2/chat",
                        json={
                            "session_id": session,
                            "message": question,
                            "locale": locale,
                            "filters": filters,
                        },
                    )
                    elapsed = time.perf_counter() - start
                    data = resp.json()
                    session = data.get("session_id")
                    selected = [r["app"] for r in data.get("apps", [])]
                    row = {
                        "case": name,
                        "repeat": repeat,
                        "seconds": round(elapsed, 6),
                        "status": resp.status_code,
                        "apps": [digest([a["store_id"], a["app_id"]]) for a in selected],
                        "facts": [digest(a) for a in selected],
                        "intent": data.get("intent"),
                        "nlu": data.get("nlu"),
                        "decision": data.get("decision"),
                        "generation": {
                            k: v
                            for k, v in (data.get("generation") or {}).items()
                            if k
                            in {
                                "source",
                                "reason",
                                "seconds",
                                "model_completed",
                                "stage",
                                "repair_count",
                            }
                        },
                        "message_digest": digest(data.get("message", "")),
                        "message_chars": len(data.get("message", "")),
                    }
                    outputs.append(row)
                    print(json.dumps(row), flush=True)
        print(
            json.dumps(
                {
                    "summary": report(outputs),
                    "resources": {
                        name: Path("/sys/fs/cgroup", name).read_text().strip()
                        for name in ("cpu.max", "memory.max", "memory.peak")
                        if Path("/sys/fs/cgroup", name).exists()
                    },
                }
            ),
            flush=True,
        )
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
