from contextlib import asynccontextmanager
import logging
from starlette.concurrency import run_in_threadpool
from app.storage import initialize_buckets

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from app.api.assets import router as assets_router

from app.api.report import router as report_router
from app.api.chat import router as chat_router
from app.api.history import router as history_router
from app.api.auth import router as auth_router
from app.api.guide import router as guide_router
from app.auth import require_user
from app.settings import get_settings
from app.localization import localize_api_message



@asynccontextmanager
async def lifespan(app):
    await run_in_threadpool(initialize_buckets)
    yield


def create_app() -> FastAPI:
    logging.basicConfig(level=getattr(logging, get_settings().APP_LOG_LEVEL.upper(), logging.INFO))
    app = FastAPI(title="Home Safety Agent", version="1.0.0", lifespan=lifespan)

    @app.exception_handler(HTTPException)
    async def localized_http_exception(_request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": localize_api_message(exc.detail)},
            headers=exc.headers,
        )

    app.include_router(report_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(history_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(guide_router, prefix="/api")
    app.include_router(assets_router, prefix="/api")

    return app


app = create_app()


@app.get("/health")
def health() -> dict:
    # Public liveness endpoint for deployment/network checks.
    return {"status": "ok"}


@app.get("/health/auth")
def health_auth(current_user: dict = Depends(require_user)) -> dict:
    return {"status": "ok", "user_id": current_user.get("user_id")}
