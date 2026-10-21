"""Factual reads must not become capability decisions or model-selected intents."""
import asyncio
from copy import deepcopy
from unittest.mock import Mock

import pytest
from hedge_shared.models_v2 import ChatRequestV2
from hedge_shared.store_explanations import readable_passage
from hedge_shared.store_knowledge import prepare
from hedge_shared.store_language import (
    catalogue_question,
    catalogue_reference,
    comparison_question,
    factual_question,
)
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


def ask(policy, question, context, *, nlu_intent='compare'):
    return asyncio.run(policy.respond_with_history(ChatRequestV2(message=question,locale='en'),
        nlu_intent, context, [], nlu={'source':'rasa','intent':nlu_intent,'confidence':1.0}))


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
    result = ask(policy, 'Compare that with the other app.',
        {'turn':2, 'focused_ids':[apps[0]['id']], 'comparison_ids':[a['id'] for a in apps],
         'last_results':[{'app':apps[0], 'rank':1}]})
    assert result['intent'] == 'compare'
    assert {r['app']['id'] for r in result['apps']} == {a['id'] for a in apps}
    interpreter.assert_not_called()


def test_implicit_subject_cannot_be_replaced_by_a_better_functional_match(conversation):
    policy, apps, interpreter = conversation
    interpreter.side_effect = None
    interpreter.return_value = {'action':'search', 'apps':['2'], 'query':'publish device records',
                                'view':'capability', 'reference':'focus'}
    context = {'turn':1, 'focused_ids':[apps[1]['id']],
               'last_results':[{'app':a, 'rank':i+1} for i,a in enumerate(apps)]}
    result = ask(policy, 'Could this application publish device records?', context)
    assert not result['apps']
    assert result['context']['focused_ids'] == [apps[1]['id']]
    assert result['intent'] == 'detail'
    assert result['message'].startswith('I couldn’t confirm that from **Sample Monitor**’s description.')
    interpreter.assert_called_once()
    # An explicit new discovery request still uses the proven prepared path.
    result = ask(policy, 'Find an app to publish device records.', context)
    assert result['apps'][0]['app']['id'] == apps[0]['id']
    assert result['generation']['source'] == 'prepared'
    interpreter.assert_called_once()


def test_resolved_singular_subject_stays_singular_after_negative_capability_check(conversation):
    policy, apps, interpreter = conversation
    interpreter.side_effect = None
    interpreter.return_value = {'action':'compare', 'apps':['1','2'], 'query':'publish device records',
                                'view':'comparison', 'reference':'other'}
    context = {'turn':2, 'focused_ids':[apps[0]['id']],
               'comparison_ids':[a['id'] for a in apps],
               'last_results':[{'app':a, 'rank':i+1} for i,a in enumerate(apps)]}
    result = ask(policy, 'Does the other one do that too?', context)
    assert not result['apps'] and result['intent'] == 'detail'
    assert 'couldn’t confirm that from **Sample Monitor**’s description' in result['message']
    assert 'main difference' not in result['message']
    result = ask(policy, 'Who provides it?', result['context'])
    assert result['message'] == '**Sample Monitor** is provided by **Other Labs**.'


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


def test_operation_composition_resolves_embedded_fields_and_sequence(conversation):
    policy, apps, interpreter = conversation
    for inspection in ['describe each one', 'explain what they do',
                       'tell me what every application is for',
                       'explain the purpose of each app']:
        for conjunction in ['and', 'then', 'and then']:
            for question in [f'List applications {conjunction} {inspection}.',
                             f'{inspection} {conjunction} list applications.']:
                result = ask(policy, question, {})
                assert result['intent'] == 'browse', question
                assert len(result['apps']) == len(apps)
                assert result['decision']['outcome'] == 'not_applicable'
    for suffix in ['with a free licence', 'and guarantee free use', 'and delete them',
                   'without registration', 'and explain automatic forecasting']:
        assert not catalogue_question('List applications and explain what they do ' + suffix)
    assert factual_question('What can Device Register do?') is None
    interpreter.assert_not_called()


