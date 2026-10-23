"""The conversation scorer cannot pass an answer that recommends Apps nobody expected."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("dialogue_score", Path(__file__).parents[2] / "evaluation/dialogue/score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)


def reply(*names, outcome="recommended"):
    return {"reply": " ".join(f"**{n}** fits what you need." for n in names), "apps": list(names),
            "decision": {"outcome": outcome}}


def test_an_extra_recommendation_fails_even_beside_the_expected_app():
    expect = {"act": "find", "subject": ["PriceLens"]}
    assert score.problems(expect, reply("PriceLens")) == []
    assert any("not anticipated" in p for p in score.problems(expect, reply("PriceLens", "PlanGrid")))


def test_an_exact_recommendation_set_is_enforced_both_ways():
    expect = {"act": "find", "recommend": ["OfflineBox"]}
    assert score.problems(expect, reply("OfflineBox")) == []
    assert score.problems(expect, reply("OfflineBox", "CloudLog"))
    assert score.problems(expect, reply(outcome="abstained") | {"reply": "No App documents that."})
    assert score.problems({"act": "find", "recommend": []}, reply("CloudLog"))


def test_apps_named_as_expected_concepts_may_be_recommended():
    assert score.problems({"act": "choose", "concepts_any": ["EdgeConnect"]}, reply("EdgeConnect")) == []
    assert score.problems({"act": "choose", "concepts_any": ["schema"]}, reply("SchemaCheck"))
