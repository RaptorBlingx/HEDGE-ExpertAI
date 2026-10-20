"""Factual reads must not become capability decisions or model-selected intents."""
import asyncio
from copy import deepcopy
from unittest.mock import Mock

import pytest
from hedge_shared.models_v2 import ChatRequestV2
from hedge_shared.store_explanations import readable_passage
from hedge_shared.store_knowledge import prepare
from hedge_shared.store_language import catalogue_question
from hedge_shared.store_v1 import StoreAppMetadata

from scripts.store_v1_playground import load_service

expert = load_service('factual_dialogue_expert', 'expert-recommend')('store_conversation')
chat = load_service('factual_dialogue_chat', 'chat-intent')('store_conversation')


@pytest.fixture
def conversation(monkeypatch):
    monkeypatch.setenv('STORE_SEMANTIC_ENABLED', 'true')
    apps = []
    for app_id, name, provider, purpose in [('alpha', 'Device Register', 'Example Labs', 'publish device records'),
                                          ('beta', 'Sample Monitor', 'Other Labs', 'monitor laboratory samples')]:
        k = prepare(StoreAppMetadata(store_id='synthetic-only', app_id=app_id, name=name,
            provider=provider, readme='Used to ' + purpose + '.', active=True, visible=True))
        apps.append({**k['projection'], 'prepared_explanation': k['explanation']})
    def resolve(ids):
        return [deepcopy(a) for a in apps if ids is None or a['id'] in ids]
    async def recommend(**kwargs):
        return expert._recommendation_decision(kwargs['query'], [{'app':a, 'rank':i+1} for i,a in enumerate(apps)], 'en')
    interpreter = Mock(side_effect=AssertionError('No inference for an exact metadata read'))
    def present(q, response, locale):
        return expert.prepared_answer(q, response, locale)
    policy = chat.StoreConversation(recommend, resolve, lambda *a:'', interpreter, Mock(),
        decide=expert._recommendation_decision, present=present)
    return policy, apps, interpreter


def ask(policy, question, context):
    return asyncio.run(policy.respond_with_history(ChatRequestV2(message=question,locale='en'),
        'compare', context, [], nlu={'source':'rasa','intent':'compare','confidence':1.0}))


@pytest.mark.parametrize('question', ['Who provides it?', 'Who is the provider of Device Register?',
    'Who is it provided by?', 'Which company provides Device Register?',
    'Who provides that one?', 'Who supplies this one?'])
def test_direct_provider_outranks_wrong_rasa_without_inference(conversation, question):
    policy, apps, interpreter = conversation
    result = ask(policy, question, {'turn':1,'focused_ids':[apps[0]['id']]})
    assert result['message'] == '**Device Register** is provided by **Example Labs**.'
    assert result['generation']['source'] == 'prepared'
    assert result['context']['focused_ids'] == [apps[0]['id']]
    interpreter.assert_not_called()


def test_named_target_switch_then_other_app_retains_identity(conversation):
    policy, apps, interpreter = conversation
    context = {'turn':1,'focused_ids':[apps[0]['id']], 'comparison_ids':[a['id'] for a in apps]}
    result = ask(policy,'Who is the provider of Sample Monitor?',context)
    assert 'Other Labs' in result['message']
    result = ask(policy,'Who provides the other App?',result['context'])
    assert result['message'] == '**Device Register** is provided by **Example Labs**.'
    interpreter.assert_not_called()


def test_no_guess_for_ambiguous_provider_or_constrained_metadata_target(conversation):
    policy, _, interpreter = conversation
    for question in ['Who is the provider?', 'Who provides Device Register with automatic forecasting?']:
        result = ask(policy, question, {'turn':1})
        assert not result['apps']
        assert 'Example Labs' not in result['message']
    interpreter.assert_not_called()


def test_explanation_binding_survives_factual_interlude(conversation):
    policy, apps, interpreter = conversation
    result = ask(policy,'What is Device Register for?',{'turn':1})
    binding = result['context']['explanation_focus']
    result = ask(policy,'Who provides it?',result['context'])
    assert result['context']['explanation_focus'] == binding
    result = ask(policy,'Can you make that simpler?',result['context'])
    assert 'share device records' in result['message']
    assert result['context']['focused_ids'] == [apps[0]['id']]
    interpreter.assert_not_called()


def test_passage_edits_retain_adjacent_qualification_and_no_new_objects():
    text = ('The percentage that each group will contribute to the total is kept on record. '
            'This information becomes critical to the subsequent review. '
            'It is unavailable without a paid account.')
    actual = readable_passage(text)
    assert 'records the percentage each group will contribute to the total' in actual
    assert 'That record is needed for the later review.' in actual
    assert 'It is unavailable without a paid account.' in actual
    assert 'offer' not in actual and 'settlement' not in actual