def test_comparison_assesses_each_app_against_the_same_need(conversation):
    policy, apps, interpreter = conversation
    context = {'turn':1, 'last_results':[{'app':a,'rank':i+1} for i,a in enumerate(apps)],
               'focused_ids':[apps[0]['id']], 'explanation_topic':'publish device records'}
    result = ask(policy, 'Compare both.', context)
    assert 'documented match is **Device Register**' in result['message']
    assert 'don’t document “publish device records” for **Sample Monitor**' in result['message']
    assert 'does not support' not in result['message']
    assert result['context']['focused_ids'] == [apps[0]['id']]
    # A new comparison criterion overrides the old need, without claiming that
    # different purpose evidence proves a negative capability.
    result = ask(policy, 'Compare Device Register and Sample Monitor for monitor laboratory samples.', context)
    assert 'documented match is **Sample Monitor**' in result['message']
    result = ask(policy, 'Compare both for monitor laboratory samples and predict prices.', context)
    assert 'documented match is' not in result['message']
    assert ('**Sample Monitor** covers “monitor laboratory samples”' in result['message']
            and 'It doesn’t mention “predict prices”.' in result['message'])
    assert 'don’t document “monitor laboratory samples and predict prices” for **Device Register**.' in result['message']
    result = ask(policy, 'Compare both without a paid account for publish device records.', context)
    assert 'documented match is' not in result['message']
    assert not result['apps']  # The commercial restriction still fails closed.
    result = ask(policy, 'Compare both offline for publish device records.', context)
    assert 'documented match is' not in result['message']
    assert 'offline' in result['context']['comparison_need']
    # An unmatched new need must not resurrect an older supported requirement.
    policy.interpret = Mock(return_value={'action':'search','apps':[],
        'query':'predict electricity prices','view':'capability'})
    result = ask(policy, 'Find an application to predict electricity prices.', context)
    result = ask(policy, 'Compare both.', result['context'])
    assert 'documented match is' not in result['message']
    interpreter.assert_not_called()


def test_rejected_commercial_and_typed_filters_keep_their_reason_without_inference(conversation):
    policy, apps, interpreter = conversation
    result = ask(policy, 'List only free applications.', {})
    assert not result['apps']
    assert result['decision']['reason'] == 'unverified_filters'
    assert '0 doesn’t confirm free use' in result['message']
    assert 'provider' in result['message'] and 'listed prices' in result['message']
    result = asyncio.run(policy.respond_with_history(ChatRequestV2(message='List applications',
        filters={'capabilities':['MQTT'], 'publisher':'Example Labs'}), 'help', {}, []))
    assert not result['apps']
    assert 'capabilities' in result['message']
    assert result['decision']['reason'] == 'unverified_filters'
    # A functional use of price vocabulary is not a commercial filter refusal.
    result = asyncio.run(policy._prepared_response(ChatRequestV2(
        message='Find applications to predict prices.'), 'search', {}, []))
    assert result.get('decision', {}).get('reason') != 'unverified_filters'
    # Suggested source inspection must actually display pricing, independent of
    # singular/plural wording; zero and false flags never establish free use.
    for app in apps:
        app['source_evidence'].update(price='0', billable='false')
    for q in ['Can you show me the listed prices for Device Register?',
              'What is the listed price of Device Register?']:
        result = ask(policy, q, {})
        assert result['source_field'] == 'billing fields'
        assert 'Pricing isn’t confirmed' in result['message']
        assert 'doesn’t establish free use' in result['message']
    interpreter.assert_not_called()


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


