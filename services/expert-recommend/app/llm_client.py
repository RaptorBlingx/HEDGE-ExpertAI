"""Ollama LLM client.

CRITICAL:
    - Always pass "think": false in API calls (Qwen3.5 non-thinking mode)
    - Strip any <think> tags from response as safety measure
    - Timeout: 180s for CPU inference with swap (qwen3.5:4b ~3 tok/s)
    - If generation stops due to output length, request one continuation automatically
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
OLLAMA_MAX_TOKENS = int(os.getenv("OLLAMA_MAX_TOKENS", "250"))

_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_LENGTH_DONE_REASONS = {"length", "max_tokens"}
_MAX_CONTINUATIONS = 1
_CONTINUATION_SUFFIX_CHARS = 160


def _clean_content(text: str) -> str:
    """Strip any leaked think tags without disturbing other whitespace."""
    return _THINK_TAG_RE.sub("", text)


def _merge_content(existing: str, incoming: str) -> str:
    """Append streamed or continued content while removing simple overlaps."""
    if not existing:
        return incoming
    if not incoming:
        return existing

    max_overlap = min(len(existing), len(incoming), 120)
    for overlap in range(max_overlap, 0, -1):
        if existing[-overlap:] == incoming[:overlap]:
            return existing + incoming[overlap:]

    return existing + incoming


def _build_continuation_messages(
    messages: list[dict[str, str]],
    partial_response: str,
) -> list[dict[str, str]]:
    """Ask the model to resume exactly from the cutoff point."""
    suffix = partial_response[-_CONTINUATION_SUFFIX_CHARS:].strip()
    resume_prompt = (
        "Your previous answer was cut off by the output token limit. "
        "Continue immediately from the exact point where it stopped. "
        "Do not repeat or restart any earlier text. "
        "Return only the remaining continuation."
    )
    if suffix:
        resume_prompt += f"\n\nAlready-written suffix:\n{suffix}"

    return [
        *messages,
        {"role": "assistant", "content": partial_response},
        {"role": "user", "content": resume_prompt},
    ]


def _hit_output_limit(response_data: dict, requested_max_tokens: int) -> bool:
    """Detect whether generation ended because the output budget was exhausted."""
    done_reason = str(response_data.get("done_reason") or "").lower()
    if done_reason:
        return done_reason in _LENGTH_DONE_REASONS

    eval_count = response_data.get("eval_count")
    return isinstance(eval_count, int) and eval_count >= requested_max_tokens


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

    def _post_chat(self, payload: dict) -> dict:
        """Send a non-streaming chat request with retry handling."""
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
                return resp.json()

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

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = OLLAMA_MAX_TOKENS,
    ) -> str:
        """Send a chat request to Ollama and return the response text."""
        prompt_messages = messages
        accumulated = ""

        for continuation_idx in range(_MAX_CONTINUATIONS + 1):
            payload = self._build_payload(prompt_messages, temperature, max_tokens, stream=False)
            data = self._post_chat(payload)
            content = _clean_content(data.get("message", {}).get("content", ""))
            accumulated = _merge_content(accumulated, content)

            if not _hit_output_limit(data, max_tokens):
                return accumulated.strip()

            if continuation_idx == _MAX_CONTINUATIONS:
                logger.warning("Ollama response hit output limit after %d continuation(s)", _MAX_CONTINUATIONS)
                break

            logger.warning("Ollama response hit output limit (%d tokens); requesting continuation", max_tokens)
            prompt_messages = _build_continuation_messages(messages, accumulated)

        return accumulated.strip()

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = OLLAMA_MAX_TOKENS,
    ) -> Iterator[str]:
        """Stream a chat response from Ollama, yielding content chunks."""
        prompt_messages = messages
        accumulated = ""

        for continuation_idx in range(_MAX_CONTINUATIONS + 1):
            payload = self._build_payload(prompt_messages, temperature, max_tokens, stream=True)
            final_data: dict = {}
            segment = ""

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
                        segment += chunk
                        yield chunk

                    if data.get("done"):
                        final_data = data

            accumulated = _merge_content(accumulated, _clean_content(segment))
            if not _hit_output_limit(final_data, max_tokens):
                return

            if continuation_idx == _MAX_CONTINUATIONS:
                logger.warning("Ollama stream hit output limit after %d continuation(s)", _MAX_CONTINUATIONS)
                return

            logger.warning("Ollama stream hit output limit (%d tokens); requesting continuation", max_tokens)
            prompt_messages = _build_continuation_messages(messages, accumulated)

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
