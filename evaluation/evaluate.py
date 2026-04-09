#!/usr/bin/env python3
"""
Evaluation script for HEDGE-ExpertAI.

Modes:
  - search (default): evaluate /api/v1/apps/search only
  - chat:             evaluate /api/v1/chat end-to-end (includes LLM)
  - stream:           evaluate /api/v1/chat/stream SSE (measures TTFT)
  - all:              run all three modes sequentially

Computes:
  - Precision@2, Recall@5, MRR, latency          (search)
  - Precision@2, latency, explanation accuracy    (chat)
  - TTFT, Time-to-First-App, total duration       (stream)
  - App exposure rate                              (chat)
  - Feedback acceptance rate                       (feedback endpoint)

Usage:
  python evaluate.py --api-url http://localhost:8000
  python evaluate.py --api-url http://localhost:8000 --mode all
  python evaluate.py --api-url http://localhost:8000 --mode chat --max-queries 10
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import httpx


FALLBACK_TEMPLATE_MARKERS = [
    "Based on your query, here are the ranked matches",
    "here are the ranked matches from the HEDGE-IoT catalog",
]


def load_queries(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Search evaluation
# ---------------------------------------------------------------------------


def search(api_url: str, query: str, top_k: int = 5, saref_class: str | None = None) -> tuple[list[str], float]:
    """Run a search query and return (app_ids, latency_seconds)."""
    start = time.monotonic()
    body: dict = {"query": query, "top_k": top_k}
    if saref_class:
        body["saref_class"] = saref_class
    resp = httpx.post(
        f"{api_url}/api/v1/apps/search",
        json=body,
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
    """Run all queries via /api/v1/apps/search and compute metrics."""
    precision_at_2_scores = []
    recall_at_5_scores = []
    mrr_scores = []
    latencies = []

    for i, q in enumerate(queries):
        query_text = q["query"]
        expected = set(q["expected_apps"])
        saref_class = q.get("saref_class")

        try:
            result_ids, latency = search(api_url, query_text, saref_class=saref_class)
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


# ---------------------------------------------------------------------------
# Chat evaluation (end-to-end with LLM)
# ---------------------------------------------------------------------------


def _extract_app_ids_from_chat(apps: list) -> list[str]:
    """Extract app IDs from chat response apps array."""
    ids = []
    for item in apps:
        if isinstance(item, dict):
            app = item.get("app", item)
            aid = app.get("id", "")
            if aid:
                ids.append(aid)
    return ids


def _check_explanation_quality(message: str, expected_app_ids: set[str]) -> dict:
    """Check whether a chat explanation meets quality criteria."""
    is_fallback = any(marker in message for marker in FALLBACK_TEMPLATE_MARKERS)
    is_long_enough = len(message) >= 50
    return {
        "is_fallback": is_fallback,
        "is_long_enough": is_long_enough,
        "quality_pass": not is_fallback and is_long_enough,
    }


def chat_evaluate(api_url: str, queries: list[dict], max_queries: int | None = None) -> dict:
    """Evaluate via POST /api/v1/chat. Measures end-to-end latency and quality."""
    subset = queries[:max_queries] if max_queries else queries
    precision_at_2_scores = []
    latencies = []
    quality_passes = 0
    all_returned_app_ids: set[str] = set()

    print(f"\n  Chat evaluation ({len(subset)} queries)...\n")

    for i, q in enumerate(subset):
        query_text = q["query"]
        expected = set(q["expected_apps"])

        try:
            start = time.monotonic()
            resp = httpx.post(
                f"{api_url}/api/v1/chat",
                json={"message": query_text},
                timeout=300.0,
            )
            latency = time.monotonic() - start
            resp.raise_for_status()
            data = resp.json()

            result_ids = _extract_app_ids_from_chat(data.get("apps", []))
            all_returned_app_ids.update(result_ids)
            latencies.append(latency)

            # Precision@2
            top2 = result_ids[:2]
            p2 = len(set(top2) & expected) / len(top2) if top2 else 0.0
            precision_at_2_scores.append(p2)

            # Explanation quality
            quality = _check_explanation_quality(data.get("message", ""), expected)
            if quality["quality_pass"]:
                quality_passes += 1

            fb = " [FALLBACK]" if quality["is_fallback"] else ""
            status = "OK" if p2 > 0 else "MISS"
            print(f"  [{status}] Q{i+1}: '{query_text}' → P@2={p2:.2f} ({latency:.1f}s){fb}")

        except Exception as e:
            print(f"  [ERR] Q{i+1}: '{query_text}' → {e}")

    evaluated = len(precision_at_2_scores)
    metrics = {
        "mode": "chat",
        "total_queries": len(subset),
        "evaluated": evaluated,
        "precision_at_2": statistics.mean(precision_at_2_scores) if precision_at_2_scores else 0,
        "median_latency_s": statistics.median(latencies) if latencies else 0,
        "p95_latency_s": sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0,
        "explanation_accuracy": quality_passes / evaluated if evaluated else 0,
        "unique_apps_returned": len(all_returned_app_ids),
    }
    return metrics


# ---------------------------------------------------------------------------
# Stream evaluation (SSE, measures TTFT)
# ---------------------------------------------------------------------------


def stream_evaluate(api_url: str, queries: list[dict], max_queries: int | None = None) -> dict:
    """Evaluate via POST /api/v1/chat/stream. Measures TTFT and Time-to-First-App."""
    subset = queries[:max_queries] if max_queries else queries
    ttft_list: list[float] = []
    ttfa_list: list[float] = []
    total_durations: list[float] = []

    print(f"\n  Stream evaluation ({len(subset)} queries)...\n")

    for i, q in enumerate(subset):
        query_text = q["query"]
        try:
            start = time.monotonic()
            first_token_at: float | None = None
            first_app_at: float | None = None

            with httpx.stream(
                "POST",
                f"{api_url}/api/v1/chat/stream",
                json={"message": query_text},
                timeout=300.0,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    now = time.monotonic()
                    try:
                        evt = json.loads(line[6:])
                    except (ValueError, KeyError):
                        continue
                    if evt.get("type") == "token" and first_token_at is None:
                        first_token_at = now
                    if evt.get("type") == "apps" and first_app_at is None:
                        first_app_at = now
                    if evt.get("type") == "done":
                        break

            total = time.monotonic() - start
            total_durations.append(total)
            ttft = (first_token_at - start) if first_token_at else total
            ttft_list.append(ttft)
            if first_app_at:
                ttfa_list.append(first_app_at - start)

            print(f"  [OK] Q{i+1}: TTFT={ttft:.2f}s total={total:.1f}s")
        except Exception as e:
            print(f"  [ERR] Q{i+1}: '{query_text}' → {e}")

    metrics = {
        "mode": "stream",
        "evaluated": len(ttft_list),
        "median_ttft_s": statistics.median(ttft_list) if ttft_list else 0,
        "p95_ttft_s": sorted(ttft_list)[int(len(ttft_list) * 0.95)] if ttft_list else 0,
        "median_ttfa_s": statistics.median(ttfa_list) if ttfa_list else 0,
        "median_total_s": statistics.median(total_durations) if total_durations else 0,
    }
    return metrics


# ---------------------------------------------------------------------------
# Feedback stats
# ---------------------------------------------------------------------------


def fetch_feedback_stats(api_url: str) -> dict | None:
    """Fetch feedback KPI stats from the gateway."""
    try:
        resp = httpx.get(f"{api_url}/api/v1/feedback/stats", timeout=10.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _print_search_results(metrics: dict) -> None:
    print(f"\n{'='*55}")
    print("  SEARCH RESULTS  (/api/v1/apps/search)")
    print(f"{'='*55}")
    print(f"  Queries evaluated: {metrics['evaluated']}/{metrics['total_queries']}")
    print(f"  Precision@2:      {metrics['precision_at_2']:.1%}  (target: ≥70%)")
    print(f"  Recall@5:         {metrics['recall_at_5']:.1%}")
    print(f"  MRR:              {metrics['mrr']:.3f}")
    print(f"  Median latency:   {metrics['median_latency_s']:.2f}s  (target: <5s)")
    print(f"  P95 latency:      {metrics['p95_latency_s']:.2f}s")
    passed = metrics["precision_at_2"] >= 0.70 and metrics["median_latency_s"] < 5.0
    print(f"\n  Search: {'PASS ✓' if passed else 'FAIL ✗'}")


def _print_chat_results(metrics: dict, total_apps: int = 50) -> None:
    exposure = metrics["unique_apps_returned"] / total_apps if total_apps else 0
    print(f"\n{'='*55}")
    print("  CHAT RESULTS  (/api/v1/chat)")
    print(f"{'='*55}")
    print(f"  Queries evaluated:    {metrics['evaluated']}/{metrics['total_queries']}")
    print(f"  Precision@2:          {metrics['precision_at_2']:.1%}  (target: ≥70%)")
    print(f"  Median latency:       {metrics['median_latency_s']:.1f}s")
    print(f"  P95 latency:          {metrics['p95_latency_s']:.1f}s")
    print(f"  Explanation accuracy:  {metrics['explanation_accuracy']:.1%}  (target: ≥80%)")
    print(f"  App exposure rate:     {exposure:.1%}  ({metrics['unique_apps_returned']}/{total_apps} apps)  (target: ≥60%)")


def _print_stream_results(metrics: dict) -> None:
    print(f"\n{'='*55}")
    print("  STREAM RESULTS  (/api/v1/chat/stream)")
    print(f"{'='*55}")
    print(f"  Queries evaluated: {metrics['evaluated']}")
    print(f"  Median TTFT:       {metrics['median_ttft_s']:.2f}s")
    print(f"  P95 TTFT:          {metrics['p95_ttft_s']:.2f}s")
    print(f"  Median TTFA:       {metrics['median_ttfa_s']:.2f}s")
    print(f"  Median total:      {metrics['median_total_s']:.1f}s")


def main():
    parser = argparse.ArgumentParser(description="Evaluate HEDGE-ExpertAI")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Gateway API URL")
    parser.add_argument("--queries", default=str(Path(__file__).parent / "test_queries.json"), help="Path to test queries JSON")
    parser.add_argument("--mode", choices=["search", "chat", "stream", "all"], default="search", help="Evaluation mode")
    parser.add_argument("--max-queries", type=int, default=None, help="Limit number of queries (for chat/stream)")
    parser.add_argument("--total-apps", type=int, default=50, help="Total apps in catalog (for exposure rate)")
    parser.add_argument("--report-feedback", action="store_true", help="Also report feedback acceptance stats")
    args = parser.parse_args()

    print(f"\nHEDGE-ExpertAI Evaluation")
    print(f"API: {args.api_url}")
    print(f"Mode: {args.mode}")
    print(f"Queries: {args.queries}\n")

    queries = load_queries(args.queries)

    modes = [args.mode] if args.mode != "all" else ["search", "chat", "stream"]
    search_passed = True

    for mode in modes:
        if mode == "search":
            print(f"Running {len(queries)} search queries...\n")
            metrics = evaluate(args.api_url, queries)
            _print_search_results(metrics)
            search_passed = metrics["precision_at_2"] >= 0.70 and metrics["median_latency_s"] < 5.0

        elif mode == "chat":
            n = args.max_queries or len(queries)
            print(f"Running {n} chat queries (this will be slow — LLM inference)...")
            metrics = chat_evaluate(args.api_url, queries, max_queries=args.max_queries)
            _print_chat_results(metrics, total_apps=args.total_apps)

        elif mode == "stream":
            n = args.max_queries or len(queries)
            print(f"Running {n} stream queries...")
            metrics = stream_evaluate(args.api_url, queries, max_queries=args.max_queries)
            _print_stream_results(metrics)

    if args.report_feedback:
        print(f"\n{'='*55}")
        print("  FEEDBACK STATS")
        print(f"{'='*55}")
        fb = fetch_feedback_stats(args.api_url)
        if fb:
            rate = fb.get("acceptance_rate")
            print(f"  Acceptance rate: {rate:.1%}" if rate is not None else "  Acceptance rate: N/A (no feedback data)")
            print(f"  Total clicks:    {fb.get('total_click', 0)}")
            print(f"  Total accepts:   {fb.get('total_accept', 0)}")
            print(f"  Total dismisses: {fb.get('total_dismiss', 0)}")
        else:
            print("  Could not fetch feedback stats.")

    print(f"\n{'='*55}")
    if args.mode in ("search", "all"):
        print(f"  Overall search: {'PASS ✓' if search_passed else 'FAIL ✗'}")

    return 0 if search_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
