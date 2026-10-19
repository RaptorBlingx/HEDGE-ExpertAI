"""Fluent source synthesis, semantic review and multi-turn interpretation seams."""
import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from hedge_shared.models_v2 import ChatRequestV2

from scripts.store_v1_playground import load_service

expert = load_service('unit_expert_conversation', 'expert-recommend')('store_conversation')
policy_module = load_service('unit_chat_conversation', 'chat-intent')('store_conversation')
APPS = [
    {'id': 'local-a', 'app_id': 'native-a', 'name': 'Meter View',
     'source_evidence': {'description': 'Displays meter readings.',
                         'readme': 'Displays meter readings. SMS is available only in simulation.'}},
    {'id': 'local-b', 'app_id': 'native-b', 'name': 'Model Studio',
     'source_evidence': {'description': 'Edits semantic models.'}},
]
RESULTS = [{'app': app, 'rank': i + 1} for i, app in enumerate(APPS)]
DRAFT = {'decision': 'answer', 'focus':['1'], 'answer': 'Meter View displays readings, with SMS limited to simulation.',
         'evidence': {'1': ['readme']}}
GOOD_REVIEW = {'issues': []}


def engine(monkeypatch, draft=DRAFT, review=GOOD_REVIEW, error=None):
    call = Mock(side_effect=error or [json.dumps(draft), json.dumps(review)])
    monkeypatch.setattr(expert, 'OllamaClient', lambda: SimpleNamespace(model='qwen3.5:2b', chat_structured=call))
    return call


def test_synthesis_is_fluent_paraphrase_with_code_owned_citations(monkeypatch):
    call = engine(monkeypatch)
    history = [{'role': 'user', 'content': 'Compare the Apps'}, {'role': 'assistant', 'content': 'Earlier explanation'}]
    result = expert.respond('Explain the first one simply', RESULTS[:1], 'en', 'answer', history)
    assert 'SMS limited to simulation.' in result['message']
    assert '[1]' in result['message'] and 'Meter View — README' in result['message']
    assert 'not verified' not in result['message'] and 'source records' not in result['message']
    assert result['generation']['reason'] == 'reviewed_source_synthesis'
    assert call.call_count == 2
    prompt = json.loads(call.call_args_list[0].args[0][1]['content'])
    assert call.call_args_list[0].args[0][2:-1] == history
    assert call.call_args_list[0].args[0][-1]['content'] == 'Explain the first one simply'
    assert prompt['current_sources'][0]['fields']['readme'] == APPS[0]['source_evidence']['readme']
    assert call.call_args_list[0].kwargs['context_tokens'] == 16384


@pytest.mark.parametrize('reason', ['unsupported_claim', 'lost_qualification', 'wrong_app', 'unsafe'])
def test_reviewer_rejects_fluent_unsupported_claims_instead_of_serving_them(monkeypatch, reason):
    draft = {'decision': 'answer', 'focus':['1'], 'answer': 'Certified to save 40% with free production SMS.', 'evidence': {'1': ['readme']}}
    engine(monkeypatch, draft, {'issues': [reason]})
    result = expert.respond('Does it support production SMS?', RESULTS[:1], 'en', 'answer', [])
    assert '40%' not in result['message'] and 'free production' not in result['message']
    assert result['generation']['source'] == 'deterministic'
    assert result['generation']['reason'] == 'grounding_review_rejected'


@pytest.mark.parametrize('ref', [{'app': '0', 'field': 'readme'}, {'app': '1', 'field': 'currency'}])
def test_invented_provenance_is_rejected_before_review(monkeypatch, ref):
    draft = deepcopy(DRAFT)
    draft['evidence'] = {ref['app']: [ref['field']]}
    call = engine(monkeypatch, draft)
    result = expert.respond('Explain it', RESULTS[:1], 'en', 'answer', [])
    assert result['generation']['source'] == 'deterministic'
    call.assert_called_once()


def test_honest_no_match_survives_synthesis_and_review(monkeypatch):
    draft = {'decision': 'no_match', 'focus':[], 'answer': 'These Apps cover readings and models; I do not have evidence of earthquake warnings.',
        'evidence': {'1': ['description'], '2': ['description']}}
    engine(monkeypatch, draft)
    result = expert.respond('I need earthquake warnings', RESULTS, 'en', 'search', [])
    assert result['decision'] == 'no_match'
    assert 'earthquake' in result['message']


def test_model_failure_returns_a_brief_honest_fallback_without_private_errors(monkeypatch):
    engine(monkeypatch, error=TimeoutError('private response content'))
    result = expert.respond('Explain it', RESULTS[:1], 'en', 'answer', [])
    assert 'private response content' not in json.dumps(result)
    assert 'try' in result['message']
    assert result['generation']['source'] == 'deterministic'


