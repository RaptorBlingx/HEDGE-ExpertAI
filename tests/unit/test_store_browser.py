"""Loopback adapter failure and request-boundary checks, with no resource bootstrap."""

from __future__ import annotations

import asyncio
import json
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
        normal = client.post("/api/v2/chat", json={"message": "EdgeConnect"})
        assert normal.status_code == 503
        assert normal.json() == {"detail": "Offline retrieval unavailable"}
        assert client.post("/evaluation/scenario/update").status_code == 404
        output = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert any(e["type"] == "stage" for e in output)
        assert output[-1]["type"] == "problem"
        assert not any(e["type"] in {"complete", "recommendations"} for e in output)


def test_overlapping_browser_turns_in_one_session_are_serialized():
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
            responses = list(pool.map(lambda _: client.post("/api/v2/chat/stream", json={"message": "question", "session_id": "same"}), range(2)))
        assert all("complete" in response.text for response in responses)
        assert peak == 1


def test_private_snapshot_status_labels_source_and_blocks_private_input_download():
    async def unused(request):
        return {}

    evaluation = playground(unused)
    evaluation.source = "authorized-api-snapshot"
    evaluation.records = [{"app_id": "published", "active": True, "visible": True}]
    with TestClient(create_app(evaluation), base_url="http://127.0.0.1:8091") as client:
        status = client.get("/api/v2/status").json()
        assert status["source"] == "authorized-api-snapshot"
        assert status["snapshot_complete"] is False
        assert "potentially incomplete" in status["catalogue"]
        assert "no model calls" in status["generation"]
        assert status["records"] == evaluation.records
        assert client.get("/input/apps.json").status_code == 404


def test_offline_stream_preserves_abstention_and_unverified_candidates():
    import json

    response = {"apps": [], "candidates": [{"app": {"id": "water"}, "rank": 1}],
                "message": "I cannot recommend an App from these fields.", "intent": "search",
                "impression_id": None, "session_id": "local",
                "decision": {"outcome": "abstained", "reason": "insufficient_evidence"}}

    async def converse(request):
        return response

    with TestClient(create_app(playground(converse)), base_url="http://127.0.0.1:8091") as client:
        normal = client.post("/api/v2/chat", json={"message": "earthquake warnings"}).json()
        stream = client.post("/api/v2/chat/stream", json={"message": "earthquake warnings"})
        records = [json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith("data: ")]
        result = next(r for r in records if r["type"] == "recommendations")
        assert result["apps"] == normal["apps"] == []
        assert result["candidates"] == normal["candidates"]
        assert result["decision"] == normal["decision"] == records[-1]["decision"]
        assert records[-1]["impression_id"] is None


def test_managed_workspace_without_authorized_observation_is_not_an_empty_catalogue():
    from fastapi import HTTPException

    async def unavailable(request):
        raise HTTPException(status_code=503, detail="No authorized Store observation available")

    evaluation = playground(unavailable)
    evaluation.sync_status = lambda: {"state": "authorization_required", "snapshot_at": None}

    def catalogue(ids):
        raise HTTPException(status_code=503, detail="No authorized Store observation available")

    evaluation.catalogue = catalogue
    with TestClient(create_app(evaluation), base_url="http://127.0.0.1:8098") as client:
        status = client.get("/api/v2/status")
        assert status.status_code == 200
        assert status.json()["records"] == []
        assert status.json()["synchronization"]["state"] == "authorization_required"
        assert client.get("/api/v2/catalogue").status_code == 503
        assert client.post("/api/v2/chat", json={"message": "List apps"}).status_code == 503
        stream = client.post("/api/v2/chat/stream", json={"message": "List apps"})
        output = [json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith("data: ")]
        assert output[-1]["type"] == "problem"
        assert not any(e["type"] == "complete" for e in output)


def test_legacy_session_restores_source_number_without_reassigning_identity():
    async def unused(request):
        return {}
    evaluation = playground(unused)
    first, second = {'id': 'first'}, {'id': 'second'}
    evaluation.chat.get_session = lambda session_id: {'messages': [], 'context': {
        'last_results': [{'app': first, 'rank': 1}, {'app': second, 'rank': 2}],
        'displayed_ids': ['second'],
    }}
    evaluation.policy = SimpleNamespace(resolve=lambda ids: [second] if ids == ['second'] else [])
    with TestClient(create_app(evaluation), base_url='http://127.0.0.1:8091') as client:
        response = client.get('/api/v2/sessions/legacy')
        assert response.status_code == 200
        assert response.json()['apps'] == [{'app': second, 'rank': 2, 'evidence_fields': ['reference']}]


def test_catalogue_preparation_does_not_lock_out_routine_chat():
    import asyncio
    from threading import Event

    import httpx

    entered, release = Event(), Event()
    async def converse(request):
        return {'message':'source evidence', 'apps':[]}
    evaluation = playground(converse)
    def refresh():
        entered.set()
        if not release.wait(3):
            raise RuntimeError('Test did not release synchronization')
        return {'status':'updated'}
    evaluation.refresh = refresh
    async def probe():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(evaluation)),
                                     base_url='http://127.0.0.1:8091') as client:
            pending = asyncio.create_task(client.post('/evaluation/refresh'))
            try:
                assert await asyncio.to_thread(entered.wait, 1)
                response = await asyncio.wait_for(client.post('/api/v2/chat',json={'message':'list apps'}),1)
                assert response.status_code == 200
            finally:
                release.set()
                await pending
    asyncio.run(probe())


def test_complex_turn_cannot_block_other_sessions_but_same_session_is_serialized():
    import asyncio

    import httpx

    async def probe():
        entered, release, second_entered = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def converse(request):
            if request.message == 'complex':
                entered.set()
                await release.wait()
            elif request.session_id == 'same':
                second_entered.set()
            return {'message':'source evidence','apps':[]}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(playground(converse))),
                                     base_url='http://127.0.0.1:8091') as client:
            pending = asyncio.create_task(client.post('/api/v2/chat',json={'message':'complex','session_id':'same'}))
            await entered.wait()
            queued = asyncio.create_task(client.post('/api/v2/chat',json={'message':'ordinary','session_id':'same'}))
            try:
                response = await asyncio.wait_for(client.post('/api/v2/chat',json={'message':'ordinary','session_id':'other'}),1)
                assert response.status_code == 200 and not second_entered.is_set()
            finally:
                release.set()
                await pending
                await queued
            assert second_entered.is_set()
    asyncio.run(probe())
