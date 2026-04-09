"""Tests for Ollama LLM client."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys as _sys

_llm_path = Path(__file__).parent.parent.parent / "services" / "expert-recommend" / "app" / "llm_client.py"
_spec = importlib.util.spec_from_file_location("expert_recommend_llm_client", _llm_path)
_mod = importlib.util.module_from_spec(_spec)
_sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

OllamaClient = _mod.OllamaClient


class TestBuildPayload:
    def test_structure(self):
        client = OllamaClient(base_url="http://test:11434", model="test-model")
        messages = [{"role": "user", "content": "hello"}]
        payload = client._build_payload(messages, temperature=0.3, max_tokens=150, stream=False)

        assert payload["model"] == "test-model"
        assert payload["messages"] == messages
        assert payload["stream"] is False
        assert payload["think"] is False
        assert payload["keep_alive"] == -1
        assert payload["options"]["temperature"] == 0.3
        assert payload["options"]["num_predict"] == 150
        assert payload["options"]["num_ctx"] == 1024

    def test_stream_true(self):
        client = OllamaClient()
        payload = client._build_payload(
            [{"role": "user", "content": "hi"}],
            temperature=0.5,
            max_tokens=100,
            stream=True,
        )
        assert payload["stream"] is True

    def test_think_always_false(self):
        client = OllamaClient()
        payload = client._build_payload(
            [{"role": "user", "content": "test"}],
            temperature=0.3,
            max_tokens=150,
            stream=False,
        )
        assert payload["think"] is False


class TestChat:
    def test_successful_response(self):
        client = OllamaClient(base_url="http://test:11434")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Hello! I'm an AI assistant."}
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response) as mock_post:
            result = client.chat([{"role": "user", "content": "hello"}])

        assert "Hello" in result
        mock_post.assert_called_once()

    def test_strips_think_tags(self):
        client = OllamaClient(base_url="http://test:11434")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "<think>internal reasoning</think>The answer is 42."}
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response):
            result = client.chat([{"role": "user", "content": "what is 6*7?"}])

        assert "<think>" not in result
        assert "The answer is 42." in result

    def test_retries_on_connect_error(self):
        import httpx as _httpx

        client = OllamaClient(base_url="http://test:11434")

        mock_success = MagicMock()
        mock_success.json.return_value = {"message": {"content": "OK"}}
        mock_success.raise_for_status = MagicMock()

        with patch("httpx.post", side_effect=[_httpx.ConnectError("fail"), mock_success]):
            with patch("time.sleep"):
                result = client.chat([{"role": "user", "content": "hi"}])
        assert result == "OK"

    def test_raises_after_max_retries(self):
        import httpx as _httpx

        client = OllamaClient(base_url="http://test:11434")
        with patch("httpx.post", side_effect=_httpx.ConnectError("fail")):
            with patch("time.sleep"):
                with pytest.raises(ConnectionError, match="unreachable"):
                    client.chat([{"role": "user", "content": "hi"}])


class TestWarmup:
    def test_warmup_sends_request(self):
        client = OllamaClient(base_url="http://test:11434", model="test-model")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            client.warmup()

        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["model"] == "test-model"
        assert payload["options"]["num_predict"] == 1
        assert payload["think"] is False

    def test_warmup_handles_failure(self):
        client = OllamaClient(base_url="http://test:11434")
        with patch("httpx.post", side_effect=Exception("connection refused")):
            # Should not raise
            client.warmup()


class TestIsHealthy:
    def test_healthy(self):
        client = OllamaClient(base_url="http://test:11434")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("httpx.get", return_value=mock_resp):
            assert client.is_healthy() is True

    def test_unhealthy(self):
        client = OllamaClient(base_url="http://test:11434")
        with patch("httpx.get", side_effect=Exception("fail")):
            assert client.is_healthy() is False
