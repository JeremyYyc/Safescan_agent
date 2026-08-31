"""Explicit local capabilities exposed through the standard function-call protocol."""
from dataclasses import dataclass, field
from contextvars import ContextVar
from contextlib import contextmanager
from typing import Any, Callable
import asyncio
import json
import logging
import traceback
from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class ToolContext:
    user_id: int | None = None
    chat_id: int | None = None
    # Server-selected resources. Never serialized into the model argument schema.
    allowed_assets: frozenset[str] = field(default_factory=frozenset)
    model: Any = None

class Arguments(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)

_runtime=ContextVar('tool_runtime',default=ToolContext())

def current_tool_context(): return _runtime.get()

@contextmanager
def tool_context(context):
    token=_runtime.set(context)
    try: yield
    finally: _runtime.reset(token)

class GuideArgs(Arguments):
    query: str = Field(min_length=1,max_length=2000)
    top_k: int = Field(default=2,ge=1,le=5)

class ValidateArgs(Arguments):
    report: dict[str,Any]

class ReportArgs(Arguments):
    report_id: str = Field(min_length=1,max_length=100)

class VideoArgs(Arguments):
    asset_id: str = Field(min_length=1,max_length=100)

class FramesArgs(Arguments):
    asset_ids: list[str] = Field(max_length=600)

@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    arguments: type[Arguments]
    function: Callable
    timeout: float = 30
    read_only: bool = True

    def schema(self):
        return {'type':'function','function':{'name':self.name,'description':self.description,'parameters':self.arguments.model_json_schema()}}

def _guide(args,ctx):
    from app.knowledge.guide import search_guide
    return [{'section':section,'score':score} for section,score in search_guide(args.query,args.top_k)]

def _validate(args,ctx):
    from app.tools.validation_tools import validate_report
    return validate_report(args.report)

def _report(args,ctx):
    from app import db
    if ctx.user_id is None or ctx.chat_id is None: raise PermissionError()
    chat=db.get_chat(ctx.chat_id)
    if not chat or chat['user_id']!=ctx.user_id: raise PermissionError()
    report=db.get_report_by_public_id(args.report_id)
    if not report or report['user_id']!=ctx.user_id: raise PermissionError()
    if report.get('origin_chat_id')!=ctx.chat_id:
        allowed={r['report_id'] for r in db.list_chat_report_refs(ctx.chat_id) if r['status']=='active'}
        if report['id'] not in allowed: raise PermissionError()
    return report['report_json']

def _check_assets(refs,ctx):
    from app.storage import asset_uuid,record
    allowed={asset_uuid(r) for r in ctx.allowed_assets}
    for ref in refs:
        if asset_uuid(ref) not in allowed: raise PermissionError()
        record(ref,ctx.user_id)

def _extract(args,ctx):
    from app.tools.video_tools import extract_frames
    _check_assets([args.asset_id],ctx)
    return extract_frames(args.asset_id)

def _filter(args,ctx):
    from app.tools.video_tools import filter_frames_with_stats
    _check_assets(args.asset_ids,ctx)
    frames,stats=filter_frames_with_stats(args.asset_ids)
    return {'asset_ids':frames,'stats':stats}

def _select(args,ctx):
    from app.tools.video_tools import select_representative_images_by_room
    _check_assets(args.asset_ids,ctx)
    if ctx.model is None: raise RuntimeError('YOLO model not bound')
    return select_representative_images_by_room(args.asset_ids,ctx.model,max_frames=15,max_per_room=3)

def _detect(args,ctx):
    from app.tools.video_tools import yolo_detect_and_draw
    _check_assets(args.asset_ids,ctx)
    if ctx.model is None: raise RuntimeError('YOLO model not bound')
    frames,summaries=yolo_detect_and_draw(args.asset_ids,ctx.model)
    return {'asset_ids':frames,'summaries':summaries}

TOOLS={t.name:t for t in (
    ToolSpec('search_guide','Search the existing Safe-Scan usage guide.',GuideArgs,_guide),
    ToolSpec('validate_report','Validate the existing report schema; return errors and repair hints.',ValidateArgs,_validate),
    ToolSpec('read_report','Read one owned report available in the current conversation.',ReportArgs,_report),
    ToolSpec('extract_video_frames','Extract 1 fps frames from an authorized video asset.',VideoArgs,_extract,120,False),
    ToolSpec('filter_video_frames','Apply the unchanged duplicate, blur, darkness and face filters.',FramesArgs,_filter,120,False),
    ToolSpec('select_representative_images','Select existing room-representative frames using the unchanged scoring policy.',FramesArgs,_select,120),
    ToolSpec('detect_objects','Run the current YOLO model and annotate authorized images.',FramesArgs,_detect,120,False),
)}

async def execute_tool(name,arguments,context,allowed):
    if name not in allowed or name not in TOOLS:
        return {'ok':False,'error':{'code':'tool_not_allowed'}}
    spec=TOOLS[name]
    try:
        args=spec.arguments.model_validate_json(arguments) if isinstance(arguments,str) else spec.arguments.model_validate(arguments)
    except (ValidationError,ValueError):
        return {'ok':False,'error':{'code':'invalid_arguments'}}
    try:
        # The timeout applies to read-only tools. Mutating media work is awaited to
        # completion: cancelling a thread cannot stop its writes safely.
        def invoke():
            from app.storage import owner_scope
            with owner_scope(context.user_id):
                return spec.function(args,context)
        task=asyncio.to_thread(invoke)
        result=await asyncio.wait_for(task,spec.timeout) if spec.read_only else await task
        return {'ok':True,'result':result}
    except asyncio.TimeoutError:
        return {'ok':False,'error':{'code':'tool_timeout'}}
    except (PermissionError,FileNotFoundError):
        return {'ok':False,'error':{'code':'resource_not_available'}}
    except Exception as exc:
        # Keep the failure location/type server-side without logging arguments,
        # exception messages or locals, which can contain credentials or user data.
        logger.error("Tool %s failed (%s)\n%s", name, type(exc).__name__,
                     ''.join(traceback.format_tb(exc.__traceback__)))
        return {'ok':False,'error':{'code':'tool_failed'}}
