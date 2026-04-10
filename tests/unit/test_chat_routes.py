"""Tests for chat-intent streaming routes."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


_app_dir = Path(__file__).parent.parent.parent / "services" / "chat-intent" / "app"

_pkg = types.ModuleType("ci_app")
_pkg.__path__ = [str(_app_dir)]
_pkg.__package__ = "ci_app"
sys.modules["ci_app"] = _pkg

_classifier_mod = types.ModuleType("ci_app.classifier")
_classifier_mod.classify = MagicMock()
sys.modules["ci_app.classifier"] = _classifier_mod

_session_mod = types.ModuleType("ci_app.session")
for _name in [
    "delete_session",
    "get_feedback_stats",
    "get_or_create_session",
    "get_session",
    "get_session_feedback",
    "record_feedback",
    "update_session",
]:
    setattr(_session_mod, _name, MagicMock())
sys.modules["ci_app.session"] = _session_mod

_routes_path = _app_dir / "routes.py"
_spec = importlib.util.spec_from_file_location(
    "ci_app.routes", _routes_path,
    submodule_search_locations=[],
)
_mod = importlib.util.module_from_spec(_spec)
_mod.__package__ = "ci_app"
sys.modules["ci_app.routes"] = _mod
_spec.loader.exec_module(_mod)

ChatRequest = _mod.ChatRequest


async def _collect_stream_body(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    return "".join(chunks)


class TestChatStreamRoutes:
    def test_detail_intent_streams_explanation_and_apps(self):
        request = ChatRequest(session_id="sess-123", message="tell me about app-001")
        detail_result = SimpleNamespace(
            intent="detail",
            confidence=0.95,
            entities={"app_id": "app-001"},
        )
        detail_apps = [{"app": {"id": "app-001", "title": "SmartEnergy Monitor"}, "score": 1.0}]

        with patch.object(_mod, "get_or_create_session", return_value=("sess-123", [])), \
             patch.object(_mod, "classify", return_value=detail_result), \
             patch.object(_mod, "_handle_detail_async", new=AsyncMock(return_value=("Detailed explanation", detail_apps))) as mock_detail, \
             patch.object(_mod, "update_session") as mock_update:
            response = asyncio.run(_mod.chat_stream(request))
            body = asyncio.run(_collect_stream_body(response))

        assert '"type": "apps"' in body
        assert "Detailed explanation" in body
        assert '"type": "done"' in body
        mock_detail.assert_awaited_once_with("tell me about app-001", "app-001")
        mock_update.assert_called_once()