def test_source_budget_keeps_whole_qualifications_and_reports_omitted_fields():
    results = deepcopy(RESULTS)
    long = 'x' * 1250 + ' Production is unavailable.'
    results[0]['app']['source_evidence']['readme'] = long
    sources = expert.source_context(results)
    assert sources[0]['fields']['readme'] == long
    results[0]['app']['source_evidence']['readme'] = 'x' * 16000
    results[0]['app']['readme_status'] = 'too_large'
    sources = expert.source_context(results)
    assert 'readme' not in sources[0]['fields']
    assert 'readme' in sources[0]['omitted_fields']
    assert sources[0]['readme_status'] == 'too_large'


def test_interpretation_receives_context_and_never_invents_identity(monkeypatch):
    call = Mock(return_value=json.dumps({'action': 'compare', 'apps': ['1', '2'], 'query': 'Compare purposes'}))
    monkeypatch.setattr(expert, 'OllamaClient', lambda: SimpleNamespace(chat_structured=call))
    directory = [{'key': str(i + 1), 'name': a['name']} for i, a in enumerate(APPS)]
    result = expert.plan('What is the difference between them?', 'en', directory,
                         {'previous': ['1', '2'], 'focus': ['1']}, [])
    assert result['apps'] == ['1', '2']
    call.return_value = json.dumps({'action': 'answer', 'apps': ['invented'], 'query': ''})
    with pytest.raises(ValueError):
        expert.plan('Explain it', 'en', directory, {}, [])


@pytest.fixture
def conversation():
    apps = deepcopy(APPS)
    def resolve(ids):
        return [deepcopy(a) for a in apps if ids is None or a['id'] in ids]
    interpret = Mock(return_value={'action': 'compare', 'apps': ['1', '2'], 'query': 'Compare purposes'})
    explain = Mock(return_value={'message': 'Different purposes. [1] [2]', 'decision': 'answer', 'focus': ['1', '2'],
                                 'generation': {'source': 'ollama', 'reason': 'reviewed_source_synthesis'}})
    search = AsyncMock(return_value={'apps': deepcopy(RESULTS), 'message': 'unused legacy narrative'})
    policy = policy_module.StoreConversation(search, resolve, lambda *a: 'source fields', interpret, explain)
    context = {'last_results': deepcopy(RESULTS), 'focused_ids': ['local-a'], 'turn': 2}
    return policy, apps, interpret, explain, search, context


def ask(conversation, message='How do they differ?', history=None, nlu=None):
    policy, *_, context = conversation
    return asyncio.run(policy.respond_with_history(ChatRequestV2(message=message), 'conversation', context, history or [], nlu=nlu))


def test_comparison_uses_previous_list_even_after_single_focus_and_passes_history(conversation):
    history = [{'role': 'user', 'content': 'Explain the first App'}]
    result = ask(conversation, history=history, nlu={"intent":"compare"})
    assert len(result['apps']) == 2
    assert result['intent'] == 'compare'
    conversation[2].assert_not_called()
    assert conversation[3].call_args.args[-1] == history
    assert result['context']['last_results'] == conversation[-1]['last_results']


def test_model_abstention_clears_cards_instead_of_forcing_recommendations(conversation):
    conversation[2].return_value = {'action': 'search', 'apps': [], 'query': 'earthquake warning'}
    conversation[3].side_effect=[{'decision':'search','message':'','focus':[],'generation':{}},
                                  {'decision':'no_match','message':'No documented warning App.','focus':[],'generation':{}}]
    result = ask(conversation, 'I need earthquake warnings')
    assert result['apps'] == [] and result['context']['focused_ids'] == []
    conversation[4].assert_awaited_once()


@pytest.mark.parametrize('status', [503, 504])
def test_retrieval_failure_never_becomes_no_match_or_generation_fallback(conversation, status):
    conversation[2].return_value = {'action': 'search', 'apps': [], 'query': 'new task'}
    conversation[4].side_effect = HTTPException(status, 'Catalogue unavailable')
    with pytest.raises(HTTPException) as error:
        ask(conversation, 'Find Apps for a new task')
    assert error.value.status_code == status
    conversation[3].assert_not_called()


def test_withdrawal_or_metadata_change_during_generation_cannot_leak_old_facts(conversation):
    def changed(*a, **kw):
        conversation[1].pop()
        return {'message': 'Old facts', 'decision': 'answer', 'generation': {'source': 'ollama'}}
    conversation[3].side_effect = changed
    result = ask(conversation)
    assert not result['apps'] and 'Old facts' not in result['message']
    assert result['generation']['reason'] == 'catalogue_changed'


def test_bad_interpretation_preserves_context_without_selecting_random_candidates(conversation):
    conversation[-1].clear()
    conversation[2].return_value = {'action': 'answer', 'apps': ['unknown'], 'query': ''}
    result = ask(conversation)
    assert not result['apps'] and result['context'] == conversation[-1]
    conversation[3].assert_not_called()