@pytest.mark.parametrize('question', ['Can you name the provider of that app?', 'Find the provider of Device Register.'])
def test_interpreted_metadata_operation_survives_functional_fallback(conversation, question):
    policy, apps, interpreter = conversation
    interpreter.side_effect = None
    interpreter.return_value = {'action':'answer', 'view':'provider', 'query':'',
                                'apps':['1'], 'reference':'focus'}
    result = ask(policy, question, {'turn':1, 'focused_ids':[apps[0]['id']],
        'last_results':[{'app':apps[0], 'rank':1}], 'comparison_need':'publish device records',
        'last_outcome':'abstained'}, nlu_intent='help')
    assert result['message'] == '**Device Register** is provided by **Example Labs**.'
    if factual_question(question):
        assert result['generation']['source'] == 'prepared'
        interpreter.assert_not_called()
    else:
        assert result['generation']['routing']['view'] == 'provider'
        interpreter.assert_called_once()
    assert result['decision']['reason'] == 'source_inspection'


def test_ordering_adverb_is_not_an_app_ordinal_or_a_capability(conversation):
    policy, apps, interpreter = conversation
    interpreter.side_effect = None
    interpreter.return_value = {'action':'answer', 'view':'access', 'query':'',
                                'apps':['2'], 'reference':'focus'}
    result = ask(policy, 'What should we check first to start using it?',
        {'turn':2, 'focused_ids':[apps[1]['id']], 'comparison_ids':[a['id'] for a in apps],
         'last_results':[{'app':a, 'rank':i+1} for i,a in enumerate(apps)]})
    assert result['generation']['routing']['subject_ids'] == [apps[1]['id']]
    assert result['decision']['reason'] == 'source_inspection'
    assert 'Installation steps' in result['message'] and 'Sample Monitor' in result['message']


def test_selection_from_displayed_set_checks_all_bound_candidates(conversation):
    policy, apps, interpreter = conversation
    interpreter.side_effect = None
    interpreter.return_value = {'action':'search', 'view':'capability', 'query':'publish device records',
                                'apps':['1','2'], 'reference':'both'}
    # Retrieval can miss an explicitly displayed candidate; this question asks
    # about that complete set, so resolve it authoritatively before assessment.
    async def missed_candidate(**kwargs):
        return expert._recommendation_decision(kwargs['query'], [{'app':apps[1], 'rank':1}], 'en')
    policy.recommend = missed_candidate
    result = ask(policy, 'From those options, which would publish device records?',
        {'turn':2, 'focused_ids':[apps[1]['id']], 'comparison_ids':[a['id'] for a in apps],
         'last_results':[{'app':a, 'rank':i+1} for i,a in enumerate(apps)]})
    assert result['intent'] == 'search' and result['decision']['outcome'] == 'recommended'
    assert [r['app']['id'] for r in result['apps']] == [apps[0]['id']]
    assert set(result['generation']['routing']['candidate_ids']) == {a['id'] for a in apps}


def test_model_focus_hint_cannot_turn_unbound_discovery_into_single_app_check(conversation):
    policy, apps, interpreter = conversation
    interpreter.side_effect = None
    interpreter.return_value = {'action':'answer', 'view':'capability', 'query':'publish device records',
                                'apps':['2'], 'reference':'focus'}
    result = ask(policy, 'Which of those would publish device records?',
        {'turn':2, 'focused_ids':[apps[1]['id']], 'comparison_ids':[a['id'] for a in apps],
         'last_results':[{'app':a, 'rank':i+1} for i,a in enumerate(apps)]}, nlu_intent='search')
    assert result['intent'] == 'search' and result['decision']['outcome'] == 'recommended'
    assert [r['app']['id'] for r in result['apps']] == [apps[0]['id']]


