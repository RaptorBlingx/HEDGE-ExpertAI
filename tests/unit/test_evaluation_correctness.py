"""Evaluator regressions use HTTP mocks only; no live services or demo resources."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from evaluation import evaluate as evaluator


@pytest.fixture
def mock_api(monkeypatch):
    clients = []

    def bind(handler):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(client)
        monkeypatch.setattr(httpx, "post", client.post)
        monkeypatch.setattr(httpx, "stream", client.stream)
        monkeypatch.setattr(httpx, "get", client.get)

    yield bind
    for client in clients:
        client.close()


def queries(count=1, expected=None):
    return [
        {"query_id": f"q-{i}", "query": f"query {i}", "expected_apps": ["app-a"] if expected is None else expected}
        for i in range(count)
    ]


def chat_response(app_id="app-a"):
    return {
        "apps": [{"app": {"id": app_id}}],
        "message": "This app guarantees 90% savings and medical certification in every country.",
    }


def test_fabricated_explanation_is_unassessed_even_with_matching_app_identity(mock_api, capsys):
    mock_api(lambda request: httpx.Response(200, json=chat_response()))
    metrics = evaluator.chat_evaluate("https://mock.invalid", queries())
    assert metrics["explanation_accuracy"] is None
    assert metrics["explanation_accuracy_status"] == "unassessed"
    assert metrics["hit_rate_at_2"] == 1.0
    evaluator._print_chat_results(metrics)
    output = capsys.readouterr().out
    assert "UNASSESSED" in output
    assert "Explanation accuracy:  100" not in output


def test_nine_timeouts_remain_in_retrieval_denominators(mock_api):
    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise httpx.ReadTimeout("mock timeout", request=request)
        return httpx.Response(200, json={"results": [{"app": {"id": "app-a"}}]})

    mock_api(respond)
    query_set = queries(10)
    for query in query_set:
        query["category"] = "Energy"
    metrics = evaluator.evaluate("https://mock.invalid", query_set)
    assert metrics["total_queries"] == 10
    assert metrics["evaluated"] == 1
    assert metrics["failed"] == 9
    assert metrics["hit_rate_at_2"] == pytest.approx(0.1)
    for metric in ("precision_at_2", "recall_at_5", "mrr", "ndcg_at_5", "map"):
        assert metrics[metric] == pytest.approx(0.1)
    assert metrics["latency_samples"] == 10
    assert metrics["per_saref"]["Energy"] == {"count": 10, "precision_at_2": 0.1}
    lower, upper = metrics["precision_at_2_ci"]
    assert 0 <= lower <= 0.1 <= upper < 1


def test_problem_only_stream_is_failed(mock_api, capsys):
    event = 'data: {"type":"problem","status":503}\n\n'
    mock_api(lambda request: httpx.Response(200, text=event, headers={"content-type": "text/event-stream"}))
    metrics = evaluator.stream_evaluate("https://mock.invalid", queries())
    assert metrics["evaluated"] == 0
    assert metrics["failed"] == 1
    assert metrics["hit_rate_at_2"] == 0.0
    assert metrics["median_ttft_s"] is None
    assert metrics["median_ttfa_s"] is None
    assert "[OK]" not in capsys.readouterr().out


def sse(*events):
    return "".join("data: " + json.dumps(event) + "\n\n" for event in events)


def response_for_mode(mode, app_ids=("app-a",)):
    apps = [{"app": {"id": aid}} for aid in app_ids]
    if mode == "search":
        return httpx.Response(200, json={"results": apps})
    if mode == "chat":
        return httpx.Response(200, json={**chat_response(), "apps": apps})
    return httpx.Response(200, text=sse(
        {"type": "recommendations", "apps": apps}, {"type": "complete"},
    ))


def evaluate_mode(mode, query_set):
    function = {"search": evaluator.evaluate, "chat": evaluator.chat_evaluate, "stream": evaluator.stream_evaluate}[mode]
    return function("https://mock.invalid", query_set)


@pytest.mark.parametrize("mode", ["search", "chat", "stream"])
def test_mean_median_and_failure_durations_are_distinct(mode, mock_api, monkeypatch):
    timer = SimpleNamespace(now=0.0)
    monkeypatch.setattr(evaluator, "time", SimpleNamespace(monotonic=lambda: timer.now))
    durations = iter([1.0, 1.0, 20.0])

    def respond(request):
        duration = next(durations)
        timer.now += duration
        if duration == 20.0:
            raise httpx.ReadTimeout("mock timeout", request=request)
        return response_for_mode(mode)

    mock_api(respond)
    metrics = evaluate_mode(mode, queries(3))
    assert metrics["mean_latency_s"] == pytest.approx(22.0 / 3)
    assert metrics["median_latency_s"] == 1.0
    assert metrics["p95_latency_s"] == 20.0
    assert metrics["latency_samples"] == 3
    assert metrics["hit_rate_at_2"] == pytest.approx(2.0 / 3)
    assert metrics["evaluated"] == 2
    assert metrics["failed"] == 1
    assert metrics["per_query"][-1]["error"] == "ReadTimeout"


@pytest.mark.parametrize("mode", ["search", "chat", "stream"])
@pytest.mark.parametrize("app_ids,expected,hit,p2,recall", [
    (("wrong-id",), ["app-a"], 0.0, 0.0, 0.0),
    (("wrong-id", "app-a"), ["app-a", "app-b"], 1.0, 0.5, 0.5),
    (("wrong-1", "wrong-2", "app-a"), ["app-a"], 0.0, 0.0, 1.0),
])
def test_exact_expected_app_identity_and_top_two_order(mode, app_ids, expected, hit, p2, recall, mock_api):
    mock_api(lambda request: response_for_mode(mode, app_ids))
    metrics = evaluate_mode(mode, queries(expected=expected))
    assert metrics["evaluated"] == 1
    assert metrics["hit_rate_at_2"] == hit
    assert metrics["precision_at_2"] == p2
    assert metrics["recall_at_5"] == recall
    assert metrics["per_query"][0]["returned_app_ids"] == list(app_ids)


@pytest.mark.parametrize("mode", ["search", "chat", "stream"])
@pytest.mark.parametrize("app_ids", [(None,), (123,), ("",), ("app-a", "app-a")])
def test_invalid_or_duplicate_result_identities_fail_without_inflating_scores(mode, app_ids, mock_api):
    mock_api(lambda request: response_for_mode(mode, app_ids))
    metrics = evaluate_mode(mode, queries())
    assert metrics["failed"] == 1
    assert metrics["hit_rate_at_2"] == 0.0
    assert metrics["map"] == 0.0
    assert metrics["unique_apps_returned"] == 0


@pytest.mark.parametrize("bad_queries", [
    [], {}, [{"query": "test"}], queries(expected=["app-a", "app-a"]),
    queries(expected=[None]), [{"query": " ", "expected_apps": ["app-a"]}],
])
def test_invalid_query_labels_are_rejected_before_requests(bad_queries, mock_api):
    def unexpected(request):
        pytest.fail("Invalid labels must never issue a request")

    mock_api(unexpected)
    with pytest.raises(ValueError):
        evaluator.evaluate("https://mock.invalid", bad_queries)


@pytest.mark.parametrize("mode", ["search", "chat", "stream"])
@pytest.mark.parametrize("status,body", [(503, "unavailable"), (200, "not JSON"), (200, "{}")])
def test_http_and_malformed_response_failures_are_accounted_for(mode, status, body, mock_api):
    mock_api(lambda request: httpx.Response(status, text=body))
    metrics = evaluate_mode(mode, queries())
    assert metrics["total_queries"] == 1
    assert metrics["evaluated"] == 0
    assert metrics["failed"] == 1
    assert metrics["hit_rate_at_2"] == 0.0
    assert metrics["latency_samples"] == 1


@pytest.mark.parametrize("ending", [
    {"type": "problem", "status": 503}, None,
])
def test_partial_output_does_not_make_a_failed_stream_successful(ending, mock_api):
    events = [
        {"type": "recommendations", "apps": [{"app": {"id": "app-a"}}]},
        {"type": "explanation_delta", "content": "Some text"},
    ]
    if ending:
        events.append(ending)
    mock_api(lambda request: httpx.Response(200, text=sse(*events)))
    metrics = evaluator.stream_evaluate("https://mock.invalid", queries())
    assert metrics["evaluated"] == 0
    assert metrics["failed"] == 1
    assert metrics["hit_rate_at_2"] == 0.0
    assert metrics["ttft_samples"] == metrics["ttfa_samples"] == 0
    assert metrics["per_query"][0]["error"] == ("stream_problem" if ending else "missing_complete")
    assert metrics["per_query"][0]["returned_app_ids"] == ["app-a"]


def test_successful_empty_complete_has_no_invented_first_output_time(mock_api):
    mock_api(lambda request: httpx.Response(200, text=sse({"type": "complete"})))
    metrics = evaluator.stream_evaluate("https://mock.invalid", queries(expected=[]))
    assert metrics["evaluated"] == 1
    assert metrics["failed"] == 0
    assert metrics["median_ttft_s"] is None
    assert metrics["median_ttfa_s"] is None
    assert metrics["explanation_accuracy"] is None


def test_sse_timing_boundaries_and_multiline_frames(mock_api, monkeypatch):
    timer = SimpleNamespace(now=0.0)
    monkeypatch.setattr(evaluator, "time", SimpleNamespace(monotonic=lambda: timer.now))

    class TimedStream(httpx.SyncByteStream):
        def __iter__(self):
            frames = [
                ': heartbeat\n\ndata: {"type":"recommendations",\ndata: "apps":[{"app":{"id":"app-a"}}]}\n\n',
                sse({"type": "explanation_delta", "content": ""}),
                sse({"type": "explanation_delta", "content": "First text"}),
                sse({"type": "complete"}),
            ]
            for frame in frames:
                timer.now += 1.0
                yield frame.encode()

    def respond(request):
        timer.now += 1.0  # Response headers are not a complete response.
        return httpx.Response(200, stream=TimedStream())

    mock_api(respond)
    metrics = evaluator.stream_evaluate("https://mock.invalid", queries())
    assert metrics["median_ttfa_s"] == 2.0
    assert metrics["median_ttft_s"] == 4.0
    assert metrics["mean_latency_s"] == 5.0
    assert metrics["hit_rate_at_2"] == 1.0
    assert metrics["ttft_samples"] == metrics["ttfa_samples"] == 1


@pytest.mark.parametrize("body", [
    'data: not JSON\n\n', 'data: []\n\n', 'data: {"type":"complete"}',
    'data: {"type":"explanation_delta","content":null}\n\ndata: {"type":"complete"}\n\n',
])
def test_malformed_sse_cannot_report_success(body, mock_api):
    mock_api(lambda request: httpx.Response(200, text=body))
    metrics = evaluator.stream_evaluate("https://mock.invalid", queries())
    assert metrics["failed"] == 1
    assert metrics["evaluated"] == 0


@pytest.mark.parametrize("mode", ["search", "chat", "stream", "all"])
@pytest.mark.parametrize("fail", [False, True])
def test_executable_entrypoint_exit_status_and_json_report(mode, fail, mock_api, monkeypatch, tmp_path, capsys):
    requests = []

    def respond(request):
        assert request.method == "POST", "No unsolicited analytics reads"
        requests.append(request.url.path)
        request_mode = {"/api/v2/apps/search": "search", "/api/v2/chat": "chat", "/api/v2/chat/stream": "stream"}[request.url.path]
        # In all mode, search/chat succeed and only stream fails.
        should_fail = fail and (mode != "all" or request_mode == "stream")
        if should_fail:
            if request_mode == "stream":
                return httpx.Response(200, text=sse({"type": "problem", "status": 503}))
            raise httpx.ReadTimeout("private response body must not leak", request=request)
        return response_for_mode(request_mode)

    mock_api(respond)
    query_file = tmp_path / "queries.json"
    query_file.write_text(json.dumps(queries()))
    report_file = tmp_path / "results.json"
    monkeypatch.setattr("sys.argv", [
        "evaluate.py", "--api-url", "https://mock.invalid", "--mode", mode,
        "--queries", str(query_file), "--output-json", str(report_file),
    ])
    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(Path(evaluator.__file__)), run_name="__main__")
    assert raised.value.code == (1 if fail else 0)
    report = json.loads(report_file.read_text())
    modes = ["search", "chat", "stream"] if mode == "all" else [mode]
    assert len(requests) == len(modes)
    assert set(report) == set(modes)
    for request_mode, metrics in report.items():
        assert metrics["total_queries"] == metrics["evaluated"] + metrics["failed"] == 1
        assert len(metrics["per_query"]) == 1
        if request_mode != "search":
            assert metrics["explanation_accuracy"] is None
    output = capsys.readouterr().out
    assert "Proposal acceptance: UNASSESSED" in output
    assert "private response body" not in output


@pytest.mark.parametrize("mode", ["search", "chat", "stream"])
def test_executable_wrong_app_identity_fails_retrieval_gate(mode, mock_api, monkeypatch, tmp_path):
    mock_api(lambda request: response_for_mode(mode, ("wrong-id",)))
    query_file = tmp_path / "queries.json"
    query_file.write_text(json.dumps(queries()))
    monkeypatch.setattr("sys.argv", ["evaluate.py", "--mode", mode, "--queries", str(query_file), "--api-url", "https://mock.invalid"])
    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(Path(evaluator.__file__)), run_name="__main__")
    assert raised.value.code == 1


@pytest.mark.parametrize("arguments", [["--max-queries", "0"], ["--max-queries", "-1"], ["--total-apps", "0"]])
def test_executable_rejects_invalid_limits(arguments, monkeypatch):
    monkeypatch.setattr("sys.argv", ["evaluate.py", *arguments])
    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(Path(evaluator.__file__)), run_name="__main__")
    assert raised.value.code == 2
