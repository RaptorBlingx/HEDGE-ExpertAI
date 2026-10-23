"""Private deployment gates and HTTP composition preserve the accepted dialogue."""
import pytest
from fastapi import HTTPException
from hedge_shared.private_store import require_internal_key, scope

from scripts.store_v1_playground import load_service


def test_private_store_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv('PRIVATE_STORE_ENABLED', raising=False)
    assert scope() == {}
    with pytest.raises(HTTPException) as error:
        require_internal_key('anything')
    assert error.value.status_code == 404


@pytest.mark.parametrize('environment,store', [('production', 'native'), ('private-testing', '')])
def test_private_mode_cannot_run_in_production_or_without_native_scope(monkeypatch, environment, store):
    monkeypatch.setenv('PRIVATE_STORE_ENABLED', 'true')
    monkeypatch.setenv('APP_ENV', environment)
    monkeypatch.setenv('HEDGE_STORE_ID', store)
    with pytest.raises(ValueError):
        scope()


def test_internal_key_and_native_scope(monkeypatch):
    monkeypatch.setenv('PRIVATE_STORE_ENABLED', 'true')
    monkeypatch.setenv('APP_ENV', 'private-testing')
    monkeypatch.setenv('HEDGE_STORE_ID', 'Some-native-Store')
    monkeypatch.setenv('GATEWAY_API_KEY', 'test-only')
    selected = scope()
    assert selected['store_id'] == 'Some-native-Store'
    assert selected['collection_name'].startswith('hedge_store_offline_')
    require_internal_key('test-only')
    with pytest.raises(HTTPException):
        require_internal_key('wrong')


def test_http_bridge_batches_example_similarity_and_degrades_without_it(monkeypatch):
    bridge = load_service('private_chat_bridge', 'chat-intent')('private_store')
    calls = []

    def call(service, path, body):
        calls.append((service, path, body))
        return {'scores': [[0.5] * len(body['passages'])]}

    monkeypatch.setattr(bridge, 'call', call)
    examples = [f'example {i}' for i in range(450)]
    assert len(bridge.semantic('hello', examples)) == 450
    assert [len(c[2]['passages']) for c in calls] == [400, 50]
    assert all(c[:2] == ('DISCOVERY_RANKING_URL', '/api/v2/evidence/similarity') and c[2]['symmetric'] for c in calls)

    def unavailable(service, path, body):
        raise HTTPException(503, 'Store service unavailable')

    monkeypatch.setattr(bridge, 'call', unavailable)
    assert bridge.semantic('hello', examples) is None
    monkeypatch.setenv('STORE_SEMANTIC_ENABLED', 'true')
    assert bridge.arbitrate('x', [{'gloss': 'a'}, {'gloss': 'b'}], {}) is None
    monkeypatch.setenv('STORE_SEMANTIC_ENABLED', 'false')
    monkeypatch.setattr(bridge, 'call', lambda *a: (_ for _ in ()).throw(AssertionError('no model call')))
    assert bridge.arbitrate('x', [{'gloss': 'a'}, {'gloss': 'b'}], {}) is None


def test_chat_service_starts_and_warms_act_examples_in_private_scope(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv('PRIVATE_STORE_ENABLED', 'true')
    monkeypatch.setenv('APP_ENV', 'private-testing')
    monkeypatch.setenv('HEDGE_STORE_ID', 'Some-native-Store')
    monkeypatch.setenv('GATEWAY_API_KEY', 'test-only')
    chat = load_service('private_chat_startup', 'chat-intent')
    warmed = []
    monkeypatch.setattr(chat('private_store'), 'warm', lambda: warmed.append(True))
    with TestClient(chat('main').app) as client:
        assert client.get('/live').status_code == 200
    assert warmed == [True]
