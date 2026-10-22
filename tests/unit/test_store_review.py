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
