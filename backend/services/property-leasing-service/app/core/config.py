import os
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    app_env: str = "development"
    database_url: SecretStr
    jwt_secret: SecretStr
    jwt_issuer: str = "safescan-identity"
    jwt_audience: str = "property-leasing-service"
    identity_base_url: str = "http://identity-access-service:8001"
    identity_service_token: SecretStr = SecretStr("")
    identity_timeout_seconds: float = Field(default=2.0, gt=0, le=10)
    pool_size: int = Field(default=5, ge=1, le=50)
    max_overflow: int = Field(default=10, ge=0, le=100)
    pool_timeout: int = Field(default=10, ge=1, le=60)
    idempotency_ttl_hours: int = Field(default=72, ge=1, le=720)
    default_page_size: int = Field(default=20, ge=1, le=100)
    max_page_size: int = Field(default=100, ge=1, le=200)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            database_url=SecretStr(os.getenv("PROPERTY_LEASING_DATABASE_URL")
                                   or os.getenv("DATABASE_URL") or ""),
            jwt_secret=SecretStr(os.getenv("PROPERTY_LEASING_JWT_SECRET")
                                 or os.getenv("AUTH_SECRET") or ""),
            jwt_issuer=os.getenv("AUTH_ISSUER", "safescan-identity"),
            jwt_audience=os.getenv("PROPERTY_LEASING_AUDIENCE", "property-leasing-service"),
            identity_base_url=os.getenv("IDENTITY_BASE_URL", "http://identity-access-service:8001"),
            identity_service_token=SecretStr(os.getenv("IDENTITY_SERVICE_TOKEN", "")),
            identity_timeout_seconds=float(os.getenv("IDENTITY_TIMEOUT_SECONDS", "2")),
            pool_size=int(os.getenv("POSTGRES_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("POSTGRES_MAX_OVERFLOW", "10")),
            pool_timeout=int(os.getenv("POSTGRES_POOL_TIMEOUT", "10")),
            idempotency_ttl_hours=int(os.getenv("IDEMPOTENCY_TTL_HOURS", "72")),
        )

    def validate_runtime(self) -> None:
        if not self.database_url.get_secret_value():
            raise RuntimeError("Missing PROPERTY_LEASING_DATABASE_URL or DATABASE_URL")
        if len(self.jwt_secret.get_secret_value()) < 24:
            raise RuntimeError("PROPERTY_LEASING_JWT_SECRET or AUTH_SECRET must be at least 24 chars")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings.from_env()
    settings.validate_runtime()
    return settings
