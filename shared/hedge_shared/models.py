"""Pydantic models shared across all HEDGE-ExpertAI services."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field


class AppMetadata(BaseModel):
    """Metadata for a single HEDGE-IoT App Store application."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    saref_class: str | None = Field(default=None, alias="saref_type")
    input_datasets: list[str] = Field(default_factory=list)
    output_datasets: list[str] = Field(default_factory=list)
    version: str = "1.0.0"
    publisher: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def checksum(self) -> str:
        """SHA-256 of the serialized core fields for change detection."""
        payload = json.dumps(
            {
                "id": self.id,
                "title": self.title,
                "description": self.description,
                "tags": sorted(self.tags),
                "saref_class": self.saref_class,
                "input_datasets": sorted(self.input_datasets),
                "output_datasets": sorted(self.output_datasets),
                "version": self.version,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_index_text(self) -> str:
        """Combine fields into a single string for embedding."""
        parts = [self.title, self.description]
        if self.tags:
            parts.append(" ".join(self.tags))
        if self.saref_class:
            parts.append(f"SAREF: {self.saref_class}")
        if self.input_datasets:
            parts.append(f"Inputs: {', '.join(self.input_datasets)}")
        if self.output_datasets:
            parts.append(f"Outputs: {', '.join(self.output_datasets)}")
        return " . ".join(parts)


class SearchQuery(BaseModel):
    """A search request."""

    query: str
    filters: dict[str, Any] | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    """A single search result with score and optional explanation."""

    app: AppMetadata
    score: float = Field(ge=0.0, le=1.0)
    explanation: str | None = None


class ChatMessage(BaseModel):
    """A single message in a chat session."""

    role: str = Field(pattern=r"^(user|assistant|system)$")
    content: str


class ChatRequest(BaseModel):
    """Incoming chat request from the frontend."""

    session_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    """Chat response sent back to the frontend."""

    session_id: str
    message: str
    apps: list[SearchResult] = Field(default_factory=list)
    intent: str = "unknown"


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    service: str = ""
    version: str = "0.1.0"


class IngestStatus(BaseModel):
    """Status of the last ingestion run."""

    last_run: datetime | None = None
    apps_indexed: int = 0
    apps_updated: int = 0
    apps_deleted: int = 0
    status: str = "idle"


class RecommendRequest(BaseModel):
    """Request for LLM-powered recommendation."""

    query: str
    search_results: list[SearchResult] = Field(default_factory=list)
    session_id: str | None = None
