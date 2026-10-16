"""Contextual generation through private HTTP/SSE, real Store persistence and sessions."""
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlparse

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from hedge_shared import storage
from hedge_shared.store_v1 import StoreAppMetadata

from scripts.store_v1_browser import create_app
from scripts.store_v1_playground import Playground

from .test_store_v1_dialogue import chat
from .test_store_v1_persistence import database as database
from .test_store_v1_recommendations import RAW, STORE, client_module, recommender
from .test_store_v1_recommendations import offline as offline

policy_module = __import__(chat.__package__ + '.store_conversation', fromlist=['StoreConversation'])


@pytest.fixture
def browser(offline, monkeypatch):
    if urlparse(os.getenv('VALKEY_SESSION_URL', '')).hostname != 'sessions':
        pytest.skip('requires disposable session infrastructure')
    monkeypatch.setenv('RASA_ENABLED', 'false')
    identities = [client_module.normalize_store_v1_app(r).id for r in RAW if r['fkAppStoreId'] == STORE]
    def resolve(ids):
        ids = identities if ids is None else ids
        rows = storage.get_catalogue_apps(ids, store_id=STORE)
        return [StoreAppMetadata.model_validate(rows[i]['payload']).recommendation_projection() for i in ids if i in rows]
    async def search(**kwargs):
        return recommender.recommend_v2(**kwargs, limit=5)
    interpret = Mock(return_value={'action':'browse','apps':[],'query':'available Apps'})
    explain = Mock(return_value={'decision':'answer','focus':['1','2','3'],'message':'These Apps serve different purposes. [1] [2]',
        'generation':{'source':'ollama','reason':'reviewed_source_synthesis'}})
    policy = policy_module.StoreConversation(search, resolve, recommender._recommendation_narrative, interpret, explain)
    playground = Playground(chat, recommender, __import__('hedge_shared.models_v2',fromlist=['ChatRequestV2']), [], policy)
    playground.catalogue = resolve
    monkeypatch.setattr(chat, 'classify', lambda text:SimpleNamespace(intent='help',source='rasa',confidence=1.0))
    def generated(*a, **kwargs):
        kwargs['progress']('review')
        return explain.return_value
    explain.side_effect = generated
    sessions = set()
    with TestClient(create_app(playground),base_url='http://127.0.0.1:8098') as client:
        yield client, interpret, explain, policy, sessions
    for session in sessions:
        chat.delete_session(session)


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]


def test_multi_turn_http_sse_share_current_identity_history_and_review_progress(browser):
    client, interpret, explain, policy, sessions = browser
    first = client.post('/api/v2/chat',json={'message':'What can these Apps help me do?'}).json()
    session = first['session_id']
    sessions.add(session)
    assert first['impression_id'] and len(first['apps']) == 3
    previous = first['apps'][:2]
    # Directory aliases are stable catalogue-order keys, not model-created identities.
    directory = interpret.call_args.args[2]
    selected = [a['key'] for a in directory if a['native_id'] in {r['app']['app_id'] for r in previous}]
    interpret.return_value = {'action':'compare','apps':selected,'query':'Compare purposes'}
    explain.return_value['focus'] = selected
    reply = client.post('/api/v2/chat/stream',json={'message':'How do those differ?','session_id':session})
    output = events(reply)
    assert output[-1]['type'] == 'complete'
    assert {'intent','explanation','review'} <= {e.get('stage') for e in output if e['type']=='stage'}
    apps = next(e['apps'] for e in output if e['type']=='recommendations')
    assert {r['app']['id'] for r in apps} == {r['app']['id'] for r in previous}
    assert any(m['content']=='What can these Apps help me do?' for m in explain.call_args.args[-1])
    history = client.get('/api/v2/sessions/'+session).json()
    assert len(history['messages']) == 4
    assert chat.get_session(session)['context']['turn'] == 2
    assert history['messages'][-1]['content'] == explain.return_value['message']
    normal = client.post('/api/v2/chat',json={'message':'How do those differ?','session_id':session}).json()
    assert chat.get_session(session)['context']['turn'] == 3
    assert normal['apps'] == apps
    assert normal['message'] == next(e['content'] for e in output if e['type']=='explanation_delta')


def test_no_match_preserves_abstention_without_impressions(browser):
    client, interpret, explain, _, sessions = browser
    interpret.return_value = {'action':'search','apps':[],'query':'energy'}
    explain.return_value = {'decision':'no_match','message':'No documented earthquake-warning capability.',
                            'generation':{'source':'ollama','reason':'reviewed_source_synthesis'}}
    r = client.post('/api/v2/chat',json={'message':'Warn me about earthquakes'}).json()
    sessions.add(r['session_id'])
    assert not r['apps'] and r['impression_id'] is None
    assert r['message'] == explain.return_value['message']
    assert client.get('/api/v2/sessions/'+r['session_id']).json()['apps'] == []


