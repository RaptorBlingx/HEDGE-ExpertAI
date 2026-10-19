"""Recommendation admission, source-only rendering and legitimate abstention."""
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from scripts.store_v1_playground import load_service

_mod = load_service("unit_rec_suitability", "expert-recommend")("recommender")
SAMPLE_RESULTS = [
    {"app": {"id": "energy", "title": "Energy Meter", "description": "Energy monitoring."}, "rank": 1,
     "relevance": "high"},
    {"app": {"id": "water", "title": "Water Meter", "description": "Displays water readings."}, "rank": 2,
     "relevance": "high"},
]


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(_mod, "_search_apps_v2", lambda *args, **kwargs: SAMPLE_RESULTS)
    monkeypatch.setattr(_mod, "_search_apps", lambda *args, **kwargs: SAMPLE_RESULTS)
    monkeypatch.setattr(_mod, "OllamaClient", lambda: SimpleNamespace(
        chat_structured=lambda *args: '{"selected_ids":["energy"]}',
    ))


def test_high_retrieval_rank_is_not_suitability(setup):
    result = _mod.recommend_v2(query="earthquake warnings", locale="en", filters={}, limit=5)
    assert result["apps"] == [] and len(result["candidates"]) == 2
    assert result["decision"]["outcome"] == "abstained"
    assert "confirmed matches" in result["message"]
    assert "Start with" not in result["message"]


def test_positive_recommendation_is_bound_to_source_and_original_order(setup):
    result = _mod.recommend_v2(query="Find apps for energy monitoring", locale="en", filters={}, limit=5)
    assert [r["app"]["id"] for r in result["apps"]] == ["energy"]
    assert result["apps"][0]["suitability"]["evidence_fields"] == ["description"]
    assert result["apps"][0]["rank"] == 1
    assert [r["app"]["id"] for r in result["candidates"]] == ["water"]
    assert 'description: "Energy monitoring."' in result["message"]


def test_structured_abstention_veto_is_preserved(setup, monkeypatch):
    monkeypatch.setattr(_mod, "OllamaClient", lambda: SimpleNamespace(
        chat_structured=lambda *args: '{"selected_ids":[]}',
    ))
    result = _mod.recommend_v2(query="energy monitoring", locale="en", filters={}, limit=5)
    assert not result["apps"]
    assert result["decision"]["reason"] == "model_abstention"
    assert "cannot recommend" in result["message"]
    assert "Start with" not in result["message"]


@pytest.mark.parametrize("generated", [
    'Energy Meter guarantees 90% savings and is medically certified.',
    '{"selected_ids":["water"]}', '{"selected_ids":["energy","energy"]}',
    '{"selected_ids":["energy"],"claim":"free forever"}',
])
def test_fabrication_and_unbacked_selection_never_become_prose(setup, monkeypatch, generated):
    monkeypatch.setattr(_mod, "OllamaClient", lambda: SimpleNamespace(chat_structured=lambda *args: generated))
    result = _mod.recommend_v2(query="energy monitoring", locale="en", filters={}, limit=5)
    assert [r["app"]["id"] for r in result["apps"]] == ["energy"]
    assert not any(word in result["message"] for word in ("90%", "certified", "forever", "Start with"))
    assert result["decision"]["reason"] == "source_evidence_fallback"


def test_normal_and_streamed_paths_decide_before_emitting_cards(setup):
    for query in ("energy monitoring", "earthquake warning"):
        normal = _mod.recommend_v2(query=query, locale="en", filters={}, limit=5)
        events = list(_mod.recommend_v2_stream(query=query, locale="en", filters={}, limit=5))
        assert events[0]["apps"] == normal["apps"]
        assert events[0]["candidates"] == normal["candidates"]
        assert events[0]["decision"] == normal["decision"]
        assert "".join(e["content"] for e in events if e["type"] == "explanation_delta") == normal["message"]
        assert events[-1]["explanations"] == normal["explanations"]


def test_legacy_and_explain_routes_have_the_same_boundary(setup):
    result = _mod.recommend("earthquake warnings")
    events = [json.loads(event[6:]) for event in _mod.recommend_stream("earthquake warnings")]
    assert result["apps"] == events[0]["apps"] == []
    assert events[1]["content"] == result["message"]
    assert "cannot recommend" in _mod.explain_app("earthquake warnings", SAMPLE_RESULTS[1]["app"])


def test_stream_does_not_turn_retrieval_failure_into_abstention(monkeypatch):
    def failed(*args, **kwargs):
        raise HTTPException(503, "Catalogue search unavailable")
    monkeypatch.setattr(_mod, "_search_apps_v2", failed)
    with pytest.raises(HTTPException):
        next(_mod.recommend_v2_stream(query="energy", locale="en", filters={}, limit=5))


def test_legacy_standalone_explanation_preserves_missing_identity(setup):
    app = {"title": "Energy App", "description": "Energy monitoring."}
    positive = _mod.explain_app("energy monitoring", app)
    negative = _mod.explain_app("earthquake warning", app)
    assert 'description: "Energy monitoring."' in positive
    assert "direct source evidence" in positive
    assert "cannot recommend" in negative
    assert "id" not in app


def test_malformed_optional_title_cannot_break_standalone_source_explanation():
    message = _mod.explain_app("energy monitoring", {"title": {"en": 17},
                                                      "description": "Energy monitoring."})
    assert 'description: "Energy monitoring."' in message
    assert "title.en" not in message
