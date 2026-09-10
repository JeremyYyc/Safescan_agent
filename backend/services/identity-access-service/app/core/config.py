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
    seed_staff: bool = False
    deletion_pepper: SecretStr = SecretStr("")
    deletion_pepper_version: int = Field(default=1, ge=1, le=32767)
    deletion_previous_peppers: SecretStr = SecretStr("")
    property_leasing_url: str = "http://property-leasing-service:8002"
    maintenance_url: str = "http://maintenance-service:8003"
    deletion_dependency_timeout_seconds: float = Field(default=1.5, gt=0, le=10)
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
            seed_staff=os.getenv("IDENTITY_SEED_STAFF", "false").lower() == "true",
            deletion_pepper=SecretStr(os.getenv("IDENTITY_DELETION_PEPPER", "")),
            deletion_pepper_version=int(os.getenv("IDENTITY_DELETION_PEPPER_VERSION", "1")),
            deletion_previous_peppers=SecretStr(os.getenv("IDENTITY_DELETION_PREVIOUS_PEPPERS", "")),
            property_leasing_url=os.getenv("PROPERTY_LEASING_INTERNAL_URL", "http://property-leasing-service:8002"),
            maintenance_url=os.getenv("MAINTENANCE_INTERNAL_URL", "http://maintenance-service:8003"),
            deletion_dependency_timeout_seconds=float(
                os.getenv("IDENTITY_DELETION_DEPENDENCY_TIMEOUT_SECONDS", "1.5")
            ),
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
        if self.app_env == "production" and self.seed_staff:
            raise RuntimeError("IDENTITY_SEED_STAFF cannot be enabled in production")
        if self.app_env == "production" and len(self.deletion_pepper.get_secret_value()) < 24:
            raise RuntimeError("IDENTITY_DELETION_PEPPER must contain at least 24 characters in production")
        versions = {self.deletion_pepper_version}
        for item in filter(None, (
            part.strip() for part in self.deletion_previous_peppers.get_secret_value().split(",")
        )):
            try:
                version_text, pepper = item.split(":", 1)
                version = int(version_text)
            except (ValueError, TypeError) as exc:
                raise RuntimeError("IDENTITY_DELETION_PREVIOUS_PEPPERS must use version:pepper entries") from exc
            if version < 1 or version in versions or not pepper:
                raise RuntimeError("Identity deletion pepper versions must be positive and unique")
            if self.app_env == "production" and len(pepper) < 24:
                raise RuntimeError("Historical identity deletion peppers must contain at least 24 characters")
            versions.add(version)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings.from_env()
    settings.validate_runtime()
    return settings
