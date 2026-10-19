"""Routine Store turns must remain useful when every generation seam is broken."""
import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, Mock

import pytest
from hedge_shared.models_v2 import ChatRequestV2
from hedge_shared.store_knowledge import prepare, project
from hedge_shared.store_language import dialogue_language, localize_prose, search_language
from hedge_shared.store_v1 import StoreAppMetadata

from scripts.store_v1_playground import load_service

expert = load_service('prepared_expert', 'expert-recommend')('recommender')
policy_module = load_service('prepared_policy', 'chat-intent')('store_conversation')
APPS = [StoreAppMetadata(store_id='Store', app_id=key, name=name,
                        description=description, provider=provider, active=True, visible=True)
        for key, name, description, provider in [
            ('native-a', 'Meter View', 'Displays energy readings.', 'Provider A'),
            ('native-b', 'Model Studio', 'Provides shared data models.', 'Provider B'),
        ]]


@pytest.fixture
def routine(monkeypatch):
    apps = [a.recommendation_projection() for a in APPS]
    def resolve(ids):
        return [deepcopy(a) for a in apps if ids is None or a['id'] in ids]
    def search(query, **kwargs):
        return [{'app':deepcopy(a), 'rank':i+1} for i,a in enumerate(apps)]
    monkeypatch.setattr(expert, '_search_apps_v2', search)
    model = Mock(side_effect=AssertionError('Routine generation attempted'))
    monkeypatch.setattr(expert, 'OllamaClient', model)
    async def recommend(**kwargs):
        return expert.recommend_v2(**kwargs, limit=5)
    policy = policy_module.StoreConversation(recommend, resolve, expert._recommendation_narrative, model, model, decide=expert._recommendation_decision)
    return policy, model, apps


def ask(policy, message, intent='search', context=None, locale='en', filters=None):
    return asyncio.run(policy.respond_with_history(
        ChatRequestV2(message=message, locale=locale, filters=filters or {}), intent,
        context or {}, [], nlu={'intent':intent},
    ))


def test_preparation_keeps_exact_facts_and_rejects_stale_versions():
    app = APPS[0]
    knowledge = prepare(app)
    row = {'id':app.id, 'checksum':app.checksum, 'payload':app.model_dump(exclude={'id','checksum','public_eligible'}),
           'prepared_knowledge':knowledge}
    assert project(row) == app.recommendation_projection()
    for mutation in [{'version':-1}, {'checksum':'stale'}, {'projection':{}}]:
        assert project({**row, 'prepared_knowledge':{**knowledge, **mutation}}) == app.recommendation_projection()
    assert 'source_evidence' not in row['payload']


@pytest.mark.parametrize(('message','locale','supported'), [
    ('Find apps for energy readings','en', True),
    ('Which app supports energy readings?','en', True),
    ('Enerji okumaları için uygulama bul','tr', True),
    ('Paylaşılan veri modelleri için uygulama bul','tr', True),
    ('Find apps for earthquake warnings','en', False),
    ('Enerji okumaları ve deprem uyarıları için uygulama bul','tr', False),
    ('Only energy readings without MQTT','en', False),
    ('Sadece enerji okumaları için uygulama bul','tr', False),
    ('Kuantumtelepati için uygulama bul','tr', False),
])
def test_multilingual_decisions_reuse_suitability_without_llm(routine, message, locale, supported):
    policy, model, apps = routine
    result = ask(policy, message, locale=locale)
    assert bool(result['apps']) is supported
    assert result['decision']['outcome'] == ('recommended' if supported else 'abstained')
    assert len(result['apps']) + len(result.get('candidates', [])) in (0, 2)
    assert result['generation']['source'] == 'prepared'
    assert {r['app']['id'] for r in [*result['apps'],*result.get('candidates',[])]} <= {a['id'] for a in apps}
    model.assert_not_called()


def test_browse_followups_comparison_and_publisher_keep_current_identity(routine):
    policy, model, apps = routine
    first = ask(policy,'Tüm uygulamaları göster',locale='tr')
    assert len(first['apps']) == 2 and 'yayımlanmış' in first['message']
    second = ask(policy, 'İkinci uygulamayı açıkla', context=first['context'], locale='tr')
    assert second['apps'][0]['app'] == apps[1]
    assert 'sağlanan' in second['message']
    compared = ask(policy, 'İkisini karşılaştır', context=first['context'],locale='tr')
    assert len(compared['apps']) == 2 and 'karşılaştırılıyor' in compared['message']
    filtered = ask(policy,'Show me all available applications',filters={'publisher':'Provider B'})
    assert [r['app']['id'] for r in filtered['apps']] == [apps[1]['id']]
    assert not ask(policy,'Tell me more about the fifth app', context=first['context'])['apps']
    model.assert_not_called()


def test_unknown_requirements_negation_and_quotes_are_never_dropped():
    assert search_language('"Enerji" olmadan MQTT kuantumtelepati','tr') == '"Enerji" without MQTT kuantumtelepati'
    assert search_language('İÇİN','tr') == 'for'
    assert dialogue_language('Sadece ücretsiz uygulamaları göster','tr') == 'Sadece ücretsiz uygulamaları göster'
    source = '- App 1: description: "Supplied source fields only; missing metadata cannot be confirmed."'
    assert localize_prose(source,'tr') == source


