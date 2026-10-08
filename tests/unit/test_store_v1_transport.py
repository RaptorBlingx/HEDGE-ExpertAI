"""Store v1 HTTP contract and credential safety; every request uses MockTransport."""

from __future__ import annotations

import json

import httpx
import pytest
from hedge_shared.config import Settings
from pydantic import ValidationError
from test_store_v1 import client

BASE = "https://store.invalid/backend/api/v1"
TOKEN = "test-only.header.signature"


def published(**changes):
    return {"appId": "App-A", "active": True, "visible": True, **changes}


def make_client(handler, **kwargs):
    options = {"store_id": "Store-A", "token": TOKEN, "max_retries": 0}
    options.update(kwargs)
    return client.HedgeApiClient(BASE, transport=httpx.MockTransport(handler), **options)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    delays = []
    monkeypatch.setattr(client.time, "sleep", delays.append)
    return delays


def test_exact_store_v1_routes_bearer_and_source_normalization():
    requests = []
    raw = published(fkAppStoreId="Store-A", name="Energy", futureField="retained")
    assets = [{"@id": "asset-A", "properties": {"features": ["unjoined"]}}]

    def handler(request):
        requests.append(request)
        assert request.method == "GET" and not request.url.query
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert request.headers["accept"] == "application/json"
        body = (
            assets
            if "/dsp/" in request.url.path
            else [raw]
            if request.url.path.endswith("/all")
            else raw
        )
        return httpx.Response(200, json=body)

    api = make_client(handler)
    assert api.fetch_all_apps() == [raw]
    assert api.fetch_app("App-A") == raw
    assert api.fetch_assets() == assets
    assert [r.url.path for r in requests] == [
        "/backend/api/v1/store/Store-A/app/all",
        "/backend/api/v1/store/Store-A/app/App-A",
        "/backend/api/v1/dsp/connector/asset/all",
    ]
    model = client.normalize_store_v1_app(raw, store_id=api.store_id)
    assert model.public_eligible and model.provider is None
    assert "futureField" not in model.model_dump()
    assert api.snapshot_complete is False


def test_opaque_native_ids_are_encoded_as_single_path_segments():
    store, app = "Store /?x#%", "App /?a#%"

    def handler(request):
        assert (
            request.url.raw_path
            == b"/backend/api/v1/store/Store%20%2F%3Fx%23%25/app/App%20%2F%3Fa%23%25"
        )
        assert not request.url.query
        return httpx.Response(200, json=published(appId=app, fkAppStoreId=store))

    assert make_client(handler, store_id=store).fetch_app(app)["appId"] == app


@pytest.mark.parametrize(
    "url",
    [
        "http://store.invalid/backend/api/v1",
        "https://store.invalid",
        "https://store.invalid/api/v2",
        "https://user:secret@store.invalid/api/v1",
        "https://store.invalid/api/v1?token=secret",
        "https://store.invalid/api/v1#secret",
        "not a URL",
    ],
)
def test_unsafe_or_wrong_version_base_is_rejected(url):
    with pytest.raises(ValueError):
        client.HedgeApiClient(url, store_id="Store-A", token=TOKEN)


@pytest.mark.parametrize("store", ["", " Store-A", ".", ".."])
def test_invalid_store_path_is_rejected(store):
    with pytest.raises(ValueError):
        client.HedgeApiClient(BASE, store_id=store, token=TOKEN)


@pytest.mark.parametrize("app", [".", "..", "", " App"])
def test_invalid_app_path_never_requests(app):
    def handler(request):
        pytest.fail("invalid identity must not issue a request")

    with pytest.raises(ValueError):
        make_client(handler).fetch_app(app)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout": 0},
        {"timeout": float("nan")},
        {"timeout": 121},
        {"timeout": True},
        {"max_retries": -1},
        {"max_retries": 4},
        {"max_retries": True},
        {"token": None},
        {"token_file": "relative.txt", "token": None},
        {"token_file": "/run/secrets/store_token"},
    ],
)
def test_invalid_client_configuration_fails_without_io(kwargs):
    with pytest.raises(ValueError):
        make_client(lambda request: pytest.fail("unexpected HTTP"), **kwargs)


