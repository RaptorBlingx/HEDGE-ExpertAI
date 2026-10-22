"""The Store assistant executes one frame from sources and keeps the dialogue state."""
import asyncio
import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from hedge_shared.models_v2 import ChatRequestV2
from hedge_shared.store_knowledge import prepare
from hedge_shared.store_v1 import StoreAppMetadata

from scripts.store_v1_playground import load_service

chat = load_service("unit_assistant_chat", "chat-intent")
assistant_module, understanding = chat("assistant"), chat("understanding")
expert = load_service("unit_assistant_expert", "expert-recommend")
answers, explainer, recommender = expert("answers"), expert("explainer"), expert("recommender")


def app(name, readme, *, provider="Example Labs", price=None):
    raw = {"app_id": "id-" + name.casefold(), "name": name, "provider": provider, "store_id": "synthetic-only",
           "active": True, "visible": True, "readme": f"<p>{readme}</p>", **({"price": price} if price is not None else {})}
    prepared = prepare(StoreAppMetadata.model_validate(raw))
    return {**prepared["projection"], "prepared_explanation": prepared["explanation"]}


RELAY = app("BidRelay", "BidRelay aggregates flexibility bids from several providers and submits a combined bid to the "
                        "energy market operator. It does not forecast prices.", price=0)
HUB = app("MeaningHub", "MeaningHub publishes shared vocabularies and mappings between data models.", provider="TNO")
LENS = app("PriceLens", "PriceLens forecasts day-ahead electricity prices using historical market data.")


def compose(mode, question, rows, locale, fields=()):
    if mode == "check":
        return answers.capability_answer(question, rows, locale)
    if mode == "review":
        return answers.search_answer(question, rows, locale)
    if mode == "list":
        return {"message": answers.listing([r["app"] for r in rows])}
    return {"message": answers.unverified(list(fields))}


class Readings:
    """Both classifiers read each message as the act the test assigns to it."""

    def __init__(self):
        self.next = "describe"
        self.labels = [n for n, a in understanding.acts().items() for _ in a["examples"]]

    def rasa(self, text):
        return [(self.next, 0.99)]

    def semantic(self, text, examples):
        return [1.0 if label == self.next else 0.5 for label in self.labels]


def assistant(apps=(RELAY, HUB, LENS), *, recommend=None, explain=None):
    catalogue = [deepcopy(a) for a in apps]
    readings = Readings()

    async def search(*, query, locale, filters):
        rows = [{"app": a, "rank": i + 1} for i, a in enumerate(catalogue)]
        return recommender._recommendation_decision(query, rows, locale)

    policy = assistant_module.Assistant(
        recommend=recommend or search,
        resolve=lambda ids: [deepcopy(a) for a in catalogue] if ids is None else
        [deepcopy(a) for i in ids for a in catalogue if a["id"] == i],
        compose=compose, explainer=explain or (lambda *a: explainer.respond(*a)),
        interpreter=understanding.Interpreter(rasa=readings.rasa, semantic=readings.semantic),
        static=lambda intent, locale: f"static {intent}")
    return policy, readings, catalogue


def converse(policy, readings, turns, context=None, **request):
    context, history, replies = context or {}, [], []
    for message, act in turns:
        readings.next = act
        reply = asyncio.run(policy.reply(ChatRequestV2(message=message, locale="en", **request), context, history))
        context = {**context, **reply["context"]}
        history += [{"role": "user", "content": message}, {"role": "assistant", "content": reply["message"]}]
        replies.append(reply)
    return replies, context


def test_a_conversation_keeps_its_subject_and_never_repeats_an_explanation(monkeypatch):
    monkeypatch.setenv("STORE_EXPLANATIONS_ENABLED", "false")
    policy, readings, _ = assistant()
    replies, context = converse(policy, readings, [
        ("Tell me about bid relay", "describe"), ("Explain it simply", "simple"), ("Give me an example", "example"),
        ("who makes it?", "provider"), ("compare it with meaninghub", "compare")])
    assert [[r["app"]["name"] for r in reply["apps"]] for reply in replies] == [
        ["BidRelay"]] * 4 + [["BidRelay", "MeaningHub"]]
    assert len({r["message"] for r in replies}) == 5
    assert all(r["decision"]["outcome"] == "not_applicable" for r in replies)
    assert context["dialogue"]["focus"] == [RELAY["id"]] and context["dialogue"]["compared"] == [RELAY["id"], HUB["id"]]


def test_listing_counts_the_catalogue_and_a_following_ordinal_binds_to_it():
    policy, readings, _ = assistant()
    (listed, second), _ = converse(policy, readings, [("what apps are there?", "list"), ("and the second one?", "describe")])
    assert listed["message"].startswith("There are 3 Apps in the Store:")
    assert [r["app"]["name"] for r in second["apps"]] == ["MeaningHub"]


def test_capability_checks_and_searches_recommend_only_through_the_verifier():
    policy, readings, _ = assistant()
    (found, no, other), context = converse(policy, readings, [
        ("I'm looking for something that forecasts electricity prices", "find"),
        ("can it submit bids?", "check"), ("which app does?", "find")])
    assert found["decision"]["outcome"] == "recommended" and [r["app"]["name"] for r in found["apps"]] == ["PriceLens"]
    assert no["decision"]["outcome"] == "abstained" and "fits what you need" not in no["message"]
    assert [r["app"]["name"] for r in other["apps"]] == ["BidRelay"]  # the elided need is "submit bids"


