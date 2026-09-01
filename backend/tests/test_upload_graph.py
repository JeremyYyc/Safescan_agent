import asyncio
import pytest
from fastapi import HTTPException
from starlette.requests import Request
from app.settings import Settings
from app.workflow import upload_graph
from app.api import assets


def request(body, mime='video/mp4'):
    async def receive():
        return {'type': 'http.request', 'body': body, 'more_body': False}
    return Request({'type': 'http', 'method': 'POST', 'path': '/',
                    'headers': [(b'content-type', mime.encode())]}, receive)


def test_ingress_nodes_clear_payload(monkeypatch):
    monkeypatch.setattr(upload_graph.storage, 'put', lambda *a, **k: '/api/assets/fixture')
    graph = upload_graph.build_upload_graph(request(b'video'))
    result = asyncio.run(graph.ainvoke({'user_id': 1}))
    assert result['asset_id'] == '/api/assets/fixture'
    assert result['data'] == b''
    assert set(graph.nodes) == {'__start__', 'receive', 'persist'}


def test_capacity_and_errors_release_slot(monkeypatch):
    monkeypatch.setattr(upload_graph, 'get_settings', lambda: Settings(UPLOAD_MAX_CONCURRENCY=1))
    with upload_graph.upload_slot():
        with pytest.raises(HTTPException) as error:
            asyncio.run(upload_graph.upload_video(request(b'x'), 1))
        assert error.value.status_code == 429
    with pytest.raises(HTTPException) as error:
        asyncio.run(upload_graph.upload_video(request(b'x', 'text/plain'), 1))
    assert error.value.status_code == 400
    assert upload_graph._active == 0
    monkeypatch.setattr(assets, 'get_settings', lambda: Settings(MAX_UPLOAD_BYTES=2))
    with pytest.raises(HTTPException) as error:
        asyncio.run(upload_graph.upload_video(request(b'oversize'), 1))
    assert error.value.status_code == 413
    assert upload_graph._active == 0