def test_real_publication_withdrawal_is_checked_after_model_generation(browser):
    client, interpret, explain, policy, sessions = browser
    available = policy.resolve(None)
    app = next(a for a in available if a.get('name'))
    directory = sorted(available,key=lambda a:a['app_id'])
    key = str(next(i+1 for i,a in enumerate(directory) if a['id']==app['id']))
    interpret.return_value = {'action':'answer','apps':[key],'query':'explain App'}
    def withdraw(*a, **kw):
        row = storage.get_catalogue_apps([app['id']],store_id=STORE)[app['id']]
        metadata = StoreAppMetadata.model_validate(row['payload']).model_copy(update={'visible':False})
        storage.upsert_catalogue_app(storage.create_ingestion_run('expert-withdraw-test'),metadata)
        return {'decision':'answer','message':'Do not leak stale explanation', 'generation':{'source':'ollama'}}
    explain.side_effect = withdraw
    r = client.post('/api/v2/chat',json={'message':'Explain the named App'}).json()
    sessions.add(r['session_id'])
    assert r['apps']==[] and r['impression_id'] is None
    assert r['generation']['reason']=='catalogue_changed'
    assert 'Do not leak' not in r['message']


@pytest.mark.parametrize('status',[503,504])
def test_http_and_stream_preserve_scrum28_retrieval_errors(browser,status):
    client, interpret, explain, policy, sessions = browser
    interpret.return_value = {'action':'search','apps':[],'query':'energy'}
    async def failed(**kwargs):
        raise HTTPException(status,'Catalogue search unavailable')
    policy.recommend = failed
    assert client.post('/api/v2/chat',json={'message':'Find energy Apps'}).status_code == status
    streamed = events(client.post('/api/v2/chat/stream',json={'message':'Find energy Apps'}))
    assert streamed[-1]['type']=='problem' and streamed[-1]['status']==status
    explain.assert_not_called()


def test_negative_answer_retains_subject_but_does_not_restore_old_cards(browser):
    client, interpret, explain, policy, sessions = browser
    first = client.post('/api/v2/chat', json={'message':'List the Apps'}).json()
    session = first['session_id']
    sessions.add(session)
    target = next(r['app'] for r in first['apps'] if r['app'].get('name'))
    key = str(next(i+1 for i,r in enumerate(first['apps']) if r['app']['id']==target['id']))
    interpret.return_value = {'action':'answer','apps':[key],'query':'Does it warn about earthquakes?'}
    explain.return_value = {'decision':'no_match','message':'No warning function is documented.',
                           'generation':{'source':'ollama','reason':'reviewed_source_synthesis'}}
    negative = client.post('/api/v2/chat', json={'message':'Does '+target['app_id']+' warn about earthquakes?','session_id':session}).json()
    assert negative['apps']==[] and negative['impression_id'] is None
    assert client.get('/api/v2/sessions/'+session).json()['apps']==[]
    explain.return_value.update(decision='answer',focus=[key],message='It can display readings.')
    follow = client.post('/api/v2/chat', json={'message':'What does it do instead?','session_id':session}).json()
    assert len(follow['apps'])==1
    assert chat.get_session(session)['context']['focused_ids']==[target['id']]
    assert client.get('/api/v2/sessions/'+session).json()['apps'][0]['app']['id']==follow['apps'][0]['app']['id']


@pytest.mark.parametrize('status',[503,504])
def test_new_discovery_directive_preserves_http_sse_errors_and_never_persists_routing_prose(browser,status):
    client, interpret, explain, policy, sessions = browser
    first=client.post('/api/v2/chat',json={'message':'List the Apps'}).json()
    session=first['session_id']
    sessions.add(session)
    explain.return_value={'decision':'search','message':'Do not serve routing prose','focus':[],'generation':{'source':'ollama'}}
    async def failed(**kw):
        raise HTTPException(status,'Catalogue unavailable')
    policy.recommend=failed
    request={'message':'I need Apps for a different task','session_id':session}
    normal=client.post('/api/v2/chat',json=request)
    assert normal.status_code==status and 'routing prose' not in normal.text
    output=events(client.post('/api/v2/chat/stream',json=request))
    assert output[-1]['type']=='problem' and output[-1]['status']==status
    assert not any(e['type']=='explanation_delta' for e in output)
    history=client.get('/api/v2/sessions/'+session).json()
    assert len(history['messages'])==2
    assert 'routing prose' not in json.dumps(history)


