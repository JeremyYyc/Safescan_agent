import os
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    app_env: str = "development"
    default_locale: str = "zh-CN"
    database_url: SecretStr
    jwt_secret: SecretStr
    jwt_issuer: str = "safescan-identity"
    jwt_audience: str = "safescan-api"
    internal_audience: str = "safescan-identity-internal"
    access_token_seconds: int = Field(default=900, ge=60, le=3600)
    refresh_token_seconds: int = Field(default=2_592_000, ge=3600)
    session_idle_seconds: int = Field(default=604_800, ge=900)
    action_token_seconds: int = Field(default=3600, ge=300, le=86_400)
    pool_size: int = Field(default=5, ge=1, le=50)
    max_overflow: int = Field(default=5, ge=0, le=100)
    pool_timeout: int = Field(default=10, ge=1, le=60)
    cookie_name: str = "safescan_refresh"
    csrf_cookie_name: str = "safescan_csrf"
    cookie_domain: str | None = None
    expose_action_tokens: bool = False
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: SecretStr = SecretStr("")
    bootstrap_admin_name: str = "SafeScan Administrator"
    bootstrap_admin_staff_code: str = "ADMIN001"

    @classmethod
    def from_env(cls) -> "Settings":
        database_url = os.getenv("IDENTITY_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
        jwt_secret = os.getenv("IDENTITY_JWT_SECRET") or os.getenv("AUTH_SECRET") or ""
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            default_locale=os.getenv("DEFAULT_LOCALE", "zh-CN"),
            database_url=SecretStr(database_url),
            jwt_secret=SecretStr(jwt_secret),
            jwt_issuer=os.getenv("AUTH_ISSUER", "safescan-identity"),
            jwt_audience=os.getenv("AUTH_AUDIENCE", "safescan-api"),
            internal_audience=os.getenv("IDENTITY_INTERNAL_AUDIENCE", "safescan-identity-internal"),
            access_token_seconds=int(os.getenv("IDENTITY_ACCESS_TOKEN_SECONDS", "900")),
            refresh_token_seconds=int(os.getenv("IDENTITY_REFRESH_TOKEN_SECONDS", "2592000")),
            session_idle_seconds=int(os.getenv("IDENTITY_SESSION_IDLE_SECONDS", "604800")),
            action_token_seconds=int(os.getenv("IDENTITY_ACTION_TOKEN_SECONDS", "3600")),
            pool_size=int(os.getenv("POSTGRES_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("POSTGRES_MAX_OVERFLOW", "5")),
            pool_timeout=int(os.getenv("POSTGRES_POOL_TIMEOUT", "10")),
            cookie_name=os.getenv("IDENTITY_REFRESH_COOKIE", "safescan_refresh"),
            csrf_cookie_name=os.getenv("IDENTITY_CSRF_COOKIE", "safescan_csrf"),
            cookie_domain=os.getenv("IDENTITY_COOKIE_DOMAIN") or None,
            expose_action_tokens=os.getenv("IDENTITY_EXPOSE_ACTION_TOKENS", "false").lower() == "true",
            bootstrap_admin_email=os.getenv("IDENTITY_BOOTSTRAP_ADMIN_EMAIL") or None,
            bootstrap_admin_password=SecretStr(os.getenv("IDENTITY_BOOTSTRAP_ADMIN_PASSWORD", "")),
            bootstrap_admin_name=os.getenv("IDENTITY_BOOTSTRAP_ADMIN_NAME", "SafeScan Administrator"),
            bootstrap_admin_staff_code=os.getenv("IDENTITY_BOOTSTRAP_ADMIN_STAFF_CODE", "ADMIN001"),
        )

    def validate_runtime(self) -> None:
        if not self.database_url.get_secret_value().strip():
            raise RuntimeError("Missing IDENTITY_DATABASE_URL or DATABASE_URL")
        if len(self.jwt_secret.get_secret_value()) < 24:
            raise RuntimeError("IDENTITY_JWT_SECRET or AUTH_SECRET must contain at least 24 characters")
        if self.app_env == "production" and self.expose_action_tokens:
            raise RuntimeError("IDENTITY_EXPOSE_ACTION_TOKENS cannot be enabled in production")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings.from_env()
    settings.validate_runtime()
    return settings
