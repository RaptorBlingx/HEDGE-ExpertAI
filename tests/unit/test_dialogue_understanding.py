"""One interpretation per turn: identity, references and structure, never a guess."""
import json

import pytest
from hedge_shared.store_knowledge import prepare
from hedge_shared.store_v1 import StoreAppMetadata

from scripts.store_v1_playground import load_service

understanding = load_service("unit_understanding_chat", "chat-intent")("understanding")


def app(name, readme, *, provider="Example Labs", description=""):
    raw = {"app_id": "id-" + name.casefold().replace(" ", ""), "name": name, "provider": provider,
           "store_id": "synthetic-only", "active": True, "visible": True, "readme": f"<p>{readme}</p>",
           "description": description or None}
    return prepare(StoreAppMetadata.model_validate(raw))["projection"]


EDGE = app("EdgeConnect", "EdgeConnect combines flexibility bids.", provider="INESCTEC")
TREE = app("Semantic Treehouse", "Used to publish shared data models.", provider="TNO")
WATCH = app("TurbineWatch", "TurbineWatch analyses gearbox vibration.")
CATALOGUE = [EDGE, TREE, WATCH]


def interpreter(rasa_act=None, semantic_act=None, *, confidence=0.95, choice=None):
    """Classifiers that read every masked message as the given acts."""
    acts = understanding.acts()
    labels = [name for name, act in acts.items() for _ in act["examples"]]
    seen = []

    def rasa(text):
        seen.append(text)
        return [(rasa_act, confidence)] if rasa_act else None

    def semantic(text, examples):
        return [1.0 if label == semantic_act else 0.5 for label in labels] if semantic_act else None

    calls = []

    def arbitrate(message, options, context):
        calls.append(options)
        return choice

    result = understanding.Interpreter(rasa=rasa, semantic=semantic, arbitrate=arbitrate)
    result.seen, result.calls = seen, calls
    return result


def interpret(text, act, state=None, catalogue=CATALOGUE, **kw):
    return interpreter(act, act, **kw).interpret(text, state or {}, catalogue)


@pytest.mark.parametrize("text", ["what do Edge Connect do?", "edgeconnect?", "Tell me about Edge-Connect",
                                  "What does INESCTEC's app do?"])
def test_an_app_named_any_way_is_the_subject_and_is_masked_for_the_classifiers(text):
    reader = interpreter("describe", "describe")
    frame = reader.interpret(text, {}, CATALOGUE)
    assert (frame.act, frame.subjects, frame.source) == ("describe", [EDGE["id"]], "agreement")
    assert "APP" in reader.seen[0] and "dge" not in reader.seen[0]


def test_references_resolve_against_what_was_shown_and_discussed():
    shown = {"shown": [EDGE["id"], TREE["id"], WATCH["id"]]}
    assert interpret("what does the second one do", "describe", shown).subjects == [TREE["id"]]
    assert interpret("compare the first and the last", "compare", shown).subjects == [EDGE["id"], WATCH["id"]]
    focused = {"focus": [EDGE["id"]], "shown": [EDGE["id"]], "compared": [EDGE["id"], TREE["id"]]}
    assert interpret("who's behind it?", "provider", focused).subjects == [EDGE["id"]]
    assert interpret("and the other one?", "provider", focused).subjects == [TREE["id"]]
    # Without a displayed set, "the other one" is the rest of a two-App catalogue.
    assert interpret("and the other app?", "describe", {"focus": [EDGE["id"]]}, [EDGE, TREE]).subjects == [TREE["id"]]


def test_an_explicit_reference_that_resolves_to_nothing_is_never_the_focus():
    frame = interpret("what does the third one do", "describe", {"focus": [EDGE["id"]], "shown": [EDGE["id"], TREE["id"]]})
    assert (frame.act, frame.problem) == ("clarify", "no_subject")


def test_a_functional_need_turns_a_description_into_a_check_and_a_listing_into_a_search():
    frame = interpreter("find", "describe").interpret("Can EdgeConnect forecast solar production?", {}, CATALOGUE)
    assert (frame.act, frame.subjects) == ("check", [EDGE["id"]]) and frame.need == "forecast solar production"
    # Only when a classifier heard a need: both reading a description keeps it one.
    assert interpret("Explain EdgeConnect like I'm new to energy data", "describe").act == "describe"
    frame = interpret("list apps for gearbox vibration", "list")
    assert frame.act == "find" and "gearbox vibration" in frame.need
    # Qualifiers of an explanation are not a need, and listings with function words stay listings.
    assert interpret("what apps do we have?", "list").act == "list"
    assert interpret("explain it like I'm new to energy data", "simple", {"focus": [WATCH["id"]]}).act == "simple"


def test_a_search_phrased_about_the_app_in_focus_is_a_check_of_that_app():
    frame = interpret("can it shut down the turbine?", "find", {"focus": [WATCH["id"]], "shown": [WATCH["id"]]})
    assert (frame.act, frame.subjects) == ("check", [WATCH["id"]])


def test_an_elided_need_and_a_repeated_question_reuse_the_dialogue_state():
    state = {"focus": [EDGE["id"]], "last": {"act": "check", "subjects": [EDGE["id"]], "need": "forecast solar"}}
    frame = interpret("ok, is there any app that does?", "find", state)
    assert (frame.act, frame.need) == ("find", "forecast solar")
    frame = interpret("what about TurbineWatch?", "same", state)
    assert (frame.act, frame.subjects, frame.need) == ("check", [WATCH["id"]], "forecast solar")