def test_browsing_cannot_be_classified_as_no_match_even_if_model_ignores_schema(monkeypatch):
    draft = deepcopy(DRAFT)
    draft['decision'] = 'no_match'
    call = engine(monkeypatch, draft)
    result = expert.respond('What Apps are available?', RESULTS, 'en', 'browse', [])
    assert result['decision'] == 'clarify'
    assert result['generation']['reason'] == 'invalid_conversation_decision'
    call.assert_called_once()


def test_natural_punctuation_survives_safe_widget_rendering(monkeypatch):
    draft = deepcopy(DRAFT)
    draft['answer'] = "It's a way to view readings & compare values."
    engine(monkeypatch, draft)
    result = expert.respond('Explain it', RESULTS[:1], 'en', 'answer', [])
    assert "It's a way" in result['message']
    assert '&#x27;' not in result['message'] and '&amp;' not in result['message']


def test_generic_or_one_sided_comparison_cannot_pass_as_a_complete_explanation(monkeypatch):
    call = engine(monkeypatch)
    result = expert.respond('What is the difference between them?', RESULTS, 'en', 'compare', [])
    assert result['generation']['reason'] == 'incomplete_app_explanation'
    call.assert_called_once()


def test_fluent_positive_comparison_can_cover_both_apps_without_quotations(monkeypatch):
    draft = {'decision': 'answer', 'focus':['1','2'], 'answer': 'Meter View helps you inspect readings; Model Studio is for editing the models that describe data.',
        'evidence': {'1': ['description'], '2': ['description']}}
    engine(monkeypatch, draft)
    result = expert.respond('Compare them simply', RESULTS, 'en', 'compare', [])
    assert result['generation']['source'] == 'ollama'
    assert 'inspect readings' in result['message'] and '[1]' in result['message'] and '[2]' in result['message']
    assert '“' not in result['message']


def test_oversized_generated_answer_is_rejected_whole_not_truncated(monkeypatch):
    draft = deepcopy(DRAFT)
    draft['answer'] = 'x' * 2401
    call = engine(monkeypatch, draft)
    result = expert.respond('Explain it', RESULTS[:1], 'en', 'answer', [])
    assert draft['answer'] not in result['message']
    assert result['generation']['source'] == 'deterministic'
    call.assert_called_once()


def test_raw_zero_values_cannot_override_an_unverified_commercial_assessment(monkeypatch):
    review = {'issues': ['The stated currency, free use and billing period are not documented.']}
    draft = {**DRAFT, 'answer': 'It is free with a EUR 0 monthly licence.'}
    engine(monkeypatch, draft, review)
    result = expert.respond('What does it cost?', RESULTS[:1], 'en', 'answer', [])
    assert result['generation']['reason'] == 'grounding_review_rejected'
    assert 'EUR' not in result['message']


def test_review_cannot_invent_a_source_quote_or_replace_the_reference_contract(monkeypatch):
    review = {**GOOD_REVIEW, 'commercial_terms': 'explicitly_documented', 'commercial_quote': 'Free forever in EUR'}
    engine(monkeypatch, review=review)
    result = expert.respond('Explain it', RESULTS[:1], 'en', 'answer', [])
    assert result['generation']['reason'] == 'invalid_or_unreviewed_output'
    assert 'Free forever' not in result['message']


def test_opaque_native_id_case_is_enforced_before_model_interpretation(conversation):
    result = ask(conversation, 'Explain NATIVE-A')
    assert result['apps'] == [] and result['intent'] == 'clarify'
    conversation[2].assert_not_called()


def test_context_budget_never_truncates_a_source_field_to_make_it_fit(monkeypatch):
    call = Mock()
    messages = [{'role': 'user', 'content': json.dumps({'history': [], 'source': 'x' * 17000})}]
    with pytest.raises(ValueError):
        expert._infer(SimpleNamespace(chat_structured=call), messages, {}, timeout=1, max_tokens=10)
    call.assert_not_called()


def test_negative_capability_answer_keeps_conversational_subject_without_recommending_it(conversation):
    conversation[2].return_value = {'action': 'answer', 'apps': ['1'], 'query': 'Does it warn about earthquakes?'}
    conversation[3].return_value.update(decision='no_match', message='I do not see earthquake warnings in its documentation.')
    negative = ask(conversation, 'Does it warn about earthquakes?')
    assert negative['apps'] == []
    assert negative['context']['focused_ids'] == ['local-a']
    conversation[-1].update(negative['context'])
    conversation[3].return_value.update(decision='answer', message='It displays readings.')
    positive = ask(conversation, 'What does it do instead?')
    assert positive['apps'][0]['app']['id'] == 'local-a'


