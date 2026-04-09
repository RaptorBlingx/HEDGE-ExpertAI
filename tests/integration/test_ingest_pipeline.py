"""Integration tests for the metadata ingestion pipeline.

Tests the client adapter pattern and change detection logic.
External services (Redis, Qdrant, Mock API) are mocked.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Load metadata-ingest client module via importlib to avoid `app` namespace clash
_mi_app = Path(__file__).resolve().parent.parent.parent / "services" / "metadata-ingest" / "app"

_spec_client = importlib.util.spec_from_file_location("mi_client", _mi_app / "client.py")
_client_mod = importlib.util.module_from_spec(_spec_client)
sys.modules["mi_client"] = _client_mod
_spec_client.loader.exec_module(_client_mod)

get_client = _client_mod.get_client
MockApiClient = _client_mod.MockApiClient
HedgeApiClient = _client_mod.HedgeApiClient
compute_checksum = _client_mod.compute_checksum

# Also import shared models directly (installed via pip install -e shared/)
from hedge_shared.models import AppMetadata  # noqa: E402


SAMPLE_APPS = [
    {
        "id": "app-001",
        "title": "SmartEnergy Monitor",
        "description": "Monitor energy consumption.",
        "tags": ["energy"],
        "saref_type": "Energy",
        "input_datasets": ["meter_readings"],
        "output_datasets": ["energy_report"],
        "version": "2.1.0",
    },
    {
        "id": "app-002",
        "title": "BuildingComfort Pro",
        "description": "HVAC comfort management.",
        "tags": ["building", "HVAC"],
        "saref_type": "Building",
        "input_datasets": ["temperature"],
        "output_datasets": ["comfort_index"],
        "version": "1.0.0",
    },
]


class TestClientAdapterPattern:
    """Test the App Store client factory and adapters."""

    def test_mock_client_returned_when_no_hedge_url(self):
        client = get_client(mock_url="http://mock:9000")
        assert isinstance(client, MockApiClient)

    def test_hedge_client_returned_when_hedge_url_set(self):
        client = get_client(mock_url="http://mock:9000", hedge_url="https://hedge.example.com")
        assert isinstance(client, HedgeApiClient)

    def test_mock_client_stores_base_url(self):
        client = get_client(mock_url="http://mock:9000")
        assert client.base_url == "http://mock:9000"

    def test_hedge_client_stores_base_url(self):
        client = get_client(mock_url="http://mock:9000", hedge_url="https://api.hedge.eu")
        assert client.base_url == "https://api.hedge.eu"


class TestChangeDetection:
    """Test the checksum-based change detection logic."""

    def test_checksum_deterministic(self):
        """Same input should always produce same checksum."""
        app = AppMetadata(**SAMPLE_APPS[0])
        checksum1 = app.checksum
        checksum2 = app.checksum
        assert checksum1 == checksum2

    def test_checksum_changes_on_update(self):
        """Changed field should change the checksum."""
        app1 = AppMetadata(**SAMPLE_APPS[0])
        modified = {**SAMPLE_APPS[0], "version": "3.0.0"}
        app2 = AppMetadata(**modified)
        assert app1.checksum != app2.checksum

    def test_checksum_stable_across_tag_order(self):
        """Tag order shouldn't affect checksum (tags are sorted)."""
        data_a = {**SAMPLE_APPS[0], "tags": ["energy", "solar"]}
        data_b = {**SAMPLE_APPS[0], "tags": ["solar", "energy"]}
        assert AppMetadata(**data_a).checksum == AppMetadata(**data_b).checksum

    def test_compute_checksum_consistency(self):
        """compute_checksum should return same hash for same dict."""
        h1 = compute_checksum(SAMPLE_APPS[0])
        h2 = compute_checksum(SAMPLE_APPS[0])
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_compute_checksum_differs_on_change(self):
        """Different data should produce different checksums."""
        h1 = compute_checksum(SAMPLE_APPS[0])
        h2 = compute_checksum(SAMPLE_APPS[1])
        assert h1 != h2
