import os
from pathlib import Path
import tempfile
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import Response
from app.auth import require_user
from app import storage
from app.settings import get_settings

router=APIRouter()

async def read_upload(request: Request):
    """Read bounded small objects such as PDFs into memory."""
    maximum=min(get_settings().MAX_UPLOAD_BYTES,get_settings().MAX_VIDEO_MEMORY_BYTES)
    data=bytearray()
    async for chunk in request.stream():
        if len(data)+len(chunk)>maximum:
            raise HTTPException(413,'Upload exceeds configured memory/size limit')
        data.extend(chunk)
    if not data: raise HTTPException(400,'Empty upload')
    return bytes(data)

async def spool_upload(request: Request):
    """Stream a bounded raw request body to disk instead of retaining it in RAM."""
    maximum=get_settings().MAX_UPLOAD_BYTES
    descriptor,path=tempfile.mkstemp(prefix='safescan-upload-')
    total=0
    try:
        with os.fdopen(descriptor,'wb') as output:
            async for chunk in request.stream():
                total+=len(chunk)
                if total>maximum:
                    raise HTTPException(413,'Upload exceeds configured size limit')
                output.write(chunk)
        if not total: raise HTTPException(400,'Empty upload')
        return path
    except BaseException:
        Path(path).unlink(missing_ok=True)
        raise

@router.get('/assets/{asset_id}')
def download_asset(asset_id: str,current_user:dict=Depends(require_user)):
    try:
        row=storage.record(asset_id,current_user['user_id'])
        content=storage.read(asset_id,current_user['user_id'])
    except (ValueError,FileNotFoundError): raise HTTPException(404,'Asset not found')
    return Response(content,media_type=row['mime_type'],headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