def test_postgres_observation_timestamp_is_serialized_without_becoming_app_freshness(monkeypatch):
    from datetime import UTC, datetime
    call = engine(monkeypatch)
    observed = datetime(2026, 10, 15, 14, 4, tzinfo=UTC)
    result = expert.respond('Explain the App', RESULTS[:1], 'en', 'answer', [], observation={
        'state':'authorization_required','snapshot_at':observed,
        'source_kind':'authorized_api','timestamp_basis':'local_response_time','snapshot_complete':False})
    assert result['generation']['source']=='ollama'
    data = json.loads(call.call_args_list[0].args[0][1]['content'])
    assert data['observation']['snapshot_at']==observed.isoformat()
    assert data['observation']['timestamp_basis']=='local_response_time'
    assert data['observation']['snapshot_complete'] is False
    # Operational authorization and routing are not evidence of App capabilities.
    assert 'state' not in data['observation'] and 'intent' not in data


def test_direct_and_embedded_description_provenance_stays_distinguishable(monkeypatch):
    results = deepcopy(RESULTS[:1])
    field = 'dataspaceAppDescription.properties.description'
    results[0]['app']['source_evidence'][field] = 'An embedded source description.'
    draft = {**DRAFT, 'evidence': {'1': ['description', field]}}
    engine(monkeypatch, draft)
    result = expert.respond('Explain it', results, 'en', 'answer', [])
    assert 'description, embedded description' in result['message']
    assert {c['field'] for c in result['generation']['citations']} == {'description', field}


def test_rejected_claim_is_revised_once_then_reviewed_again_before_delivery(monkeypatch):
    bad = {**DRAFT, 'answer': 'It supports production SMS.'}
    rejected = {'issues':['README limits SMS to simulation.']}
    call = Mock(side_effect=[json.dumps(bad),json.dumps(rejected),json.dumps(DRAFT),json.dumps(GOOD_REVIEW)])
    monkeypatch.setattr(expert,'OllamaClient',lambda:SimpleNamespace(model='qwen3.5:2b',chat_structured=call))
    progress = Mock()
    r = expert.respond('Does it support SMS?',RESULTS[:1],'en','answer',[],progress=progress)
    assert r['generation']['source']=='ollama' and r['generation']['repair_count']==1
    assert r['generation']['rejected_drafts']==1 and call.call_count==4
    assert 'production SMS' not in r['message'] and 'limited to simulation' in r['message']
    assert any(c.args==('revision',) for c in progress.call_args_list)
    repaired = json.loads(call.call_args_list[2].args[0][1]['content'])
    assert repaired['current_sources'][0]['fields']['readme']==APPS[0]['source_evidence']['readme']
    assert repaired['revision_feedback']['issues']==['README limits SMS to simulation.']


def test_two_rejected_drafts_never_loop_or_force_an_unsupported_answer(monkeypatch):
    rejected = {'issues':['Unsupported App capability.']}
    call=Mock(side_effect=[json.dumps(DRAFT),json.dumps(rejected)]*2)
    monkeypatch.setattr(expert,'OllamaClient',lambda:SimpleNamespace(model='qwen3.5:2b',chat_structured=call))
    r=expert.respond('Explain it',RESULTS[:1],'en','answer',[])
    assert r['generation']['source']=='deterministic'
    assert r['generation']['rejected_drafts']==2 and call.call_count==4


def test_app_explanation_cannot_drop_all_citations_after_successful_paraphrase(monkeypatch):
    call = engine(monkeypatch, {**DRAFT, 'evidence': {}})
    result = expert.respond('Explain it simply', RESULTS[:1], 'en', 'answer', [])
    assert result['generation']['source'] == 'deterministic'
    assert result['generation']['reason'] == 'missing_source_evidence'
    call.assert_called_once()
    schema = call.call_args.args[1]
    assert schema['$defs']['InspectedEvidence']['required'] == ['1']
    assert schema['$defs']['InspectedEvidence']['properties']['1']['minItems'] == 1


@pytest.mark.parametrize('focused,previous,expected', [(['1'],['1','2'],['2']), (['2'],['1','2'],['1']), ([],['1','2'],[]), (['1'],['1','2','3'],[])])
def test_relative_bindings_use_current_identity_and_leave_ambiguous_alternatives_unbound(conversation,focused,previous,expected):
    policy,apps,_,explain,_,context=conversation
    if '3' in previous:
        apps.append({'id':'local-c','app_id':'native-c','name':'Third Example','source_evidence':{'description':'Another function.'}})
    identities={str(i+1):a['id'] for i,a in enumerate(apps)}
    context['last_results']=[{'app':deepcopy(apps[int(k)-1]),'rank':i+1} for i,k in enumerate(previous)]
    context['focused_ids']=[identities[k] for k in focused]
    explain.return_value.update(decision='clarify',focus=[])
    result=ask(conversation,'Explain the alternative')
    assert explain.call_args.kwargs['references']['other']==expected
    assert result['apps']==[]
    if expected:
        explain.return_value.update(decision='answer',focus=expected)
        selected=ask(conversation,'Explain the alternative')
        assert [r['app']['id'] for r in selected['apps']]==[identities[k] for k in expected]


