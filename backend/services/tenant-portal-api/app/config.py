import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    service_name: str = "tenant-portal-api"
    issuer: str = os.getenv("AUTH_ISSUER", "safescan-identity")
    audience: str = os.getenv(
        "TENANT_PORTAL_AUDIENCE", os.getenv("AUTH_AUDIENCE", "safescan-api")
    )
    jwt_secret: str = os.getenv("AUTH_SECRET", "development-only-secret-change-me")
    service_token: str = os.getenv("PORTAL_SERVICE_TOKEN", "")
    identity_url: str = os.getenv(
        "IDENTITY_SERVICE_URL", "http://identity-access-service:8001"
    )
    leasing_url: str = os.getenv(
        "PROPERTY_LEASING_SERVICE_URL", "http://property-leasing-service:8002"
    )
    maintenance_url: str = os.getenv(
        "MAINTENANCE_SERVICE_URL", "http://maintenance-service:8003"
    )
    report_url: str = os.getenv(
        "INSPECTION_REPORT_SERVICE_URL", "http://inspection-report-service:8004"
    )
    redis_url: str = os.getenv("REDIS_URL", "")
    connect_timeout: float = float(os.getenv("PORTAL_CONNECT_TIMEOUT_SECONDS", "0.3"))
    request_timeout: float = float(os.getenv("PORTAL_REQUEST_TIMEOUT_SECONDS", "1.2"))
    pool_connections: int = int(os.getenv("PORTAL_POOL_CONNECTIONS", "50"))
    pool_keepalive: int = int(os.getenv("PORTAL_POOL_KEEPALIVE", "20"))


settings = Settings()
