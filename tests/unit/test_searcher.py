"""Tests for discovery-ranking hybrid search module."""

import importlib
import importlib.util
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys as _sys

# Set up the package structure so relative imports work
_app_dir = Path(__file__).parent.parent.parent / "services" / "discovery-ranking" / "app"

# Create a fake parent package
_pkg = types.ModuleType("dr_app")
_pkg.__path__ = [str(_app_dir)]
_pkg.__package__ = "dr_app"
_sys.modules["dr_app"] = _pkg

# Stub embeddings
_embeddings_mod = types.ModuleType("dr_app.embeddings")
_embeddings_mod.encode_single = MagicMock(return_value=[0.1] * 384)
_embeddings_mod.VECTOR_DIM = 384
_embeddings_mod.encode = MagicMock()
_sys.modules["dr_app.embeddings"] = _embeddings_mod

# Stub indexer
_indexer_mod = types.ModuleType("dr_app.indexer")
_indexer_mod.COLLECTION_NAME = "hedge_apps"
_indexer_mod.get_client = MagicMock()
_sys.modules["dr_app.indexer"] = _indexer_mod

# Load searcher with proper package context
_searcher_path = _app_dir / "searcher.py"
_spec = importlib.util.spec_from_file_location("dr_app.searcher", _searcher_path,
                                                 submodule_search_locations=[])
_mod = importlib.util.module_from_spec(_spec)
_mod.__package__ = "dr_app"
_spec.loader.exec_module(_mod)
_sys.modules["dr_app.searcher"] = _mod

_tokenize = _mod._tokenize
_tokenize_query = _mod._tokenize_query
_keyword_score = _mod._keyword_score
hybrid_search = _mod.hybrid_search
invalidate_cache = _mod.invalidate_cache
STOPWORDS = _mod.STOPWORDS
SCORE_THRESHOLD = _mod.SCORE_THRESHOLD
W_VECTOR = _mod.W_VECTOR
W_KEYWORD = _mod.W_KEYWORD
W_SAREF = _mod.W_SAREF


class TestTokenize:
    def test_basic(self):
        assert _tokenize("Hello World") == ["hello", "world"]

    def test_punctuation(self):
        assert _tokenize("energy-monitoring!") == ["energy", "monitoring"]

    def test_empty(self):
        assert _tokenize("") == []

    def test_numbers(self):
        assert _tokenize("app 123") == ["app", "123"]


class TestTokenizeQuery:
    def test_removes_stopwords(self):
        tokens = _tokenize_query("I need an app for energy monitoring")
        assert "i" not in tokens
        assert "need" not in tokens
        assert "an" not in tokens
        assert "app" not in tokens
        assert "for" not in tokens
        assert "energy" in tokens
        assert "monitoring" in tokens

    def test_keeps_content_words(self):
        tokens = _tokenize_query("smart building HVAC solution")
        assert "smart" in tokens
        assert "building" in tokens
        assert "hvac" in tokens
        assert "solution" in tokens

    def test_falls_back_if_all_stopwords(self):
        # "I am the one" — all stopwords, should fall back to original tokens
        tokens = _tokenize_query("I am the one")
        assert len(tokens) > 0  # should not be empty

    def test_domain_stopwords(self):
        tokens = _tokenize_query("find energy monitoring apps")
        assert "find" not in tokens
        assert "apps" not in tokens
        assert "energy" in tokens
        assert "monitoring" in tokens


class TestKeywordScore:
    def test_full_match(self):
        score = _keyword_score(["energy", "monitoring"], "SmartEnergy Monitor for energy monitoring")
        # Both query tokens are present; score should be high (BM25 normalized)
        assert score > 0.5

    def test_partial_match(self):
        score = _keyword_score(["energy", "water"], "SmartEnergy Monitor for energy monitoring")
        full = _keyword_score(["energy", "monitoring"], "SmartEnergy Monitor for energy monitoring")
        assert 0 < score < full

    def test_no_match(self):
        score = _keyword_score(["agriculture"], "SmartEnergy Monitor")
        assert score == 0.0

    def test_empty_query(self):
        assert _keyword_score([], "some text") == 0.0


class TestStopwords:
    def test_common_stopwords_present(self):
        for word in ["i", "the", "a", "is", "for", "and", "to", "in", "of"]:
            assert word in STOPWORDS

    def test_domain_fillers_present(self):
        for word in ["app", "apps", "find", "show", "need", "looking"]:
            assert word in STOPWORDS

    def test_content_words_absent(self):
        for word in ["energy", "water", "building", "hvac", "sensor", "monitor"]:
            assert word not in STOPWORDS


