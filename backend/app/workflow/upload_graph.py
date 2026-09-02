"""Ingress graph. Only the returned asset reference enters the report graph.

The per-process slot covers both receiving bytes and persisting them. Raw bodies
are bounded and spooled to disk so large videos do not consume equivalent RAM.
"""
from contextlib import contextmanager
from threading import Lock
from pathlib import Path
from typing import TypedDict
from fastapi import HTTPException, Request
from langgraph.graph import StateGraph, START, END
from starlette.concurrency import run_in_threadpool
from app import storage
from app.api.assets import spool_upload
from app.settings import get_settings

_lock = Lock()
_active = 0


@contextmanager
def upload_slot():
    global _active
    with _lock:
        if _active >= get_settings().UPLOAD_MAX_CONCURRENCY:
            raise HTTPException(429, 'Upload capacity reached; retry after this upload finishes')
        _active += 1
    try:
        yield
    finally:
        with _lock:
            _active -= 1


class UploadState(TypedDict, total=False):
    user_id: int
    mime: str
    temp_path: str
    asset_id: str


def build_upload_graph(request: Request):
    async def receive(state):
        mime = request.headers.get('content-type', '').split(';')[0]
        if not mime.startswith('video/'):
            raise HTTPException(400, 'Send raw video bytes with a video Content-Type')
        return {'mime': mime, 'temp_path': await spool_upload(request)}

    async def persist(state):
        try:
            ref = await run_in_threadpool(storage.put_file, state['temp_path'], state['mime'],
                                          user_id=state['user_id'], category='media')
            return {'asset_id': ref, 'temp_path': ''}
        finally:
            Path(state['temp_path']).unlink(missing_ok=True)

    graph = StateGraph(UploadState)
    graph.add_node('receive', receive)
    graph.add_node('persist', persist)
    graph.add_edge(START, 'receive')
    graph.add_edge('receive', 'persist')
    graph.add_edge('persist', END)
    return graph.compile()


async def upload_video(request: Request, user_id: int):
    with upload_slot():
        state = await build_upload_graph(request).ainvoke({'user_id': user_id})
    return {'video_asset_id': state['asset_id']}