@pytest.mark.parametrize('streamed', [False, True])
def test_model_timeout_is_a_retry_without_recommendation_impressions(browser, monkeypatch, streamed):
    client, _, explain, _, sessions = browser
    expert = __import__(recommender.__package__ + '.store_conversation', fromlist=['respond'])
    class UnavailableModel:
        def chat_structured(self, *args, **kwargs):
            raise TimeoutError('protected provider detail')
    monkeypatch.setattr(expert, 'OllamaClient', UnavailableModel)
    explain.side_effect = expert.respond
    request = {'message': 'List the Apps'}
    if streamed:
        output = events(client.post('/api/v2/chat/stream', json=request))
        result = output[-1]
        message = next(e['content'] for e in output if e['type'] == 'explanation_delta')
        apps = next(e['apps'] for e in output if e['type'] == 'recommendations')
        assert result['type'] == 'complete'
    else:
        response = client.post('/api/v2/chat', json=request)
        assert response.status_code == 200
        result = response.json()
        message, apps = result['message'], result['apps']
    sessions.add(result['session_id'])
    assert apps == [] and result['impression_id'] is None
    assert result['generation']['reason'] == 'model_unavailable_or_timeout'
    assert 'try' in message and 'protected provider' not in message
    assert client.get('/api/v2/sessions/' + result['session_id']).json()['apps'] == []


@pytest.mark.parametrize('streamed', [False, True])
def test_app_explanation_keeps_context_cards_when_model_uses_chat_label(browser, streamed):
    client, _, explain, _, sessions = browser
    first = client.post('/api/v2/chat', json={'message': 'List the Apps'}).json()
    session = first['session_id']
    sessions.add(session)
    target = first['apps'][0]['app']
    explain.return_value = {'decision': 'chat', 'focus': ['1'],
                            'message': 'This explanation is about the named App.',
                            'generation': {'source': 'ollama', 'reason': 'reviewed_source_synthesis'}}
    request = {'message': 'Explain ' + target['app_id'], 'session_id': session}
    if streamed:
        output = events(client.post('/api/v2/chat/stream', json=request))
        result = output[-1]
        apps = next(e['apps'] for e in output if e['type'] == 'recommendations')
        assert result['type'] == 'complete'
    else:
        result = client.post('/api/v2/chat', json=request).json()
        apps = result['apps']
    assert result['intent'] == 'conversation'
    assert len(apps) == 1 and apps[0]['app']['id'] == target['id']
    assert apps[0]['app']['store_id'] == target['store_id']
    assert apps[0]['app']['app_id'] == target['app_id']
    assert result['impression_id'] is not None
    restored = client.get('/api/v2/sessions/' + session).json()
    assert [r['app']['id'] for r in restored['apps']] == [target['id']]


@pytest.mark.parametrize('streamed', [False, True])
@pytest.mark.parametrize('unsafe_answer', ['See https://not-served.invalid', '.'])
def test_format_revision_is_reviewed_before_http_or_sse_delivery(browser, monkeypatch, streamed, unsafe_answer):
    client, _, explain, policy, sessions = browser
    target = next(a for a in policy.resolve(None) if a.get('name') and a.get('source_evidence', {}).get('name'))
    expert = __import__(recommender.__package__ + '.store_conversation', fromlist=['respond'])
    safe = {'decision': 'answer', 'focus': ['1'], 'answer': 'The Store names this App ' + target['name'] + '.',
            'evidence': {'1': ['name']}}
    unsafe = {**safe, 'answer': unsafe_answer}
    model = Mock(side_effect=[json.dumps(unsafe), json.dumps(safe), json.dumps({'issues': []})])
    monkeypatch.setattr(expert, 'OllamaClient', lambda: SimpleNamespace(model='test-model', chat_structured=model))
    explain.side_effect = expert.respond
    request = {'message': 'What is the name of ' + target['app_id'] + '?'}
    if streamed:
        response = client.post('/api/v2/chat/stream', json=request)
        output = events(response)
        result = output[-1]
        apps = next(e['apps'] for e in output if e['type'] == 'recommendations')
        assert {'revision', 'review'} <= {e.get('stage') for e in output if e['type'] == 'stage'}
    else:
        response = client.post('/api/v2/chat', json=request)
        assert response.status_code == 200
        result = response.json()
        apps = result['apps']
    sessions.add(result['session_id'])
    assert 'not-served.invalid' not in response.text and safe['answer'] in response.text
    assert result['generation']['source'] == 'ollama' and result['generation']['repair_count'] == 1
    assert len(apps) == 1 and apps[0]['app']['id'] == target['id']
    assert result['generation']['citations'] == [{'number': 1, 'rank': 1, 'field': 'name'}]
    assert model.call_count == 3


