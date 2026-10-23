"""App mentions are found by name however they are spelled, never guessed."""
import json

import pytest
from hedge_shared.app_linker import AppLinker, compact
from hedge_shared.store_knowledge import prepare
from hedge_shared.store_v1 import StoreAppMetadata


def app(name, *, app_id=None, provider="Example Labs", description="", listing=""):
    raw = {"app_id": app_id or "id-" + compact(name), "name": name, "provider": provider,
           "store_id": "synthetic-only", "active": True, "visible": True,
           "readme": f"<p>{name} does something useful.</p>", "description": description or None}
    if listing:
        raw["dataspace_app_description"] = json.dumps({"properties": {"name": listing}})
    return prepare(StoreAppMetadata.model_validate(raw))["projection"]


APPS = [app("EdgeConnect", provider="INESCTEC", listing="EdgeConnect-the best service"),
        app("Semantic Treehouse", provider="TNO", description="STH demo app", listing="Semantic Tree House"),
        app("e-Flex Hub"), app("TurbineWatch"), app("Grid Guardian"), app("Flow")]
LINKER = AppLinker(APPS)
NAMES = {a["id"]: a["name"] for a in APPS}


def named(text):
    return [(m.text, [NAMES[i] for i in m.app_ids], m.kind) for m in LINKER.mentions(text)]


@pytest.mark.parametrize("text, name", [
    ("what do Edge Connect do?", "EdgeConnect"), ("Tell me about Edge-Connect", "EdgeConnect"),
    ("edgeconnect?", "EdgeConnect"), ("EDGECONNECT", "EdgeConnect"), ("what about edge conect", "EdgeConnect"),
    ("Semantic Tree House", "Semantic Treehouse"), ("semantic treehouse please", "Semantic Treehouse"),
    ("e flex hub", "e-Flex Hub"), ("Turbine watch??", "TurbineWatch"), ("grid guardian vs", "Grid Guardian"),
    ("What is STH?", "Semantic Treehouse"),
])
def test_names_match_whatever_the_spacing_case_punctuation_or_a_small_typo(text, name):
    assert [n for _, names, _ in named(text) for n in names] == [name]


def test_provider_names_refer_to_their_apps_with_the_reference_noun():
    assert named("What does TNO's app do?") == [("TNO's app", ["Semantic Treehouse"], "provider")]
    assert named("and the one from INESCTEC") == [("INESCTEC", ["EdgeConnect"], "provider")]


def test_short_names_and_acronyms_need_the_publishers_spelling():
    # "sth" is chat slang and "flow" an ordinary word: neither names an App.
    assert named("can you do sth about data flow") == []
    assert named("Flow") == [("Flow", ["Flow"], "name")]


def test_listing_slogans_do_not_become_names_and_ordinary_words_do_not_match():
    assert named("the best service for settlement") == []
    assert named("a vocabulary hub for watch lists") == []


def test_native_ids_are_exact_and_case_sensitive():
    target = APPS[3]
    assert [m.kind for m in LINKER.mentions(f"show {target['app_id']}")] == ["id"]
    wrong = LINKER.mentions(f"show {target['app_id'].upper()}")
    assert [m.kind for m in wrong] == ["id_case"] and wrong[0].app_ids == ()


def test_shared_names_are_ambiguous_rather_than_guessed():
    twins = AppLinker([app("MeterScope", app_id="a"), app("MeterScope", app_id="b")])
    (mention,) = twins.mentions("tell me about meterscope")
    assert mention.ambiguous and len(mention.app_ids) == 2
