"""Semantic recovery may publish only reviewed, request/current-source-bound evidence."""
from copy import deepcopy

from scripts.store_v1_playground import load_service

assessor = load_service("unit_t2_boundary", "expert-recommend")("suitability")

APP = {"id": "local", "source_profile": "hedge-store-v1", "app_id": "native", "store_id": "contract-test-only", "name": "Example",
       "source_evidence": {"readme": "The service joins regional flexibility offers into a single market submission."}}
QUESTION = "Coordinate our participants' offers for the system operator"


def receipt(app=APP, **changes):
    return assessor.ReviewedSupport(**{
        "request": QUESTION, "app_id": app["id"], "source_digest": assessor.source_digest(app, "en"),
        "quotes": (("readme", app["source_evidence"]["readme"]),), **changes})


def test_semantic_receipt_extends_lexical_assessment_without_changing_native_identity():
    assert assessor.assess(QUESTION, APP, "en")["status"] == "uncertain"
    result = assessor.assess(QUESTION, APP, "en", reviewed_support=receipt())
    assert result["status"] == "source_supported"
    assert result["evidence_spans"] == [APP["source_evidence"]["readme"]]


def test_unreviewed_network_dictionary_and_invented_quotes_are_not_proof():
    for proof in ({"reviewed": True, "request": QUESTION},
                  receipt(quotes=(("readme", "An invented supported capability."),))):
        assert assessor.assess(QUESTION, APP, "en", reviewed_support=proof)["status"] == "uncertain"


def test_receipt_cannot_cross_requests_apps_or_source_revisions():
    for proof in (receipt(request="A different need"), receipt(app_id="other")):
        assert assessor.assess(QUESTION, APP, "en", reviewed_support=proof)["status"] == "uncertain"
    changed = deepcopy(APP)
    # The quotation is still present; a newly added restriction invalidates the receipt.
    changed["source_evidence"]["readme"] += " Live operation is disabled."
    assert assessor.assess(QUESTION, changed, "en", reviewed_support=receipt())["status"] == "uncertain"

expert = load_service("unit_t2_generation", "expert-recommend")("store_conversation")


def test_recommendation_needs_exact_quotes_and_separate_semantic_review(monkeypatch):
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock

    draft = {"support": ["1.0"], "focus": ["1"], "kind": "answer",
             "answer": "Example joins participants' offers into a single market submission."}
    call = Mock(side_effect=[json.dumps(draft), json.dumps({"issues": []})])
    monkeypatch.setattr(expert, "OllamaClient", lambda: SimpleNamespace(model="test-only", chat_structured=call))
    result = expert.respond(QUESTION, [{"rank": 1, "app": APP}], "en", "search", [], semantic=True, allow_repair=False)
    assert result["generation"]["source"] == "ollama" and result["recommendations"] == ["1"]
    assert call.call_count == 2
    # A fabricated quote cannot reach review or published prose.
    draft["support"] = ["invented-reference"]
    call.reset_mock(side_effect=True)
    call.side_effect = [json.dumps(draft)]
    result = expert.respond(QUESTION, [{"rank": 1, "app": APP}], "en", "search", [], semantic=True, allow_repair=False)
    assert result["generation"]["reason"] == "unknown_support_reference"
    assert call.call_count == 1 and draft["answer"] not in result["message"]


def test_rejected_full_requirement_review_cannot_publish_positive_prose(monkeypatch):
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock

    draft = {"support": ["1.0"], "focus": ["1"], "kind": "answer",
             "answer": "Example guarantees an unsupported rate."}
    call = Mock(side_effect=[json.dumps(draft), json.dumps({"issues": ["The source does not state a guaranteed rate."]})])
    monkeypatch.setattr(expert, "OllamaClient", lambda: SimpleNamespace(model="test-only", chat_structured=call))
    result = expert.respond("Guarantee a specific rate", [{"rank": 1, "app": APP}], "en", "search", [], semantic=True, allow_repair=False)
    assert result["generation"]["reason"] == "grounding_review_rejected"
    assert result["generation"]["source"] == "deterministic" and draft["answer"] not in result["message"]


def test_multiple_complete_fields_survive_review_and_the_http_suitability_boundary(monkeypatch):
    """Mock model output verifies plumbing, never a recommendation-quality score."""
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    service = load_service('unit_t2_http', 'expert-recommend')
    routes = service('private_store')
    writer = service('store_conversation')
    app = deepcopy(APP)
    app['source_evidence'].update({
        f'dataspaceAppDescription.properties.featureList[{i}]':
            f'The application records participant contribution {i} for settlement.' for i in range(4)
    })
    selected = {'support': [f'1.{i}' for i in range(5)], 'focus': ['1'], 'kind': 'answer',
                'answer': 'Example coordinates the participants’ offers into one market submission.'}
    call = Mock(side_effect=[json.dumps(selected), json.dumps({'issues': []})])
    monkeypatch.setattr(writer, 'OllamaClient', lambda: SimpleNamespace(model='contract-test-only', chat_structured=call))
    for key, value in {'PRIVATE_STORE_ENABLED': 'true', 'HEDGE_STORE_ID': 'contract-test-only',
                       'APP_ENV': 'private-testing', 'GATEWAY_API_KEY': 'unit-only',
                       'STORE_SEMANTIC_ENABLED': 'false'}.items():
        monkeypatch.setenv(key, value)
    api = FastAPI()
    api.include_router(routes.router)
    with TestClient(api) as client:
        body = {'question': QUESTION, 'action': 'search', 'rows': [{'rank': 1, 'app': app}]}
        assert client.post('/internal/store/reason', json=body).status_code == 401
        assert client.post('/internal/store/reason', json=body, headers={'X-API-Key': 'unit-only'}).status_code == 404
        assert call.call_count == 0
        monkeypatch.setenv('STORE_SEMANTIC_ENABLED', 'true')
        response = client.post('/internal/store/reason', json=body, headers={'X-API-Key': 'unit-only'})
        assert response.status_code == 200
        result = response.json()
        assert result['recommendation_decision']['outcome'] == 'recommended'
        assert result['reviewed_rows'][0]['app']['app_id'] == 'native'
        assert len(result['support']['1']) == 5
        assert call.call_count == 2
        assert all(q['quote'] == app['source_evidence'][q['field']] for q in result['support']['1'])


def test_valid_clarification_plan_is_not_reported_as_inference_failure(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, Mock

    from hedge_shared.models_v2 import ChatRequestV2

    monkeypatch.setenv('STORE_SEMANTIC_ENABLED', 'true')
    policy_type = load_service('unit_t2_clarification', 'chat-intent')('store_conversation').StoreConversation
    interpret = Mock(return_value={'action': 'clarify', 'apps': [], 'query': 'How would that work?'})
    writer = Mock(side_effect=AssertionError('Clarification makes no App claims to synthesize'))
    policy = policy_type(AsyncMock(return_value={'apps': [], 'candidates': [], 'message': 'No match'}),
                         lambda ids: [deepcopy(APP)] if ids is None else [], lambda *a: '',
                         interpret, writer)
    result = asyncio.run(policy.respond_with_history(
        ChatRequestV2(message='How would that work?', locale='en'), 'help', {},
        [{'role': 'user', 'content': 'An earlier unresolved request'}]))
    assert result['intent'] == 'clarify' and result['apps'] == []
    assert result['generation']['reason'] == 'interpreted_clarification'
    assert result['generation']['model_completed'] is True
    interpret.assert_called_once()
    writer.assert_not_called()
