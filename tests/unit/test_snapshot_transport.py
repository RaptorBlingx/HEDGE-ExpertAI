"""Mock pagination must prove completeness before it can authorize absence."""

from __future__ import annotations

import httpx
import pytest
from test_store_v1 import client


def install_pages(monkeypatch, pages):
    responses = iter(pages)

    def get(url, **kwargs):
        data = next(responses)
        if isinstance(data, Exception):
            raise data
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))

    monkeypatch.setattr(client.httpx, "get", get)


def test_complete_mock_pagination(monkeypatch):
    first = [{"id": str(i)} for i in range(50)]
    second = [{"id": "50"}]
    install_pages(monkeypatch, [{"apps": first, "total": 51}, {"apps": second, "total": 51}])
    assert client.MockApiClient("https://mock.invalid").fetch_all_apps() == first + second


@pytest.mark.parametrize(
    "pages",
    [
        [{"apps": [{}]}],  # total missing
        [{"apps": [{}], "total": True}],
        [{"apps": [{}], "total": -1}],
        [{"apps": None, "total": 1}],
        [[{}]],
        [{"apps": [{}], "total": 2}],  # short page before declared end
        [{"apps": [{}, {}], "total": 1}],
        [{"apps": [{}] * 50, "total": 51}, {"apps": [], "total": 51}],
        [{"apps": [{}] * 50, "total": 51}, {"apps": [{}], "total": 52}],
    ],
)
def test_malformed_truncated_or_changing_pages_fail(monkeypatch, pages):
    install_pages(monkeypatch, pages)
    with pytest.raises(ValueError):
        client.MockApiClient("https://mock.invalid").fetch_all_apps()


def test_later_page_failure_never_returns_a_partial_list(monkeypatch):
    install_pages(
        monkeypatch,
        [
            {"apps": [{}] * 50, "total": 51},
            httpx.ReadTimeout("later page timed out"),
        ],
    )
    with pytest.raises(httpx.ReadTimeout):
        client.MockApiClient("https://mock.invalid").fetch_all_apps()
