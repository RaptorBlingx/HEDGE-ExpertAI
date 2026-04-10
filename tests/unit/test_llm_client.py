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


class _MockStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        return None

    def iter_lines(self):
        return iter(self._lines)


class _MockStreamContext:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self._response

    def __exit__(self, exc_type, exc, tb):
        return False


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
    def test_default_max_tokens_is_250(self):
        client = OllamaClient(base_url="http://test:11434")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "Hello!"},
            "done_reason": "stop",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response) as mock_post:
            client.chat([{"role": "user", "content": "hello"}])

        payload = mock_post.call_args.kwargs["json"]
        assert payload["options"]["num_predict"] == 250

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

    def test_continues_once_when_output_limit_hit(self):
        client = OllamaClient(base_url="http://test:11434")

        first_response = MagicMock()
        first_response.json.return_value = {
            "message": {"content": "App 1: SmartEnergy Monitor\n\n**App"},
            "done_reason": "length",
            "eval_count": 250,
        }
        first_response.raise_for_status = MagicMock()

        second_response = MagicMock()
        second_response.json.return_value = {
            "message": {"content": " 4:** BuildingComfort Pro"},
            "done_reason": "stop",
            "eval_count": 12,
        }
        second_response.raise_for_status = MagicMock()

        with patch("httpx.post", side_effect=[first_response, second_response]) as mock_post:
            result = client.chat([{"role": "user", "content": "find energy apps"}])

        assert "BuildingComfort Pro" in result
        assert mock_post.call_count == 2
        second_payload = mock_post.call_args_list[1].kwargs["json"]
        assert "cut off by the output token limit" in second_payload["messages"][-1]["content"]


class TestChatStream:
    def test_stream_continues_once_when_output_limit_hit(self):
        client = OllamaClient(base_url="http://test:11434")

        first_stream = _MockStreamContext(
            _MockStreamResponse(
                [
                    json.dumps({"message": {"content": "Hello "}, "done": False}),
                    json.dumps({"message": {"content": "world"}, "done": False}),
                    json.dumps({"message": {"content": ""}, "done": True, "done_reason": "length", "eval_count": 250}),
                ]
            )
        )
        second_stream = _MockStreamContext(
            _MockStreamResponse(
                [
                    json.dumps({"message": {"content": "!"}, "done": False}),
                    json.dumps({"message": {"content": ""}, "done": True, "done_reason": "stop", "eval_count": 1}),
                ]
            )
        )

        with patch("httpx.stream", side_effect=[first_stream, second_stream]) as mock_stream:
            chunks = list(client.chat_stream([{"role": "user", "content": "hello"}]))

        assert "".join(chunks) == "Hello world!"
        assert mock_stream.call_count == 2


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
