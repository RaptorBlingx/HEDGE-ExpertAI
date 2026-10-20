"""Contract guards for one-pass understanding; model quality is tested in the widget."""
import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from hedge_shared.models_v2 import ChatRequestV2
from hedge_shared.store_knowledge import prepare
from hedge_shared.store_v1 import StoreAppMetadata

from scripts.store_v1_playground import load_service

expert = load_service("single_understanding_expert", "expert-recommend")("store_conversation")
policy_module = load_service("single_understanding_chat", "chat-intent")("store_conversation")


@pytest.fixture
def app():
    knowledge = prepare(StoreAppMetadata(store_id="contract-only", app_id="opaque-new",
        name="Sample Register", readme="Used to collect device measurements.", active=True, visible=True))
    return {**knowledge["projection"], "prepared_explanation": knowledge["explanation"]}


def test_interpreter_selects_current_assessed_preparation_in_one_bounded_call(monkeypatch, app):
    call = Mock(return_value=json.dumps({"query": "collect device measurements", "mode": "search", "task": "1.1"}))
    monkeypatch.setattr(expert, "OllamaClient", lambda: SimpleNamespace(chat_structured=call))
    result = expert.understand("Gather our devices' readings", [{"key": "1", "app": app}],
                              {'nlu':{'intent':'compare','confidence':1.0}}, [])
    call.assert_called_once()
    assert result["apps"] == ["1"] and "collect" in result["query"]
    assert call.call_args.kwargs["max_tokens"] == 80
    assert call.call_args.kwargs["deadline"] > 0
    payload = json.loads(call.call_args.args[0][1]["content"])
    assert payload["catalogue"][0]["tasks"][0]["text"] == "Used to collect device measurements."
    assert payload.get('nlu_intent') is None
    assert 'reference' not in call.call_args.args[1]['properties']
    call.return_value = json.dumps({"query": "collect device measurements", "mode": "search", "task": "invented"})
    with pytest.raises(ValueError, match="Unknown"):
        expert.understand("Anything", [{"key": "1", "app": app}], {}, [])


def test_unknown_function_survives_even_when_model_selects_a_partial_task(monkeypatch, app):
    query = "collect measurements and forecast storms"
    call = Mock(return_value=json.dumps({"query": query, "task": "1.1", "mode": "search"}))
    monkeypatch.setattr(expert, "OllamaClient", lambda: SimpleNamespace(chat_structured=call))
    result = expert.understand(query, [{"key": "1", "app": app}], {}, [])
    assert result["query"] == query
    assert not expert._recommendation_decision(result["query"], [{"app": app, "rank": 1}], "en")["apps"]


def test_conversational_subject_is_independent_of_task_match(monkeypatch, app):
    call = Mock(return_value=json.dumps({'query':'collect device measurements', 'task':'1.1',
                                        'mode':'capability', 'reference':'other'}))
    monkeypatch.setattr(expert, 'OllamaClient', lambda: SimpleNamespace(chat_structured=call))
    other = {**app, 'id':'other-local', 'app_id':'other-native'}
    directory = [{'key':'1', 'app':app}, {'key':'2', 'app':other}]
    result = expert.understand('Could the other application gather readings?', directory,
        {'focus':['1'], 'previous':['1','2']}, [])
    assert result['apps'] == ['2'] and result['reference'] == 'other'
    # An unresolved reference cannot bind to the App with the nearest task.
    result = expert.understand('Could the other application gather readings?', directory,
        {'focus':[], 'previous':['1','2']}, [])
    assert not result['apps']


def policy(monkeypatch, app, *, withdraw=False):
    monkeypatch.setenv("STORE_SEMANTIC_ENABLED", "true")
    available = [app]
    def resolve(ids):
        return [deepcopy(a) for a in available if ids is None or a["id"] in ids]
    async def recommend(**kw):
        return expert._recommendation_decision(kw["query"], [{"app": deepcopy(app), "rank": 1}], "en")
    def interpretation(*args):
        if withdraw:
            available.clear()
        # Even a model's wrong act must not turn initial discovery into inspection.
        return {"action": "answer", "apps": ["1"], "query": "collect device measurements", "view": "purpose"}
    interpreter = Mock(side_effect=interpretation)
    writer = Mock(side_effect=AssertionError("No writer/reviewer in this path"))
    def present(question, response, locale):
        # The real HTTP presenter returns a deserialized context, not an alias.
        response["context"] = deepcopy(response["context"])
        return expert.prepared_answer(question, response, locale)
    instance = policy_module.StoreConversation(recommend, resolve, lambda *a: "", interpreter, writer,
        decide=expert._recommendation_decision, present=present)
    return instance, interpreter, writer


