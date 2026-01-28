from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.auth import require_user
from app.knowledge.guide import load_guide_sections

router = APIRouter()


@router.get("/guide")
def get_quick_guide(current_user: dict = Depends(require_user)) -> JSONResponse:
    sections = load_guide_sections()
    return JSONResponse({"sections": sections})
