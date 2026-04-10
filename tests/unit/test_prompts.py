"""Tests for LLM prompt templates."""

import importlib.util
from pathlib import Path

import pytest

import sys as _sys

_prompts_path = Path(__file__).parent.parent.parent / "services" / "expert-recommend" / "app" / "prompts.py"
_spec = importlib.util.spec_from_file_location("expert_recommend_prompts", _prompts_path)
_mod = importlib.util.module_from_spec(_spec)
_sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

SYSTEM_PROMPT = _mod.SYSTEM_PROMPT
build_explanation_messages = _mod.build_explanation_messages
build_recommendation_messages = _mod.build_recommendation_messages
format_apps_context = _mod.format_apps_context


class TestPrompts:
    def test_system_prompt_not_empty(self):
        assert len(SYSTEM_PROMPT) > 50

    def test_system_prompt_mentions_hedge(self):
        assert "HEDGE" in SYSTEM_PROMPT

    def test_format_apps_context(self):
        apps = [
            {
                "app": {
                    "title": "TestApp",
                    "description": "A test",
                    "tags": ["t1", "t2"],
                    "saref_type": "Energy",
                    "input_datasets": ["in1"],
                    "output_datasets": ["out1"],
                },
                "score": 0.85,
            }
        ]
        text = format_apps_context(apps)
        assert "TestApp" in text
        assert "t1" in text
        assert "0.85" in text

    def test_build_recommendation_messages(self):
        apps = [
            {
                "app": {"title": "App1", "description": "D1", "tags": [], "saref_type": None, "input_datasets": [], "output_datasets": []},
                "score": 0.9,
            }
        ]
        messages = build_recommendation_messages("test query", apps)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "test query" in messages[1]["content"]
        assert "markdown bullet points" in messages[1]["content"]
        assert "Do not use numbered lists" in messages[1]["content"]

    def test_build_explanation_messages(self):
        app = {"title": "App1", "description": "D1", "tags": ["a"], "saref_type": "Energy", "input_datasets": ["i"], "output_datasets": ["o"]}
        messages = build_explanation_messages("what does it do", app)
        assert len(messages) == 2
        assert "App1" in messages[1]["content"]
