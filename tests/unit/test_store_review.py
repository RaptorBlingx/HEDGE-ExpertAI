"""Model review can confirm a paraphrase, never a quantity, absence, condition or limitation."""
import json

import pytest
from hedge_shared.store_knowledge import prepare
from hedge_shared.store_v1 import StoreAppMetadata

from scripts.store_v1_playground import load_service

expert = load_service("unit_review_expert", "expert-recommend")
review, evidence = expert("review"), expert("evidence")


def app(name, readme):
    raw = {"app_id": "id-" + name.casefold(), "name": name, "store_id": "synthetic-only", "active": True,
           "visible": True, "readme": f"<p>{readme}</p>"}
    return prepare(StoreAppMetadata.model_validate(raw))["projection"]


MAPPER = app("FlowMapper", "FlowMapper transforms JSON messages according to mappings configured by an operator.")
SIM = app("LoopLab", "LoopLab converts JSON messages only in simulation.")


@pytest.fixture
def model(monkeypatch):
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


def test_a_reviewed_paraphrase_recommends_with_its_exact_quotation(model):
    rows = [{"app": MAPPER, "rank": 1}]
    decision = review.reviewed_decision("turn JSON messages from one format into another", rows, "en")
    assert decision["decision"] == {"outcome": "recommended", "reason": "reviewed_source_support"}
    (row,) = decision["apps"]
    assert row["suitability"]["evidence_spans"][0] in MAPPER["source_evidence"]["readme"]
    assert "FlowMapper transforms JSON messages" in model[0]


@pytest.mark.parametrize("need", ["convert 5000 JSON messages per second", "convert JSON messages without mappings",
                                  "never store JSON messages", "convert JSON messages only offline"])
def test_quantities_absences_and_conditions_are_never_reviewed(model, need):
    decision = review.reviewed_decision(need, [{"app": MAPPER, "rank": 1}], "en")
    assert decision["decision"]["outcome"] == "abstained" and not model


def test_a_stated_limitation_is_never_reviewed(model):
    decision = review.reviewed_decision("convert JSON messages", [{"app": SIM, "rank": 1}], "en")
    assert decision["decision"]["outcome"] == "abstained" and not model


def test_review_is_off_without_the_model_flags_and_failures_keep_the_decision(model, monkeypatch):
    rows = [{"app": MAPPER, "rank": 1}]
    monkeypatch.setenv("STORE_SEMANTIC_ENABLED", "false")
    assert review.reviewed_decision("turn JSON into another format", rows, "en")["decision"]["outcome"] == "abstained"
    monkeypatch.setenv("STORE_SEMANTIC_ENABLED", "true")

    class Broken:
        def chat_structured(self, *a, **k):
            return json.dumps({"supported": ["yes"]})

    monkeypatch.setattr(review, "OllamaClient", Broken)
    decision = review.reviewed_decision("turn JSON into another format", rows, "en")
    assert decision["decision"]["outcome"] == "abstained" and decision["review"] == "unavailable"


answers = expert("answers")


def test_field_answers_quote_supplied_values_without_inferring_meaning():
    record = {"app_id": "id-x", "name": "Meter View", "provider": "Provider A", "store_id": "synthetic-only",
              "active": True, "visible": True, "readme": "<p>Meter View displays readings. Documentation: "
              "https://docs.example.invalid/meter</p>", "connector_version": "1.2", "built_for_connector": "EDC",
              "price": 0, "billable": False}
    app = prepare(StoreAppMetadata.model_validate(record))["projection"]
    assert answers.fact_answer("provider", [app]) == "**Meter View** is provided by **Provider A**."
    assert "doesn’t establish free use" in answers.fact_answer("price", [app])
    assert "Connector version: 1.2" in answers.fact_answer("details", [app])
    assert "https://docs.example.invalid/meter" in answers.fact_answer("access", [app])
    bare = prepare(StoreAppMetadata.model_validate({**record, "readme": "<p>Meter View displays readings.</p>",
                                                     "connector_version": None, "built_for_connector": None}))["projection"]
    assert "doesn’t say how to access it" in answers.fact_answer("access", [bare])
    assert answers.listing([app]).startswith("**Meter View** displays readings.")
    assert "price of 0 doesn’t confirm free use" in answers.unverified(["pricing"])
    assert "protocol support" in answers.unverified(["protocols"])
