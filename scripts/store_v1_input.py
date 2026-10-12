"""One-shot private input for the isolated playground; never an ingestion service."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

from scripts.store_v1_playground import load_service

client_module = load_service("evaluation_store_input", "metadata-ingest")("client")
BASE = "https://store.haslab-dataspace.pt/backend/api/v1"
# Retain only fields consumed by the source normalizer, never owner/contact or
# embedded asset descriptions. README is retained but excluded from retrieval.
APP_FIELDS = {
    "appId", "fkAppStoreId", "name", "description", "provider", "readme", "active",
    "visible", "registrationDate", "uiUrl", "openAPIURL", "deployURL", "registryBaseURL",
}
VERSION_FIELDS = {"appVersionId", "fkAppId", "version", "registrationDate", "versionComments"}


def validated_records(raw: object, store_id: str) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        raw = [raw]  # A saved getApp object is a partial input, never a catalogue.
    if not isinstance(raw, list) or not raw:
        raise ValueError("Evaluation requires a nonempty App object or array")
    records, identities = [], set()
    for row in raw:
        app = client_module.normalize_store_v1_app(row, store_id=store_id)
        if app.id in identities:
            raise ValueError("Duplicate App identity")
        identities.add(app.id)
        record = {key: value for key, value in row.items() if key in APP_FIELDS}
        # Endpoint scope supplies an absent Store ID, just as in the real client.
        record["fkAppStoreId"] = app.store_id
        versions = row.get("appVersionList")
        if versions is not None:
            record["appVersionList"] = [
                {key: value for key, value in version.items() if key in VERSION_FIELDS}
                for version in versions
            ]
        records.append(record)
    if not any(client_module.normalize_store_v1_app(r).public_eligible for r in records):
        raise ValueError("No explicitly active and visible Apps for evaluation")
    return records


def load_input(
    *, store_id: str, token_file: str | None = None, apps_json: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if bool(token_file) == bool(apps_json):
        raise ValueError("Choose exactly one private input")
    detail_status = None
    if token_file:
        client = client_module.HedgeApiClient(
            BASE, store_id=store_id, token_file=token_file, timeout=20,
            max_retries=1, transport=transport,
        )
        raw = client.fetch_all_apps()
        records = validated_records(raw, store_id)
        first = next(r for r in records if client_module.normalize_store_v1_app(r).public_eligible)
        # A diagnostic GET only. Do not mix a later detail into the earlier snapshot.
        detail_status = 200 if client.fetch_app(first["appId"]) is not None else 404
        mode = "authorized-api-snapshot"
    else:
        with Path(apps_json).open("rb") as handle:
            body = handle.read(client_module.HedgeApiClient.MAX_RESPONSE_BYTES + 1)
        if len(body) > client_module.HedgeApiClient.MAX_RESPONSE_BYTES:
            raise ValueError("Input size limit exceeded")
        raw = json.loads(body, parse_constant=client_module._reject_json_constant,
                         object_pairs_hook=client_module._unique_json_object)
        records = validated_records(raw, store_id)
        mode = "private-json-import"
    evidence = {"source": mode, "snapshot_complete": False, "apps": len(records),
                "eligible_apps": sum(client_module.normalize_store_v1_app(r).public_eligible for r in records)}
    if token_file:
        evidence.update(getAllApps_status=200, getApp_status=detail_status)
    return records, evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--token-file")
    source.add_argument("--apps-json")
    parser.add_argument("--store-id", required=True)
    args = parser.parse_args()
    try:
        records, evidence = load_input(**vars(args))
    except client_module.StoreApiError as error:
        print(json.dumps({"error": str(error), "status": error.status_code}), file=sys.stderr)
        raise SystemExit(1) from None
    except (OSError, ValueError, RecursionError):
        # Pydantic/JSON errors can contain private input; never render them.
        print("Private input unavailable, malformed, mismatched or ineligible", file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(evidence), file=sys.stderr)
    # Only the launcher redirects this private normalized input into its temp file.
    json.dump(records, sys.stdout)


if __name__ == "__main__":
    main()