def test_planner_preserves_real_conversation_roles_and_newest_question(monkeypatch):
    call=Mock(return_value=json.dumps({'action':'answer','apps':['2'],'query':'Explain the second App'}))
    monkeypatch.setattr(expert,'OllamaClient',lambda:SimpleNamespace(chat_structured=call))
    history=[{'role':'user','content':'Explain Example 1'},{'role':'assistant','content':'Earlier explanation'}]
    result=expert.plan('Explain the second App','en',[{'key':'1'},{'key':'2'}],{},history)
    messages=call.call_args.args[0]
    assert messages[2:-1]==history
    assert messages[-1]=={'role':'user','content':'Explain the second App'}
    assert result['apps']==['2']


def test_context_budget_preserves_current_json_question_and_whole_source_message():
    client=SimpleNamespace(chat_structured=Mock(return_value='{}'))
    question=json.dumps({'history':['This is part of the question, not session history.']})
    source='Source restriction: simulation only.'
    messages=[{'role':'system','content':'Planner'},{'role':'user','content':source},
              {'role':'assistant','content':'x'*17000},{'role':'user','content':question}]
    expert._infer(client,messages,{},timeout=1,max_tokens=10,embedded_history=False)
    sent=client.chat_structured.call_args.args[0]
    assert sent[-1]['content']==question and sent[1]['content']==source
    assert len(sent)==3


@pytest.mark.parametrize('message,query',[('Find Apps for semantic models','semantic models'),('Please search for earthquake warnings via SMS','earthquake warnings via SMS'),('Can you recommend an App with MQTT but not paid billing?','an App with MQTT but not paid billing?')])
def test_explicit_discovery_cannot_be_downgraded_to_unfiltered_browsing(conversation,message,query):
    conversation[2].return_value={'action':'browse','apps':[],'query':'Apps'}
    result=ask(conversation,message)
    assert result['intent']=='search'
    conversation[2].assert_not_called()
    conversation[4].assert_awaited_once()
    assert conversation[4].call_args.kwargs['query']==query


def test_expert_can_select_a_grounded_focus_when_thin_planning_cannot_resolve_the_question(conversation):
    conversation[2].return_value={'action':'clarify','apps':[],'query':'Which helps semantic models?'}
    conversation[3].return_value.update(focus=['2'],message='Model Studio edits semantic models.')
    result=ask(conversation,'Which one would help with semantic models?')
    assert [r['app']['id'] for r in result['apps']]==['local-b']
    assert result['context']['focused_ids']==['local-b']
    assert len(result['context']['last_results'])==2
    assert conversation[3].call_args.kwargs['references']['other']==['2']


def test_context_fallback_cannot_replace_a_withdrawn_reference(conversation):
    conversation[1].pop()
    conversation[2].return_value={'action':'clarify','apps':[],'query':'Explain other App'}
    result=ask(conversation,'What about the other one?')
    assert result['apps']==[] and result['intent']=='clarify'
    conversation[3].assert_not_called()
    conversation[2].assert_not_called()


@pytest.mark.parametrize('focus,reason',[(['foreign'],'unknown_app_focus'),([], 'missing_app_focus'),(['1','1'],'unknown_app_focus')])
def test_unvalidated_app_focus_cannot_become_a_served_answer(monkeypatch,focus,reason):
    call=engine(monkeypatch,{**DRAFT,'focus':focus})
    result=expert.respond('Explain it',RESULTS[:1],'en','answer',[])
    assert result['generation']['reason']==reason
    assert result['focus']==[] and result['decision']=='clarify'
    call.assert_called_once()


def test_small_talk_in_context_does_not_force_app_focus_or_source_footer(monkeypatch):
    engine(monkeypatch,{**DRAFT,'decision':'chat','focus':[],'answer':"You're welcome!",'evidence':{}},review=GOOD_REVIEW)
    result=expert.respond('Thanks!',RESULTS[:1],'en','answer',[])
    assert result['decision']=='chat' and result['focus']==[]
    assert result['message']=="You're welcome!" and result['generation']['citations']==[]


def test_native_id_is_bound_before_generation_even_when_the_previous_focus_differs(conversation):
    conversation[3].return_value.update(focus=['1'],message='Model Studio edits models.')
    result=ask(conversation,'Explain native-b')
    assert [r['app']['id'] for r in result['apps']]==['local-b']
    references=conversation[3].call_args.kwargs['references']
    assert references['named']==['1'] and references['focus']==['2']
    conversation[2].assert_not_called()


