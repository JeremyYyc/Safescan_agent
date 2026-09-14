import os
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)
    database_url: SecretStr
    jwt_secret: SecretStr
    jwt_issuer: str = "safescan-identity"
    jwt_audience: str = "maintenance-service"
    identity_base_url: str = "http://identity-access-service:8001"
    property_base_url: str = "http://property-leasing-service:8002"
    identity_service_token: SecretStr = SecretStr("")
    dependency_timeout_seconds: float = Field(default=2.0, gt=0, le=10)
    pool_size: int = Field(default=5, ge=1, le=50)
    max_overflow: int = Field(default=10, ge=0, le=100)
    pool_timeout: int = Field(default=10, ge=1, le=60)
    idempotency_ttl_hours: int = Field(default=72, ge=1, le=720)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=SecretStr(
                os.getenv("MAINTENANCE_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
            ),
            jwt_secret=SecretStr(
                os.getenv("MAINTENANCE_JWT_SECRET") or os.getenv("AUTH_SECRET") or ""
            ),
            jwt_issuer=os.getenv("AUTH_ISSUER", "safescan-identity"),
            jwt_audience=os.getenv("MAINTENANCE_AUDIENCE", "maintenance-service"),
            identity_base_url=os.getenv(
                "IDENTITY_BASE_URL", "http://identity-access-service:8001"
            ),
            property_base_url=os.getenv(
                "PROPERTY_LEASING_INTERNAL_URL", "http://property-leasing-service:8002"
            ),
            identity_service_token=SecretStr(
                os.getenv("MAINTENANCE_IDENTITY_SERVICE_TOKEN", "")
            ),
            dependency_timeout_seconds=float(
                os.getenv("MAINTENANCE_DEPENDENCY_TIMEOUT_SECONDS", "2")
            ),
            pool_size=int(os.getenv("POSTGRES_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("POSTGRES_MAX_OVERFLOW", "10")),
            pool_timeout=int(os.getenv("POSTGRES_POOL_TIMEOUT", "10")),
            idempotency_ttl_hours=int(os.getenv("IDEMPOTENCY_TTL_HOURS", "72")),
        )

    def validate_runtime(self) -> None:
        if not self.database_url.get_secret_value():
            raise RuntimeError("Missing MAINTENANCE_DATABASE_URL or DATABASE_URL")
        if len(self.jwt_secret.get_secret_value()) < 24:
            raise RuntimeError(
                "MAINTENANCE_JWT_SECRET or AUTH_SECRET must be at least 24 chars"
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings.from_env()
    settings.validate_runtime()
    return settings
