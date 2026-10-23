"""SCRUM-38 review regressions: complete quotations and honest extraction limits."""

import pytest
from hedge_shared.store_v1 import StoreAppMetadata

from scripts.store_v1_playground import load_service

recommend = load_service("unit_store_evidence_rendering", "expert-recommend")("recommender")


def app(**metadata):
    return StoreAppMetadata(store_id="Review-Store", app_id="Review-App", active=True,
                            visible=True, **metadata)


def render(source):
    results = [{"app": source.recommendation_projection(), "rank": 1}]
    return results, recommend._evidence_explanations(results, "en")[0]


def qualified_readme(length):
    start = "Specification notes: "
    end = " MQTT is supported only in simulation; production does not support MQTT."
    return start + "x" * (length - len(start) - len(end)) + end


def test_reported_1254_character_qualification_is_not_silently_cut():
    source = app(readme=qualified_readme(1254))
    assert source.readme[:1200].endswith("MQTT is supported")
    results, explanation = render(source)
    assert results[0]["app"]["source_evidence"]["readme"] == source.readme
    assert results[0]["app"]["id"] == source.id
    assert explanation["store_id"] == source.store_id
    assert explanation["source_app_id"] == source.app_id
    assert explanation["evidence_fields"] == ["readme"]
    assert 'readme: "' not in explanation["text"]
    assert "complete quotation omitted" in explanation["text"]
    assert "MQTT is supported" not in explanation["text"]
    assert recommend._recommendation_narrative("MQTT", results, "en") == (
        "- App 1: " + explanation["text"]
    )


@pytest.mark.parametrize("length", [1199, 1200, 1201, 16000])
def test_quotation_limit_keeps_complete_fields_or_omits_the_whole_field(length):
    source = app(readme=qualified_readme(length), provider="Example provider")
    results, explanation = render(source)
    assert results[0]["app"]["readme_status"] == "extracted"
    assert 'provider: "Example provider"' in explanation["text"]
    assert results[0]["app"]["source_evidence"]["readme"] == source.readme
    if length <= 1200:
        assert f'readme: "{source.readme}"' in explanation["text"]
        assert "production does not support MQTT" in explanation["text"]
        assert "omitted" not in explanation["text"]
    else:
        assert 'readme: "' not in explanation["text"]
        assert "readme: complete quotation omitted" in explanation["text"]
        assert "MQTT is supported" not in explanation["text"]


@pytest.mark.parametrize("field", ["description", "provider", "built_for_connector"])
def test_omission_applies_to_other_source_fields_with_late_qualifications(field):
    source = app(**{field: qualified_readme(1254)})
    _, explanation = render(source)
    assert "complete quotation omitted" in explanation["text"]
    assert "MQTT is supported" not in explanation["text"]


@pytest.mark.parametrize(("metadata", "status_field", "status"), [
    ({"readme": "a" * 16001}, "readme_status", "too_large"),
    ({"readme": "<script>not descriptive evidence</script>"}, "readme_status", "not_projected"),
    ({"dataspace_app_description": "broken JSON"}, "dataspace_description_status", "malformed"),
    ({"dataspace_app_description": "x" * 65537}, "dataspace_description_status", "too_large"),
    ({"dataspace_app_description": "[]"}, "dataspace_description_status", "unsupported_shape"),
    ({"dataspace_app_description": '{"properties":{"description":7}}'},
     "dataspace_description_status", "no_supported_text"),
])
def test_extraction_limits_are_not_reported_as_source_absence(metadata, status_field, status):
    source = app(**metadata)
    results, explanation = render(source)
    assert results[0]["app"][status_field] == status
    assert "supplied no descriptive metadata" not in explanation["text"]
    assert "could be extracted or projected" in explanation["text"]
    assert status.replace("_", " ") in explanation["text"]
    assert explanation["evidence_fields"] == []
    assert explanation["app_id"] == source.id
    assert recommend._recommendation_narrative("", results, "en") == "- App 1: " + explanation["text"]


