"""Private one-shot input: actual client transport, no credentials or raw records retained."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import httpx
import pytest

from scripts import store_v1_input as source

RAW = json.loads(Path("tests/fixtures/store-v1/manual-apps.json").read_text())
STORE = "Manual-Store-Fixture"


def test_authorized_file_uses_existing_client_and_strips_unused_private_fields(tmp_path):
    token = tmp_path / "token"
    token.write_text("ephemeral-test-token\n")
    requests = []
    private = dict(RAW[0], ownerEmail="private@example.invalid", dataspaceAppDescription="private embedded data")

    def respond(request):
        requests.append(request)
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer ephemeral-test-token"
        return httpx.Response(200, json=[private, RAW[1]] if request.url.path.endswith("/all") else private)

    records, evidence = source.load_input(store_id=STORE, token_file=str(token), transport=httpx.MockTransport(respond))
    assert len(requests) == 2
    assert requests[0].url.path == f"/backend/api/v1/store/{STORE}/app/all"
    assert requests[1].url.path.endswith("/app/" + RAW[0]["appId"])
    assert evidence == {"source": "authorized-api-snapshot", "snapshot_complete": False,
                        "apps": 2, "eligible_apps": 2, "getAllApps_status": 200, "getApp_status": 200}
    assert records == source.validated_records([private, RAW[1]], STORE)
    assert "ownerEmail" not in json.dumps(records)
    assert records[0]["dataspaceAppDescription"] == "private embedded data"
    assert "ephemeral-test-token" not in json.dumps(evidence)


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_user_token_has_no_refresh_no_fallback_and_no_payload_leak(tmp_path, status):
    token = tmp_path / "token"
    token.write_text("ephemeral-test-token")
    calls = []

    def reject(request):
        calls.append(request)
        return httpx.Response(status, text="sensitive remote error")

    with pytest.raises(source.client_module.StoreApiError) as raised:
        source.load_input(store_id=STORE, token_file=str(token), transport=httpx.MockTransport(reject))
    assert len(calls) == 1
    assert raised.value.status_code == status
    assert "sensitive" not in str(raised.value)
    assert "ephemeral" not in str(raised.value)


def test_detail_disappearance_is_diagnostic_and_does_not_grant_absence_authority(tmp_path):
    token = tmp_path / "token"
    token.write_text("test-token")
    records, evidence = source.load_input(store_id=STORE, token_file=str(token), transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=RAW) if request.url.path.endswith("/all") else httpx.Response(404)))
    assert records == source.validated_records(RAW, STORE)
    assert evidence["getApp_status"] == 404
    assert evidence["snapshot_complete"] is False


@pytest.mark.parametrize("raw", [RAW, RAW[0]])
def test_local_import_accepts_catalogue_or_single_app_without_completeness(tmp_path, raw):
    path = tmp_path / "apps.json"
    path.write_text(json.dumps(raw))
    records, evidence = source.load_input(store_id=STORE, apps_json=str(path))
    assert len(records) == (len(raw) if isinstance(raw, list) else 1)
    assert evidence["source"] == "private-json-import"
    assert evidence["snapshot_complete"] is False
    assert "getAllApps_status" not in evidence


@pytest.mark.parametrize("raw", [[], None, [RAW[0], RAW[0]], [dict(RAW[0], visible="true")],
                                     [dict(RAW[0], fkAppStoreId="another-store")], [dict(RAW[0], active=False)]])
def test_bad_ineligible_or_wrong_scope_input_fails_closed(raw):
    with pytest.raises(ValueError):
        source.validated_records(raw, STORE)


def test_absent_endpoint_store_identity_is_supplied_without_inventing_other_fields():
    raw = {"appId": "sparse", "active": True, "visible": True}
    assert source.validated_records([raw], STORE) == [dict(raw, fkAppStoreId=STORE)]


@pytest.mark.parametrize("body", ['[{"appId":"a","appId":"b"}]', '[NaN]', 'not JSON'])
def test_import_rejects_nonstandard_json(tmp_path, body):
    path = tmp_path / "apps.json"
    path.write_text(body)
    with pytest.raises(ValueError):
        source.load_input(store_id=STORE, apps_json=str(path))


def test_cli_failure_never_prints_pydantic_input_or_response_records(tmp_path, monkeypatch, capsys):
    path = tmp_path / "apps.json"
    path.write_text(json.dumps([dict(RAW[0], visible="private-secret-value")]))
    monkeypatch.setattr("sys.argv", ["input", "--apps-json", str(path), "--store-id", STORE])
    with pytest.raises(SystemExit) as raised:
        source.main()
    assert raised.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "private-secret-value" not in output.err
    assert "malformed" in output.err


def test_import_size_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(source.client_module.HedgeApiClient, "MAX_RESPONSE_BYTES", 5)
    path = tmp_path / "apps.json"
    path.write_text(" " * 6)
    with pytest.raises(ValueError, match="size limit"):
        source.load_input(store_id=STORE, apps_json=str(path))


@pytest.mark.parametrize("kind", ["public-permissions", "symlink", "missing"])
def test_launcher_rejects_unsafe_private_file_before_starting_resources(tmp_path, kind):
    path = tmp_path / "private"
    if kind != "missing":
        path.write_text("private-test-content-never-logged")
        path.chmod(0o600 if kind == "symlink" else 0o644)
    if kind == "symlink":
        link = tmp_path / "link"
        link.symlink_to(path)
        path = link
    result = subprocess.run(["bash", "scripts/store-v1-playground.sh", "--apps-json", str(path),
                             "--store-id", STORE], capture_output=True, text=True)
    assert result.returncode != 0
    assert "mode-0600" in result.stderr
    assert "private-test-content" not in result.stdout + result.stderr
    assert "docker" not in result.stderr.lower()
