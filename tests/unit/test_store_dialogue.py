"""Store-only policy regression tests; synthetic route tests remain unchanged."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from hedge_shared.models_v2 import ChatRequestV2

from scripts.store_v1_playground import load_service

policy_module = load_service("unit_store_dialogue", "chat-intent")("store_dialogue")


@pytest.fixture
def dialogue():
    apps = [
        {"id": "local-edge", "app_id": "native-edge", "name": "EdgeConnect", "provider": None},
        {"id": "local-tree", "app_id": "native-tree", "name": "Semantic Treehouse", "provider": None},
    ]

    def resolve(ids):
        return [deepcopy(a) for a in apps if ids is None or a["id"] in ids]

    search = AsyncMock(return_value={"apps": [{"app": a, "rank": i + 1} for i, a in enumerate(apps)], "message": "source facts"})
    policy = policy_module.StoreDialogue(search, resolve, lambda query, results, locale: "source facts")
    context = {"last_results": [{"app": deepcopy(a), "rank": i + 1} for i, a in enumerate(apps)],
               "last_query": "sensor", "focused_ids": ["local-tree"]}
    return policy, apps, search, context


def ask(dialogue, message, intent="detail", filters=None):
    policy, _, _, context = dialogue
    return asyncio.run(policy.respond(ChatRequestV2(message=message, filters=filters or {}), intent, context))


def test_ordinal_detail_preserves_original_order_and_rehydrates(dialogue):
    dialogue[1][1]["name"] = "Current title"
    result = ask(dialogue, "Tell me more about the second app")
    assert result["apps"][0]["app"]["name"] == "Current title"
    assert result["context"]["last_results"] == dialogue[3]["last_results"]
    assert result["context"]["focused_ids"] == ["local-tree"]
    dialogue[2].assert_not_awaited()


@pytest.mark.parametrize("message", ["Compare the first two apps", "Compare first and second", "Compare both", "Compare EdgeConnect and Semantic Treehouse"])
def test_comparison_selects_both_native_entities_without_searching_prose(dialogue, message):
    result = ask(dialogue, message, "compare")
    assert len(result["apps"]) == 2
    assert "Source-field comparison only" in result["message"]
    assert "score" not in result["apps"][0]
    dialogue[2].assert_not_awaited()


@pytest.mark.parametrize("message", ["What does it cost?", "Only free apps instead", "Does EdgeConnect support MQTT?", "Compare prices of both apps"])
def test_unsupported_requests_preserve_context_without_claims(dialogue, message):
    result = ask(dialogue, message)
    assert result["apps"] == []
    assert "cannot confirm" in result["message"]
    assert result["context"] == dialogue[3]
    dialogue[2].assert_not_awaited()


def test_withdrawal_is_not_resurrected_from_context(dialogue):
    dialogue[1].pop()
    result = ask(dialogue, "Compare first and second", "compare")
    assert result["apps"] == []
    assert "currently published" in result["message"]


def test_missing_reference_asks_for_names(dialogue):
    result = ask(dialogue, "Tell me about the fifth app")
    assert not result["apps"]


def test_pronoun_uses_focus_and_new_search_clears_focus(dialogue):
    assert ask(dialogue, "Describe it")["apps"][0]["app"]["id"] == "local-tree"
    result = ask(dialogue, "Find apps for sensor readings", "search")
    dialogue[2].assert_awaited_once_with(query="sensor readings", locale="en", filters=ChatRequestV2(message="x").filters.model_dump(mode="json"))
    assert result["context"]["focused_ids"] == []
    assert result["context"]["last_query"] == "sensor readings"


def test_unsupported_explicit_filter_fails_closed_even_for_named_detail(dialogue):
    assert ask(dialogue, "Describe EdgeConnect", filters={"capabilities": ["MQTT"]})["apps"] == []


def test_named_new_search_uses_names_but_keeps_ranking(dialogue):
    result = ask(dialogue, "Show me EdgeConnect and Semantic Treehouse", "search")
    assert dialogue[2].await_args.kwargs["query"] == '"EdgeConnect" OR "Semantic Treehouse"'
    assert len(result["context"]["last_results"]) == 2


@pytest.mark.parametrize("message", [
    "Show me all available applications", "List apps", "Browse the catalogue",
    "Could you show me available Apps?", "Please display all published applications.",
    "What applications are currently available?", "Which apps are in the Store?",
    "Show all the available applications in the HEDGE Store", "What apps do you have?",
])
def test_browsing_lists_authoritative_entities_without_search_terms(dialogue, message):
    result = ask(dialogue, message, "search")
    assert result["intent"] == "browse"
    assert [r["app"]["app_id"] for r in result["apps"]] == ["native-edge", "native-tree"]
    assert all(r["evidence_fields"] == ["catalogue"] and "score" not in r for r in result["apps"])
    assert "snapshot may be incomplete" in result["message"]
    assert "coverage of the entire HEDGE catalogue is not established" in result["message"]
    assert result["context"]["last_query"] == ""
    assert result["context"]["last_results"] == result["apps"]
    dialogue[2].assert_not_awaited()


@pytest.mark.parametrize("message", [
    "Show me all applications for sensor readings", "List applications about semantic data",
    "Find apps without cloud processing", "Show me apps that monitor energy",
])
def test_constrained_searches_are_not_reclassified_as_catalogue_browsing(dialogue, message):
    result = ask(dialogue, message, "search")
    assert result["intent"] == "search"
    dialogue[2].assert_awaited_once()


def test_browsing_is_bounded_stable_and_filters_before_limit(dialogue):
    dialogue[1].extend({"id": f"local-{i}", "app_id": f"native-{i}", "name": None,
                       "provider": "Provider"} for i in range(10))
    result = ask(dialogue, "List available applications", "search", {"publisher": "provider"})
    assert len(result["apps"]) == 5
    assert [r["app"]["app_id"] for r in result["apps"]] == [f"native-{i}" for i in range(5)]
    assert all(r["app"]["provider"] == "Provider" for r in result["apps"])


def test_empty_browse_clears_old_references_without_claiming_empty_store(dialogue):
    dialogue[1].clear()
    result = ask(dialogue, "List applications", "search")
    assert result["apps"] == []
    assert result["context"]["last_results"] == []
    assert result["context"]["focused_ids"] == []
    assert "Showing 0" in result["message"]
    assert "snapshot may be incomplete" in result["message"]
    dialogue[2].assert_not_awaited()


def test_unavailable_authoritative_browse_never_falls_back_to_cached_results(dialogue):
    def unavailable(ids):
        raise ConnectionError("PostgreSQL unavailable")
    dialogue[0].resolve = unavailable
    with pytest.raises(ConnectionError):
        ask(dialogue, "Show me all applications", "search")
    dialogue[2].assert_not_awaited()


def test_unsupported_browse_requests_remain_limited(dialogue):
    assert ask(dialogue, "List all free applications", "search")["apps"] == []
    assert ask(dialogue, "List applications", "search", {"capabilities": ["MQTT"]})["apps"] == []
    dialogue[2].assert_not_awaited()


def test_generic_browse_words_do_not_bind_to_an_app_named_store(dialogue):
    dialogue[1].append({"id": "local-store", "app_id": "native-store", "name": "Store", "provider": None})
    result = ask(dialogue, "Show all available applications in the Store", "search")
    assert result["intent"] == "browse"
    assert len(result["apps"]) == 3
    dialogue[2].assert_not_awaited()


def test_model_delay_cannot_return_withdrawn_or_changed_apps(dialogue):
    def generate(*args):
        dialogue[1].pop()
        return {'message':'generated old facts','generation':{'source':'ollama'}}
    dialogue[0].generate=generate
    result=ask(dialogue,'Compare both','compare')
    assert result['apps']==[]
    assert 'old facts' not in result['message']
    assert result['context']['last_results']==[]
    assert result['generation']['reason']=='catalogue_changed'


def test_generator_cannot_replace_authoritative_app_results(dialogue):
    dialogue[0].generate=lambda *args:{'message':'source excerpts','generation':{'source':'ollama'},
                                      'apps':[{'app':{'id':'fabricated'}}]}
    result=ask(dialogue,'Compare both','compare')
    assert [r['app']['id'] for r in result['apps']]==['local-edge','local-tree']