def test_unverifiable_conditions_hold_back_recommendations_until_dropped():
    policy, readings, _ = assistant()
    (free, dropped), context = converse(policy, readings, [
        ("I need a free app that forecasts electricity prices", "find"), ("forget the free part", "remove_constraint")])
    assert free["decision"] == {"outcome": "abstained", "reason": "unverified_filters"} and not free["apps"]
    assert "price of 0 doesn’t confirm free use" in free["message"]
    assert dropped["decision"]["outcome"] == "recommended" and dropped["apps"][0]["app"]["name"] == "PriceLens"
    assert context["dialogue"]["pending_filters"] == []


def test_typed_catalogue_filters_fail_closed_for_every_app_answer():
    policy, readings, _ = assistant()
    (reply,), _ = converse(policy, readings, [("Tell me about BidRelay", "describe")],
                           filters={"protocols": ["MQTT"]})
    assert reply["decision"]["reason"] == "unverified_filters" and not reply["apps"]


def test_a_zero_price_is_reported_without_claiming_free_use():
    policy, readings, _ = assistant()
    (reply,), _ = converse(policy, readings, [("is BidRelay free?", "price")])
    assert "doesn’t establish free use" in reply["message"] and "is free" not in reply["message"]


def test_a_clicked_card_is_answered_about_its_own_app_and_a_withdrawn_one_never_about_another():
    policy, readings, _ = assistant()
    action = {"type": "inspect", "store_id": HUB["store_id"], "app_id": HUB["app_id"]}
    (reply,), context = converse(policy, readings, [("Tell me about it", "compare")],
                                 context={"dialogue": {"focus": [RELAY["id"]]}}, app_action=action)
    assert [r["app"]["id"] for r in reply["apps"]] == [HUB["id"]] and "BidRelay" not in reply["message"]
    assert context["dialogue"]["focus"] == [HUB["id"]]
    gone = {**action, "app_id": "withdrawn-app"}
    (reply,), _ = converse(policy, readings, [("Tell me about it", "describe")],
                           context={"dialogue": {"focus": [RELAY["id"]]}}, app_action=gone)
    assert not reply["apps"] and "no longer available" in reply["message"]


def test_a_catalogue_change_during_an_answer_withdraws_its_apps():
    policy, readings, catalogue = assistant()

    def change(*args):
        catalogue[0]["source_evidence"]["readme"] = "Changed."
        return explainer.respond(*args)

    policy.explainer = change
    (reply,), context = converse(policy, readings, [("Explain BidRelay simply", "simple")])
    assert reply["decision"]["reason"] == "catalogue_changed" and not reply["apps"]
    assert "focus" not in context["dialogue"]


@pytest.mark.parametrize("change_after", [0, 1])
def test_streamed_sentences_are_released_only_while_the_app_is_still_authorized(change_after):
    policy, readings, catalogue = assistant()
    sentences = ["It combines bids.", " It tracks contributions."]

    def streaming(*args):
        relay = assistant_module.STREAM.get()
        for index, sentence in enumerate(sentences):
            if index == change_after:
                catalogue[0]["source_evidence"]["readme"] = "Withdrawn or revised."
            relay(sentence)
        return {"message": "".join(sentences), "generation": {"source": "ollama", "model_completed": True}}

    policy.explainer = streaming
    shown = []
    token = assistant_module.STREAM.set(shown.append)
    try:
        (reply,), _ = converse(policy, readings, [("How would BidRelay help an energy cooperative?", "ask")])
    finally:
        assistant_module.STREAM.reset(token)
    assert shown == sentences[:change_after]
    assert reply["message"].startswith("".join(shown)) and "changed while" in reply["message"]
    assert reply["decision"]["reason"] == "catalogue_changed" and not reply["apps"]


def test_search_failures_stay_errors_rather_than_no_match():
    policy, readings, _ = assistant(recommend=AsyncMock(side_effect=HTTPException(504, "Catalogue search timed out")))
    with pytest.raises(HTTPException):
        converse(policy, readings, [("find an app for meter data", "find")])


def test_two_readings_without_a_model_become_one_plain_question():
    policy, readings, _ = assistant()
    policy.interpreter.semantic = lambda text, examples: [1.0 if label == "price" else 0.5 for label in readings.labels]
    (reply,), _ = converse(policy, readings, [("BidRelay?", "provider")])
    assert reply["intent"] == "clarify" and reply["message"].startswith("Do you want me to ")
    assert "**BidRelay**" in reply["message"]


def test_small_talk_is_store_specific_and_keeps_the_dialogue():
    policy, readings, _ = assistant()
    (hello, about), context = converse(policy, readings, [("hi", "greeting"), ("help", "help")])
    assert "HEDGE Store" in hello["message"] and "3 Apps" in about["message"]
    (_, thanks), context = converse(policy, readings, [("Tell me about BidRelay", "describe"), ("thanks", "thanks")])
    assert context["dialogue"]["focus"] == [RELAY["id"]]
    json.dumps(context)  # the state is session-serializable


def test_choosing_between_named_apps_says_why_the_others_fall_short():
    policy, readings, _ = assistant()
    (reply,), _ = converse(policy, readings, [("Which is better for forecasting electricity prices: PriceLens or BidRelay?",
                                               "choose")])
    assert reply["decision"]["outcome"] == "recommended" and "**PriceLens** fits" in reply["message"]
    assert "**BidRelay**’s description says: “It does not forecast prices.”" in reply["message"]


def test_an_ambiguous_pronoun_after_several_results_offers_those_results():
    policy, readings, _ = assistant()
    context = {"dialogue": {"shown": [HUB["id"], LENS["id"]]}}
    (reply,), _ = converse(policy, readings, [("how does it work", "how")], context=context)
    assert reply["intent"] == "clarify" and "**MeaningHub** or **PriceLens**" in reply["message"]
