#!/usr/bin/env python3
"""
Evaluation script for HEDGE-ExpertAI search quality.

Computes:
  - Precision@2: fraction of top-2 results that are relevant
  - Recall@5: fraction of expected apps found in top-5
  - Mean Reciprocal Rank (MRR)
  - Median response latency

Usage:
  python evaluate.py --api-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import httpx


def load_queries(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def search(api_url: str, query: str, top_k: int = 5) -> tuple[list[str], float]:
    """Run a search query and return (app_ids, latency_seconds)."""
    start = time.monotonic()
    resp = httpx.post(
        f"{api_url}/api/v1/apps/search",
        json={"query": query, "top_k": top_k},
        timeout=60.0,
    )
    latency = time.monotonic() - start
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    app_ids = []
    for r in results:
        app = r.get("app", {})
        app_ids.append(app.get("id", ""))
    return app_ids, latency


def evaluate(api_url: str, queries: list[dict]) -> dict:
    """Run all queries and compute metrics."""
    precision_at_2_scores = []
    recall_at_5_scores = []
    mrr_scores = []
    latencies = []

    for i, q in enumerate(queries):
        query_text = q["query"]
        expected = set(q["expected_apps"])

        try:
            result_ids, latency = search(api_url, query_text)
            latencies.append(latency)

            # Precision@2
            top2 = result_ids[:2]
            if top2:
                p2 = len(set(top2) & expected) / len(top2)
            else:
                p2 = 0.0
            precision_at_2_scores.append(p2)

            # Recall@5
            top5 = set(result_ids[:5])
            if expected:
                r5 = len(top5 & expected) / len(expected)
            else:
                r5 = 1.0
            recall_at_5_scores.append(r5)

            # MRR
            rr = 0.0
            for rank, aid in enumerate(result_ids, 1):
                if aid in expected:
                    rr = 1.0 / rank
                    break
            mrr_scores.append(rr)

            status = "OK" if p2 > 0 else "MISS"
            print(f"  [{status}] Q{i+1}: '{query_text}' → P@2={p2:.2f} R@5={r5:.2f} RR={rr:.2f} ({latency:.2f}s)")

        except Exception as e:
            print(f"  [ERR] Q{i+1}: '{query_text}' → {e}")

    metrics = {
        "total_queries": len(queries),
        "evaluated": len(precision_at_2_scores),
        "precision_at_2": statistics.mean(precision_at_2_scores) if precision_at_2_scores else 0,
        "recall_at_5": statistics.mean(recall_at_5_scores) if recall_at_5_scores else 0,
        "mrr": statistics.mean(mrr_scores) if mrr_scores else 0,
        "median_latency_s": statistics.median(latencies) if latencies else 0,
        "p95_latency_s": sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0,
    }
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Evaluate HEDGE-ExpertAI search quality")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Gateway API URL")
    parser.add_argument("--queries", default=str(Path(__file__).parent / "test_queries.json"), help="Path to test queries JSON")
    args = parser.parse_args()

    print(f"\nHEDGE-ExpertAI Evaluation")
    print(f"API: {args.api_url}")
    print(f"Queries: {args.queries}\n")

    queries = load_queries(args.queries)
    print(f"Running {len(queries)} queries...\n")

    metrics = evaluate(args.api_url, queries)

    print(f"\n{'='*50}")
    print(f"RESULTS")
    print(f"{'='*50}")
    print(f"  Queries evaluated: {metrics['evaluated']}/{metrics['total_queries']}")
    print(f"  Precision@2:      {metrics['precision_at_2']:.1%}  (target: ≥70%)")
    print(f"  Recall@5:         {metrics['recall_at_5']:.1%}")
    print(f"  MRR:              {metrics['mrr']:.3f}")
    print(f"  Median latency:   {metrics['median_latency_s']:.2f}s  (target: <5s)")
    print(f"  P95 latency:      {metrics['p95_latency_s']:.2f}s")

    # Pass/fail
    passed = metrics["precision_at_2"] >= 0.70 and metrics["median_latency_s"] < 5.0
    print(f"\n  Overall: {'PASS ✓' if passed else 'FAIL ✗'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
