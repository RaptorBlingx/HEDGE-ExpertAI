"""Sparse Store v1 source metadata, independent of ExpertAI's public v2 API."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
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
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def to_index_text(self, locale: str = "en") -> str:
        """Index supplied App text without README HTML, embedded data or language claims."""
        del locale
        return " . ".join(value for value in (self.name, self.description, self.provider) if value)

    def recommendation_projection(self) -> dict[str, Any]:
        """Sparse source facts; no synthetic fields, HTML README or inferred navigation."""
        return self.model_dump(
            mode="json",
            include={
                "id", "source_profile", "store_id", "app_id", "name", "description",
                "provider", "active", "visible", "public_eligible",
            },
        )


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