class TestScoreThreshold:
    def test_threshold_value(self):
        assert SCORE_THRESHOLD == 0.30


class TestCacheInvalidation:
    def test_invalidate_clears(self):
        # Access the internal cache
        cache = _mod._cache
        cache["test_key"] = [{"score": 0.5}]
        assert len(cache) > 0
        invalidate_cache()
        assert len(cache) == 0


class TestHybridSearch:
    def _make_mock_point(self, app_id, title, description, tags, saref_type, score):
        point = MagicMock()
        point.score = score
        point.payload = {
            "id": app_id,
            "title": title,
            "description": description,
            "tags": tags,
            "saref_type": saref_type,
        }
        return point

    def _make_mock_client(self, points):
        client = MagicMock()
        response = MagicMock()
        response.points = points
        client.query_points.return_value = response
        return client

    def test_basic_search(self):
        invalidate_cache()
        points = [
            self._make_mock_point("app-001", "SmartEnergy Monitor", "Energy monitoring", ["energy"], "Energy", 0.9),
            self._make_mock_point("app-002", "BuildingComfort", "HVAC optimization", ["hvac"], "Building", 0.5),
        ]
        client = self._make_mock_client(points)
        results = hybrid_search(client, "energy monitoring", top_k=5)
        assert len(results) > 0
        assert results[0]["app"]["id"] == "app-001"

    def test_saref_boost(self):
        invalidate_cache()
        points = [
            self._make_mock_point("app-001", "SmartEnergy", "Energy", ["energy"], "Energy", 0.6),
            self._make_mock_point("app-002", "OtherApp", "Other thing", ["other"], "Building", 0.61),
        ]
        client = self._make_mock_client(points)
        # Without SAREF boost, app-002 wins by vector score
        results_no_saref = hybrid_search(client, "energy", top_k=5)
        invalidate_cache()
        # With SAREF boost matching app-001, it should get +0.1
        results_with_saref = hybrid_search(client, "energy", top_k=5, saref_class="Energy")
        # app-001 should get boosted when SAREF matches
        energy_score_boosted = next(r["score"] for r in results_with_saref if r["app"]["id"] == "app-001")
        energy_score_normal = next(r["score"] for r in results_no_saref if r["app"]["id"] == "app-001")
        assert energy_score_boosted > energy_score_normal

    def test_score_threshold_filters_low(self):
        invalidate_cache()
        points = [
            self._make_mock_point("app-001", "Good", "Relevant app", ["energy"], "Energy", 0.8),
            self._make_mock_point("app-002", "Bad", "Irrelevant", ["xyz"], "Other", 0.1),
        ]
        client = self._make_mock_client(points)
        results = hybrid_search(client, "energy", top_k=5)
        # Low-vector-score app should be filtered out if below threshold
        ids = [r["app"]["id"] for r in results]
        # app-002 has vector=0.1 → final ~0.06+keyword, likely below 0.30
        for r in results:
            assert r["score"] >= SCORE_THRESHOLD

    def test_empty_results(self):
        invalidate_cache()
        client = self._make_mock_client([])
        results = hybrid_search(client, "nonexistent", top_k=5)
        assert results == []

    def test_scoring_formula(self):
        invalidate_cache()
        points = [
            self._make_mock_point("app-001", "Energy Monitor", "Energy monitoring system", ["energy", "monitoring"], "Energy", 0.8),
        ]
        client = self._make_mock_client(points)
        results = hybrid_search(client, "energy monitoring", top_k=5, saref_class="Energy")
        r = results[0]
        # Verify scoring components
        expected = W_VECTOR * r["vector_score"] + W_KEYWORD * r["keyword_score"] + W_SAREF * r["saref_boost"]
        assert abs(r["score"] - round(expected, 4)) < 0.001
        assert r["saref_boost"] == 1.0

    def test_caching_works(self):
        invalidate_cache()
        points = [
            self._make_mock_point("app-001", "Test", "Test app", ["test"], "Energy", 0.7),
        ]
        client = self._make_mock_client(points)
        r1 = hybrid_search(client, "test query", top_k=5)
        r2 = hybrid_search(client, "test query", top_k=5)
        assert r1 == r2
        # Qdrant should only be called once (second call is cached)
        assert client.query_points.call_count == 1