@pytest.mark.parametrize(
    "token", ["", "Bearer secret", "secret\r\nX-Evil: injected", "two tokens", "x" * 16385]
)
def test_bad_bearer_token_never_enters_a_header_or_error(token):
    with pytest.raises(client.StoreApiError) as caught:
        make_client(lambda request: pytest.fail("unexpected HTTP"), token=token).fetch_all_apps()
    assert str(caught.value) == "Store backend Bearer token is empty or invalid"


def test_token_file_reloads_after_external_rotation_and_unauthorized_response(tmp_path):
    file = tmp_path / "backend_token"
    file.write_text(TOKEN + "\n")
    headers = []

    def handler(request):
        headers.append(request.headers["authorization"])
        return (
            httpx.Response(401, json={"error": TOKEN})
            if len(headers) == 1
            else httpx.Response(200, json=[published()])
        )

    api = make_client(handler, token=None, token_file=str(file), max_retries=2)
    with pytest.raises(client.StoreApiError) as caught:
        api.fetch_all_apps()
    assert caught.value.status_code == 401 and TOKEN not in str(caught.value)
    assert len(headers) == 1  # no guessed acquisition/refresh or 401 retries
    file.write_text("externally-rotated-token\n")
    assert api.fetch_all_apps() == [published()]
    assert headers == [f"Bearer {TOKEN}", "Bearer externally-rotated-token"]


def test_missing_token_file_fails_before_network(tmp_path):
    api = make_client(
        lambda request: pytest.fail("unexpected HTTP"),
        token=None,
        token_file=str(tmp_path / "missing"),
    )
    with pytest.raises(client.StoreApiError, match="unavailable"):
        api.fetch_all_apps()


@pytest.mark.parametrize("status", [301, 302, 307, 308, 401, 403, 400, 404, 422, 204, 206])
def test_terminal_status_and_redirects_do_not_retry_or_forward_credentials(
    status, caplog, no_sleep
):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status, headers={"location": "https://other.invalid/steal"}, content=TOKEN
        )

    with pytest.raises(client.StoreApiError) as caught:
        make_client(handler, max_retries=3).fetch_all_apps()
    assert caught.value.status_code == status
    assert len(requests) == 1 and no_sleep == []
    assert TOKEN not in str(caught.value) and TOKEN not in caplog.text


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_status_retries_are_bounded(status, no_sleep):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, content=TOKEN)

    with pytest.raises(client.StoreApiError) as caught:
        make_client(handler, max_retries=2).fetch_all_apps()
    assert caught.value.status_code == status and len(requests) == 3
    assert no_sleep == [0.25, 0.5] and TOKEN not in str(caught.value)


@pytest.mark.parametrize("retry_after", ["99999999", "Wed, 21 Oct 2026 07:28:00 GMT", "invalid"])
def test_server_deferred_retry_stops_without_guessing_or_waiting(retry_after, no_sleep):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(429, headers={"retry-after": retry_after}, content=TOKEN)

    with pytest.raises(client.StoreApiError, match="deferred retry") as caught:
        make_client(handler, max_retries=3).fetch_all_apps()
    assert caught.value.status_code == 429 and len(requests) == 1 and no_sleep == []


def test_timeout_retry_then_success_uses_configured_http_limits(monkeypatch, no_sleep):
    requests, options = [], []
    real_client = client.httpx.Client

    def http_client(**kwargs):
        options.append(kwargs)
        return real_client(**kwargs)

    monkeypatch.setattr(client.httpx, "Client", http_client)

    def handler(request):
        requests.append(request)
        assert all(0 < value <= 1.25 for value in request.extensions["timeout"].values())
        if len(requests) == 1:
            raise httpx.ReadTimeout(TOKEN, request=request)
        return httpx.Response(200, json=[published()])

    assert make_client(handler, timeout=1.25, max_retries=2).fetch_all_apps() == [published()]
    assert len(requests) == 2 and no_sleep == [0.25]
    assert options[0]["trust_env"] is options[0]["follow_redirects"] is False
    assert options[0]["verify"] is True