def test_late_withdrawal_clears_cards_and_references(routine):
    policy, model, apps = routine
    original = policy.resolve
    count = 0
    def resolve(ids):
        nonlocal count
        count += 1
        return [] if count > 1 else original(ids)
    policy.resolve = resolve
    result = ask(policy,'Show me all available apps')
    assert result['apps'] == [] and result['decision']['reason'] == 'catalogue_changed'
    assert result['context']['last_results'] == result['context']['focused_ids'] == []


def test_complex_reasoning_is_disabled_by_default_and_has_useful_fallback(routine):
    policy, model, apps = routine
    result = ask(policy, 'Reason in depth: Tell me about Meter View', intent='detail')
    assert result['apps'] and result['generation']['reason'] == 'reasoning_disabled'
    assert 'Displays energy readings.' in result['message']
    model.assert_not_called()


def test_optional_reasoning_timeout_keeps_source_evidence_and_abstention(routine, monkeypatch):
    policy, model, apps = routine
    policy.settings.STORE_REASONING_ENABLED = True
    policy.settings.STORE_REASONING_SECONDS = 0.01
    def explain(*args, **kwargs):
        import time
        time.sleep(.2)
        return {'message':'unsafe late prose','generation':{'source':'ollama'}}
    policy.explain = explain
    result = ask(policy, 'Reason in depth: Tell me about Meter View', intent='detail')
    assert result['apps'] and 'unsafe' not in result['message']
    assert result['generation']['reason'] == 'reasoning_fallback'


def test_search_errors_are_not_abstentions(routine):
    from fastapi import HTTPException
    policy, *_ = routine
    policy.recommend = AsyncMock(side_effect=HTTPException(504,'Catalogue search timed out'))
    with pytest.raises(HTTPException) as error:
        ask(policy,'Find energy readings')
    assert error.value.status_code == 504


def test_unique_other_app_and_comparison_followups_do_not_call_model(routine):
    policy, model, apps = routine
    first = ask(policy,'Show me all available apps')
    detail = ask(policy,'Tell me about the first app', context=first['context'])
    other = ask(policy,'What does the other one do?',intent='detail',context=detail['context'])
    assert [r['app']['id'] for r in other['apps']] == [apps[1]['id']]
    assert not ask(policy,'What does the other one do?',intent='detail',context=first['context'])['apps']
    compared = ask(policy,'How do those differ?',context=first['context'])
    assert len(compared['apps']) == 2
    model.assert_not_called()


def test_optional_model_abstention_is_preserved_without_promoting_candidates(routine):
    policy, model, apps = routine
    policy.settings.STORE_REASONING_ENABLED = True
    policy.explain = lambda *a, **k: {'message':'Evidence does not establish suitability.',
        'decision':'no_match', 'generation':{'source':'ollama','reason':'reviewed_source_synthesis'}}
    result = ask(policy,'Reason in depth: Find energy readings')
    assert not result['apps'] and result['decision']['reason'] == 'model_abstention'
    assert result['context']['last_results'] == result['context']['focused_ids'] == []
    assert len(result['candidates']) == 2


def test_expert_readiness_does_not_require_optional_ollama(monkeypatch):
    from fastapi import Response
    main = load_service('prepared_expert_health','expert-recommend')('main')
    monkeypatch.setattr(main.httpx,'get',lambda *a,**k: Mock(status_code=200))
    model = Mock(side_effect=AssertionError('Readiness touched optional generation'))
    monkeypatch.setattr(main,'OllamaClient',model,raising=False)
    response = Response()
    assert main.health(response)['status'] == 'ok'
    assert response.status_code == 200
    model.assert_not_called()


def test_optional_reasoning_has_one_transport_deadline(monkeypatch):
    import time

    import httpx

    llm = load_service('prepared_deadline_expert','expert-recommend')('llm_client')
    original_client = httpx.AsyncClient
    cancelled = []
    async def slow(request):
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        return httpx.Response(200,json={'done':True,'message':{'content':'unserved'}})
    monkeypatch.setattr(llm.httpx,'AsyncClient', lambda **kwargs:
        original_client(transport=httpx.MockTransport(slow),**kwargs))
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        llm.OllamaClient().chat_structured([],{},deadline=started+.03)
    assert time.monotonic()-started < .5 and cancelled == [True]


def test_version_numbers_in_requirements_do_not_become_ordinal_references(routine):
    policy, model, apps = routine
    first = ask(policy,'List apps')
    result = ask(policy,'Find apps supporting connector version 1.2',context=first['context'])
    assert result['apps'] == [] and result['decision']['outcome'] == 'abstained'
    detail = ask(policy,'Show me the second app',context=first['context'])
    assert [r['app']['id'] for r in detail['apps']] == [apps[1]['id']]
    model.assert_not_called()


@pytest.mark.parametrize(('message','locale','supported'),[
    ('Does Meter View support energy readings?','en',True),
    ('Does Meter View support earthquake warnings?','en',False),
    ('Meter View enerji okumaları destekliyor mu?','tr',True),
    ('Meter View deprem uyarıları destekliyor mu?','tr',False),
])
def test_named_capability_questions_use_the_existing_source_decision(routine,message,locale,supported):
    policy, model, apps = routine
    result = ask(policy,message,intent='detail',locale=locale)
    assert bool(result['apps']) is supported
    assert result['decision']['outcome'] == ('recommended' if supported else 'abstained')
    assert all(r['app']['id'] == apps[0]['id'] for r in [*result['apps'],*result.get('candidates',[])])
    model.assert_not_called()
