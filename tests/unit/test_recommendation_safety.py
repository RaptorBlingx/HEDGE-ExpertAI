"""Negation, conditions, actor ownership and input roles survive every recommendation path."""
import asyncio
import json
from copy import deepcopy

import pytest
from hedge_shared.models_v2 import ChatRequestV2
from hedge_shared.store_knowledge import prepare
from hedge_shared.store_v1 import StoreAppMetadata

from scripts.store_v1_playground import load_service

expert = load_service("unit_safety_expert", "expert-recommend")
suitability, evidence, review, answers, recommender = (
    expert(m) for m in ("suitability", "evidence", "review", "answers", "recommender"))
chat = load_service("unit_safety_chat", "chat-intent")
assistant_module, understanding = chat("assistant"), chat("understanding")


def app(name, readme):
    raw = {"app_id": "id-" + name.casefold(), "name": name, "provider": "Example", "store_id": "synthetic-only",
           "active": True, "visible": True, "readme": f"<p>{readme}</p>", "price": 0}
    prepared = prepare(StoreAppMetadata.model_validate(raw))
    return {**prepared["projection"], "prepared_explanation": prepared["explanation"]}


PRIVATE = app("PrivacyMeter", "PrivacyMeter aggregates smart meter readings for neighbourhood reports. "
                              "It does not collect personal data.")
PROFILE = app("HomeTrack", "HomeTrack collects personal data and appliance usage from households.")
FORECAST = app("ForecastHub", "ForecastHub forecasts day-ahead electricity prices from market data.")
PLANNER = app("PlanGrid", "PlanGrid schedules battery charging against day-ahead price forecasts supplied by the user.")
PREDICT = app("LoadAhead", "LoadAhead predicts next-day electricity consumption from historical meter readings "
                           "and weather data.")
FORWARD = app("TelemetryLink", "TelemetryLink forwards sensor telemetry from MQTT devices to HTTP endpoints.")
PASSIVE = app("Compound", "Regional readings from multiple meters are combined under a common record.")
CATALOGUE = [PRIVATE, PROFILE, FORECAST, PLANNER, PREDICT, FORWARD]


def status(need, target):
    return suitability.assess(need, target, "en")["status"]


@pytest.mark.parametrize("need,target", [
    ("forecast electricity prices", PLANNER), ("price forecasts", PLANNER),
    ("weather data", PREDICT), ("historical meter readings", PREDICT),
    ("MQTT devices", FORWARD),  # the devices it reads from are not something it provides
])
def test_what_an_app_works_from_is_not_what_it_provides(need, target):
    assert status(need, target) != "source_supported"


@pytest.mark.parametrize("need,target", [
    ("forecast electricity prices", FORECAST), ("predict consumption", PREDICT),
    ("forward telemetry from MQTT devices", FORWARD),     # the request itself names the input
    ("combine readings from multiple meters", PASSIVE),  # passive voice, input phrase ends at the verb
    ("mqtt", FORWARD),                                   # an interface it reads from is one it supports
])
def test_capabilities_and_requested_inputs_are_still_documented(need, target):
    assert status(need, target) == "source_supported"


@pytest.mark.parametrize("text,kept", [
    ("I need an app that must not collect personal data", "not collect personal data"),
    ("it must never store data", "never store data"),
    ("find an app that does not require internet", "not require internet"),
    ("is there an app for forecasting instead of trading", "forecasting instead of trading"),
    ("an app that only works if a licence is installed", "only works if a licence is installed"),
])
def test_need_normalization_never_drops_negation_conditions_or_exclusions(text, kept):
    assert understanding.need_text(text, [], understanding.references(text)) == kept


def test_a_negative_requirement_recommends_only_apps_stating_the_absence():
    need = understanding.need_text("I need an app that must not collect personal data", [], [])
    decision = recommender._recommendation_decision(need, [{"app": a, "rank": i + 1} for i, a in enumerate(CATALOGUE)], "en")
    assert [r["app"]["name"] for r in decision["apps"]] == ["PrivacyMeter"]


@pytest.fixture
def approving_model(monkeypatch):
    """A model that approves every review: only deterministic guards can prevent promotion."""
    monkeypatch.setenv("STORE_SEMANTIC_ENABLED", "true")
    monkeypatch.setenv("STORE_EXPLANATIONS_ENABLED", "true")
    evidence.set_similarity(lambda queries, passages: [[0.9] * len(passages) for _ in queries])
    calls = []

    class Client:
        def chat_structured(self, messages, schema, **kwargs):
            calls.append(messages[-1]["content"])
            return json.dumps({"supported": [True] * schema["properties"]["supported"]["minItems"]})

    monkeypatch.setattr(review, "OllamaClient", Client)
    yield calls
    evidence.set_similarity(evidence._remote_similarity)


@pytest.mark.parametrize("need,target", [("price forecasts", PLANNER), ("weather data", PREDICT),
                                         ("not collect personal data", PROFILE)])
