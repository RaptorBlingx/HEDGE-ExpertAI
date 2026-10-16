"""Conversational source selection cannot author facts or cut qualifications."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts.store_v1_playground import load_service

answers = load_service("unit_contextual_expert", "expert-recommend")("store_answers")
RESULTS = [{"rank": 1, "app": {"id": "local", "app_id": "native", "name": "Sensor App",
    "source_evidence": {"description": "Collects readings. Production requires a licence.",
                        "readme": "MQTT works only in simulation. It is disabled in production.",
                        "price": "0", "billable": "false"}, "readme_status": "extracted"}}]


def run(monkeypatch, value=None, error=None, results=RESULTS):
    call = Mock(return_value=json.dumps(value or {"apps": [{"rank": 1, "paths": ["description"]}]}), side_effect=error)
    monkeypatch.setattr(answers, "OllamaClient", lambda: SimpleNamespace(model="qwen3.5:2b", chat_structured=call))
    fallback = answers.render("Describe it", results, "en")
    return answers.respond("Describe it", results, "en", "detail", fallback), call


def test_model_selection_preserves_neighboring_and_cross_field_qualifications(monkeypatch):
    result, call = run(monkeypatch)
    assert result["generation"]["source"] == "ollama"
    assert "Production requires a licence." in result["message"]
    assert "It is disabled in production." in result["message"]
    assert "[description]" in result["message"] and "[readme]" in result["message"]
    assert "[price]" not in result["message"] and "[billable]" not in result["message"]
    call.assert_called_once()


@pytest.mark.parametrize("value", [
    {"apps": [{"rank": 1, "paths": ["currency"]}]},
    {"apps": [{"rank": 2, "paths": ["description"]}]},
    {"apps": [{"rank": 1, "paths": ["description"], "claim": "Certified and free"}]},
    {"apps": [{"rank": 1, "paths": ["description", "description"]}]},
    {"apps": [{"rank": True, "paths": []}]},
])
def test_invalid_or_invented_generation_uses_readable_fallback(monkeypatch, value):
    result, _ = run(monkeypatch, value)
    assert result["generation"]["source"] == "deterministic"
    assert "Production requires a licence." in result["message"]
    assert "Certified and free" not in result["message"]


def test_model_failure_does_not_leak_errors_or_prevent_answer(monkeypatch):
    result, _ = run(monkeypatch, error=TimeoutError("private text"))
    assert result["generation"]["reason"] == "model_unavailable_or_timeout"
    assert "private text" not in json.dumps(result)
    assert "[description]" in result["message"]


@pytest.mark.parametrize("size", [1200, 1201, 16000])
def test_long_evidence_is_whole_or_explicitly_incomplete(size):
    source = "x" * (size - 26) + " Production is unsupported."
    results = [{"rank": 1, "app": {"app_id": "native", "source_evidence": {"description": source}}}]
    text = answers.render("Describe it", results, "en")
    if len(source) <= 1200:
        assert source in text
    else:
        assert "Incomplete evidence" in text and source[:100] not in text


@pytest.mark.parametrize("status", ["missing", "too_large", "malformed", "unsupported_shape", "no_supported_text", "not_projected"])
def test_extraction_status_is_not_misrepresented_as_source_absence(status):
    text = answers.render("Describe it", [{"rank": 1, "app": {"app_id": "native", "readme_status": status}}], "en")
    assert f"README: {status}" in text
    assert "not proof of source absence" in text


def test_unknown_aspect_never_turns_model_selection_into_capability_claim(monkeypatch):
    result, _ = run(monkeypatch, {"apps": [{"rank": 1, "paths": []}]})
    assert "not verified" in result["message"]
    assert "It is disabled in production." in result["message"]
