import sqlalchemy as sa
from fastapi import FastAPI
from safescan_common.http.health import create_health_router
from safescan_common.http.middleware import install_http_infrastructure

from app.controllers import admin_controller, auth_controller, internal_controller, profile_controller
from app.controllers.common import install_identity_error_contract
from app.core.database import get_engine


app = FastAPI(title="SafeScan Identity Access Service", version="1.0.0")
install_http_infrastructure(app)
install_identity_error_contract(app)
app.include_router(auth_controller.router)
app.include_router(profile_controller.router)
app.include_router(admin_controller.router)
app.include_router(internal_controller.router)


def identity_readiness() -> None:
    with get_engine().connect() as connection:
        connection.execute(sa.text("SELECT 1 FROM identity_access.users LIMIT 1"))


app.include_router(create_health_router("identity-access", identity_readiness))