def test_model_review_never_promotes_inputs_or_reversed_constraints(approving_model, need, target):
    decision = review.reviewed_decision(need, [{"app": target, "rank": 1}], "en")
    assert decision["decision"]["outcome"] == "abstained" and not approving_model


class Readings:
    def __init__(self):
        self.next = "find"
        self.labels = [n for n, a in understanding.acts().items() for _ in a["examples"]]

    def rasa(self, text):
        return [(self.next, 0.99)]

    def semantic(self, text, examples):
        return [1.0 if label == self.next else 0.5 for label in self.labels]


def assistant(compose):
    catalogue, readings = [deepcopy(a) for a in CATALOGUE], Readings()

    async def search(*, query, locale, filters):
        return recommender._recommendation_decision(query, [{"app": a, "rank": i + 1} for i, a in enumerate(catalogue)], locale)

    policy = assistant_module.Assistant(
        recommend=search, resolve=lambda ids: deepcopy(catalogue) if ids is None else
        [deepcopy(a) for i in ids for a in catalogue if a["id"] == i],
        compose=compose, explainer=lambda *a: {"message": "x"},
        interpreter=understanding.Interpreter(rasa=readings.rasa, semantic=readings.semantic),
        static=lambda intent, locale: intent)
    return policy, readings


def converse(policy, readings, turns):
    context, history, replies = {}, [], []
    for message, act in turns:
        readings.next = act
        reply = asyncio.run(policy.reply(ChatRequestV2(message=message, locale="en"), context, history))
        context = {**context, **reply["context"]}
        replies.append(reply)
    return replies


def test_a_pending_pricing_condition_holds_back_every_recommendation_path():
    """However a recommendation is reached (search, model review, a check, a choice), it waits for the condition."""
    def compose(mode, question, rows, locale, fields=()):
        if mode == "review":  # a model review that promotes the closest candidate
            return {**recommender._recommendation_decision(question, rows, locale),
                    "apps": rows[:1], "decision": {"outcome": "recommended", "reason": "reviewed_source_support"}}
        if mode == "check":
            return {**answers.capability_answer(question, rows, locale),
                    "apps": rows, "decision": {"outcome": "recommended", "reason": "reviewed_source_support"}}
        return {"message": answers.unverified(list(fields))}

    policy, readings = assistant(compose)
    replies = converse(policy, readings, [
        ("I need a free app that forecasts electricity prices", "find"),
        ("is there an app that schedules dishwashers?", "find"),        # nothing documented: review promotes
        ("does ForecastHub forecast electricity prices?", "check"),
        ("which of ForecastHub or PlanGrid forecasts electricity prices?", "choose"),
        ("forget the price condition", "remove_constraint"),
        ("does ForecastHub forecast electricity prices?", "check"),
    ])
    for reply in replies[:4]:
        assert reply["apps"] == [] and reply["decision"]["reason"] == "unverified_filters", reply["message"]
    assert replies[5]["decision"]["outcome"] == "recommended"  # the gate lifts only once the condition is dropped


OFFLINE = app("OfflineBox", "OfflineBox logs meter data locally and works without internet access.")
CLOUD = app("CloudLog", "CloudLog logs meter data in the cloud. An internet connection is required.")
CREW = app("FieldCrew", "Field engineers inspect substations and record faults in FieldCrew. FieldCrew stores the fault reports.")
PARTNER = app("PartnerLink", "PartnerLink sends equipment data to an external analytics service. "
                             "Another application predicts the failures.")


def test_a_requested_absence_is_met_only_by_a_stated_absence():
    assert status("log meter data without internet access", OFFLINE) == "source_supported"
    assert status("works without internet access to log meter data", OFFLINE) == "source_supported"
    assert status("log meter data without internet access", CLOUD) != "source_supported"


@pytest.mark.parametrize("need,target", [("inspect substations", CREW), ("predict failures", PARTNER)])
def test_what_people_or_other_products_do_is_not_the_apps_capability(need, target):
    assert status(need, target) != "source_supported"
    assert status("store fault reports", CREW) == "source_supported"


SCHEMA = app("SchemaCheck", "SchemaCheck validates JSON messages against supplied schemas and reports invalid fields.")


def test_a_requirement_that_names_the_input_matches_the_apps_input():
    assert status("validates against a schema", SCHEMA) == "source_supported"
    assert status("supplied schemas", SCHEMA) != "source_supported"


def test_a_structural_fallback_yields_to_a_reading_that_stands_on_its_own():
    labels = [n for n, a in understanding.acts().items() for _ in a["examples"]]
    reader = understanding.Interpreter(
        rasa=lambda text: [("price", 0.9)],
        semantic=lambda text, ex: [1.0 if label == "remove_constraint" else 0.5 for label in labels])
    frame = reader.interpret("forget the free part", {"pending_filters": ["pricing"]}, CATALOGUE)
    assert frame.act == "remove_constraint"
