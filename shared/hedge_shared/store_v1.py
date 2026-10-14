"""Sparse Store v1 source metadata, independent of ExpertAI's public v2 API."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    FiniteFloat,
    StrictBool,
    StrictStr,
    StringConstraints,
    computed_field,
    field_validator,
)


def _native_identifier(value: str) -> str:
    if value != value.strip():
        raise ValueError("native identifiers must be nonblank without surrounding whitespace")
    return value


NativeIdentifier = Annotated[
    StrictStr, StringConstraints(min_length=1), AfterValidator(_native_identifier)
]


def _date_input(value: object) -> object:
    if type(value) is int:
        # Store v1 uses milliseconds, never infer seconds from the magnitude.
        try:
            return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=value)
        except OverflowError:
            raise ValueError("registrationDate milliseconds are out of range") from None
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    if value is not None and not isinstance(value, datetime):
        raise ValueError("registrationDate must be an ISO date-time or integer milliseconds")
    return value


def _date_timezone(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("registrationDate must include a timezone")
    return value


StoreDate = Annotated[datetime, BeforeValidator(_date_input), AfterValidator(_date_timezone)]


# These are source claims, not compatibility, licensing or pricing guarantees.
STORE_APP_FIELDS = {
    "builtForConnector": "built_for_connector",
    "connectorVersion": "connector_version",
    "type": "app_type",
    "billable": "billable",
    "price": "price",
    "dataspaceAppDescription": "dataspace_app_description",
}
EVIDENCE_TEXT_LIMIT = 16_000
EMBEDDED_JSON_LIMIT = 65_536


class _SourceText(HTMLParser):
    """Extract visible text without rendering markup or following resources."""

    BLOCKED = {"script", "style", "iframe", "object", "svg", "template", "head"}
    SEPARATORS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
                  "table", "tr", "td", "th", "pre", "blockquote", "section", "hr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocked: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.BLOCKED:
            self.blocked.append(tag)
        if not self.blocked and tag in self.SEPARATORS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self.blocked and tag == self.blocked[-1]:
            self.blocked.pop()
        if not self.blocked and tag in self.SEPARATORS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.blocked:
            self.parts.append(data)


def _source_text(value: str) -> str:
    # Bound parser work as well as the derived evidence. Raw input stays local.
    if len(value) > EVIDENCE_TEXT_LIMIT:
        return ""  # Do not turn a truncated qualification into a complete source fact.
    parser = _SourceText()
    parser.feed(value)
    parser.close()
    return " ".join("".join(parser.parts).split())


def _unique_embedded_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate embedded key")
        result[key] = value
    return result


def _reject_embedded_constant(value: str) -> None:
    raise ValueError("non-finite embedded number")


def _dataspace_evidence(raw: str | None) -> tuple[str, dict[str, str]]:
    """Read only documented AssetProperties within this App; never join Assets.

    Do not repair Java-string/JSON-LD variants or interpret offers/dataAddress.
    Unsupported shapes stay in the raw source with an explicit status.
    """
    if raw is None:
        return "missing", {}
    if len(raw) > EMBEDDED_JSON_LIMIT:
        return "too_large", {}
    try:
        data = json.loads(raw, object_pairs_hook=_unique_embedded_object,
                          parse_constant=_reject_embedded_constant)
    except (ValueError, RecursionError):
        return "malformed", {}
    if not isinstance(data, dict) or not isinstance(data.get("properties"), dict):
        return "unsupported_shape", {}
    properties = data["properties"]
    evidence = {}
    for field in ("name", "description", "applicationCategory", "operatingSystem"):
        value = properties.get(field)
        if isinstance(value, str) and (text := _source_text(value)):
            evidence[f"dataspaceAppDescription.properties.{field}"] = text
    features = properties.get("featureList")
    if isinstance(features, list):
        for index, value in enumerate(features[:64]):
            if isinstance(value, str) and (text := _source_text(value)):
                evidence[f"dataspaceAppDescription.properties.featureList[{index}]"] = text
    return "extracted" if evidence else "no_supported_text", evidence


class StoreAppVersion(BaseModel):
    """Source versions in source order; no inferred current/latest version."""

    model_config = ConfigDict(extra="forbid")

    app_version_id: NativeIdentifier | None = None
    version: StrictStr | None = None
    registration_date: StoreDate | None = None
    comments: StrictStr | None = None


class StoreAppMetadata(BaseModel):
    """Normalized source projection, never a fabricated AppMetadataV2.

    Native identifiers are opaque and case-sensitive. The local key hashes an
    unambiguous ordered pair while retaining both native values for navigation.
    """

    model_config = ConfigDict(extra="forbid")

    registration_date: StoreDate | None = None
    source_profile: Literal["hedge-store-v1"] = "hedge-store-v1"
    store_id: NativeIdentifier
    app_id: NativeIdentifier
    name: StrictStr | None = None
    description: StrictStr | None = None
    provider: StrictStr | None = None
    readme: StrictStr | None = None
    built_for_connector: StrictStr | None = None
    connector_version: StrictStr | None = None
    app_type: StrictStr | None = None
    billable: StrictBool | None = None
    price: Annotated[FiniteFloat, Field(strict=True)] | None = None
    dataspace_app_description: StrictStr | None = None
    active: StrictBool | None = None
    visible: StrictBool | None = None
    ui_url: AnyHttpUrl | None = None
    openapi_url: AnyHttpUrl | None = None
    deploy_url: AnyHttpUrl | None = None
    # Docker registry locations may lack a scheme; they are not navigation links.
    registry_base_url: StrictStr | None = None
    versions: list[StoreAppVersion] | None = Field(default=None, strict=True)

    @field_validator(
        "name",
        "description",
        "provider",
        "readme",
        "built_for_connector",
        "connector_version",
        "app_type",
        "dataspace_app_description",
        "ui_url",
        "openapi_url",
        "deploy_url",
        "registry_base_url",
        mode="before",
    )
    @classmethod
    def blank_is_missing(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def id(self) -> str:
        pair = json.dumps([self.store_id, self.app_id], ensure_ascii=False, separators=(",", ":"))
        return "store-v1-" + hashlib.sha256(pair.encode()).hexdigest()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def public_eligible(self) -> bool:
        # Conservative pending HEDGE confirmation of active/service-client semantics.
        return self.visible is True and self.active is True

    @computed_field  # type: ignore[prop-decorator]
    @property
    def checksum(self) -> str:
        payload = self.model_dump(mode="json", exclude={"checksum"})
        # New absent fields must not invalidate historical sparse-row checksums.
        for field in STORE_APP_FIELDS.values():
            if payload.get(field) is None:
                payload.pop(field, None)
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def source_evidence(self) -> dict[str, str]:
        """Bounded source quotations with original Store field paths."""
        evidence = {}
        fields = {"name": "name", "description": "description", "provider": "provider",
                  **STORE_APP_FIELDS}
        for source, target in fields.items():
            if source == "dataspaceAppDescription":
                continue
            value = getattr(self, target)
            if value is not None:
                # False and zero are supplied values, never missing/free claims.
                text = _source_text(value) if isinstance(value, str) else json.dumps(value)
                if text:
                    evidence[source] = text
        if self.readme and (text := _source_text(self.readme)):
            evidence["readme"] = text
        evidence.update(_dataspace_evidence(self.dataspace_app_description)[1])
        if self.versions is not None:
            for index, version in enumerate(self.versions[:64]):
                for source, target in (("version", "version"), ("versionComments", "comments")):
                    value = getattr(version, target)
                    if value and (text := _source_text(value)):
                        evidence[f"appVersionList[{index}].{source}"] = text
        # Bound the complete derived document as well as each individual source.
        bounded = {}
        remaining = EMBEDDED_JSON_LIMIT
        for path, text in evidence.items():
            if len(bounded) == 128:
                break
            if len(text) <= remaining:
                bounded[path] = text
                remaining -= len(text)
        return bounded

    def to_index_text(self, locale: str = "en") -> str:
        """Index supplied utility text, without interpreting billing or compatibility."""
        del locale
        return " . ".join(value for path, value in self.source_evidence().items()
                          if path not in {"billable", "price"})

    def recommendation_projection(self) -> dict[str, Any]:
        """Source values and plain-text evidence; raw HTML/embedded JSON stay local."""
        projection = self.model_dump(
            mode="json",
            include={
                "id", "source_profile", "store_id", "app_id", "name", "description",
                "provider", "active", "visible", "public_eligible", "versions",
                "built_for_connector", "connector_version", "app_type", "billable", "price",
            },
        )
        projection["source_evidence"] = self.source_evidence()
        if self.readme is None:
            projection["readme_status"] = "missing"
        elif len(self.readme) > EVIDENCE_TEXT_LIMIT:
            projection["readme_status"] = "too_large"
        else:
            projection["readme_status"] = (
                "extracted" if projection["source_evidence"].get("readme") else "not_projected"
            )
        projection["dataspace_description_status"] = _dataspace_evidence(
            self.dataspace_app_description
        )[0]
        return projection


def validate_offline_store_scope(store_id: str | None, collection_name: str | None) -> None:
    """Explicit Python-only scope; public routes never provide these arguments."""
    if store_id is None and collection_name is None:
        return
    if (
        not isinstance(store_id, str)
        or not store_id.strip()
        or store_id != store_id.strip()
        or not isinstance(collection_name, str)
        or not re.fullmatch(r"hedge_store_offline_[a-f0-9]{32}", collection_name)
    ):
        raise ValueError(
            "Offline Store access requires a native Store ID and disposable collection"
        )