def test_search_directive_is_internal_and_does_not_serve_prose_or_impressions(monkeypatch):
    call=engine(monkeypatch,{**DRAFT,'decision':'search','focus':[],'answer':'Do not serve this routing text.'})
    result=expert.respond('I need a different kind of App',RESULTS[:1],'en','answer',[])
    assert result['decision']=='search' and result['message']=='' and result['focus']==[]
    call.assert_called_once()


def test_repeated_search_directive_cannot_loop_or_force_a_recommendation(conversation):
    conversation[3].return_value.update(decision='search',message='Unserved directive',focus=[])
    result=ask(conversation,'Find an App for a new task')
    assert result['apps']==[] and 'Unserved' not in result['message']
    assert result['generation']['reason']=='repeated_search_directive'
    conversation[4].assert_awaited_once()


@pytest.mark.parametrize('status',[503,504])
def test_source_aware_new_discovery_retains_retrieval_failure_semantics(conversation,status):
    conversation[3].return_value.update(decision='search',message='',focus=[])
    conversation[4].side_effect=HTTPException(status,'Catalogue unavailable')
    with pytest.raises(HTTPException) as error:
        ask(conversation,'I need Apps for another task')
    assert error.value.status_code==status
    assert conversation[3].call_count==1


def test_positive_schema_requires_app_focus_without_preventing_structured_abstention(monkeypatch):
    call=engine(monkeypatch)
    expert.respond('Explain it',RESULTS[:1],'en','answer',[])
    schema=call.call_args_list[0].args[1]
    positive,neutral=schema['anyOf']
    assert positive['properties']['decision']['enum']==['answer']
    assert positive['properties']['focus']['minItems']==1
    assert neutral['properties']['focus']['maxItems']==1
    assert {'no_match','clarify','chat'}<=set(neutral['properties']['decision']['enum'])
    assert positive['properties']['evidence']['$ref']!=neutral['properties']['evidence']['$ref']
    assert schema['$defs']['OptionalEvidence']['required']==[]


def test_empty_local_catalogue_is_not_a_claim_that_the_store_has_no_apps(monkeypatch):
    client=Mock()
    monkeypatch.setattr(expert,'OllamaClient',client)
    result=expert.respond('List the Apps',[],'en','browse',[])
    assert result['message']=='There are no Apps in this local catalogue yet.'
    assert result['focus']==[] and result['generation']['reason']=='empty_local_catalogue'
    client.assert_not_called()


def test_chat_label_cannot_remove_provenance_for_an_explicit_current_app(monkeypatch):
    engine(monkeypatch,{**DRAFT,'decision':'chat','focus':[]},review=GOOD_REVIEW)
    result=expert.respond('Explain that simply',RESULTS[:1],'en','answer',[],references={'focus':['1']})
    assert result['decision']=='chat' and result['focus']==['1']
    assert 'Sources:' in result['message'] and result['generation']['citations'][0]['rank']==1


def test_implicit_app_claims_retain_attribution_and_conversational_decision(monkeypatch):
    engine(monkeypatch,{**DRAFT,'decision':'chat','focus':[],'answer':'It displays meter readings.'})
    result=expert.respond('Explain that simply',RESULTS[:1],'en','answer',[],references={'focus':['1']})
    assert 'Sources:' in result['message'] and result['decision']=='chat'
    assert result['focus']==['1']


@pytest.mark.parametrize('approved,reason', [(False, 'supported'), (True, 'unsupported_claim')])
def test_independent_approval_fields_cannot_override_the_issue_contract(monkeypatch, approved, reason):
    engine(monkeypatch, review={**GOOD_REVIEW, 'supported': approved, 'reason': reason})
    result = expert.respond('Explain it', RESULTS[:1], 'en', 'answer', [], allow_repair=False)
    assert result['generation']['source'] == 'deterministic'
    assert result['generation']['reason'] == 'invalid_or_unreviewed_output'
    assert result['decision'] == 'clarify' and result['focus'] == []


def test_chat_label_cannot_admit_an_uncited_named_app_claim(monkeypatch):
    call = engine(monkeypatch, {**DRAFT, 'decision': 'chat', 'focus': [], 'evidence': {}})
    result = expert.respond('Explain that simply', RESULTS[:1], 'en', 'answer', [])
    assert result['generation']['reason'] == 'missing_source_evidence'
    assert result['focus'] == []
    call.assert_called_once()


@pytest.mark.parametrize('decision,expected', [('chat', ['local-b']), ('no_match', []), ('clarify', [])])
def test_validated_app_context_survives_chat_tone_but_not_abstention(conversation, decision, expected):
    conversation[3].return_value.update(decision=decision, focus=['2'], message='Model Studio explains models.')
    result = ask(conversation, 'Which one would help with models?')
    assert [r['app']['id'] for r in result['apps']] == expected
    if expected:
        assert result['intent'] == 'conversation'
        assert result['context']['focused_ids'] == expected


