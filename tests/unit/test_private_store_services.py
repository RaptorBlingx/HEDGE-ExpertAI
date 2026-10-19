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


def test_http_composition_preserves_context_updates(monkeypatch):
    bridge = load_service('private_chat_bridge', 'chat-intent')('private_store')
    calls = []

    def call(service, path, body):
        calls.append((service, path, body))
        return {'message': 'Simpler.', 'context': {**body['response']['context'],
                                                'simplification': {'topic': 'records'}}}

    monkeypatch.setattr(bridge, 'call', call)
    response = {'apps': [], 'context': {'explanation_topic': 'records'}}
    assert bridge.present('Explain it simply', response, 'en') == 'Simpler.'
    assert response['context']['explanation_topic'] == 'records'
    assert response['context']['simplification']['topic'] == 'records'
    assert calls[0][:2] == ('EXPERT_RECOMMEND_URL', '/internal/store/compose')
