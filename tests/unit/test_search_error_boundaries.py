"""SCRUM-28: real HTTP route chain with disposable dependency doubles, no services."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).parents[2]


def load(service):
    name = "scrum28_" + service.replace("-", "_")
    package = ModuleType(name)
    package.__path__ = [str(ROOT / "services" / service / "app")]
    sys.modules[name] = package
    return importlib.import_module(name + ".routes")


@pytest.fixture
def chain(monkeypatch):
    discovery = load("discovery-ranking")
    expert = load("expert-recommend")
    chat = load("chat-intent")
    gateway = load("gateway")
    searcher = importlib.import_module(discovery.__package__ + ".searcher_v2")
    recommender = importlib.import_module(expert.__package__ + ".recommender")
    monkeypatch.setattr(discovery, "get_client", lambda: object())
    monkeypatch.setattr(discovery, "current_catalogue_revision", lambda: "test")
    monkeypatch.setattr(searcher, "_cache", lambda: Mock(get=Mock(return_value=None)))
    monkeypatch.setattr(searcher, "lexical_search", lambda *a, **k: [])
    monkeypatch.setattr(searcher, "_dense_candidates", lambda *a, **k: [])
    monkeypatch.setattr(searcher, "get_catalogue_apps", lambda *a, **k: {})
    monkeypatch.setattr(chat, "get_or_create_session", lambda _: ("qa-session", []))
    monkeypatch.setattr(chat, "get_session", lambda _: {})
    monkeypatch.setattr(chat, "classify", lambda _: SimpleNamespace(intent="search", entities={}))
    updates = Mock()
    monkeypatch.setattr(chat, "update_session", updates)
    monkeypatch.setattr(chat, "log_session_event", Mock())
    monkeypatch.setattr(chat, "create_impression", Mock(return_value="qa-impression"))
    monkeypatch.setattr(
        recommender, "OllamaClient", Mock(side_effect=AssertionError("no live model"))
    )
    apps = []
    for routes in (discovery, expert, chat):
        app = FastAPI()
        app.include_router(routes.v2_router)
        apps.append(app)
    dc = TestClient(apps[0], raise_server_exceptions=False)
    ec = TestClient(apps[1], raise_server_exceptions=False)
    cc = TestClient(apps[2], raise_server_exceptions=False)
    gateway_app = FastAPI()
    gateway_app.include_router(gateway.router)
    gc = TestClient(gateway_app, raise_server_exceptions=False)
    monkeypatch.setattr(
        gateway,
        "httpx",
        SimpleNamespace(
            AsyncClient=lambda: httpx.AsyncClient(transport=httpx.ASGITransport(app=apps[2])),
        ),
    )
    state = {"mode": "ok", "queries": []}

    def post(url, *, json, timeout):
        state["queries"].append(json["query"])
        if state["mode"] == "timeout":
            raise httpx.ReadTimeout("synthetic timeout")
        if state["mode"] == "offline":
            raise httpx.ConnectError("synthetic unavailable")
        if state["mode"] == "malformed":
            return httpx.Response(200, json={}, request=httpx.Request("POST", url))
        if state["mode"] in {"http503", "http504"}:
            return httpx.Response(
                int(state["mode"][4:]),
                json={"detail": "synthetic failure"},
                request=httpx.Request("POST", url),
            )
        if state["mode"] == "validation":
            return httpx.Response(
                422, json={"detail": "synthetic invalid"}, request=httpx.Request("POST", url)
            )
        return dc.post("/api/v2/apps/search", json=json)

    monkeypatch.setattr(
        recommender,
        "httpx",
        SimpleNamespace(
            post=post,
            TimeoutException=httpx.TimeoutException,
            HTTPStatusError=httpx.HTTPStatusError,
            RequestError=httpx.RequestError,
        ),
    )
    monkeypatch.setattr(
        chat,
        "httpx",
        SimpleNamespace(
            AsyncClient=lambda: httpx.AsyncClient(transport=httpx.ASGITransport(app=apps[1])),
            TimeoutException=httpx.TimeoutException,
            HTTPStatusError=httpx.HTTPStatusError,
            RequestError=httpx.RequestError,
        ),
    )
    return SimpleNamespace(
        dc=dc, ec=ec, cc=cc, gc=gc, state=state, chat=chat, searcher=searcher, updates=updates
    )


def events(response):
    assert response.status_code == 200
    return [json.loads(line[5:]) for line in response.text.splitlines() if line.startswith("data:")]


@pytest.mark.parametrize("stream", [False, True])
def test_501_characters_reach_discovery_without_false_no_match(chain, stream):
    query = "x" * 501
    response = chain.cc.post(
        "/api/v2/chat" + ("/stream" if stream else ""), json={"message": query}
    )
    assert chain.dc.post("/api/v2/apps/search", json={"query": query}).status_code == 200
    assert chain.state["queries"] == [query]
    if stream:
        assert events(response)[-1]["type"] == "complete"
    else:
        assert response.status_code == 200


@pytest.mark.parametrize(
    "mode,status",
    [
        ("offline", 503),
        ("timeout", 504),
        ("validation", 422),
        ("malformed", 503),
        ("http503", 503),
        ("http504", 504),
    ],
)
@pytest.mark.parametrize("stream", [False, True])
def test_failures_never_claim_no_match_and_retry_recovers(chain, mode, status, stream):
    chain.state["mode"] = mode
    path = "/api/v2/chat" + ("/stream" if stream else "")
    response = chain.cc.post(path, json={"message": "energy"})
    assert "find an App in the catalogue" not in response.text
    if stream:
        payloads = events(response)
        assert payloads[-1]["type"] == "problem"
        assert payloads[-1]["status"] == status
        assert not any(
            e["type"] in {"complete", "recommendations", "explanation_delta"} for e in payloads
        )
    else:
        assert response.status_code == status
    chain.updates.assert_not_called()
    chain.state["mode"] = "ok"
    recovered = chain.cc.post(path, json={"message": "energy"})
    assert recovered.status_code == 200
    assert "find an App in the catalogue" in recovered.text
    if stream:
        assert events(recovered)[-1]["type"] == "complete"
    chain.updates.assert_called_once()


@pytest.mark.parametrize("stream", [False, True])
def test_authoritative_retrieval_failure_is_unavailable(chain, monkeypatch, stream):
    monkeypatch.setattr(
        chain.searcher, "lexical_search", Mock(side_effect=RuntimeError("db unavailable"))
    )
    assert chain.dc.post("/api/v2/apps/search", json={"query": "energy"}).status_code == 503
    response = chain.cc.post(
        "/api/v2/chat" + ("/stream" if stream else ""), json={"message": "energy"}
    )
    if stream:
        assert events(response)[-1]["status"] == 503
        assert events(response)[-1]["type"] == "problem"
    else:
        assert response.status_code == 503
    assert "find an App in the catalogue" not in response.text


@pytest.mark.parametrize("stream", [False, True])
def test_refinement_overflow_is_validation_not_no_match(chain, monkeypatch, stream):
    monkeypatch.setattr(
        chain.chat, "classify", lambda _: SimpleNamespace(intent="refine", entities={})
    )
    monkeypatch.setattr(
        chain.chat, "get_session", lambda _: {"context": {"last_query": "x" * 1500}}
    )
    response = chain.cc.post(
        "/api/v2/chat" + ("/stream" if stream else ""), json={"message": "y" * 600}
    )
    if stream:
        assert events(response)[-1]["type"] == "problem"
        assert events(response)[-1]["status"] == 422
        assert not any(e["type"] == "complete" for e in events(response))
    else:
        assert response.status_code == 422
    assert not chain.state["queries"]
    chain.updates.assert_not_called()


@pytest.mark.parametrize("query", ["", "x" * 2001])
def test_invalid_inputs_rejected_at_all_request_boundaries(chain, query):
    for client, path, key in (
        (chain.dc, "/api/v2/apps/search", "query"),
        (chain.ec, "/api/v2/recommend", "query"),
        (chain.ec, "/api/v2/recommend/stream", "query"),
        (chain.cc, "/api/v2/chat", "message"),
        (chain.cc, "/api/v2/chat/stream", "message"),
    ):
        assert client.post(path, json={key: query}).status_code == 422
    assert not chain.state["queries"]


@pytest.mark.parametrize("stream", [False, True])
def test_successful_results_preserve_response_and_impression(chain, monkeypatch, stream):
    app = {"id": "app-001", "title": {"en": "Energy"}, "description": "Energy monitoring."}
    result = {"app": app, "rank": 1, "score": 0.8}
    discovery = sys.modules[chain.searcher.__package__ + ".routes"]
    monkeypatch.setattr(discovery, "search_apps_v2", lambda *a, **k: [result])
    recommender = sys.modules["scrum28_expert_recommend.recommender"]
    monkeypatch.setattr(recommender, "_recommendation_narrative", lambda *a: "Energy monitoring.")
    response = chain.cc.post(
        "/api/v2/chat" + ("/stream" if stream else ""), json={"message": "energy"}
    )
    assert response.status_code == 200
    if stream:
        payloads = events(response)
        returned = next(e for e in payloads if e["type"] == "recommendations")["apps"]
        assert [{k: v for k, v in row.items() if k != "suitability"} for row in returned] == [result]
        assert returned[0]["suitability"]["status"] == "source_supported"
        assert payloads[-1]["type"] == "complete"
        assert payloads[-1]["impression_id"] == "qa-impression"
    else:
        returned = response.json()["apps"]
        assert [{k: v for k, v in row.items() if k != "suitability"} for row in returned] == [result]
        assert returned[0]["suitability"]["status"] == "source_supported"
        assert response.json()["impression_id"] == "qa-impression"
    chain.updates.assert_called_once()


def test_2000_character_search_and_vector_fallback_are_successful(chain, monkeypatch):
    monkeypatch.setattr(
        chain.searcher, "_dense_candidates", Mock(side_effect=RuntimeError("vector offline"))
    )
    response = chain.cc.post("/api/v2/chat", json={"message": "x" * 2000})
    assert response.status_code == 200
    assert "find an App in the catalogue" in response.text
    assert chain.state["queries"] == ["x" * 2000]


@pytest.mark.parametrize("stream", [False, True])
def test_authoritative_service_recovers_on_next_request(chain, monkeypatch, stream):
    path = "/api/v2/chat" + ("/stream" if stream else "")
    monkeypatch.setattr(
        chain.searcher, "lexical_search", Mock(side_effect=RuntimeError("db offline"))
    )
    failed = chain.cc.post(path, json={"message": "energy"})
    assert (events(failed)[-1]["status"] if stream else failed.status_code) == 503
    monkeypatch.setattr(chain.searcher, "lexical_search", lambda *a, **k: [])
    recovered = chain.cc.post(path, json={"message": "energy"})
    assert recovered.status_code == 200
    assert "find an App in the catalogue" in recovered.text
    if stream:
        assert events(recovered)[-1]["type"] == "complete"


@pytest.mark.parametrize("status", [422, 503, 504, None])
def test_partial_stream_failure_preserves_session_without_completion(chain, monkeypatch, status):
    session = importlib.import_module(chain.chat.__package__ + ".session")
    initial = {
        "messages": [{"role": "assistant", "content": "Existing answer"}],
        "context": {"last_query": "old", "turn": 3},
    }
    stored = {"hedge:session:qa-session": json.dumps(initial)}
    redis = Mock()
    redis.get.side_effect = stored.get
    redis.setex.side_effect = lambda key, ttl, value: stored.__setitem__(key, value)
    monkeypatch.setattr(session, "_get_redis", lambda: redis)
    monkeypatch.setattr(chain.chat, "get_or_create_session", session.get_or_create_session)
    monkeypatch.setattr(chain.chat, "get_session", session.get_session)
    update = Mock(wraps=session.update_session)
    monkeypatch.setattr(chain.chat, "update_session", update)
    payloads = [
        {"type": "recommendations", "apps": [{"app": {"id": "app-001"}, "rank": 1}]},
        {"type": "explanation_delta", "content": "Partial explanation"},
    ]
    if status is not None:
        payloads.append({"type": "problem", "status": status, "title": "upstream internal detail"})

    async def respond(request):
        return httpx.Response(
            200, text="".join("data: " + json.dumps(payload) + "\n\n" for payload in payloads)
        )

    monkeypatch.setattr(
        chain.chat.httpx,
        "AsyncClient",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    response = chain.gc.post(
        "/api/v2/chat/stream", json={"message": "energy", "session_id": "qa-session"}
    )
    received = events(response)
    assert any(event["type"] == "recommendations" for event in received)
    assert any(event["type"] == "explanation_delta" for event in received)
    assert received[-1]["type"] == "problem"
    assert received[-1]["status"] == (503 if status is None else status)
    assert not any(event["type"] == "complete" for event in received)
    assert "upstream internal detail" not in response.text
    update.assert_not_called()
    redis.setex.assert_not_called()
    assert json.loads(stored["hedge:session:qa-session"]) == initial
    # Preserve the existing impression for ranked results already delivered.
    chain.chat.create_impression.assert_called_once()


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("exception,status", [(httpx.ConnectError, 503), (httpx.ReadTimeout, 504)])
def test_chat_to_recommendation_transport_failure(chain, monkeypatch, stream, exception, status):
    async def respond(request):
        raise exception("synthetic expert dependency failure")

    monkeypatch.setattr(
        chain.chat.httpx,
        "AsyncClient",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    response = chain.cc.post(
        "/api/v2/chat" + ("/stream" if stream else ""), json={"message": "energy"}
    )
    if stream:
        assert events(response)[-1]["type"] == "problem"
        assert events(response)[-1]["status"] == status
        assert not any(e["type"] == "complete" for e in events(response))
    else:
        assert response.status_code == status
    chain.updates.assert_not_called()


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "mode,status", [("ok", 200), ("offline", 503), ("timeout", 504), ("validation", 422)]
)
def test_public_gateway_preserves_chat_outcomes(chain, stream, mode, status):
    chain.state["mode"] = mode
    response = chain.gc.post(
        "/api/v2/chat" + ("/stream" if stream else ""), json={"message": "x" * 501}
    )
    if stream:
        payloads = events(response)
        if status == 200:
            assert payloads[-1]["type"] == "complete"
            assert "find an App in the catalogue" in response.text
        else:
            assert payloads[-1]["type"] == "problem"
            assert payloads[-1]["status"] == status
            assert not any(e["type"] == "complete" for e in payloads)
    else:
        assert response.status_code == status
        if status != 200:
            assert response.headers["content-type"].startswith("application/problem+json")
    if status != 200:
        assert "find an App in the catalogue" not in response.text


@pytest.mark.parametrize("stream", [False, True])
def test_genuine_zero_results_are_successful_no_match(chain, stream):
    response = chain.cc.post(
        "/api/v2/chat" + ("/stream" if stream else ""), json={"message": "absent app"}
    )
    assert response.status_code == 200
    assert "find an App in the catalogue" in response.text
    if stream:
        payloads = events(response)
        assert next(e for e in payloads if e["type"] == "recommendations")["apps"] == []
        assert payloads[-1]["type"] == "complete"
        assert payloads[-1]["impression_id"] is None
        assert not any(e["type"] == "problem" for e in payloads)
    else:
        assert response.json()["apps"] == []
        assert response.json()["impression_id"] is None
    chain.chat.create_impression.assert_not_called()
    chain.updates.assert_called_once()
