"""Discovery's E5 similarity route and Expert's fail-closed client."""
import httpx
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts.store_v1_playground import load_service

embeddings = load_service("unit_similarity_discovery", "discovery-ranking")("embeddings")
routes = load_service("unit_similarity_discovery", "discovery-ranking")("routes")
evidence = load_service("unit_similarity_expert", "expert-recommend")("evidence")


@pytest.fixture
def encoder(monkeypatch):
    encoded = []

    def fake(texts):
        encoded.extend(texts)
        return np.array([[1.0, 0.0] if "bid" in t else [0.0, 1.0] for t in texts], dtype=np.float32)

    monkeypatch.setattr(embeddings, "encode", fake)
    monkeypatch.setattr(embeddings, "encode_queries", fake)
    monkeypatch.setattr(embeddings, "_passages", {})
    return encoded


def test_similarity_scores_queries_against_passages_and_caches_passages(encoder):
    assert embeddings.similarity(["bids"], ["bid pooling", "room temperatures"]) == [[1.0, 0.0]]
    assert embeddings.similarity(["rooms"], ["room temperatures", "bid pooling"]) == [[1.0, 0.0]]
    assert encoder == ["bid pooling", "room temperatures", "bids", "rooms"]


def test_route_returns_scores_and_bounds_input(encoder):
    app = FastAPI()
    app.include_router(routes.v2_router)
    client = TestClient(app)
    response = client.post("/api/v2/evidence/similarity", json={"queries": ["bids"], "passages": ["bid pooling"]})
    assert response.status_code == 200 and response.json() == {"scores": [[1.0]]}
    assert client.post("/api/v2/evidence/similarity",
                       json={"queries": ["a" * 2001], "passages": ["b"]}).status_code == 422
    assert client.post("/api/v2/evidence/similarity",
                       json={"queries": ["a"] * 9, "passages": ["b"]}).status_code == 422


def remote(monkeypatch, handler):
    monkeypatch.setenv("DISCOVERY_RANKING_URL", "http://discovery")
    monkeypatch.setattr(evidence, "_client", httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(evidence, "_unavailable_until", 0.0)


def test_remote_similarity_returns_validated_scores(monkeypatch):
    remote(monkeypatch, lambda request: httpx.Response(200, json={"scores": [[0.9, 0.1]]}))
    assert evidence._remote_similarity(["q"], ["a", "b"]) == [[0.9, 0.1]]


@pytest.mark.parametrize("response", [
    httpx.Response(503), httpx.Response(200, json={"scores": [[0.9]]}), httpx.Response(200, json={}),
    httpx.Response(200, json={"scores": [[0.9, "not-a-number"]]}), httpx.Response(200, json={"scores": [[0.9, True]]}),
    httpx.Response(200, content=b'{"scores": [[0.9, NaN]]}', headers={"content-type": "application/json"}),
    httpx.Response(200, json=[[0.9, 0.1]]),
])
def test_unavailable_or_malformed_similarity_falls_back_and_pauses_calls(monkeypatch, response):
    calls = []
    remote(monkeypatch, lambda request: calls.append(request) or response)
    assert evidence._remote_similarity(["q"], ["a", "b"]) is None
    assert evidence._remote_similarity(["q"], ["a", "b"]) is None
    assert len(calls) == 1


def test_similarity_is_not_requested_without_a_configured_discovery_url(monkeypatch):
    monkeypatch.delenv("DISCOVERY_RANKING_URL", raising=False)
    monkeypatch.setattr(evidence, "_client", httpx.Client(transport=httpx.MockTransport(
        lambda request: pytest.fail("unexpected request"))))
    assert evidence._remote_similarity(["q"], ["a"]) is None


def test_requests_beyond_discovery_bounds_are_batched_and_clipped(monkeypatch):
    requests = []

    def handler(request):
        body = __import__("json").loads(request.content)
        requests.append(body)
        assert len(body["queries"]) <= evidence.MAX_QUERIES and len(body["passages"]) <= evidence.MAX_PASSAGES
        assert all(len(text) <= evidence.MAX_TEXT for text in [*body["queries"], *body["passages"]])
        return httpx.Response(200, json={"scores": [[0.5] * len(body["passages"]) for _ in body["queries"]]})

    remote(monkeypatch, handler)
    scores = evidence._remote_similarity([f"q{i}" for i in range(10)], ["p" * 3000] + [f"p{i}" for i in range(450)])
    assert len(scores) == 10 and all(len(row) == 451 for row in scores)
    assert len(requests) == 4


def test_malformed_scores_never_reach_assessment(monkeypatch):
    suitability = load_service("unit_similarity_expert", "expert-recommend")("suitability")
    remote(monkeypatch, lambda request: httpx.Response(200, json={"scores": [["not-a-number"]]}))
    evidence.set_similarity(evidence._remote_similarity)
    try:
        result = suitability.assess("flexibility bid aggregation",
                                    {"description": "Aggregates flexibility bids from several providers."}, "en")
    finally:
        evidence.set_similarity(lambda queries, passages: None)
    assert result["status"] == "source_supported"
