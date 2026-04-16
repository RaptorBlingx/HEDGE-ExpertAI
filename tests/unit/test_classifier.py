"""Tests for keyword-based intent classifier."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

import sys as _sys

_classifier_path = Path(__file__).parent.parent.parent / "services" / "chat-intent" / "app" / "classifier.py"
_spec = importlib.util.spec_from_file_location("chat_intent_classifier", _classifier_path)
_mod = importlib.util.module_from_spec(_spec)
_sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

classify = _mod.classify


class TestClassifier:
    """Test intent classification accuracy."""

    # --- Greeting ---
    @pytest.mark.parametrize("text", ["hi", "hello", "hey", "Hello!", "good morning", "Hi!"])
    def test_greeting(self, text):
        result = classify(text)
        assert result.intent == "greeting"

    # --- Help ---
    @pytest.mark.parametrize(
        "text",
        [
            "help",
            "what can you do",
            "how do I use this",
            "I need help",
        ],
    )
    def test_help(self, text):
        result = classify(text)
        assert result.intent == "help"

    # --- Search ---
    @pytest.mark.parametrize(
        "text",
        [
            "find apps for energy monitoring",
            "I need a smart irrigation solution",
            "search for building automation",
            "show me environmental sensors",
            "recommend IoT apps for water management",
            "looking for traffic optimization",
        ],
    )
    def test_search(self, text):
        result = classify(text)
        assert result.intent == "search"

    # --- Detail ---
    @pytest.mark.parametrize(
        "text",
        [
            "tell me about app-001",
            "what does SmartEnergy do",
            "details of this app",
            "explain app-005",
        ],
    )
    def test_detail(self, text):
        result = classify(text)
        assert result.intent == "detail"

    # --- App ID extraction ---
    def test_app_id_extraction(self):
        result = classify("tell me about app-001")
        assert result.entities.get("app_id") == "app-001"

    def test_saref_class_extraction(self):
        result = classify("find apps for energy monitoring")
        assert result.entities.get("saref_class") == "Energy"

    # --- Unknown / fallback ---
    def test_empty_input(self):
        result = classify("")
        assert result.intent == "unknown"

    def test_short_unknown(self):
        result = classify("ok")
        assert result.intent == "unknown"

    # --- Long input defaults to search ---
    def test_long_input_defaults_to_search(self):
        result = classify("something about weather and climate data analysis")
        assert result.intent == "search"


class TestRasaFallback:
    def setup_method(self):
        _mod._RASA_CONSECUTIVE_FAILURES = 0
        _mod._RASA_CIRCUIT_OPEN_UNTIL = 0.0

    def test_rasa_high_confidence_used(self, monkeypatch):
        monkeypatch.setenv("RASA_ENABLED", "true")
        monkeypatch.setenv("RASA_CONFIDENCE_THRESHOLD", "0.6")

        with patch.object(
            _mod,
            "_request_rasa_parse",
            return_value={"intent": {"name": "help", "confidence": 0.91}, "entities": []},
        ):
            result = classify("find apps for energy monitoring")

        assert result.intent == "help"

    def test_rasa_low_confidence_falls_back(self, monkeypatch):
        monkeypatch.setenv("RASA_ENABLED", "true")
        monkeypatch.setenv("RASA_CONFIDENCE_THRESHOLD", "0.8")

        with patch.object(
            _mod,
            "_request_rasa_parse",
            return_value={"intent": {"name": "help", "confidence": 0.41}, "entities": []},
        ):
            result = classify("find apps for energy monitoring")

        assert result.intent == "search"

    def test_rasa_shadow_mode_keeps_regex_result(self, monkeypatch):
        monkeypatch.setenv("RASA_ENABLED", "true")
        monkeypatch.setenv("RASA_SHADOW_MODE", "true")

        with patch.object(
            _mod,
            "_request_rasa_parse",
            return_value={"intent": {"name": "help", "confidence": 0.99}, "entities": []},
        ):
            result = classify("find apps for energy monitoring")

        assert result.intent == "search"

    def test_rasa_failure_opens_circuit_after_three_errors(self, monkeypatch):
        monkeypatch.setenv("RASA_ENABLED", "true")
        monkeypatch.setenv("RASA_CIRCUIT_OPEN_SECONDS", "60")

        with patch.object(_mod, "_request_rasa_parse", side_effect=TimeoutError("boom")) as mock_request:
            for _ in range(4):
                result = classify("find apps for energy monitoring")
                assert result.intent == "search"

        assert mock_request.call_count == 3
        assert _mod._RASA_CIRCUIT_OPEN_UNTIL > 0
