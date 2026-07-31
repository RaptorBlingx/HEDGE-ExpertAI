"""Strict, versioned public contracts for the production catalogue API."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
    field_validator,
    model_validator,
)

SUPPORTED_LOCALES = ("en", "de", "fr", "es", "it", "nl", "pt", "tr")
Locale = Literal["en", "de", "fr", "es", "it", "nl", "pt", "tr"]
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    ),
]


class StrictModel(BaseModel):
    """Base contract that rejects unknown fields."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)


class LocalizedText(StrictModel):
    """Required English text plus provisional or reviewed translations."""

    en: NonEmptyString
    de: NonEmptyString | None = None
    fr: NonEmptyString | None = None
    es: NonEmptyString | None = None
    it: NonEmptyString | None = None
    nl: NonEmptyString | None = None
    pt: NonEmptyString | None = None
    tr: NonEmptyString | None = None

    def for_locale(self, locale: str) -> str:
        """Return requested locale, falling back to English."""
        return getattr(self, locale, None) or self.en


class Publisher(StrictModel):
    """Application publisher identity and support channels."""

    name: NonEmptyString
    website: AnyHttpUrl | None = None
    support_url: AnyHttpUrl | None = None
    contact: str | None = Field(default=None, max_length=254)


class LifecycleStatus(StrEnum):
    """Supported application lifecycle states."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class Lifecycle(StrictModel):
    """Version and lifecycle information for an app revision."""

    version: NonEmptyString = "1.0.0"
    status: LifecycleStatus = LifecycleStatus.ACTIVE
    released_at: datetime | None = None
    updated_at: datetime | None = None
    deprecated_at: datetime | None = None
    replaced_by: Identifier | None = None


class DataContract(StrictModel):
    """Typed input or output exposed by an application."""

    name: NonEmptyString
    description: str = Field(default="", max_length=1000)
    media_type: NonEmptyString = "application/json"
    schema_uri: AnyHttpUrl | None = None
    unit_uri: AnyHttpUrl | None = None
    frequency: str | None = Field(default=None, max_length=100)
    data_classification: Literal[
        "public",
        "internal",
        "confidential",
        "personal",
        "sensitive",
    ] = "internal"


class DeploymentProfile(StrictModel):
    """Where an app runs and its minimum edge footprint."""

    modes: list[Literal["edge", "cloud", "hybrid", "on-premises"]] = Field(min_length=1)
    platforms: list[str] = Field(default_factory=list)
    minimum_cpu_cores: float = Field(default=0.5, gt=0, le=128)
    minimum_memory_mb: int = Field(default=256, ge=32, le=1_048_576)
    architectures: list[Literal["amd64", "arm64", "armv7"]] = Field(
        default_factory=lambda: ["amd64"]
    )
    regions: list[str] = Field(default_factory=list)


class TrustProfile(StrictModel):
    """Machine-readable commercial, privacy, security, and support facts."""

    license_spdx: NonEmptyString
    pricing_model: Literal[
        "free",
        "open-source",
        "subscription",
        "usage-based",
        "contact-vendor",
    ]
    authentication: list[str] = Field(default_factory=list)
    data_residency: list[str] = Field(default_factory=list)
    privacy_summary: str = Field(default="", max_length=2000)
    security_features: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    support_tier: str = Field(default="community", max_length=100)
    sla_summary: str | None = Field(default=None, max_length=500)


class SemanticAnnotation(StrictModel):
    """A reviewed or inferred URI-level semantic assertion."""

    term_uri: AnyHttpUrl
    label: NonEmptyString
    ontology_uri: AnyHttpUrl
    ontology_version: NonEmptyString
    relation: Literal[
        "domain",
        "capability",
        "device-kind",
        "feature-kind",
        "property",
        "state",
        "function",
        "command",
    ]
    provenance: Literal["publisher", "curated", "inferred"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    review_status: Literal["unreviewed", "reviewed", "approved", "rejected"] = "unreviewed"
    reviewed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_confidence(self) -> SemanticAnnotation:
        """Confidence is meaningful only for inferred assertions."""
        if self.provenance == "inferred" and self.confidence is None:
            raise ValueError("inferred annotations require confidence")
        if self.provenance != "inferred" and self.confidence is not None:
            raise ValueError("confidence is only allowed for inferred annotations")
        if self.review_status in {"reviewed", "approved", "rejected"} and self.reviewed_at is None:
            raise ValueError("reviewed annotations require reviewed_at")
        return self


class Provenance(StrictModel):
    """Source and review provenance for catalogue metadata."""

    synthetic: bool
    source: NonEmptyString
    source_version: NonEmptyString
    generated_by: str | None = Field(default=None, max_length=200)
    license_spdx: NonEmptyString
    review_status: Literal["unreviewed", "reviewed", "approved", "rejected"]
    reviewed_at: datetime | None = None


class AppMetadataV2(StrictModel):
    """Production catalogue contract used by v2 APIs and durable storage."""

    schema_version: Literal["2.0"] = "2.0"
    id: Identifier
    slug: Identifier
    title: LocalizedText
    summary: LocalizedText
    description: NonEmptyString
    localized_keywords: dict[Locale, list[str]]
    publisher: Publisher
    lifecycle: Lifecycle
    app_url: AnyHttpUrl
    documentation_url: AnyHttpUrl
    icon_url: AnyHttpUrl | None = None
    screenshot_urls: list[AnyHttpUrl] = Field(default_factory=list)
    tags: list[str] = Field(min_length=1)
    domains: list[str] = Field(min_length=1)
    capabilities: list[str] = Field(min_length=1)
    industries: list[str] = Field(min_length=1)
    supported_languages: list[Locale] = Field(min_length=1)
    protocols: list[str] = Field(default_factory=list)
    standards: list[str] = Field(default_factory=list)
    deployment: DeploymentProfile
    inputs: list[DataContract] = Field(default_factory=list)
    outputs: list[DataContract] = Field(default_factory=list)
    trust: TrustProfile
    semantic_annotations: list[SemanticAnnotation] = Field(min_length=1)
    provenance: Provenance

    @field_validator(
        "tags",
        "domains",
        "capabilities",
        "industries",
        "protocols",
        "standards",
        mode="after",
    )
    @classmethod
    def normalize_unique_strings(cls, values: list[str]) -> list[str]:
        """Remove blanks and duplicates while preserving source order."""
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = value.strip()
            key = item.casefold()
            if item and key not in seen:
                normalized.append(item)
                seen.add(key)
        return normalized

    @field_validator("supported_languages", mode="after")
    @classmethod
    def normalize_languages(cls, values: list[Locale]) -> list[Locale]:
        """Keep supported locale identifiers unique."""
        return list(dict.fromkeys(values))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def checksum(self) -> str:
        """Stable SHA-256 for transactional change detection."""
        payload = self.model_dump(mode="json", exclude={"checksum"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def to_index_text(self, locale: str = "en") -> str:
        """Build a multilingual passage for lexical and vector indexing."""
        keywords = self.localized_keywords.get(locale) or self.localized_keywords.get("en", [])
        parts = [
            self.title.for_locale(locale),
            self.summary.for_locale(locale),
            self.description,
            " ".join(self.tags),
            " ".join(keywords),
            " ".join(self.domains),
            " ".join(self.capabilities),
            " ".join(self.protocols),
            " ".join(contract.name for contract in [*self.inputs, *self.outputs]),
            " ".join(annotation.label for annotation in self.semantic_annotations),
        ]
        return " . ".join(part for part in parts if part)

    def to_legacy_dict(self) -> dict[str, object]:
        """Return the one-release v1 compatibility representation."""
        return {
            "id": self.id,
            "title": self.title.en,
            "description": self.description,
            "tags": self.tags,
            "saref_type": self.domains[0] if self.domains else None,
            "input_datasets": [item.name for item in self.inputs],
            "output_datasets": [item.name for item in self.outputs],
            "version": self.lifecycle.version,
            "publisher": self.publisher.name,
            "created_at": self.lifecycle.released_at,
            "updated_at": self.lifecycle.updated_at,
        }


class SearchFilters(StrictModel):
    """Typed public catalogue filters."""

    semantic_uri: AnyHttpUrl | None = None
    extension_uri: AnyHttpUrl | None = None
    publisher: str | None = Field(default=None, max_length=200)
    capabilities: list[str] = Field(default_factory=list, max_length=20)
    tags: list[str] = Field(default_factory=list, max_length=20)
    protocols: list[str] = Field(default_factory=list, max_length=20)
    deployment_modes: list[str] = Field(default_factory=list, max_length=10)
    license_spdx: str | None = Field(default=None, max_length=100)
    lifecycle_status: LifecycleStatus | None = None
    supported_languages: list[Locale] = Field(default_factory=list)
    data_classifications: list[str] = Field(default_factory=list, max_length=10)


class SearchRequestV2(StrictModel):
    """Versioned search request."""

    query: str = Field(min_length=1, max_length=500)
    locale: Locale = "en"
    filters: SearchFilters = Field(default_factory=SearchFilters)
    limit: int = Field(default=5, ge=1, le=20)
    cursor: str | None = Field(default=None, max_length=500)


class RelevanceBand(StrEnum):
    """Public, non-probabilistic relevance indicator."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SearchResultV2(StrictModel):
    """Public v2 result; fusion diagnostics are deliberately not exposed."""

    app: AppMetadataV2
    rank: int = Field(ge=1)
    relevance: RelevanceBand
    evidence_fields: list[str] = Field(default_factory=list)


class ChatRequestV2(StrictModel):
    """Versioned conversational search request."""

    session_id: str | None = Field(default=None, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    locale: Locale = "en"
    filters: SearchFilters = Field(default_factory=SearchFilters)


class ReindexRequestV2(StrictModel):
    """Administrative request for a versioned, atomically promoted index."""

    collection_name: str = Field(pattern=r"^hedge_apps_v2_[a-z0-9_-]{3,40}$")


class RecommendationEventType(StrEnum):
    """Allowed recommendation telemetry events."""

    ACCEPTED = "recommendation_accepted"
    DISMISSED = "recommendation_dismissed"
    APP_OPENED = "app_opened"


class RecommendationEventRequest(StrictModel):
    """Verified and replay-safe recommendation event."""

    impression_id: Identifier
    idempotency_key: Identifier
    event_type: RecommendationEventType
    app_id: Identifier | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_app_reference(self) -> RecommendationEventRequest:
        """Only app-open events carry an app identifier."""
        if self.event_type == RecommendationEventType.APP_OPENED and self.app_id is None:
            raise ValueError("app_id is required for app_opened")
        if self.event_type != RecommendationEventType.APP_OPENED and self.app_id is not None:
            raise ValueError("app_id is only allowed for app_opened")
        return self