def test_semantic_singular_reference_survives_missing_lexical_reference(conversation):
    policy, apps, interpreter = conversation
    interpreter.side_effect = None
    interpreter.return_value = {'action':'answer', 'view':'capability', 'query':'publish device records',
                                'apps':['2'], 'reference':'focus'}
    for reference in ['focus', 'none']:
        interpreter.return_value['reference'] = reference
        result = ask(policy, 'Would the application from our earlier discussion publish device records?',
            {'turn':2, 'focused_ids':[apps[1]['id']], 'comparison_ids':[a['id'] for a in apps],
             'last_results':[{'app':apps[1], 'rank':1}]}, nlu_intent='detail')
        assert result['intent'] == 'detail' and not result['apps']
        assert result['context']['focused_ids'] == [apps[1]['id']]
        assert result['generation']['routing']['subject_ids'] == [apps[1]['id']]
    interpreter.return_value.update(action='search', reference='none', apps=[])
    result = ask(policy, 'Does it publish device records?',
        {'turn':2, 'focused_ids':[apps[1]['id']], 'comparison_ids':[a['id'] for a in apps],
         'last_results':[{'app':apps[1], 'rank':1}]}, nlu_intent='detail')
    assert result['intent'] == 'detail' and not result['apps']
    assert result['generation']['routing']['subject_ids'] == [apps[1]['id']]


def test_comparison_does_not_replace_normalized_need_with_operation_text(conversation):
    policy, apps, interpreter = conversation
    interpreter.side_effect = None
    interpreter.return_value = {'action':'compare', 'view':'comparison', 'query':'publish device records',
                                'apps':['1','2'], 'reference':'both'}
    result = ask(policy, 'How would the two fit publication of device records?',
        {'turn':2, 'focused_ids':[apps[1]['id']], 'comparison_ids':[a['id'] for a in apps],
         'last_results':[{'app':a, 'rank':i+1} for i,a in enumerate(apps)],
         'comparison_need':'monitor laboratory samples'})
    assert result['context']['comparison_need'] == 'publish device records'
    assert 'documented match is **Device Register**' in result['message']
    assert 'document “publish device records” for **Sample Monitor**' in result['message']


def test_unextracted_comparison_command_cannot_replace_established_need(conversation):
    policy, apps, interpreter = conversation
    interpreter.side_effect = None
    question = "Compare its role with the other application's."
    interpreter.return_value = {'action':'compare', 'view':'comparison', 'query':question.rstrip('.'),
                                'apps':['1'], 'reference':'focus'}
    result = ask(policy, question,
        {'turn':2, 'focused_ids':[apps[0]['id']], 'comparison_ids':[a['id'] for a in apps],
         'last_results':[{'app':apps[0], 'rank':1}], 'comparison_need':'publish device records',
        'last_outcome':'abstained'}, nlu_intent='help')
    assert result['context']['comparison_need'] == 'publish device records'
    assert 'documented match is **Device Register**' in result['message']
    interpreter.assert_called_once()


def test_interpretation_preserves_retrieval_order_instead_of_native_id_order(conversation):
    policy, apps, interpreter = conversation
    interpreter.side_effect = None
    interpreter.return_value = {'action':'search', 'view':'capability', 'query':'monitor room temperatures',
                                'apps':[], 'reference':'none'}
    async def ranked(**kwargs):
        return {'message':'No confirmed match.', 'apps':[],
                'candidates':[{'app':apps[1], 'rank':1}, {'app':apps[0], 'rank':2}],
                'decision':{'outcome':'abstained', 'reason':'insufficient_evidence'}}
    policy.recommend = ranked
    result = ask(policy, 'We need a tool for monitoring temperatures in rooms.', {}, nlu_intent='search')
    assert [entry['app']['id'] for entry in interpreter.call_args.args[2]] == [apps[1]['id'], apps[0]['id']]
    assert result['generation']['interpretation']['catalogue_ids'] == [apps[1]['id'], apps[0]['id']]


def test_failed_new_search_retains_discussed_app_for_factual_followups(conversation):
    policy, apps, interpreter = conversation
    interpreter.side_effect = None
    interpreter.return_value = {'action':'search', 'view':'capability', 'query':'forecast storms',
                                'apps':[], 'reference':'none'}
    result = ask(policy, 'Find a tool to forecast storms.',
        {'turn':2, 'focused_ids':[apps[1]['id']], 'last_results':[{'app':apps[1], 'rank':1}]},
        nlu_intent='search')
    assert not result['apps'] and not result['context']['last_results']
    assert result['context']['focused_ids'] == [apps[1]['id']]
    answer = ask(policy, 'Who provides it?', result['context'], nlu_intent='detail')
    assert answer['message'] == '**Sample Monitor** is provided by **Other Labs**.'
    interpreter.assert_called_once()