def test_missing_focus_never_promotes_the_whole_retrieved_context(conversation):
    conversation[3].return_value.pop('focus')
    result = ask(conversation, 'Which one would help with models?')
    assert result['apps'] == []


@pytest.mark.parametrize('bad_text', ['Read https://not-served.invalid', '<b>Meter View</b>', '[Docs](https://not-served.invalid)'])
def test_bad_presentation_gets_one_revision_without_serving_unvalidated_text(monkeypatch, bad_text):
    unsafe = {**DRAFT, 'answer': bad_text}
    call = Mock(side_effect=[json.dumps(unsafe), json.dumps(DRAFT), json.dumps(GOOD_REVIEW)])
    monkeypatch.setattr(expert, 'OllamaClient', lambda: SimpleNamespace(model='test-model', chat_structured=call))
    result = expert.respond('Explain it', RESULTS[:1], 'en', 'answer', [])
    assert result['generation']['source'] == 'ollama' and result['generation']['repair_count'] == 1
    assert bad_text not in result['message'] and 'SMS limited to simulation.' in result['message']
    assert call.call_count == 3
    repaired = json.loads(call.call_args_list[1].args[0][1]['content'])
    assert repaired['current_sources'][0]['fields']['readme'] == APPS[0]['source_evidence']['readme']


def test_repeated_bad_presentation_stays_a_retry_not_an_unsafe_answer(monkeypatch):
    unsafe = {**DRAFT, 'answer': '<script>not served</script>'}
    call = Mock(return_value=json.dumps(unsafe))
    monkeypatch.setattr(expert, 'OllamaClient', lambda: SimpleNamespace(model='test-model', chat_structured=call))
    result = expert.respond('Explain it', RESULTS[:1], 'en', 'answer', [])
    assert result['generation']['reason'] == 'unsafe_output_markup'
    assert result['generation']['source'] == 'deterministic' and result['focus'] == []
    assert 'script' not in result['message'] and call.call_count == 2


def test_comparison_context_does_not_replace_the_conversational_anchor(monkeypatch):
    draft = {'decision': 'answer', 'focus': ['2'],
             'answer': 'Meter View displays readings, while Model Studio edits semantic models.',
             'evidence': {'1': ['description'], '2': ['description']}}
    engine(monkeypatch, draft)
    result = expert.respond('How do they differ?', RESULTS, 'en', 'answer', [])
    assert result['focus'] == ['2'] and result['display'] == ['1', '2']


def test_conversational_named_subject_survives_a_source_backed_contrast(monkeypatch):
    draft = {'decision': 'chat', 'focus': [],
             'answer': 'Meter View displays readings; Model Studio edits models.',
             'evidence': {'1': ['description'], '2': ['description']}}
    engine(monkeypatch, draft)
    result = expert.respond('Explain Meter View', RESULTS, 'en', 'answer', [], references={'named':['1'],'focus':['2']})
    assert result['focus'] == ['1'] and result['display'] == ['1','2']


def test_context_cards_do_not_infer_identity_from_a_duplicate_name(monkeypatch):
    results = deepcopy(RESULTS)
    for row in results:
        row['app']['name'] = 'Shared Name'
    draft = {'decision': 'answer', 'focus': ['1'], 'answer': 'Shared Name displays readings.',
             'evidence': {'1':['description'], '2':['description']}}
    engine(monkeypatch, draft)
    result = expert.respond('Explain the first App', results, 'en', 'answer', [])
    assert result['display'] == ['1']


def test_discussed_context_records_do_not_overwrite_selected_subject(conversation):
    conversation[3].return_value.update(focus=['2'], display=['1','2'])
    result = ask(conversation, 'How do they differ?')
    assert len(result['apps']) == 2
    assert result['context']['focused_ids'] == ['local-b']
    assert result['generation']['focus_ids'] == ['local-b']


def test_negative_answer_can_inspect_apps_without_promoting_them(monkeypatch):
    negative = {'decision': 'no_match', 'focus': ['1', '2'],
                'answer': 'Neither App documents earthquake warnings.',
                'evidence': {'1': ['readme'], '2': ['description']}}
    call = engine(monkeypatch, negative)
    result = expert.respond('Would either warn me about earthquakes?', RESULTS, 'en', 'answer', [])
    assert result['decision'] == 'no_match' and result['focus'] == [] and result['display'] == []
    assert result['message'].startswith(negative['answer']) and 'Sources:' in result['message']
    assert result['generation']['source'] == 'ollama' and call.call_count == 2


