from collections.abc import Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse


ReadinessCheck = Callable[[], None]


def create_health_router(service_name: str, readiness_check: ReadinessCheck) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/health/live")
    def live():
        return {"status": "ok", "service": service_name}

    @router.get("/health/ready")
    def ready():
        try:
            readiness_check()
            return {"status": "ready"}
        except Exception:
            return JSONResponse(status_code=503, content={"status": "not_ready"})

    return router
