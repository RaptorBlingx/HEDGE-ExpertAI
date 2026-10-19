"""Backend credential renewal and failure containment; no live credentials."""
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs

import httpx
import pytest
from test_store_v1 import client

Auth = client.StoreClientCredentials
AuthError = client.StoreAuthError
ISSUER = 'https://identity.invalid/realms/store'


def provider(tmp_path, handler):
    secret = tmp_path / 'secret'
    secret.write_text('test-client-secret')
    secret.chmod(0o600)
    return Auth(ISSUER, 'test-client', str(secret), transport=httpx.MockTransport(handler)), secret


def discovery():
    return httpx.Response(200, json={'issuer': ISSUER, 'token_endpoint': ISSUER + '/token'})


def issued(token='token-one', expiry=300):
    return httpx.Response(200, json={'access_token': token, 'token_type': 'Bearer',
                                    'expires_in': expiry})


def test_cached_thread_safe_renewal_and_atomic_secret_rotation(tmp_path):
    grants = []
    def handler(request):
        if request.method == 'GET':
            return discovery()
        grants.append(parse_qs(request.content.decode()))
        return issued('token-' + str(len(grants)))
    auth, secret = provider(tmp_path, handler)
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert list(pool.map(lambda _: auth.token(time.monotonic()+5), range(12))) == ['token-1']*12
    assert len(grants) == 1
    # Simulate expiry, not a different auth architecture; rotate atomically.
    replacement = tmp_path / 'rotated'
    replacement.write_text('replacement-secret')
    replacement.chmod(0o600)
    replacement.replace(secret)
    auth._expires = 0
    assert auth.token(time.monotonic()+5) == 'token-2'
    assert grants[-1]['client_secret'] == ['replacement-secret']
    auth.invalidate('old-rejected-token')
    assert auth.token(time.monotonic()+5) == 'token-2'
    assert 'replacement-secret' not in repr(auth)


def test_401_refresh_once_without_using_get_retry_budget_and_no_403_refresh(tmp_path):
    issued_tokens, store_calls = [], []
    def identity(request):
        if request.method == 'GET':
            return discovery()
        issued_tokens.append(1)
        return issued('token-' + str(len(issued_tokens)))
    auth, _ = provider(tmp_path, identity)
    def store(request):
        store_calls.append(request.headers['authorization'])
        return httpx.Response(401) if len(store_calls) == 1 else httpx.Response(200, json=[])
    api = client.HedgeApiClient('https://store.invalid/api/v1', store_id='Store',
                               credentials=auth, max_retries=0, transport=httpx.MockTransport(store))
    assert api.fetch_catalogue_records() == []
    assert store_calls == ['Bearer token-1', 'Bearer token-2']
    for status in (401, 403):
        api._transport = httpx.MockTransport(lambda _, code=status: httpx.Response(code))
        before = len(issued_tokens)
        with pytest.raises(client.StoreApiError) as error:
            api.fetch_catalogue_records()
        assert error.value.status_code == status
        assert len(issued_tokens) - before == (1 if status == 401 else 0)


@pytest.mark.parametrize('kind', ['wrong-issuer', 'foreign-endpoint', 'redirect', 'denied',
                                  'oversize', 'bad-token', 'bad-expiry', 'public-secret', 'symlink'])
def test_fail_closed_without_exposing_identity_bodies_or_sending_store_requests(tmp_path, kind):
    posts = []
    def handler(request):
        if request.method == 'GET':
            if kind == 'wrong-issuer':
                return httpx.Response(200, json={'issuer':'different', 'token_endpoint':ISSUER+'/token'})
            if kind == 'foreign-endpoint':
                return httpx.Response(200, json={'issuer':ISSUER,
                                                'token_endpoint':'https://other.invalid/token'})
            if kind == 'redirect':
                return httpx.Response(302, headers={'location':ISSUER+'/other'})
            return discovery()
        posts.append(1)
        if kind == 'denied':
            return httpx.Response(401, json={'error_description':'test-client-secret'})
        if kind == 'oversize':
            return httpx.Response(200, content=b' '*65537,
                                  headers={'content-type':'application/json'})
        return issued('bad\ntoken' if kind == 'bad-token' else 'ok',
                      -1 if kind == 'bad-expiry' else 300)
    auth, secret = provider(tmp_path, handler)
    if kind == 'public-secret':
        secret.chmod(0o644)
    if kind == 'symlink':
        target = tmp_path/'real'
        secret.replace(target)
        secret.symlink_to(target)
    with pytest.raises(AuthError) as error:
        auth.token(time.monotonic()+5)
    assert 'test-client-secret' not in str(error.value)
    if kind in {'wrong-issuer', 'foreign-endpoint', 'redirect', 'public-secret', 'symlink'}:
        assert not posts
