"""Suitability decisions through the real Discovery → Expert → Chat → Gateway APIs."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_search_error_boundaries import chain as chain
from test_search_error_boundaries import events


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(("description", "supported"), [
    ("Displays water readings.", False),
    ("Earthquake warnings.", True),
    ("Earthquake warnings only in simulation.", False),
])
def test_rank_only_cannot_create_an_earthquake_recommendation(chain, monkeypatch, stream, description, supported):
    discovery = sys.modules[chain.searcher.__package__ + ".routes"]
    result = {"app": {"id": "native-qa", "title": {"en": "QA App"}, "description": description},
              "rank": 1, "relevance": "high", "evidence_fields": ["dense"]}
    monkeypatch.setattr(discovery, "search_apps_v2", lambda *a, **k: [result])
    response = chain.gc.post('/api/v2/chat' + ('/stream' if stream else ''),
                             json={'message': 'Find apps for earthquake warnings'})
    assert response.status_code == 200
    if stream:
        records = events(response)
        payload = next(e for e in records if e['type'] == 'recommendations')
        text = ''.join(e['content'] for e in records if e['type'] == 'explanation_delta')
        assert records[-1]['decision'] == payload['decision']
    else:
        payload = response.json()
        text = payload['message']
    assert bool(payload['apps']) is supported
    assert bool(payload['candidates']) is not supported
    assert payload['decision']['outcome'] == ('recommended' if supported else 'abstained')
    assert 'Start with' not in text and 'highest-ranked' not in text
    if supported:
        assert payload['apps'][0]['app'] == result['app']
        assert payload['apps'][0]['suitability']['evidence_fields'] == ['description']
    else:
        assert payload['candidates'][0]['app'] == result['app']
        assert payload.get('impression_id') is None


@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize(('query', 'description', 'readme', 'locale', 'supported'), [
    ('earthquake warnings', 'Earthquake warnings are planned for a future release.', None, 'en', False),
    ('earthquake warnings', 'Earthquake warnings. They are not supported by this App.', None, 'en', False),
    ('earthquake warnings', 'Provides earthquake warnings.', 'This feature is disabled. It cannot be used.', 'en', False),
    ('earthquake warnings', 'Provides earthquake warnings if sensors are installed.', None, 'en', False),
    ('earthquake warnings SMS', 'Provides earthquake warnings without SMS.', None, 'en', False),
    ('earthquake warnings', 'Provides water readings.', None, 'en', False),
    ('real-time earthquake warnings', 'Provides earthquake warnings.', None, 'en', False),
    ('real-time earthquake warnings', 'Provides real-time earthquake warnings.', None, 'en', True),
    ('earthquake warnings SMS', 'Provides earthquake warnings. Sends them via SMS.', None, 'en', True),
    ('earthquake warnings SMS', 'Provides earthquake warnings. Another App sends them via SMS.', None, 'en', False),
    ('earthquake warnings SMS', 'Provides earthquake warnings and water readings. Sends them via SMS.', None, 'en', True),
    ('earthquake warnings SMS', 'Provides earthquake warnings.', 'Delivers earthquake warnings via SMS.', 'en', True),
    ('earthquake warnings', 'Provides earthquake warnings.', 'MQTT is unavailable.', 'en', True),
    ('alertas de terremoto', 'Não envia alertas de terremoto.', None, 'pt', False),
    ('Preciso de apps para alertas de terremoto', 'Envia alertas de terremoto.', None, 'pt', True),
    ('MQTT', 'Unterstützt MQTT nicht.', None, 'de', False),
    ('Ich brauche eine App für MQTT', 'Unterstützt MQTT.', None, 'de', True),
])
def test_coherent_store_evidence_controls_gateway_cards_and_impressions(
    chain, monkeypatch, stream, query, description, readme, locale, supported,
):
    from copy import deepcopy

    from hedge_shared.store_v1 import StoreAppMetadata

    app = StoreAppMetadata(store_id='Review-Store', app_id='Source-App', name='Review App',
                           description=description, readme=readme,
                           active=True, visible=True).recommendation_projection()
    original = deepcopy(app)
    discovery = sys.modules[chain.searcher.__package__ + '.routes']
    monkeypatch.setattr(discovery, 'search_apps_v2', lambda *a, **k: [{
        'app': app, 'rank': 1, 'evidence_fields': ['dense'],
    }])
    response = chain.gc.post('/api/v2/chat' + ('/stream' if stream else ''),
                             json={'message': query, 'locale': locale})
    assert response.status_code == 200
    if stream:
        records = events(response)
        payload = next(e for e in records if e['type'] == 'recommendations')
        assert records[-1]['decision'] == payload['decision']
        message = ''.join(e['content'] for e in records if e['type'] == 'explanation_delta')
    else:
        payload = response.json()
        message = payload['message']
    assert bool(payload['apps']) is supported
    assert payload['decision']['outcome'] == ('recommended' if supported else 'abstained')
    returned = (payload['apps'] if supported else payload['candidates'])[0]
    assert returned['app'] == original and app == original
    assert returned['app']['store_id'] == 'Review-Store' and returned['app']['app_id'] == 'Source-App'
    assert (returned['suitability']['status'] == 'source_supported') is supported
    if supported:
        assert payload['impression_id'] == 'qa-impression'
        chain.chat.create_impression.assert_called_once()
        assert returned['suitability']['evidence_fields']
    else:
        assert payload['impression_id'] is None
        chain.chat.create_impression.assert_not_called()
        assert 'fits what you need' not in message
    assert '90%' not in message and 'medically certified' not in message


@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize(('description', 'supported'), [
    ('Provides earthquake warnings. Sends them via SMS.', True),
    ('Earthquake warnings. They are not supported by this App.', False),
    ('Provides earthquake warnings. Sends them via SMS. SMS delivery is disabled.', False),
    ('Provides earthquake warnings. Sends them via SMS. Another App is required for the feature.', False),
    ('Earthquake warnings and water readings are available. Sends water readings via SMS.', False),
    ('Provides earthquake warnings. Sends them via SMS. MQTT delivery is disabled.', True),
    ('Provides earthquake warnings. Sends them via SMS. Earthquake warnings are only available via MQTT.', False),
    ('Provides earthquake warnings. Sends them via SMS. Earthquake warnings are only available in simulation via SMS.', False),
    ('Provides earthquake warnings. Sends them via SMS. Earthquake warnings do not require another App, but SMS delivery requires another App.', False),
    ('Provides earthquake warnings. Sends them via SMS. Earthquake warnings are only available via SMS.', True),
])
def test_routine_decisions_never_consult_a_model(chain, monkeypatch, stream, description, supported):
    from unittest.mock import Mock

    app = {'id': 'qa', 'title': {'en': 'Warning App'}, 'description': description}
    discovery = sys.modules[chain.searcher.__package__ + '.routes']
    monkeypatch.setattr(discovery, 'search_apps_v2', lambda *a, **k: [{
        'app': app, 'rank': 1, 'relevance': 'high',
    }])
    generation = Mock(side_effect=AssertionError('no model'))
    recommender = sys.modules['scrum28_expert_recommend.recommender']
    monkeypatch.setattr(recommender, 'OllamaClient', lambda: SimpleNamespace(chat_structured=generation))
    response = chain.gc.post('/api/v2/chat' + ('/stream' if stream else ''),
                             json={'message': 'earthquake warnings SMS'})
    payload = next(e for e in events(response) if e['type'] == 'recommendations') if stream else response.json()
    assert bool(payload['apps']) is supported
    assert bool(payload['impression_id']) is supported
    assert payload['decision']['outcome'] == ('recommended' if supported else 'abstained')
    generation.assert_not_called()


@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('case', json.loads(
    (Path(__file__).parents[1] / 'fixtures/store-v1/suitability-ownership.json').read_text()
), ids=lambda case: case['case'])
def test_feature_ownership_at_gateway(chain, monkeypatch, stream, case):
    from copy import deepcopy

    from hedge_shared.store_v1 import StoreAppMetadata

    app = StoreAppMetadata(store_id='Ownership-Store', app_id='Ownership-App', name='Review App',
                           active=True, visible=True, **case['source']).recommendation_projection()
    original = deepcopy(app)
    discovery = sys.modules[chain.searcher.__package__ + '.routes']
    monkeypatch.setattr(discovery, 'search_apps_v2', lambda *a, **k: [
        {'app': app, 'rank': 1, 'relevance': 'high', 'evidence_fields': ['dense']},
    ])
    response = chain.gc.post('/api/v2/chat' + ('/stream' if stream else ''),
                             json={'message': case['query'], 'locale': case['locale']})
    assert response.status_code == 200
    if stream:
        records = events(response)
        payload = next(e for e in records if e['type'] == 'recommendations')
        assert records[-1]['decision'] == payload['decision']
        message = ''.join(e['content'] for e in records if e['type'] == 'explanation_delta')
    else:
        payload = response.json()
        message = payload['message']
    supported = case['supported']
    assert bool(payload['apps']) is supported
    assert payload['decision']['outcome'] == ('recommended' if supported else 'abstained')
    returned = (payload['apps'] if supported else payload['candidates'])[0]
    assert returned['app'] == original and app == original
    assert (returned['suitability']['status'] == 'source_supported') is supported
    assert returned['app']['store_id'] == 'Ownership-Store' and returned['app']['app_id'] == 'Ownership-App'
    assert bool(payload['impression_id']) is supported
    assert chain.chat.create_impression.call_count == int(supported)
    if not supported:
        assert 'fits what you need' not in message
