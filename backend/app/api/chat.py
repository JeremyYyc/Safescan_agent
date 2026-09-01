"""HTTP transport only; business state transitions are in the chat graph."""
from fastapi import APIRouter,Depends,Request,HTTPException
from starlette.concurrency import run_in_threadpool
from app.auth import require_user
from app.workflow.chat_graph import process_chat as run_chat

router=APIRouter()

@router.post('/processChat')
async def process_chat(request:Request,current_user:dict=Depends(require_user)):
    try:
        payload=await request.json()
    except Exception:
        raise HTTPException(400,'Expected a JSON chat request')
    if not isinstance(payload,dict): raise HTTPException(400,'Expected a JSON object')
    return await run_in_threadpool(run_chat,payload,None,current_user)
