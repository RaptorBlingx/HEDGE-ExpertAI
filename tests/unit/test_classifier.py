"""Tests for keyword-based intent classifier."""

import importlib.util
from pathlib import Path

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
