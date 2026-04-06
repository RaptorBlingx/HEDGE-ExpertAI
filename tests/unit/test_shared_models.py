"""Tests for shared Pydantic models."""

import pytest

from hedge_shared.models import (
    AppMetadata,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    SearchQuery,
    SearchResult,
)


class TestAppMetadata:
    def test_basic_creation(self):
        app = AppMetadata(
            id="app-001",
            title="Test App",
            description="A test application",
            tags=["test", "demo"],
        )
        assert app.id == "app-001"
        assert app.title == "Test App"
        assert len(app.tags) == 2

    def test_checksum_computed(self):
        app = AppMetadata(
            id="app-001",
            title="Test App",
            description="A test application",
            tags=["test"],
        )
        assert app.checksum is not None
        assert len(app.checksum) == 64  # SHA-256 hex digest

    def test_checksum_changes_with_data(self):
        app1 = AppMetadata(id="app-001", title="App A", description="Desc A", tags=[])
        app2 = AppMetadata(id="app-001", title="App B", description="Desc B", tags=[])
        assert app1.checksum != app2.checksum

    def test_to_index_text(self):
        app = AppMetadata(
            id="app-001",
            title="SmartEnergy",
            description="Energy monitoring",
            tags=["energy", "monitoring"],
        )
        text = app.to_index_text()
        assert "SmartEnergy" in text
        assert "Energy monitoring" in text
        assert "energy" in text

    def test_optional_fields_default(self):
        app = AppMetadata(id="app-001", title="T", description="D", tags=[])
        assert app.saref_class is None
        assert app.input_datasets == []
        assert app.output_datasets == []


class TestSearchQuery:
    def test_defaults(self):
        q = SearchQuery(query="test")
        assert q.top_k == 5
        assert q.filters is None

    def test_custom_top_k(self):
        q = SearchQuery(query="test", top_k=10)
        assert q.top_k == 10


class TestSearchResult:
    def test_creation(self):
        app = AppMetadata(id="app-001", title="T", description="D", tags=[])
        result = SearchResult(app=app, score=0.95)
        assert result.score == 0.95
        assert result.explanation is None


class TestChatRequest:
    def test_without_session(self):
        req = ChatRequest(message="hello")
        assert req.session_id is None

    def test_with_session(self):
        req = ChatRequest(session_id="abc-123", message="hello")
        assert req.session_id == "abc-123"


class TestHealthResponse:
    def test_creation(self):
        h = HealthResponse(status="ok", version="0.1.0")
        assert h.status == "ok"