@pytest.mark.parametrize(
    "error",
    [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError],
)
def test_exhausted_network_failure_is_sanitized_and_bounded(error, caplog, no_sleep):
    requests = []

    def handler(request):
        requests.append(request)
        raise error(TOKEN, request=request)

    with pytest.raises(client.StoreApiError) as caught:
        make_client(handler, max_retries=1).fetch_all_apps()
    assert len(requests) == 2 and no_sleep == [0.25]
    assert TOKEN not in str(caught.value) and TOKEN not in caplog.text
    assert caught.value.__suppress_context__


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"apps": [published()]},
        [None],
        [published(visible="true")],
        [published(fkAppStoreId="Other-Store")],
        [published(), published()],
    ],
)
def test_malformed_catalogue_or_source_contract_cannot_become_a_snapshot(payload, no_sleep):
    api = make_client(lambda request: httpx.Response(200, json=payload), max_retries=2)
    with pytest.raises(client.StoreApiError):
        api.fetch_all_apps()
    assert api.snapshot_complete is False and no_sleep == []


def test_empty_catalogue_has_no_completeness_authority():
    api = make_client(lambda request: httpx.Response(200, json=[]))
    assert api.fetch_all_apps() == [] and api.snapshot_complete is False


@pytest.mark.parametrize(
    "payload", [None, [], published(appId="Other-App"), published(fkAppStoreId="Other-Store")]
)
def test_detail_null_or_wrong_identity_is_not_a_not_found_response(payload):
    api = make_client(
        lambda request: httpx.Response(
            200, content=json.dumps(payload), headers={"content-type": "application/json"}
        )
    )
    with pytest.raises(client.StoreApiError):
        api.fetch_app("App-A")


def test_detail_404_is_not_found_only_for_that_request():
    api = make_client(lambda request: httpx.Response(404, content=TOKEN))
    assert api.fetch_app("App-A") is None and api.snapshot_complete is False


@pytest.mark.parametrize("payload", [None, {}, [None], ["not an asset"]])
def test_asset_envelope_rejects_nonobjects_without_inventing_a_join(payload):
    with pytest.raises(client.StoreApiError):
        make_client(lambda request: httpx.Response(200, json=payload)).fetch_assets()


@pytest.mark.parametrize(
    "body,media",
    [
        (b"not JSON", "application/json"),
        (b"\xff", "application/json"),
        (b'[{"appId":"App-A","future":NaN}]', "application/json"),
        (b'[{"appId":"App-A","future":Infinity}]', "application/json"),
        (b'[{"appId":"App-A","visible":false,"visible":true}]', "application/json"),
        (b'[{"appId":"App-A","future":{"x":1,"x":2}}]', "application/json"),
        (b"[]", "text/html"),
        (b"[]", ""),
    ],
)
def test_malformed_json_or_media_type_does_not_retry(body, media, no_sleep):
    with pytest.raises(client.StoreApiError):
        make_client(
            lambda request: httpx.Response(200, content=body, headers={"content-type": media}),
            max_retries=2,
        ).fetch_all_apps()
    assert no_sleep == []


def test_content_decoding_failure_is_sanitized_and_not_retried(no_sleep):
    requests = []

    def handler(request):
        requests.append(request)
        raise httpx.DecodingError(TOKEN, request=request)

    with pytest.raises(client.StoreApiError, match="decoding failed") as caught:
        make_client(handler, max_retries=3).fetch_all_apps()
    assert len(requests) == 1 and no_sleep == [] and TOKEN not in str(caught.value)