def test_recorded_measure_simplifies_a_new_process_without_dropping_conditions():
    source = ('The percentage that each group will contribute to the total is kept on record. '
              'This information becomes critical to the subsequent allocation process, '
              'which requires information about the ratio to divide the available budget, as applicable.')
    assert readable_passage(source, brief=True) == (
        'Allocation uses the recorded percentages to divide the available budget, as applicable.')
    restricted = source.replace('is kept on record', 'is kept on record only with a licensed account')
    actual = readable_passage(restricted, brief=True)
    assert 'only with a licensed account' in actual
    assert actual != readable_passage(source, brief=True)


@pytest.mark.parametrize('question', ['What is Sample Monitor for?', 'What is Sample Monitor used for?',
                                    'What does Sample Monitor do?'])
def test_purpose_target_does_not_swallow_the_used_for_suffix(conversation, question):
    policy, apps, interpreter = conversation
    result = ask(policy, question, {'turn':1,'focused_ids':[apps[0]['id']]})
    assert 'monitor laboratory samples' in result['message']
    assert result['context']['focused_ids'] == [apps[1]['id']]
    interpreter.assert_not_called()


def test_catalogue_operation_is_invariant_to_presentation_and_composes_inspection(conversation):
    policy, apps, interpreter = conversation
    for operation in ['List applications', 'What apps are available',
                      'List applications and describe each one',
                      'Browse the catalogue; explain their purposes']:
        for transform in [str.lower, str.upper, lambda s: '  ' + s.replace(' ', '   ') + '  ']:
            for punctuation in ['', ',', '?!', '…']:
                result = ask(policy, transform(operation + punctuation), {})
                assert result['intent'] == 'browse'
                assert {r['app']['id'] for r in result['apps']} == {a['id'] for a in apps}
                assert 'publish device records' in result['message']
                assert 'monitor laboratory samples' in result['message']
                assert result['decision']['outcome'] == 'not_applicable'
    interpreter.assert_not_called()


def test_composed_browse_never_drops_unknown_words_or_constraints():
    for suffix in ['for forecasting', 'without registration', 'and predict prices',
                   'and describe each one with automatic translation', 'but only free ones']:
        assert not catalogue_question('List applications ' + suffix)
    assert not catalogue_question('List only free applications and describe each one')


def test_resolved_inspection_uses_sources_and_preserves_topic_switches(conversation):
    policy, apps, interpreter = conversation
    context = {}
    for target in ['Device Register', 'beta', 'the other App']:
        result = ask(policy, 'Tell me about ' + target, context)
        context = result['context']
        assert result['intent'] == 'source_fields'
        assert len(result['apps']) == 1
        assert result['generation']['source'] == 'prepared'
    assert context['focused_ids'] == [apps[0]['id']]
    interpreter.assert_not_called()


def test_ui_action_resolves_pair_even_with_duplicate_or_missing_names(conversation):
    policy, apps, interpreter = conversation
    new = prepare(StoreAppMetadata(store_id='second-store', app_id=apps[0]['app_id'],
        name=apps[0]['name'], provider='New Supplier', readme='Used to track deliveries.',
        active=True, visible=True))
    apps.append({**new['projection'], 'prepared_explanation': new['explanation']})
    for name in [apps[-1]['name'], None]:
        apps[-1]['name'] = name
        policy.routine = name is not None  # UI identity does not depend on planner mode.
        result = asyncio.run(policy.respond_with_history(ChatRequestV2(
            message='Tell me about Unnamed App', app_action={
                'type':'inspect', 'store_id':apps[-1]['store_id'], 'app_id':apps[-1]['app_id']}),
            'help', {}, []))
        assert [r['app']['id'] for r in result['apps']] == [apps[-1]['id']]
        assert 'track deliveries' in result['message']
        assert result['context']['focused_ids'] == [apps[-1]['id']]
    interpreter.assert_not_called()


def test_stale_or_out_of_scope_action_never_rebinds_to_a_different_app(conversation):
    policy, apps, interpreter = conversation
    result = asyncio.run(policy.respond_with_history(ChatRequestV2(message='Tell me about Device Register',
        app_action={'type':'inspect','store_id':'not-authorized','app_id':apps[0]['app_id']}),
        'detail', {'focused_ids':[apps[1]['id']]}, []))
    assert not result['apps'] and not result['context']['focused_ids']
    assert result['decision']['reason'] == 'unavailable_action_target'
    interpreter.assert_not_called()


def test_broader_synthetic_catalogue_is_bounded_without_ranking_or_manual_preparation(conversation):
    policy, apps, interpreter = conversation
    for i in range(100):
        k = prepare(StoreAppMetadata(store_id='synthetic-only', app_id=f'new-{i:03}',
            name=f'Catalogue Tool {i}', readme=f'Used to record device group {i}.', active=True, visible=True))
        apps.append({**k['projection'], 'prepared_explanation':k['explanation']})
    result = ask(policy, 'List applications and describe each one.', {})
    assert len(result['apps']) == 5
    assert all(r['evidence_fields'] == ['catalogue'] for r in result['apps'])
    assert 'Catalogue Tool 0' in result['message']
    # This is an authored fixture contract check, not live retrieval-quality evidence.
    interpreter.assert_not_called()