@pytest.mark.parametrize('streamed', [False, True])
def test_discussed_sources_remain_visible_without_changing_followup_subject(browser, streamed):
    client, _, explain, _, sessions = browser
    first = client.post('/api/v2/chat', json={'message': 'List the Apps'}).json()
    session = first['session_id']
    sessions.add(session)
    explain.return_value = {'decision': 'answer', 'focus': ['1'], 'display': ['1', '2'],
                            'message': 'One App has a different purpose from the other.',
                            'generation': {'source': 'ollama', 'reason': 'reviewed_source_synthesis'}}
    request = {'message': 'Explain their differences', 'session_id': session}
    if streamed:
        output = events(client.post('/api/v2/chat/stream', json=request))
        result = output[-1]
        apps = next(e['apps'] for e in output if e['type'] == 'recommendations')
    else:
        result = client.post('/api/v2/chat', json=request).json()
        apps = result['apps']
    assert len(apps) == 2 and result['impression_id'] is not None
    assert result['generation']['focus_ids'] == [first['apps'][0]['app']['id']]
    assert chat.get_session(session)['context']['focused_ids'] == result['generation']['focus_ids']
    assert client.get('/api/v2/sessions/' + session).json()['apps'] == apps


@pytest.mark.parametrize('streamed', [False, True])
def test_negative_source_plan_cannot_create_cards_or_impressions(browser, monkeypatch, streamed):
    client, _, explain, policy, sessions = browser
    first = client.post('/api/v2/chat', json={'message': 'List the Apps'}).json()
    session = first['session_id']
    sessions.add(session)
    expert = __import__(recommender.__package__ + '.store_conversation', fromlist=['respond'])
    sources = expert.source_context(first['apps'])
    evidence = {s['key']: [next(iter(s['fields']))] for s in sources if s['fields']}
    draft = {'decision': 'no_match', 'focus': list(evidence),
             'answer': 'None of these Apps documents earthquake warnings.', 'evidence': evidence}
    model = Mock(side_effect=[json.dumps(draft), json.dumps({'issues': []})])
    monkeypatch.setattr(expert, 'OllamaClient', lambda: SimpleNamespace(model='test-model', chat_structured=model))
    explain.side_effect = expert.respond
    request = {'message': 'Would either warn me about earthquakes?', 'session_id': session}
    if streamed:
        output = events(client.post('/api/v2/chat/stream', json=request))
        result = output[-1]
        apps = next(e['apps'] for e in output if e['type'] == 'recommendations')
    else:
        result = client.post('/api/v2/chat', json=request).json()
        apps = result['apps']
    assert apps == [] and result['impression_id'] is None
    assert result['generation']['source'] == 'ollama'
    assert model.call_count == 2 and 'repair_count' not in result['generation']
    assert client.get('/api/v2/sessions/' + session).json()['apps'] == []


@pytest.mark.parametrize('streamed', [False, True])
@pytest.mark.parametrize('missing_initial_citations', [False, True])
def test_retrieved_candidates_do_not_force_unasked_comparisons_or_citations(browser, monkeypatch, streamed, missing_initial_citations):
    client, _, explain, _, sessions = browser
    expert = __import__(recommender.__package__ + '.store_conversation', fromlist=['respond'])
    inspected = []
    def generate(messages, schema, **kwargs):
        if 'issues' in schema.get('properties', {}):
            return json.dumps({'issues': []})
        data = json.loads(messages[1]['content'])
        assert data['retrieval_complete'] is True and len(data['current_sources']) >= 2
        target = [s for s in data['current_sources'] if s['fields'].get('description')][-1]
        inspected.append(target['key'])
        return json.dumps({'decision': 'answer', 'focus': [target['key']],
                           'answer': target['fields']['description'],
                           'evidence': {} if missing_initial_citations and len(inspected) == 1 else {target['key']: ['description']}})
    monkeypatch.setattr(expert, 'OllamaClient', lambda: SimpleNamespace(model='test', chat_structured=generate))
    explain.side_effect = expert.respond
    request = {'message': 'Find Apps for energy'}
    if streamed:
        output = events(client.post('/api/v2/chat/stream', json=request))
        result = output[-1]
        apps = next(e['apps'] for e in output if e['type'] == 'recommendations')
    else:
        result = client.post('/api/v2/chat', json=request).json()
        apps = result['apps']
    sessions.add(result['session_id'])
    assert result['generation']['source'] == 'ollama' and len(apps) == 1
    assert str(apps[0]['rank']) == inspected[0]
    assert result['generation']['focus_ids'] == [apps[0]['app']['id']]
    assert len(result['generation']['citations']) == 1
    assert result['generation'].get('repair_count', 0) == int(missing_initial_citations)
    assert result['impression_id'] is not None
    restored = client.get('/api/v2/sessions/' + result['session_id']).json()
    assert len(restored['apps']) == 1
    assert restored['apps'][0]['rank'] == apps[0]['rank']
    assert [r['app']['id'] for r in chat.get_session(result['session_id'])['context']['last_results']] == [apps[0]['app']['id']]
