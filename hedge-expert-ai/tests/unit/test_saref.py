"""Tests for SAREF ontology class inference."""

import pytest

from hedge_shared.saref import get_saref_class_for_query, infer_saref_class


class TestInferSarefClass:
    """Test infer_saref_class with both str and list[str] inputs."""

    def test_energy_from_string(self):
        assert infer_saref_class("energy monitoring solar") == "Energy"

    def test_energy_from_list(self):
        assert infer_saref_class(["energy", "solar", "power"]) == "Energy"

    def test_building_from_string(self):
        assert infer_saref_class("hvac building temperature") == "Building"

    def test_building_from_list(self):
        assert infer_saref_class(["hvac", "building"]) == "Building"

    def test_environment_from_string(self):
        assert infer_saref_class("air quality pollution") == "Environment"

    def test_water_from_string(self):
        assert infer_saref_class("water leak pipeline") == "Water"

    def test_agriculture_from_string(self):
        assert infer_saref_class("irrigation crop soil") == "Agriculture"

    def test_city_from_string(self):
        assert infer_saref_class("traffic parking urban") == "City"

    def test_health_from_string(self):
        assert infer_saref_class("heart rate patient wearable") == "Health"

    def test_manufacturing_from_string(self):
        assert infer_saref_class("factory assembly vibration") == "Manufacturing"

    def test_no_match(self):
        assert infer_saref_class("random unrelated words") is None

    def test_empty_string(self):
        assert infer_saref_class("") is None

    def test_empty_list(self):
        assert infer_saref_class([]) is None

    def test_single_keyword_string(self):
        assert infer_saref_class("solar") == "Energy"

    def test_case_insensitive(self):
        assert infer_saref_class("ENERGY SOLAR") == "Energy"


class TestGetSarefClassForQuery:
    def test_energy_query(self):
        result = get_saref_class_for_query("I need an app for energy monitoring")
        assert result == "Energy"

    def test_building_query(self):
        result = get_saref_class_for_query("Show me HVAC solutions")
        assert result == "Building"

    def test_no_match_query(self):
        result = get_saref_class_for_query("hello how are you")
        assert result is None