def test_limited_readme_does_not_hide_other_successful_quotes():
    _, explanation = render(app(name="Telemetry", description="Collects readings.", readme="a" * 16001))
    assert 'name: "Telemetry"' in explanation["text"]
    assert 'description: "Collects readings."' in explanation["text"]
    assert "readme" in explanation["text"] and "too large" in explanation["text"]
    assert explanation["evidence_fields"] == ["name", "description"]


def test_missing_statuses_confirm_absence_but_legacy_projections_do_not():
    results, explanation = render(app())
    assert results[0]["app"]["readme_status"] == "missing"
    assert results[0]["app"]["dataspace_description_status"] == "missing"
    assert explanation["text"] == "The Store supplied no descriptive metadata."
    del results[0]["app"]["readme_status"]
    del results[0]["app"]["dataspace_description_status"]
    explanation = recommend._evidence_explanations(results, "en")[0]
    assert explanation["text"] == "No descriptive source text could be extracted or projected."


def test_oversized_description_is_not_reported_as_missing():
    _, explanation = render(app(description="a" * 16001))
    assert explanation["text"] == "No descriptive source text could be extracted or projected."


def test_short_valid_quotations_remain_escaped_and_complete():
    _, explanation = render(app(readme='MQTT requires [simulation] & excludes production.'))
    assert explanation["text"] == (
        r'readme: "MQTT requires \[simulation\] &amp; excludes production."'
    )


def test_normal_and_streamed_recommendations_use_the_same_omission_and_statuses(monkeypatch):
    source = app(readme=qualified_readme(1254))
    limited = app(readme="a" * 16001).model_copy(update={"app_id": "Limited-App"})
    results = [{"app": a.recommendation_projection(), "rank": rank}
               for rank, a in enumerate((source, limited), 1)]
    monkeypatch.setattr(recommend, "_search_apps_v2", lambda *args, **kwargs: results)
    normal = recommend.recommend_v2(query="MQTT", locale="en", filters={}, limit=2)
    events = list(recommend.recommend_v2_stream(query="MQTT", locale="en", filters={}, limit=2))
    assert normal["apps"] == events[0]["apps"] == []
    assert [row["app"] for row in normal["candidates"]] == [row["app"] for row in results]
    assert normal["candidates"] == events[0]["candidates"]
    assert normal["message"] == "".join(e["content"] for e in events if e["type"] == "explanation_delta")
    assert normal["explanations"] == events[-1]["explanations"]
    # Unverified candidates are not narrated in the decision; source inspection still is.
    described = recommend._recommendation_narrative("MQTT", normal["candidates"], "en")
    assert "complete quotation omitted" in described and "too large" in described
    assert "supplied no descriptive metadata" not in described


@pytest.mark.parametrize("length", [1200, 1201])
def test_extractively_generated_quotes_stay_complete_with_bounded_name_display(monkeypatch, length):
    import json
    from types import SimpleNamespace

    source = app(name="N" * length, description="MQTT is supported only in simulation.")
    results = [{"app": source.recommendation_projection(), "rank": 1}]
    answer = {"apps": [{"rank": 1, "evidence": [
        {"field": "description", "quote": source.description},
    ]}]}
    monkeypatch.setattr(recommend, "OllamaClient", lambda: SimpleNamespace(
        chat_structured=lambda *args: json.dumps(answer), model="test-only",
    ))
    result = recommend.grounded_store_response("MQTT", results, "en", "detail", "fallback")
    assert result["generation"]["source"] == "ollama"
    assert source.description in result["message"]
    if length == 1200:
        assert f"**{source.name}**" in result["message"]
    else:
        assert "**App 1**" in result["message"]
        assert "N" * 1200 not in result["message"]
    assert results[0]["app"]["app_id"] == source.app_id
    assert results[0]["app"]["id"] == source.id
