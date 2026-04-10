"""Tests for recommendation orchestrator."""

import importlib
import importlib.util
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys as _sys

# Set up the package structure so relative imports work
_app_dir = Path(__file__).parent.parent.parent / "services" / "expert-recommend" / "app"

# Create a fake parent package
_pkg = types.ModuleType("er_app")
_pkg.__path__ = [str(_app_dir)]
_pkg.__package__ = "er_app"
_sys.modules["er_app"] = _pkg

# Stub llm_client
_llm_mod = types.ModuleType("er_app.llm_client")
_llm_mod.OllamaClient = MagicMock()
_sys.modules["er_app.llm_client"] = _llm_mod

# Stub prompts - load real prompts module since it has no problematic imports
_prompts_path = _app_dir / "prompts.py"
_p_spec = importlib.util.spec_from_file_location("er_app.prompts", _prompts_path)
_prompts_mod = importlib.util.module_from_spec(_p_spec)
_prompts_mod.__package__ = "er_app"
_p_spec.loader.exec_module(_prompts_mod)
_sys.modules["er_app.prompts"] = _prompts_mod

# Load recommender with proper package context
_recommender_path = _app_dir / "recommender.py"
_spec = importlib.util.spec_from_file_location("er_app.recommender", _recommender_path,
                                                 submodule_search_locations=[])
_mod = importlib.util.module_from_spec(_spec)
_mod.__package__ = "er_app"
_spec.loader.exec_module(_mod)
_sys.modules["er_app.recommender"] = _mod

_is_ranking_consistent = _mod._is_ranking_consistent
_build_ranked_fallback = _mod._build_ranked_fallback
_ensure_ranking_consistency = _mod._ensure_ranking_consistency
_first_sentence = _mod._first_sentence


SAMPLE_RESULTS = [
    {
        "app": {"id": "app-001", "title": "SmartEnergy Monitor", "description": "Energy monitoring app.", "tags": ["energy"]},
        "score": 0.85,
    },
    {
        "app": {"id": "app-002", "title": "BuildingComfort Pro", "description": "HVAC system.", "tags": ["hvac"]},
        "score": 0.70,
    },
]


class TestIsRankingConsistent:
    def test_consistent_top_mention(self):
        explanation = "SmartEnergy Monitor is the top choice for energy monitoring."
        assert _is_ranking_consistent(explanation, SAMPLE_RESULTS) is True

    def test_inconsistent_wrong_app_called_top(self):
        explanation = "BuildingComfort Pro is the best option for your needs."
        assert _is_ranking_consistent(explanation, SAMPLE_RESULTS) is False

    def test_no_ranking_claim(self):
        # No "top" / "best" / "recommendation" words — should pass
        explanation = "SmartEnergy Monitor handles energy data. BuildingComfort Pro handles HVAC."
        assert _is_ranking_consistent(explanation, SAMPLE_RESULTS) is True

    def test_empty_explanation(self):
        assert _is_ranking_consistent("", SAMPLE_RESULTS) is True

    def test_empty_results(self):
        assert _is_ranking_consistent("Some text", []) is True

    def test_app_name_before_keyword(self):
        # App name appears BEFORE "top" keyword within 200 char window
        explanation = "SmartEnergy Monitor is the top pick for energy."
        assert _is_ranking_consistent(explanation, SAMPLE_RESULTS) is True

    def test_recommendation_keyword(self):
        explanation = "My recommendation is SmartEnergy Monitor for this use case."
        assert _is_ranking_consistent(explanation, SAMPLE_RESULTS) is True

    def test_start_with_keyword(self):
        explanation = "I suggest you start with SmartEnergy Monitor."
        assert _is_ranking_consistent(explanation, SAMPLE_RESULTS) is True

    def test_multiple_claims_all_consistent(self):
        explanation = "SmartEnergy Monitor is the best and top recommendation for energy monitoring."
        assert _is_ranking_consistent(explanation, SAMPLE_RESULTS) is True


class TestBuildRankedFallback:
    def test_contains_apps(self):
        fallback = _build_ranked_fallback(SAMPLE_RESULTS)
        assert "SmartEnergy Monitor" in fallback
        assert "BuildingComfort Pro" in fallback

    def test_ranking_order(self):
        fallback = _build_ranked_fallback(SAMPLE_RESULTS)
        pos1 = fallback.index("SmartEnergy Monitor")
        pos2 = fallback.index("BuildingComfort Pro")
        assert pos1 < pos2

    def test_recommendation_line(self):
        fallback = _build_ranked_fallback(SAMPLE_RESULTS)
        assert fallback.startswith("Start with **SmartEnergy Monitor**")

    def test_bullet_list(self):
        fallback = _build_ranked_fallback(SAMPLE_RESULTS)
        assert "- **App 1: SmartEnergy Monitor**" in fallback
        assert "- **App 2: BuildingComfort Pro**" in fallback


class TestEnsureRankingConsistency:
    def test_consistent_kept(self):
        explanation = "SmartEnergy Monitor is the top choice."
        result = _ensure_ranking_consistency(explanation, SAMPLE_RESULTS)
        assert result == explanation

    def test_inconsistent_replaced(self):
        explanation = "BuildingComfort Pro is the best option for your needs."
        result = _ensure_ranking_consistency(explanation, SAMPLE_RESULTS)
        assert result.startswith("Start with **SmartEnergy Monitor**")


class TestFirstSentence:
    def test_normal_sentence(self):
        assert _first_sentence("Energy monitoring app. Second sentence.") == "Energy monitoring app."

    def test_no_period(self):
        assert _first_sentence("Just some text") == "Just some text"

    def test_empty(self):
        assert _first_sentence("") == "No description available."

    def test_exclamation(self):
        # Function checks '.' before '!' so period wins here
        assert _first_sentence("Great app! Very useful.") == "Great app! Very useful."
        # Pure exclamation without period
        assert _first_sentence("Great app! Very useful") == "Great app!"