def test_response_size_limit_fails_closed(monkeypatch):
    api = make_client(lambda request: httpx.Response(200, json=[published()]))
    monkeypatch.setattr(api, "MAX_RESPONSE_BYTES", 8)
    with pytest.raises(client.StoreApiError, match="size limit"):
        api.fetch_all_apps()


def test_slow_stream_cannot_reset_the_operation_time_budget(monkeypatch):
    now, consumed = [0.0], []
    monkeypatch.setattr(client.time, "monotonic", lambda: now[0])

    class SlowBody(httpx.SyncByteStream):
        def __iter__(self):
            for chunk in (b"[", b" ", b"]"):
                now[0] += 0.6
                consumed.append(chunk)
                yield chunk

    api = make_client(
        lambda request: httpx.Response(
            200, stream=SlowBody(), headers={"content-type": "application/json"}
        ),
        timeout=1,
    )
    with pytest.raises(client.StoreApiError, match="time budget"):
        api.fetch_all_apps()
    assert len(consumed) == 2


def test_timeout_exhausting_total_budget_does_not_start_another_request(monkeypatch):
    now, requests = [0.0], []
    monkeypatch.setattr(client.time, "monotonic", lambda: now[0])

    def handler(request):
        requests.append(request)
        now[0] += 1
        raise httpx.ReadTimeout(TOKEN, request=request)

    with pytest.raises(client.StoreApiError, match="time budget"):
        make_client(handler, timeout=1, max_retries=3).fetch_all_apps()
    assert len(requests) == 1


def test_interrupted_body_is_discarded_before_retry(no_sleep):
    requests = []

    class InterruptedBody(httpx.SyncByteStream):
        def __iter__(self):
            yield b"["
            raise httpx.ReadError(TOKEN)

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200, stream=InterruptedBody(), headers={"content-type": "application/json"}
            )
        return httpx.Response(200, json=[published()])

    assert make_client(handler, max_retries=1).fetch_all_apps() == [published()]
    assert len(requests) == 2 and no_sleep == [0.25]


def test_oversized_token_file_is_not_silently_truncated(tmp_path):
    file = tmp_path / "backend_token"
    file.write_text("x" * 16384 + "  more-token-data")
    api = make_client(
        lambda request: pytest.fail("unexpected HTTP"), token=None, token_file=str(file)
    )
    with pytest.raises(client.StoreApiError, match="empty or invalid"):
        api.fetch_all_apps()


def test_factory_uses_only_outbound_store_settings(monkeypatch, tmp_path):
    token_file = tmp_path / "backend_token"
    token_file.write_text(TOKEN)
    for name, value in {
        "HEDGE_STORE_ID": "Store-A",
        "HEDGE_STORE_TOKEN_FILE": str(token_file),
        "HEDGE_STORE_TIMEOUT_SECONDS": 2.0,
        "HEDGE_STORE_MAX_RETRIES": 1,
    }.items():
        monkeypatch.setattr(client.settings, name, value)
    api = client.get_client("http://mock.invalid", BASE)
    assert api.store_id == "Store-A" and api.timeout == 2.0 and api.max_retries == 1
    assert TOKEN not in repr(api) and TOKEN not in repr(api._token)
    assert isinstance(client.get_client("http://mock.invalid"), client.MockApiClient)


def test_shared_settings_defaults_and_bounds():
    defaults = Settings(_env_file=None)
    assert defaults.HEDGE_STORE_ID == defaults.HEDGE_STORE_TOKEN_FILE == ""
    assert defaults.HEDGE_STORE_TIMEOUT_SECONDS == 30 and defaults.HEDGE_STORE_MAX_RETRIES == 2
    for values in [
        {"HEDGE_STORE_TIMEOUT_SECONDS": 0},
        {"HEDGE_STORE_TIMEOUT_SECONDS": 121},
        {"HEDGE_STORE_MAX_RETRIES": -1},
        {"HEDGE_STORE_MAX_RETRIES": 4},
    ]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **values)
