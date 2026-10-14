"""Suitability decisions through the real Discovery → Expert → Chat → Gateway APIs."""
import sys
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
def test_model_abstention_remains_abstention_at_gateway(chain, monkeypatch, stream):
    discovery = sys.modules[chain.searcher.__package__ + '.routes']
    monkeypatch.setattr(discovery, 'search_apps_v2', lambda *a, **k: [{
        'app': {'id':'qa', 'title':{'en':'Warning App'}, 'description':'Earthquake warnings.'},
        'rank':1, 'relevance':'high',
    }])
    recommender = sys.modules['scrum28_expert_recommend.recommender']
    monkeypatch.setattr(recommender, 'OllamaClient', lambda: SimpleNamespace(
        chat_structured=lambda *args: '{"selected_ids":[]}',
    ))
    response = chain.gc.post('/api/v2/chat' + ('/stream' if stream else ''),
                             json={'message':'earthquake warnings'})
    payload = next(e for e in events(response) if e['type']=='recommendations') if stream else response.json()
    assert response.status_code == 200
    assert payload['apps'] == [] and payload['decision']['reason'] == 'model_abstention'
    assert payload['impression_id'] is None
