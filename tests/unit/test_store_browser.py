"""Loopback adapter failure and request-boundary checks, with no resource bootstrap."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from fastapi.testclient import TestClient

from scripts.store_v1_browser import create_app


def playground(converse):
    return SimpleNamespace(
        converse=converse, records=[],
        chat=SimpleNamespace(delete_session_v2=lambda session_id: {},
                             submit_recommendation_event=lambda: {}),
    )


def test_local_boundary_rejects_cross_origin_and_rebinding_before_dialogue():
    async def unavailable(request):
        raise AssertionError("Unauthorized boundary must not invoke dialogue")

    with TestClient(create_app(playground(unavailable)), base_url="http://127.0.0.1:8091") as client:
        assert client.post("/api/v2/chat", headers={"Origin": "https://external.invalid"}, json={"message": "x"}).status_code == 403
        assert client.get("/", headers={"Host": "external.invalid"}).status_code == 403
        assert client.get("/.env").status_code == 404
        assert client.get("/tests/fixtures/store-v1/manual-apps.json").status_code == 404
        assert client.post("/api/v2/admin/outbox/replay", json={}).status_code == 404
        assert client.post("/api/v2/chat", json={"message": ""}).status_code == 422


def test_failed_retrieval_stream_emits_problem_and_never_success():
    async def unavailable(request):
        raise ConnectionError("isolated PostgreSQL unavailable")

    with TestClient(create_app(playground(unavailable)), base_url="http://127.0.0.1:8091") as client:
        response = client.post("/api/v2/chat/stream", json={"message": "EdgeConnect"})
        assert '"type":"stage"' in response.text
        assert '"type":"problem"' in response.text
        assert "complete" not in response.text
        assert "recommendations" not in response.text


def test_overlapping_browser_turns_are_serialized():
    active = 0
    peak = 0

    async def converse(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.03)
        active -= 1
        return {"apps": [], "message": "No match", "intent": "search", "impression_id": None, "session_id": "local"}

    with TestClient(create_app(playground(converse)), base_url="http://127.0.0.1:8091") as client:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: client.post("/api/v2/chat/stream", json={"message": "question"}), range(2)))
        assert all("complete" in response.text for response in responses)
        assert peak == 1
