"""Prepared Store knowledge: exact facts, current revisions, and requests that keep every term."""
from unittest.mock import Mock

from hedge_shared.store_knowledge import prepare, project
from hedge_shared.store_language import dialogue_language, localize_prose, search_language
from hedge_shared.store_v1 import StoreAppMetadata

from scripts.store_v1_playground import load_service

expert = load_service('prepared_expert', 'expert-recommend')('recommender')
APPS = [StoreAppMetadata(store_id='Store', app_id=key, name=name,
                        description=description, provider=provider, active=True, visible=True)
        for key, name, description, provider in [
            ('native-a', 'Meter View', 'Displays energy readings.', 'Provider A'),
            ('native-b', 'Model Studio', 'Provides shared data models.', 'Provider B'),
        ]]


def test_preparation_keeps_exact_facts_and_rejects_stale_versions():
    app = APPS[0]
    knowledge = prepare(app)
    row = {'id':app.id, 'checksum':app.checksum, 'payload':app.model_dump(exclude={'id','checksum','public_eligible'}),
           'prepared_knowledge':knowledge}
    projected = project(row)
    assert projected.pop("prepared_explanation") == knowledge["explanation"]
    assert projected == app.recommendation_projection()
    for mutation in [{'version':-1}, {'checksum':'stale'}, {'projection':{}}]:
        assert project({**row, 'prepared_knowledge':{**knowledge, **mutation}}) == app.recommendation_projection()
    assert 'source_evidence' not in row['payload']


def test_unknown_requirements_negation_and_quotes_are_never_dropped():
    assert search_language('"Enerji" olmadan MQTT kuantumtelepati','tr') == '"Enerji" without MQTT kuantumtelepati'
    assert search_language('İÇİN','tr') == 'for'
    assert dialogue_language('Sadece ücretsiz uygulamaları göster','tr') == 'Sadece ücretsiz uygulamaları göster'
    source = '- App 1: description: "Supplied source fields only; missing metadata cannot be confirmed."'
    assert localize_prose(source,'tr') == source


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


def test_aliases_preserve_unknown_constraints_quoted_identity_and_prior_requirements():
    assert search_language('"Common Vocabulary" without quantumtelepathy', 'en') == '"Common Vocabulary" without quantumtelepathy'
    query = 'Our teams need offline access. Is there something for shared data models?'
    assert 'offline' in search_language(query, 'en')
    query = 'Our teams use MQTT. Could you help us manage data models?'
    assert 'MQTT' in search_language(query, 'en')
    query = 'Our teams use different names for the same data. Could you help us manage data models?'
    assert search_language(query, 'en') == 'Could you help us manage data models?'


def test_reviewed_compound_passage_requires_current_original_support():
    assessor = load_service('prepared_semantics', 'expert-recommend')('suitability')
    app = StoreAppMetadata(store_id='Store', app_id='Compound', name='Compound',
        description='Regional readings from multiple meters are combined under a common record.',
        active=True, visible=True)
    projection = app.recommendation_projection()
    prose = {'summary':'Combines readings from multiple meters.',
             'simple':'Brings meter readings together.', 'use_when':'combining meter readings'}
    artifact = {'version':1, 'review':{'method':'agent_source_review', 'reviewer':'Fixture', 'note':'Checked source.'}, 'en':prose, 'tr':prose, 'facts':[{
        'path':'description', 'quote':app.description,
        'en':prose['summary'], 'tr':prose['summary']}]}
    projection['prepared_explanation'] = artifact
    assert assessor.assess('combine readings from multiple meters', projection, 'en')['status'] == 'source_supported'
    assert assessor.assess('combine earthquake predictions', projection, 'en')['status'] == 'uncertain'
    assert assessor.assess('combine readings without MQTT', projection, 'en')['status'] != 'source_supported'
    assert assessor.assess('combine no readings from multiple meters', projection, 'en')['status'] == 'uncertain'
    projection['source_evidence']['readme'] = 'This app does not combine readings from multiple meters.'
    assert assessor.assess('combine readings from multiple meters', projection, 'en')['status'] == 'uncertain'
    projection['source_evidence'].pop('readme')
    projection['source_evidence']['description'] = 'The earlier workflow has been removed.'
    assert assessor.assess('combine readings from multiple meters', projection, 'en')['status'] == 'uncertain'
    knowledge = {**prepare(app), 'explanation':artifact}
    row = {'id':app.id, 'checksum':'changed', 'payload':app.model_dump(exclude={'id','checksum','public_eligible'}), 'prepared_knowledge':knowledge}
    assert 'prepared_explanation' not in project(row)
