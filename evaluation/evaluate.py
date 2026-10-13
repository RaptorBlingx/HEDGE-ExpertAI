#!/usr/bin/env python3
"""
Evaluation script for HEDGE-ExpertAI.

Modes:
  - search (default): evaluate /api/v2/apps/search only
  - chat:             evaluate /api/v2/chat end-to-end (includes LLM)
  - stream:           evaluate /api/v2/chat/stream SSE (measures TTFA/TTFT)
  - all:              run all three modes sequentially

Computes:
  - Precision@2, Recall@5, MRR, NDCG@5, MAP, latency   (search)
  - HitRate@2, Precision@2, latency; accuracy unassessed  (chat)
  - TTFT, Time-to-First-App, total duration              (stream)
  - Returned-App coverage (not qualified visits)          (search & chat)
  - Per-SAREF-category breakdown                         (search)
  - Confidence intervals (95% bootstrap)                 (search)
  - Feedback acceptance rate                             (feedback endpoint)

Usage:
  python evaluate.py --api-url http://localhost:8000
  python evaluate.py --api-url http://localhost:8000 --mode all
  python evaluate.py --api-url http://localhost:8000 --mode chat --max-queries 10
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import time
from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path

import httpx

FALLBACK_TEMPLATE_MARKERS = [
    "Based on your query, here are the ranked matches",
    "here are the ranked matches from the HEDGE-IoT catalog",
]


def load_queries(path: str) -> list[dict]:
    with open(path) as f:
        queries = json.load(f)
    _validate_queries(queries)
    return queries


def _validate_queries(queries: list[dict]) -> None:
    if not isinstance(queries, list) or not queries:
        raise ValueError("A nonempty labelled query list is required")
    for query in queries:
        if not isinstance(query, dict) or not isinstance(query.get("query"), str) or not query["query"].strip():
            raise ValueError("Each query requires nonempty query text")
        _validate_app_ids(query.get("expected_apps"))


def _validate_app_ids(ids: list[str]) -> list[str]:
    if not isinstance(ids, list) or any(not isinstance(aid, str) or not aid.strip() for aid in ids):
        raise ValueError("App identities must be a list of nonempty strings")
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate App identities are invalid")
    return ids


def _extract_app_ids_from_chat(apps: list) -> list[str]:
    """Check actual App identities, never infer identity from titles or prose."""
    if not isinstance(apps, list):
        raise ValueError("Expected an App result list")
    ids = []
    for item in apps:
        if not isinstance(item, dict):
            raise ValueError("Invalid App result")
        app = item.get("app", item)
        if not isinstance(app, dict):
            raise ValueError("Invalid App metadata")
        ids.append(app.get("id"))
    return _validate_app_ids(ids)


def _latency_summary(latencies: list[float]) -> dict:
    """Observed durations include failures; missing measurements are not zero."""
    return {
        "latency_samples": len(latencies),
        "mean_latency_s": statistics.mean(latencies) if latencies else None,
        "median_latency_s": statistics.median(latencies) if latencies else None,
        "p95_latency_s": sorted(latencies)[math.ceil(len(latencies) * 0.95) - 1] if latencies else None,
    }


def _retrieval_summary(rows: list[dict], mode: str) -> dict:
    """Every attempt contributes: failed attempts score zero for all IR metrics."""
    scores = defaultdict(list)
    categories = defaultdict(list)
    all_ids = set()
    for row in rows:
        expected = set(row["expected_app_ids"])
        ids = row["returned_app_ids"] if row["status"] == "success" else []
        all_ids.update(ids)
        top2 = ids[:2]
        success = row["status"] == "success"
        per_query = {
            "precision_at_2": len(set(top2) & expected) / len(top2) if top2 else 0.0,
            "hit_rate_at_2": float(bool(set(top2) & expected)),
            "recall_at_5": len(set(ids[:5]) & expected) / len(expected) if expected else float(success and not ids),
            "mrr": next((1.0 / rank for rank, aid in enumerate(ids, 1) if aid in expected), 0.0),
            "ndcg_at_5": _ndcg_at_k(ids, expected, k=5),
            "map": _average_precision(ids, expected),
        }
        row["retrieval_scores"] = per_query
        for name, value in per_query.items():
            scores[name].append(value)
        if row.get("category"):
            categories[row["category"]].append(per_query["precision_at_2"])
    succeeded = sum(row["status"] == "success" for row in rows)
    return {
        "mode": mode,
        "latency_boundary": (
            "Immediately before request to terminal complete or failure"
            if mode == "stream"
            else "Immediately before request to fully read/validated JSON response or failure"
        ),
        "total_queries": len(rows),
        "evaluated": succeeded,
        "failed": len(rows) - succeeded,
        **{name: statistics.mean(values) for name, values in scores.items()},
        **_latency_summary([row["latency_s"] for row in rows]),
        "unique_apps_returned": len(all_ids),
        "precision_at_2_ci": _bootstrap_ci(scores["precision_at_2"]),
        "mrr_ci": _bootstrap_ci(scores["mrr"]),
        "per_saref": {
            category: {"count": len(values), "precision_at_2": statistics.mean(values)}
            for category, values in sorted(categories.items())
        },
        "per_query": rows,
    }


def _query_row(query: dict, index: int) -> dict:
    return {
        "query_id": query.get("query_id", str(index + 1)),
        "category": query.get("category"),
        "expected_app_ids": query["expected_apps"],
        "returned_app_ids": [],
        "status": "failed",
    }


def _explanation_diagnostics(message: str) -> dict:
    """Formatting/fallback signals cannot establish factual accuracy."""
    if not isinstance(message, str):
        raise ValueError("Invalid explanation text")
    return {
        "is_fallback": any(marker in message for marker in FALLBACK_TEMPLATE_MARKERS),
        "is_long_enough": len(message) >= 50,
    }


def _unassessed_accuracy() -> dict:
    return {
        "explanation_accuracy": None,
        "explanation_accuracy_status": "unassessed",
        "explanation_accuracy_reason": "Requires human claim-to-evidence reviews of these actual responses",
    }


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------


def _dcg(relevances: list[float], k: int) -> float:
    """Discounted Cumulative Gain at rank k."""
    score = 0.0
    for i, rel in enumerate(relevances[:k]):
        score += rel / math.log2(i + 2)  # i+2 because rank is 1-indexed
    return score


def _ndcg_at_k(result_ids: list[str], expected: set[str], k: int = 5) -> float:
    """Normalized Discounted Cumulative Gain at k (binary relevance)."""
    relevances = [1.0 if rid in expected else 0.0 for rid in result_ids[:k]]
    dcg = _dcg(relevances, k)
    # Ideal: all relevant docs first
    ideal_relevances = sorted(relevances, reverse=True)
    # In case there are more relevant docs than returned
    n_relevant = min(len(expected), k)
    ideal_relevances = [1.0] * n_relevant + [0.0] * (k - n_relevant)
    idcg = _dcg(ideal_relevances, k)
    return dcg / idcg if idcg > 0 else 0.0


def _average_precision(result_ids: list[str], expected: set[str]) -> float:
    """Average Precision for a single query."""
    if not expected:
        return 0.0
    hits = 0
    sum_prec = 0.0
    for i, rid in enumerate(result_ids):
        if rid in expected:
            hits += 1
            sum_prec += hits / (i + 1)
    return sum_prec / len(expected)


def _bootstrap_ci(values: list[float], n_bootstrap: int = 2000, alpha: float = 0.05) -> tuple[float, float]:
    """Bootstrap 95% confidence interval for the mean."""
    if len(values) < 2:
        m = values[0] if values else 0.0
        return (m, m)
    rng = random.Random(42)
    n = len(values)
    means = []
    for _ in range(n_bootstrap):
        sample = [rng.choice(values) for _ in range(n)]
        means.append(statistics.mean(sample))
    means.sort()
    lo = means[int(n_bootstrap * alpha / 2)]
    hi = means[int(n_bootstrap * (1 - alpha / 2))]
    return (lo, hi)


# ---------------------------------------------------------------------------
# Search evaluation
# ---------------------------------------------------------------------------


def search(
    api_url: str,
    query: str,
    *,
    locale: str = "en",
    filters: dict | None = None,
    top_k: int = 5,
) -> list[str]:
    """Read and validate the full search response."""
    body = {"query": query, "locale": locale, "filters": filters or {}, "limit": top_k}
    resp = httpx.post(f"{api_url}/api/v2/apps/search", json=body, timeout=60.0)
    resp.raise_for_status()
    data = resp.json()
    return _extract_app_ids_from_chat(data["results"])


def evaluate(api_url: str, queries: list[dict]) -> dict:
    """Evaluate /api/v2/apps/search with all attempted queries in denominators."""
    _validate_queries(queries)
    rows = []
    for i, query in enumerate(queries):
        row = _query_row(query, i)
        start = time.monotonic()
        try:
            row["returned_app_ids"] = search(
                api_url, query["query"], locale=query.get("locale", "en"), filters=query.get("filters"),
            )
            row["status"] = "success"
        except Exception as exc:
            row["error"] = type(exc).__name__
        row["latency_s"] = time.monotonic() - start
        rows.append(row)
        print(f"  [{row['status'].upper()}] Q{i+1}: {row['latency_s']:.2f}s")
    return _retrieval_summary(rows, "search")


def chat_evaluate(api_url: str, queries: list[dict], max_queries: int | None = None) -> dict:
    """Measure complete v2 chat responses; contextual accuracy needs human review."""
    subset = queries[:max_queries] if max_queries is not None else queries
    _validate_queries(subset)
    rows = []
    for i, query in enumerate(subset):
        row = _query_row(query, i)
        start = time.monotonic()
        try:
            resp = httpx.post(
                f"{api_url}/api/v2/chat",
                json={"message": query["query"], "locale": query.get("locale", "en"), "filters": query.get("filters", {})},
                timeout=300.0,
            )
            resp.raise_for_status()
            data = resp.json()
            row["returned_app_ids"] = _extract_app_ids_from_chat(data["apps"])
            row["explanation_diagnostics"] = _explanation_diagnostics(data["message"])
            row["status"] = "success"
        except Exception as exc:
            row["error"] = type(exc).__name__
        row["latency_s"] = time.monotonic() - start
        rows.append(row)
        print(f"  [{row['status'].upper()}] Q{i+1}: {row['latency_s']:.2f}s")
    return {**_retrieval_summary(rows, "chat"), **_unassessed_accuracy()}


def _sse_events(lines: Iterable[str]) -> Iterator[dict]:
    """Parse SSE data frames, including multiline JSON and comment heartbeats."""
    data = []
    for line in lines:
        if line == "":
            if data:
                event = json.loads("\n".join(data))
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    raise ValueError("Invalid SSE event")
                yield event
                data = []
        elif line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
    if data:
        raise ValueError("Unterminated SSE event")


def stream_evaluate(api_url: str, queries: list[dict], max_queries: int | None = None) -> dict:
    """Require terminal complete; timing of partial output never proves success."""
    subset = queries[:max_queries] if max_queries is not None else queries
    _validate_queries(subset)
    rows = []
    for i, query in enumerate(subset):
        row = {**_query_row(query, i), "ttft_s": None, "ttfa_s": None}
        start = time.monotonic()
        text = ""
        completed = False
        try:
            with httpx.stream(
                "POST", f"{api_url}/api/v2/chat/stream",
                json={"message": query["query"], "locale": query.get("locale", "en"), "filters": query.get("filters", {})},
                timeout=300.0,
            ) as resp:
                resp.raise_for_status()
                for event in _sse_events(resp.iter_lines()):
                    elapsed = time.monotonic() - start
                    kind = event["type"]
                    if kind == "problem":
                        row["error"] = "stream_problem"
                        raise ValueError("SSE problem")
                    if kind == "recommendations":
                        row["returned_app_ids"] = _extract_app_ids_from_chat(event["apps"])
                        if row["returned_app_ids"] and row["ttfa_s"] is None:
                            row["ttfa_s"] = elapsed
                    elif kind == "explanation_delta":
                        content = event["content"]
                        if not isinstance(content, str):
                            raise ValueError("Invalid explanation delta")
                        text += content
                        if content.strip() and row["ttft_s"] is None:
                            row["ttft_s"] = elapsed
                    elif kind == "complete":
                        completed = True
                        break
            if not completed:
                row["error"] = "missing_complete"
                raise ValueError("Stream ended without complete")
            row["explanation_diagnostics"] = _explanation_diagnostics(text)
            row["status"] = "success"
        except Exception as exc:
            row.setdefault("error", type(exc).__name__)
        row["latency_s"] = time.monotonic() - start
        rows.append(row)
        print(f"  [{row['status'].upper()}] Q{i+1}: {row['latency_s']:.2f}s")

    successful = [row for row in rows if row["status"] == "success"]
    ttft = [row["ttft_s"] for row in successful if row["ttft_s"] is not None]
    ttfa = [row["ttfa_s"] for row in successful if row["ttfa_s"] is not None]
    return {
        **_retrieval_summary(rows, "stream"), **_unassessed_accuracy(),
        "ttft_samples": len(ttft),
        "ttfa_samples": len(ttfa),
        "median_ttft_s": statistics.median(ttft) if ttft else None,
        "p95_ttft_s": sorted(ttft)[math.ceil(len(ttft) * 0.95) - 1] if ttft else None,
        "median_ttfa_s": statistics.median(ttfa) if ttfa else None,
        "median_total_s": statistics.median([row["latency_s"] for row in successful]) if successful else None,
    }


# ---------------------------------------------------------------------------
# Feedback stats
# ---------------------------------------------------------------------------


def fetch_feedback_stats(api_url: str) -> dict | None:
    """Fetch feedback KPI stats from the gateway."""
    try:
        resp = httpx.get(f"{api_url}/api/v2/analytics/recommendations", timeout=10.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _seconds(value: float | None) -> str:
    return "UNASSESSED" if value is None else f"{value:.2f}s"


def _print_request_results(metrics: dict) -> None:
    print(f"  Requests: {metrics['total_queries']} attempted, {metrics['evaluated']} successful, {metrics['failed']} failed")
    print(f"  HitRate@2:    {metrics['hit_rate_at_2']:.1%} (all attempts; exploratory threshold ≥70%)")
    print(f"  Precision@2:  {metrics['precision_at_2']:.1%}")
    print(f"  Mean duration:   {_seconds(metrics['mean_latency_s'])} (all attempts, including failures)")
    print(f"  Median duration: {_seconds(metrics['median_latency_s'])}")
    print(f"  P95 duration:    {_seconds(metrics['p95_latency_s'])}")
    print("  Proposal timing acceptance: UNASSESSED (boundary/environment protocol requires agreement)")


def _print_search_results(metrics: dict, total_apps: int = 75) -> None:
    print("\n  SEARCH RESULTS (/api/v2/apps/search)")
    _print_request_results(metrics)
    for key in ("recall_at_5", "mrr", "ndcg_at_5", "map"):
        print(f"  {key}: {metrics[key]:.3f}")
    for key in ("precision_at_2", "mrr"):
        lower, upper = metrics[f"{key}_ci"]
        print(f"  {key} 95% bootstrap CI: [{lower:.3f}, {upper:.3f}]")
    print(f"  Returned-App coverage: {metrics['unique_apps_returned']}/{total_apps} (diagnostic; not qualified visits)")
    for category, values in metrics["per_saref"].items():
        print(f"  {category}: {values['count']} attempts, P@2={values['precision_at_2']:.1%}")


def _print_chat_results(metrics: dict, total_apps: int = 75) -> None:
    print("\n  CHAT RESULTS (/api/v2/chat)")
    _print_request_results(metrics)
    print("  Explanation accuracy: UNASSESSED (human claim-to-evidence review required)")
    print(f"  Returned-App coverage: {metrics['unique_apps_returned']}/{total_apps} (diagnostic; not qualified visits)")


def _print_stream_results(metrics: dict) -> None:
    print("\n  STREAM RESULTS (/api/v2/chat/stream)")
    _print_request_results(metrics)
    print(f"  Median first explanation text: {_seconds(metrics['median_ttft_s'])} ({metrics['ttft_samples']} successful-stream samples)")
    print(f"  P95 first explanation text: {_seconds(metrics['p95_ttft_s'])}")
    print(f"  Median first App: {_seconds(metrics['median_ttfa_s'])} ({metrics['ttfa_samples']} successful-stream samples)")
    print("  Explanation accuracy: UNASSESSED (human claim-to-evidence review required)")


def main():
    parser = argparse.ArgumentParser(description="Evaluate HEDGE-ExpertAI")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Gateway API URL")
    parser.add_argument("--queries", default=str(Path(__file__).parent / "test_queries.json"), help="Path to test queries JSON")
    parser.add_argument("--mode", choices=["search", "chat", "stream", "all"], default="search", help="Evaluation mode")
    parser.add_argument("--max-queries", type=int, default=None, help="Limit number of queries (for chat/stream)")
    parser.add_argument("--total-apps", type=int, default=120, help="Total apps in catalog (returned-App coverage diagnostic)")
    parser.add_argument("--output-json", help="Write diagnostic metrics and per-attempt accounting to this file")
    parser.add_argument("--report-feedback", action="store_true", help="Also report feedback acceptance stats")
    args = parser.parse_args()
    if args.max_queries is not None and args.max_queries <= 0:
        parser.error("--max-queries must be positive")
    if args.total_apps <= 0:
        parser.error("--total-apps must be positive")

    print("\nHEDGE-ExpertAI Evaluation")
    print(f"API: {args.api_url}")
    print(f"Mode: {args.mode}")
    print(f"Queries: {args.queries}\n")

    try:
        queries = load_queries(args.queries)
    except (OSError, ValueError) as exc:
        parser.error(f"Invalid query set ({type(exc).__name__})")

    modes = [args.mode] if args.mode != "all" else ["search", "chat", "stream"]
    results = {}

    for mode in modes:
        if mode == "search":
            print(f"Running {len(queries)} search queries...\n")
            metrics = evaluate(args.api_url, queries)
            _print_search_results(metrics, total_apps=args.total_apps)

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

        results[mode] = metrics

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(results, indent=2, allow_nan=False) + "\n")

    if args.report_feedback:
        # Legacy opt-in diagnostics; recommendation analytics are outside this remediation.
        print(f"\n{'='*55}")
        print("  FEEDBACK STATS")
        print(f"{'='*55}")
        fb = fetch_feedback_stats(args.api_url)
        if fb:
            total_accept = fb.get("total_accept", 0)
            total_dismiss = fb.get("total_dismiss", 0)
            total_actions = total_accept + total_dismiss
            if total_actions > 0:
                acceptance_rate = total_accept / total_actions
                rate_pass = acceptance_rate >= 0.70
                print(f"  Acceptance rate:  {acceptance_rate:.1%}  (target: ≥70%)  {'✓' if rate_pass else '✗'}")
            else:
                print("  Acceptance rate:  N/A (no feedback data yet)")
            print(f"  Total clicks:     {fb.get('total_click', 0)}")
            print(f"  Total accepts:    {total_accept}")
            print(f"  Total dismisses:  {total_dismiss}")
            avg = fb.get("avg_rating")
            if avg is not None:
                print(f"  Avg rating:       {avg}/5")
        else:
            print("  Could not fetch feedback stats.")

    passed = all(metrics["failed"] == 0 and metrics["hit_rate_at_2"] >= 0.70 for metrics in results.values())
    print(f"\n  Engineering retrieval/run checks: {'PASS' if passed else 'FAIL'}")
    print("  Proposal acceptance: UNASSESSED; requires reviewed labels and target-environment evidence.")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
