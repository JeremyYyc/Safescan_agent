import os
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    database_url: SecretStr
    jwt_secret: SecretStr
    jwt_issuer: str = "safescan-identity"
    jwt_audience: str = "inspection-report-service"
    identity_base_url: str = "http://identity-access-service:8001"
    identity_client_id: str = "inspection-report"
    identity_client_secret: SecretStr = SecretStr("")
    property_leasing_base_url: str = "http://property-leasing-service:8002"
    maintenance_base_url: str = "http://maintenance-service:8003"
    dependency_timeout_seconds: float = Field(default=2.0, gt=0, le=10)
    minio_endpoint: str = "minio:9000"
    minio_access_key: SecretStr
    minio_secret_key: SecretStr
    minio_secure: bool = False
    minio_media_bucket: str = "safescan-media"
    minio_derived_bucket: str = "safescan-derived"
    max_upload_bytes: int = Field(default=8_589_934_592, gt=0)
    upload_chunk_bytes: int = Field(default=8_388_608, ge=65_536)
    pipeline_version: str = "langgraph-v1"
    worker_lease_seconds: int = Field(default=180, ge=30, le=3600)
    worker_poll_seconds: float = Field(default=0.5, gt=0, le=30)
    max_attempts: int = Field(default=3, ge=1, le=10)
    pool_size: int = Field(default=5, ge=1, le=50)
    max_overflow: int = Field(default=5, ge=0, le=100)
    pool_timeout: int = Field(default=10, ge=1, le=60)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=SecretStr(os.getenv("INSPECTION_REPORT_DATABASE_URL") or os.getenv("DATABASE_URL") or ""),
            jwt_secret=SecretStr(os.getenv("INSPECTION_REPORT_JWT_SECRET") or os.getenv("AUTH_SECRET") or ""),
            jwt_issuer=os.getenv("AUTH_ISSUER", "safescan-identity"),
            jwt_audience=os.getenv("INSPECTION_REPORT_AUDIENCE", "inspection-report-service"),
            identity_base_url=os.getenv("IDENTITY_BASE_URL", "http://identity-access-service:8001"),
            identity_client_secret=SecretStr(os.getenv("IDENTITY_CLIENT_SECRET", "")),
            property_leasing_base_url=os.getenv("PROPERTY_LEASING_INTERNAL_URL", "http://property-leasing-service:8002"),
            maintenance_base_url=os.getenv("MAINTENANCE_INTERNAL_URL", "http://maintenance-service:8003"),
            dependency_timeout_seconds=float(os.getenv("REPORT_DEPENDENCY_TIMEOUT_SECONDS", "2")),
            minio_endpoint=os.getenv("MINIO_ENDPOINT", "minio:9000"),
            minio_access_key=SecretStr(os.getenv("MINIO_ACCESS_KEY", "")),
            minio_secret_key=SecretStr(os.getenv("MINIO_SECRET_KEY", "")),
            minio_secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
            minio_media_bucket=os.getenv("MINIO_MEDIA_BUCKET", "safescan-media"),
            minio_derived_bucket=os.getenv("MINIO_DERIVED_BUCKET", "safescan-derived"),
            max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", "8589934592")),
            upload_chunk_bytes=int(os.getenv("VIDEO_IO_CHUNK_BYTES", "8388608")),
            pipeline_version=os.getenv("REPORT_PIPELINE_VERSION", "langgraph-v1"),
            worker_lease_seconds=int(os.getenv("REPORT_JOB_LEASE_SECONDS", "180")),
            worker_poll_seconds=float(os.getenv("REPORT_JOB_POLL_SECONDS", "0.5")),
            max_attempts=int(os.getenv("REPORT_JOB_MAX_ATTEMPTS", "3")),
            pool_size=int(os.getenv("POSTGRES_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("POSTGRES_MAX_OVERFLOW", "5")),
            pool_timeout=int(os.getenv("POSTGRES_POOL_TIMEOUT", "10")),
        )

    def validate_runtime(self) -> None:
        if not self.database_url.get_secret_value():
            raise RuntimeError("Missing INSPECTION_REPORT_DATABASE_URL or DATABASE_URL")
        if len(self.jwt_secret.get_secret_value()) < 24:
            raise RuntimeError("INSPECTION_REPORT_JWT_SECRET or AUTH_SECRET must be at least 24 chars")
        if not self.minio_access_key.get_secret_value() or not self.minio_secret_key.get_secret_value():
            raise RuntimeError("Missing private MinIO credentials")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings.from_env()
    settings.validate_runtime()
    return settings