def test_abstention_never_approves_factual_mismatches(monkeypatch):
    engine(monkeypatch, {**DRAFT, 'decision': 'no_match', 'answer': 'It provides production SMS.'},
           {'issues': ['SMS is limited to simulation.']})
    result = expert.respond('Can it deliver production SMS?', RESULTS[:1], 'en', 'answer', [], allow_repair=False)
    assert result['generation']['source'] == 'deterministic'
    assert 'provides production SMS' not in result['message'] and result['display'] == []


@pytest.mark.parametrize('placeholder', ['.', '   '])
def test_placeholder_abstention_is_revised_before_source_review(monkeypatch, placeholder):
    draft = {'decision': 'no_match', 'focus': [], 'answer': placeholder, 'evidence': {'1': ['readme']}}
    corrected = {**draft, 'answer': 'No earthquake-warning capability is documented.'}
    call = Mock(side_effect=[json.dumps(draft), json.dumps(corrected), json.dumps(GOOD_REVIEW)])
    monkeypatch.setattr(expert, 'OllamaClient', lambda: SimpleNamespace(model='test', chat_structured=call))
    result = expert.respond('Can it warn about earthquakes?', RESULTS[:1], 'en', 'answer', [])
    assert result['decision'] == 'no_match' and result['display'] == []
    assert result['message'].startswith(corrected['answer'])
    assert result['generation']['repair_count'] == 1 and call.call_count == 3


def test_search_can_explain_one_supported_app_without_promoting_other_candidates(monkeypatch):
    draft = {'decision': 'answer', 'focus': ['2'], 'answer': 'Model Studio edits semantic models.',
             'evidence': {'2': ['description']}}
    engine(monkeypatch, draft)
    result = expert.respond('Find Apps for semantic models', RESULTS, 'en', 'search', [])
    assert result['generation']['source'] == 'ollama'
    assert result['focus'] == ['2'] and result['display'] == ['2']
    assert result['generation']['citations'] == [{'number': 2, 'rank': 2, 'field': 'description'}]
    assert 'Meter View' not in result['message']


@pytest.mark.parametrize('draft', [
    {**DRAFT, 'focus': ['2']},
    {**DRAFT, 'answer': 'Meter View displays readings. Model Studio edits models.'},
])
def test_search_subset_still_requires_citations_for_focused_and_named_apps(monkeypatch, draft):
    call = engine(monkeypatch, draft)
    result = expert.respond('Find Apps for readings', RESULTS, 'en', 'search', [], allow_repair=False)
    assert result['generation']['source'] == 'deterministic'
    assert result['generation']['reason'] in {'incomplete_app_explanation', 'missing_source_evidence'}
    call.assert_called_once()


def test_unshown_search_candidate_cannot_bind_a_later_other_app(conversation):
    policy, _, _, explain, _, _ = conversation
    explain.return_value.update(focus=['2'], display=['2'])
    result = ask(conversation, 'Find Apps for semantic models')
    assert [r['app']['id'] for r in result['context']['last_results']] == ['local-b']
    assert result['context']['focused_ids'] == ['local-b']
    explain.return_value.update(decision='clarify', focus=[], display=[], message='Which other App do you mean?')
    follow = asyncio.run(policy.respond_with_history(
        ChatRequestV2(message='What about the other one?'), 'conversation', result['context'], []))
    assert explain.call_args.kwargs['references']['other'] == []
    assert follow['apps'] == []


def test_missing_search_citations_are_revised_and_reviewed_once(monkeypatch):
    good = {'decision': 'answer', 'focus': ['2'], 'answer': 'Model Studio edits semantic models.',
            'evidence': {'2': ['description']}}
    call = Mock(side_effect=[json.dumps({**good, 'evidence': {}}), json.dumps(good), json.dumps(GOOD_REVIEW)])
    monkeypatch.setattr(expert, 'OllamaClient', lambda: SimpleNamespace(model='test', chat_structured=call))
    result = expert.respond('Find Apps for semantic models', RESULTS, 'en', 'search', [])
    assert result['generation']['source'] == 'ollama' and result['generation']['repair_count'] == 1
    assert result['display'] == ['2'] and call.call_count == 3
    schema = call.call_args_list[0].args[1]
    assert schema['$defs']['InspectedEvidence']['minProperties'] == 1
    assert 'minProperties' not in schema['$defs']['OptionalEvidence']


def test_explicit_source_plan_keeps_a_pronoun_answer_on_the_selected_app(monkeypatch):
    draft = {'decision': 'chat', 'focus': ['2'], 'answer': 'It edits semantic models.',
             'evidence': {'2': ['description']}}
    engine(monkeypatch, draft)
    result = expert.respond('What about the other one?', RESULTS, 'en', 'answer', [],
                            references={'focus': ['1'], 'other': ['2']})
    assert result['generation']['source'] == 'ollama'
    assert result['focus'] == ['2'] and result['display'] == ['2']
    assert 'Model Studio' in result['message'] and 'Meter View' not in result['message']
