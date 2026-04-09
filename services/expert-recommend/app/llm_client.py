"""Ollama LLM client.

CRITICAL:
  - Always pass "think": false in API calls (Qwen3.5 non-thinking mode)
  - Strip any <think> tags from response as safety measure
  - Timeout: 180s for CPU inference with swap (qwen3.5:4b ~3 tok/s)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Iterator

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:2b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "180"))

_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class OllamaClient:
    """Client for Ollama /api/chat endpoint."""

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = OLLAMA_MODEL,
        timeout: int = OLLAMA_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def _build_payload(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> dict:
        """Build the Ollama API payload."""
        return {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "think": False,  # MUST always be false for Qwen3.5
            "keep_alive": -1,  # keep model loaded between requests
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 1024,
            },
        }

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 150,
    ) -> str:
        """Send a chat request to Ollama and return the response text."""
        payload = self._build_payload(messages, temperature, max_tokens, stream=False)

        last_exc = None
        for attempt in range(3):
            try:
                start = time.monotonic()
                resp = httpx.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                elapsed = time.monotonic() - start
                logger.info("Ollama response in %.1fs (attempt %d)", elapsed, attempt + 1)

                data = resp.json()
                content = data.get("message", {}).get("content", "")

                # Safety: strip any <think> tags that may leak through
                content = _THINK_TAG_RE.sub("", content).strip()
                return content

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning(
                    "Ollama request failed (attempt %d): %s — retrying in %ds",
                    attempt + 1, exc, wait,
                )
                time.sleep(wait)
            except httpx.HTTPStatusError as exc:
                logger.error("Ollama HTTP error: %s", exc)
                raise

        raise ConnectionError(f"Ollama unreachable after 3 attempts: {last_exc}")

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 150,
    ) -> Iterator[str]:
        """Stream a chat response from Ollama, yielding content chunks."""
        payload = self._build_payload(messages, temperature, max_tokens, stream=True)
        with httpx.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                chunk = data.get("message", {}).get("content", "")
                if chunk:
                    yield chunk

    def is_healthy(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    def warmup(self) -> None:
        """Send a minimal request to ensure the model is loaded in memory."""
        try:
            resp = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                    "think": False,
                    "keep_alive": -1,
                    "options": {"num_predict": 1, "num_ctx": 128},
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            logger.info("Ollama model %s warmed up", self.model)
        except Exception:
            logger.warning("Ollama warmup failed — model will load on first request")
