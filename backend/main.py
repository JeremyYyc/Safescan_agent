import os

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

    allow_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    extra_origins = os.getenv("CORS_ORIGINS", "")
    if extra_origins:
        allow_origins.extend(
            [origin.strip() for origin in extra_origins.split(",") if origin.strip()]
        )
    allow_origin_regex = os.getenv(
        "CORS_ORIGIN_REGEX",
        r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$",
    )

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
def health(current_user: dict = Depends(require_user)) -> dict:
    return {"status": "ok"}
