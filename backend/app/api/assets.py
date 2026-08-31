from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import Response
from app.auth import require_user
from app import storage
from app.settings import get_settings

router=APIRouter()

async def read_upload(request: Request):
    """Raw request body: no multipart parser or SpooledTemporaryFile."""
    maximum=min(get_settings().MAX_UPLOAD_BYTES,get_settings().MAX_VIDEO_MEMORY_BYTES)
    data=bytearray()
    async for chunk in request.stream():
        if len(data)+len(chunk)>maximum:
            raise HTTPException(413,'Upload exceeds configured memory/size limit')
        data.extend(chunk)
    if not data: raise HTTPException(400,'Empty upload')
    return bytes(data)

@router.get('/assets/{asset_id}')
def download_asset(asset_id: str,current_user:dict=Depends(require_user)):
    try:
        row=storage.record(asset_id,current_user['user_id'])
        content=storage.read(asset_id,current_user['user_id'])
    except (ValueError,FileNotFoundError): raise HTTPException(404,'Asset not found')
    return Response(content,media_type=row['mime_type'],headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