def test_disagreeing_classifiers_go_to_the_model_and_otherwise_to_the_user():
    reader = interpreter("describe", "audience", choice=1)
    frame = reader.interpret("TurbineWatch?", {}, CATALOGUE)
    assert (frame.act, frame.source) == ("audience", "model") and len(reader.calls[0]) == 2
    # Readings that agree once completed ("describe" with a need is a check) need no choice.
    assert interpreter("describe", "find").interpret("TurbineWatch gearbox", {}, CATALOGUE).act == "check"
    # A reading that fails its structure (a search without a need) is dropped.
    assert interpreter("describe", "find").interpret("TurbineWatch?", {}, CATALOGUE).act == "describe"
    frame = interpreter("provider", "price").interpret("TurbineWatch?", {}, CATALOGUE)
    assert (frame.act, frame.problem) == ("clarify", "two_readings")
    assert {o["gloss"] for o in frame.options} == {"say who provides **TurbineWatch**",
                                                   "show what is listed about the price of **TurbineWatch**"}


def test_a_low_confidence_rasa_reading_is_not_a_reading():
    frame = interpreter("provider", "price", confidence=0.2).interpret("TurbineWatch?", {}, CATALOGUE)
    assert (frame.act, frame.source) == ("price", "consistent")


def test_identity_problems_are_clarified_never_guessed():
    assert interpret(f"show {EDGE['app_id'].upper()}", "describe").problem == "id_case"
    twins = [app("MeterScope", "Reads meters."), {**app("MeterScope", "Reads meters too."), "id": "other", "app_id": "x2"}]
    assert interpret("tell me about meterscope", "describe", catalogue=twins).problem == "ambiguous_name"
    assert interpret("who provides it?", "provider").problem == "no_subject"


def test_a_clicked_card_is_described_by_its_native_identity_whatever_the_focus():
    reader = interpreter("compare", "compare")
    frame = reader.interpret("Tell me about it", {"focus": [EDGE["id"]]}, CATALOGUE, clicked=[TREE["id"]])
    assert (frame.act, frame.subjects, frame.source) == ("describe", [TREE["id"]], "action")
    assert reader.interpret("x", {}, CATALOGUE, clicked=[]).problem == "unavailable_action"


def test_dialogue_acts_are_one_labelled_dataset_with_masked_apps():
    data = json.loads((understanding.files("hedge_shared") / "dialogue_acts.json").read_text())
    assert data["placeholder"] == "APP" and {"describe", "check", "find", "list", "same"} <= set(data["acts"])
    assert all(act["gloss"] and len(act["examples"]) >= 6 for act in data["acts"].values())


@pytest.mark.parametrize("text,need", [
    ("Which is better for settlement?", "settlement"),
    ("I'm looking for something that forecasts electricity prices", "forecasts electricity prices"),
    ("we need to turn JSON messages from one format into another", "turn JSON messages from one format into another"),
    ("I need a free app that forecasts solar", "free app that forecasts solar"),  # a condition is never trimmed
    ("does it handle settlement too?", "handle settlement"),
    ("any tool for gearbox vibration, which app should I look at?", "gearbox vibration"),
])
def test_the_need_keeps_every_requested_word_and_drops_only_asking(text, need):
    assert understanding.need_text(text, [], understanding.references(text)) == need


def test_an_agreed_check_without_a_pronoun_is_about_the_app_in_focus():
    state = {"focus": [EDGE["id"]], "shown": [EDGE["id"]]}
    frame = interpret("and how is settlement handled then?", "check", state)
    assert (frame.act, frame.subjects) == ("check", [EDGE["id"]])


def test_ranges_and_a_single_result_are_addressable_by_position():
    shown = {"shown": [EDGE["id"], TREE["id"], WATCH["id"]], "focus": [TREE["id"]]}
    assert interpret("compare the first two apps", "compare", shown).subjects == [EDGE["id"], TREE["id"]]
    assert interpret("Tell me about the first app", "describe", {"shown": [WATCH["id"]]}).subjects == [WATCH["id"]]


def test_both_after_a_withdrawal_is_never_some_other_pair():
    state = {"shown": ["withdrawn", EDGE["id"]], "compared": ["withdrawn", EDGE["id"]]}
    frame = interpret("Compare both", "compare", state, [EDGE, TREE])
    assert (frame.act, frame.problem) == ("clarify", "no_comparison_pair")
    assert interpret("compare the two apps", "compare", {}, [EDGE, TREE]).subjects == [EDGE["id"], TREE["id"]]


@pytest.mark.parametrize("text,act", [("mqtt", "term"), ("gearbox vibration analysis", "describe"),
                                      ("We need a common glossary so partners read data fields alike", "meaning")])
def test_a_need_without_an_app_is_a_search_whatever_the_reading(text, act):
    frame = interpret(text, act)
    assert frame.act == "find" and frame.need


def test_a_bare_app_name_or_a_term_question_keeps_its_act():
    assert interpret("EdgeConnect", "describe").act == "describe"
    assert interpret("what is an aggregator?", "term").act == "term"
    assert interpret("how does it work", "how").problem == "no_subject"