def ask(instance, question):
    return asyncio.run(instance.respond_with_history(ChatRequestV2(message=question, locale="en"),
        "compare", {}, [], nlu={"intent": "compare", "confidence": 1.0}))


def test_initial_discovery_reuses_assessor_and_never_calls_writer(monkeypatch, app):
    instance, interpreter, writer = policy(monkeypatch, app)
    result = ask(instance, "Our sensors produce readings we need to gather in one place.")
    interpreter.assert_called_once()
    writer.assert_not_called()
    assert result["decision"]["outcome"] == "recommended"
    assert result["apps"][0]["app"]["app_id"] == "opaque-new"
    assert result["generation"]["model_calls"] == 1


@pytest.mark.parametrize("question", [
    "Find a tool to collect measurements and forecast storms",
    "Find a tool to collect measurements from 500 sensors",
    "Find a tool to collect measurements without registration",
])
def test_interpretation_cannot_erase_explicit_restrictions(monkeypatch, app, question):
    instance, _, writer = policy(monkeypatch, app)
    result = ask(instance, question)
    assert not result["apps"] and result["decision"]["outcome"] == "abstained"
    writer.assert_not_called()


def test_withdrawal_during_interpretation_still_fails_closed(monkeypatch, app):
    instance, _, _ = policy(monkeypatch, app, withdraw=True)
    result = ask(instance, "Our sensors produce readings we need to gather in one place.")
    assert not result["apps"] and result["decision"]["reason"] == "catalogue_changed"
    assert result["context"]["last_results"] == result["context"]["focused_ids"] == []


def test_invalid_native_id_is_terminal_without_model_reinterpretation(monkeypatch, app):
    instance, interpreter, _ = policy(monkeypatch, app)
    result = ask(instance, "Find OPAQUE-NEW to collect measurements")
    interpreter.assert_not_called()
    assert not result["apps"] and result["decision"]["reason"] == "invalid_native_reference"
    assert "case-sensitive" in result["message"]


def test_prepared_simplification_stays_fast_on_repeat_without_masking_new_search(monkeypatch, app):
    instance, interpreter, writer = policy(monkeypatch, app)
    context = {"turn": 1, "focused_ids": [app["id"]], "last_results": [{"app": app, "rank": 1}],
               "explanation_topic": "collect device measurements"}
    for _ in range(2):
        result = asyncio.run(instance.respond_with_history(
            ChatRequestV2(message="Can you make that simpler?", locale="en"), "search", context, []))
        assert result["apps"] and result["generation"]["source"] == "prepared"
        context = result["context"]
    interpreter.assert_not_called()
    asyncio.run(instance.respond_with_history(
        ChatRequestV2(message="I want to anticipate storms", locale="en"), "search", context, []))
    interpreter.assert_called_once()
    writer.assert_not_called()


@pytest.mark.parametrize("query,expected", [("forecast storms", "abstained"), ("collect device measurements", "recommended")])
def test_rasa_help_uses_no_match_state_but_cannot_veto_source_support(monkeypatch, app, query, expected):
    instance, interpreter, writer = policy(monkeypatch, app)
    interpreter.side_effect = None
    interpreter.return_value = {"action": "search", "apps": [], "query": query, "view": "capability"}
    result = asyncio.run(instance.respond_with_history(ChatRequestV2(message="What options could you offer?", locale="en"),
        "help", {"last_outcome": "abstained", "turn": 1}, [],
        nlu={"source": "rasa", "intent": "help", "confidence": 1.0}))
    assert result["decision"]["outcome"] == expected
    if expected == "abstained":
        assert result["generation"]["nlu_policy"] == "no_match_recovery"
        assert result["intent"] == "conversation"
    else:
        assert "nlu_policy" not in result["generation"]
    writer.assert_not_called()


def test_model_clarification_cannot_discard_a_resolved_app_or_approve_an_unknown_feature(monkeypatch, app):
    instance, interpreter, writer = policy(monkeypatch, app)
    interpreter.side_effect = None
    interpreter.return_value = {'action':'clarify','apps':[],'query':'predict earthquakes','view':'clarify'}
    context = {'turn':1,'focused_ids':[app['id']],'last_results':[{'app':app,'rank':1}]}
    result = asyncio.run(instance.respond_with_history(
        ChatRequestV2(message='Does it predict earthquakes automatically?',locale='en'),
        'detail', context, []))
    assert not result['apps']
    assert result['context']['focused_ids'] == [app['id']]
    assert result['decision']['outcome'] == 'abstained'
    assert 'Which App' not in result['message']
    writer.assert_not_called()


