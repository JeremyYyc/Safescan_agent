from app.settings import get_settings

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.report import router as report_router
from app.api.chat import router as chat_router
from app.api.history import router as history_router
from app.api.auth import router as auth_router
from app.api.guide import router as guide_router
from app.auth import require_user
from app.api.report import OUTPUT_DIR


def create_app() -> FastAPI:
    app = FastAPI(title="Home Safety Agent", version="1.0.0")

    settings = get_settings()
    allow_origins = [v.strip() for v in settings.CORS_ORIGINS.split(",") if v.strip()]
    allow_origin_regex = settings.CORS_ORIGIN_REGEX or None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_origin_regex=allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(report_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(history_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(guide_router, prefix="/api")
    app.mount("/uploads", StaticFiles(directory=str(OUTPUT_DIR)), name="uploads")

    return app


app = create_app()


@app.get("/health")
def health() -> dict:
    # Public liveness endpoint for deployment/network checks.
    return {"status": "ok"}


@app.get("/health/auth")
def health_auth(current_user: dict = Depends(require_user)) -> dict:
    return {"status": "ok", "user_id": current_user.get("user_id")}