@pytest.mark.parametrize('question', [
    'Could you state the supplier of Device Register?',
    'Which organisation is responsible for this application?',
    'Please name its provider.',
    'Can I see who provides that product?',
])
def test_metadata_operation_and_reference_compose_without_model(conversation, question):
    policy, apps, interpreter = conversation
    result = ask(policy, question, {'turn':2, 'focused_ids':[apps[0]['id']],
        'last_query':'forecast storms', 'comparison_need':'forecast storms'}, nlu_intent='out_of_scope')
    assert result['message'] == '**Device Register** is provided by **Example Labs**.'
    assert result['generation']['source'] == 'prepared'
    assert result['context']['comparison_need'] == 'forecast storms'
    interpreter.assert_not_called()


def test_historical_search_reference_is_independent_of_current_focus(conversation):
    policy, apps, interpreter = conversation
    result = ask(policy, 'Who supplies the tool we mentioned before the last search?',
        {'turn':3, 'focused_ids':[apps[0]['id']], 'search_origin_ids':[apps[1]['id']]})
    assert result['message'] == '**Sample Monitor** is provided by **Other Labs**.'
    # A stale historical identity cannot silently fall back to the current App.
    result = ask(policy, 'Who supplies the tool we mentioned before the last search?',
        {'turn':3, 'focused_ids':[apps[0]['id']], 'search_origin_ids':['withdrawn-native']})
    assert not result['apps']
    interpreter.assert_not_called()


@pytest.mark.parametrize('target', ['it with automatic forecasting', 'an unknown product'])
def test_unresolved_metadata_target_is_not_widened_by_semantic_recovery(conversation, target):
    policy, apps, interpreter = conversation
    result = ask(policy, 'Who provides ' + target + '?', {'turn':2, 'focused_ids':[apps[0]['id']]})
    assert not result['apps'] and result['context']['focused_ids'] == [apps[0]['id']]
    interpreter.assert_not_called()


def test_singular_reference_does_not_choose_between_two_focused_apps(conversation):
    policy, apps, interpreter = conversation
    result = ask(policy, 'Who provides this application?', {'turn':2, 'focused_ids':[a['id'] for a in apps]})
    assert not result['apps']
    interpreter.assert_not_called()


@pytest.mark.parametrize('question', ['How do their purposes differ?',
                                    'What are the differences between their roles?'])
def test_comparison_frame_owns_operation_and_displayed_set(conversation, question):
    policy, apps, interpreter = conversation
    result = ask(policy, question, {'turn':2, 'last_results':[{'app':a,'rank':i+1} for i,a in enumerate(apps)],
        'comparison_ids':[a['id'] for a in apps]}, nlu_intent='compare')
    assert result['intent'] == 'compare'
    assert {r['app']['id'] for r in result['apps']} == {a['id'] for a in apps}
    assert 'main difference' in result['message']
    interpreter.assert_not_called()


@pytest.mark.parametrize('question', ['Which of them publishes device records?',
    'How do their roles differ for automatic forecasting?',
    'What are the differences between their prices?'])
def test_purpose_comparison_parser_never_drops_unknown_axis_or_requirement(question):
    assert comparison_question(question) is None


def test_reference_parser_consumes_complete_targets():
    assert catalogue_reference('that application') == 'focus'
    assert catalogue_reference('the tool we discussed earlier') == 'focus'
    assert catalogue_reference('the product we mentioned before that search') == 'before_search'
    assert catalogue_reference('the other application') == 'other'
    assert catalogue_reference('these products') == 'both'
    assert catalogue_reference('this application with offline support') is None
    assert catalogue_reference('another application') is None