def test_capability_paraphrase_uses_interpretation_with_the_same_source_assessor(monkeypatch, app):
    instance, interpreter, writer = policy(monkeypatch, app)
    interpreter.side_effect = None
    interpreter.return_value = {'action':'answer', 'apps':['1'], 'query':'collect device measurements', 'view':'capability'}
    context = {'turn':1, 'focused_ids':[app['id']], 'last_results':[{'app':app, 'rank':1}]}
    result = asyncio.run(instance.respond_with_history(
        ChatRequestV2(message='Could it gather the readings our devices produce?', locale='en'),
        'detail', context, []))
    assert result['decision']['outcome'] == 'recommended'
    assert result['context']['focused_ids'] == [app['id']]
    assert interpreter.call_count == 1
    # Interpretation must not erase a second unknown operation or a restriction.
    for question in ['Could it gather readings and predict storms?',
                     'Could it gather readings without registration?',
                     'Could it gather readings from 500 devices?']:
        result = asyncio.run(instance.respond_with_history(ChatRequestV2(message=question, locale='en'),
            'detail', context, []))
        assert not result['apps']
    writer.assert_not_called()


def test_unverified_conditions_survive_source_reads_and_later_recommendations(monkeypatch, app):
    instance, interpreter, writer = policy(monkeypatch, app)
    result = ask(instance, 'Find only free applications to collect device measurements.')
    assert result['context']['pending_filters'] == ['pricing']
    interpreter.assert_not_called()
    additional = asyncio.run(instance.respond_with_history(ChatRequestV2(
        message='Find only free applications.', locale='en', filters={'protocols':['MQTT']}),
        'search', result['context'], []))
    assert additional['context']['pending_filters'] == ['pricing', 'protocols']
    context = {**result['context'], 'turn':1, 'focused_ids':[app['id']]}
    result = asyncio.run(instance.respond_with_history(ChatRequestV2(message='Tell me about it', locale='en'),
        'detail', context, []))
    assert result['apps'] and 'pricing requirement remains unconfirmed' in result['message']
    result = asyncio.run(instance.respond_with_history(ChatRequestV2(message='Find an app to collect device measurements.', locale='en'),
        'search', result['context'], []))
    assert not result['apps'] and result['decision']['reason'] == 'unverified_filters'
    assert result['context']['pending_filters'] == ['pricing']
    interpreter.assert_not_called()
    writer.assert_not_called()


def test_pending_conditions_are_passed_to_one_pass_recovery(monkeypatch, app):
    instance, interpreter, _ = policy(monkeypatch, app)
    interpreter.side_effect = None
    interpreter.return_value = {'action':'chat', 'apps':[], 'query':'verify terms', 'view':'next_steps'}
    result = asyncio.run(instance.respond_with_history(ChatRequestV2(message='What would we need to check next?', locale='en'),
        'help', {'turn':1, 'pending_filters':['pricing'], 'constraint_request':'only free apps'}, []))
    assert 'licence terms' in result['message'] and 'price of 0' in result['message']
    assert interpreter.call_args.args[3]['pending_filters'] == ['pricing']
    assert interpreter.call_args.args[3]['constraint_request'] == 'only free apps'
    assert result['context']['pending_filters'] == ['pricing']
    interpreter.reset_mock()
    result = asyncio.run(instance.respond_with_history(ChatRequestV2(message='How should we check those conditions?', locale='en'),
        'help', {'turn':1, 'last_outcome':'abstained', 'pending_filters':['pricing']}, [],
        nlu={'source':'rasa', 'intent':'help', 'confidence':1.0}))
    assert result['message'].startswith('Ask the provider to confirm the licence terms')
    assert result['generation']['nlu_policy'] == 'constraint_help'
    interpreter.assert_not_called()


def test_constraint_removal_consumes_the_whole_operand_and_preserves_remaining_request(monkeypatch, app):
    instance, interpreter, _ = policy(monkeypatch, app)
    context = {'turn':1, 'pending_filters':['pricing'], 'constraint_request':'only free apps',
               'focused_ids':[app['id']]}
    result = asyncio.run(instance.respond_with_history(ChatRequestV2(
        message='Remove the pricing restriction. Find an app to collect device measurements.', locale='en'),
        'search', context, []))
    assert result['decision']['outcome'] == 'recommended'
    assert result['context']['pending_filters'] == []
    assert context['pending_filters'] == ['pricing']
    interpreter.assert_not_called()
    for clause in ['Do not remove the pricing restriction', 'Remove the pricing restriction unless it is free',
                   'Remove the pricing restriction and guarantee offline access']:
        result = asyncio.run(instance.respond_with_history(ChatRequestV2(
            message=clause + '. Find an app to collect device measurements.', locale='en'),
            'search', context, []))
        assert not result['apps']
        assert result['context']['pending_filters'] == ['pricing']
