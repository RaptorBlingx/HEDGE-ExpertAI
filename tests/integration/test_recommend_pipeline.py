"""Integration tests for the recommendation pipeline.

Tests the orchestration flow in expert-recommend: search → LLM → consistency check.
Backend calls (Qdrant, Ollama) are mocked.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Load expert-recommend modules via importlib to avoid `app` namespace clash.
# The recommender module uses relative imports (from .llm_client, from .prompts),
# so we must register all sub-modules under a fake parent package first.
_er_app = Path(__file__).resolve().parent.parent.parent / "services" / "expert-recommend" / "app"

# Create a virtual package for expert-recommend
import types as _types
_er_pkg = _types.ModuleType("er_app")
_er_pkg.__path__ = [str(_er_app)]
sys.modules["er_app"] = _er_pkg


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(
        f"er_app.{name}", _er_app / filename,
        submodule_search_locations=[],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"er_app.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


_prompts_mod = _load("prompts", "prompts.py")
_llm_mod = _load("llm_client", "llm_client.py")

# Patch the virtual package so relative imports in recommender.py resolve
_er_pkg.prompts = _prompts_mod
_er_pkg.llm_client = _llm_mod

# Now load recommender (its `from .llm_client` / `from .prompts` will find our mods)
_rec_spec = importlib.util.spec_from_file_location(
    "er_app.recommender", _er_app / "recommender.py",
    submodule_search_locations=[],
)
_rec_mod = importlib.util.module_from_spec(_rec_spec)
sys.modules["er_app.recommender"] = _rec_mod
_rec_spec.loader.exec_module(_rec_mod)

recommend = _rec_mod.recommend
_is_ranking_consistent = _rec_mod._is_ranking_consistent
_build_ranked_fallback = _rec_mod._build_ranked_fallback


SAMPLE_RESULTS = [
    {
        "app": {
            "id": "app-001",
            "title": "SmartEnergy Monitor",
            "description": "Real-time energy consumption monitoring.",
            "tags": ["energy", "monitoring"],
            "saref_type": "Energy",
        },
        "score": 0.92,
        "vector_score": 0.95,
        "keyword_score": 0.85,
        "saref_boost": 1.0,
    },
    {
        "app": {
            "id": "app-038",
            "title": "SolarPanel Optimizer",
            "description": "Optimize solar panel output.",
            "tags": ["energy", "solar"],
            "saref_type": "Energy",
        },
        "score": 0.81,
        "vector_score": 0.88,
        "keyword_score": 0.70,
        "saref_boost": 1.0,
    },
]


class TestRecommendPipeline:
    """End-to-end recommendation pipeline tests."""

    @patch.object(_rec_mod, "httpx")
    @patch.object(_rec_mod, "OllamaClient")
    def test_recommend_returns_message_and_apps(self, mock_llm_class, mock_httpx):
        """Full pipeline should return both message and apps."""
        # Mock search response
        mock_search_resp = MagicMock()
        mock_search_resp.status_code = 200
        mock_search_resp.json.return_value = {"results": SAMPLE_RESULTS}
        mock_search_resp.raise_for_status = MagicMock()
        mock_httpx.post.return_value = mock_search_resp

        # Mock LLM response
        mock_llm = MagicMock()
        mock_llm.chat.return_value = (
            "Here are the top matches: 1. **SmartEnergy Monitor** monitors energy. "
            "2. **SolarPanel Optimizer** optimizes solar output."
        )
        mock_llm_class.return_value = mock_llm

        result = recommend(query="energy monitoring", top_k=2)

        assert "message" in result
        assert "apps" in result
        assert len(result["apps"]) == 2
        assert result["apps"][0]["score"] >= result["apps"][1]["score"]

    @patch.object(_rec_mod, "httpx")
    def test_recommend_no_results(self, mock_httpx):
        """When search returns nothing, pipeline should return helpful message."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status = MagicMock()
        mock_httpx.post.return_value = mock_resp

        result = recommend(query="quantum teleportation apps")

        assert "apps" in result
        assert len(result["apps"]) == 0
        assert "couldn't find" in result["message"].lower() or "no" in result["message"].lower()

    @patch.object(_rec_mod, "httpx")
    @patch.object(_rec_mod, "OllamaClient")
    def test_ranking_consistency_fallback(self, mock_llm_class, mock_httpx):
        """When LLM contradicts ranking, deterministic fallback should be used."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": SAMPLE_RESULTS}
        mock_resp.raise_for_status = MagicMock()
        mock_httpx.post.return_value = mock_resp

        # LLM says App 2 is best (contradicts ranking)
        mock_llm = MagicMock()
        mock_llm.chat.return_value = (
            "I recommend starting with **SolarPanel Optimizer** as the best match."
        )
        mock_llm_class.return_value = mock_llm

        result = recommend(query="energy monitoring", top_k=2)

        # Should use fallback which mentions App 1 as top
        assert result["message"].startswith("Start with **SmartEnergy Monitor**")

    @patch.object(_rec_mod, "httpx")
    @patch.object(_rec_mod, "OllamaClient")
    def test_llm_failure_returns_results_anyway(self, mock_llm_class, mock_httpx):
        """If LLM fails, results should still be returned with a generic message."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": SAMPLE_RESULTS}
        mock_resp.raise_for_status = MagicMock()
        mock_httpx.post.return_value = mock_resp

        mock_llm = MagicMock()
        mock_llm.chat.side_effect = ConnectionError("Ollama unreachable")
        mock_llm_class.return_value = mock_llm

        result = recommend(query="energy monitoring", top_k=2)

        assert len(result["apps"]) == 2
        assert result["message"]  # Some fallback message


class TestRankingConsistency:
    """Test the ranking consistency checker directly."""

    def test_consistent_explanation_passes(self):
        assert _is_ranking_consistent(
            "The top match is **SmartEnergy Monitor** for energy use.",
            SAMPLE_RESULTS,
        )

    def test_contradictory_explanation_fails(self):
        assert not _is_ranking_consistent(
            "I recommend starting with **SolarPanel Optimizer** as best.",
            SAMPLE_RESULTS,
        )

    def test_no_ranking_claims_passes(self):
        assert _is_ranking_consistent(
            "Here are two energy apps that may help.",
            SAMPLE_RESULTS,
        )

    def test_fallback_mentions_top_app(self):
        fallback = _build_ranked_fallback(SAMPLE_RESULTS)
        assert "SmartEnergy Monitor" in fallback
        assert "SolarPanel Optimizer" in fallback
