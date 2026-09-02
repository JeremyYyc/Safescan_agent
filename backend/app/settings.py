"""The only configuration reader. Process environment wins over root .env.

Tests inject values via Settings.from_sources(environ=..., env_file=None).
No dotenv mutation of os.environ; no secrets in repr or validation errors.
"""
import os
from functools import lru_cache
from pathlib import Path
from typing import Mapping
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseModel):
    model_config = ConfigDict(extra='ignore', hide_input_in_errors=True, frozen=True)
    APP_ENV: str = 'development'
    APP_TIMEZONE: str = 'Asia/Shanghai'
    DEFAULT_LOCALE: str = 'zh-CN'
    LLM_OUTPUT_LANGUAGE: str = 'Simplified Chinese'
    APP_LOG_LEVEL: str = 'INFO'
    DATABASE_URL: SecretStr = SecretStr('')
    AUTH_SECRET: SecretStr = SecretStr('')
    PUBLIC_ID_SECRET: SecretStr = SecretStr('')
    AUTH_EXPIRE_HOURS: int = Field(default=8, gt=0)
    DASHSCOPE_API_KEY: SecretStr = SecretStr('')
    QWEN_BASE_URL: str = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    QWEN_CONNECT_TIMEOUT_SECONDS: int = Field(default=10,gt=0)
    QWEN_READ_TIMEOUT_SECONDS: int = Field(default=120,gt=0)
    TOOL_MAX_ROUNDS: int = Field(default=4,ge=1,le=12)
    TOOL_MAX_CALLS: int = Field(default=12,ge=1,le=64)
    TOOL_MAX_OUTPUT_CHARS: int = Field(default=64000,gt=0)
    ALIBABA_MODEL_L1: str = 'qwen-turbo-latest'
    ALIBABA_MODEL_L2: str = 'qwen-plus-latest'
    ALIBABA_MODEL_L3: str = 'qwen-max-latest'
    ALIBABA_MODEL_VL: str = 'qwen3-vl-plus'
    AGENT_MAX_CONCURRENCY: int = Field(default=5, gt=0)
    MINIO_ENDPOINT: str = 'gateway:9000'
    MINIO_ACCESS_KEY: SecretStr = SecretStr('')
    MINIO_SECRET_KEY: SecretStr = SecretStr('')
    MINIO_SECURE: bool = False
    MINIO_REGION: str = 'us-east-1'
    MINIO_MEDIA_BUCKET: str = 'safescan-media'
    MINIO_DERIVED_BUCKET: str = 'safescan-derived'
    MINIO_REPORTS_BUCKET: str = 'safescan-reports'
    MINIO_POOL_MAXSIZE: int = Field(default=32, gt=0, le=256)
    MAX_UPLOAD_BYTES: int = Field(default=8589934592, gt=0)
    UPLOAD_MAX_CONCURRENCY: int = Field(default=1, gt=0, le=20)
    MAX_VIDEO_MEMORY_BYTES: int = Field(default=536870912, gt=0)
    MAX_VIDEO_SECONDS: int = Field(default=6000, gt=0)
    MAX_VIDEO_PIXELS: int = Field(default=8294400, gt=0)
    MAX_EXTRACTED_FRAMES: int = Field(default=1200, gt=0, le=10000)
    VIDEO_FRAME_SAMPLE_RATE: float = Field(default=1.0, gt=0, le=10)
    VIDEO_TOOL_TIMEOUT_SECONDS: int = Field(default=3600, gt=0)
    VIDEO_MAX_REPRESENTATIVE_FRAMES: int = Field(default=30, gt=0)
    VIDEO_MAX_FRAMES_PER_ROOM: int = Field(default=5, gt=0)
    VIDEO_IO_CHUNK_BYTES: int = Field(default=8388608, gt=0)
    VIDEO_WORKER_CONCURRENCY: int = Field(default=1, gt=0, le=20)
    REPORT_JOB_POLL_SECONDS: float = Field(default=1.0, gt=0, le=60)
    REPORT_JOB_LEASE_SECONDS: int = Field(default=7200, gt=60, le=86400)
    UUID7_FORCE_FALLBACK: bool = False
    GATEWAY_PORT: int = Field(default=8080, gt=0, le=65535)
    GATEWAY_S3_PORT: int = Field(default=9000, gt=0, le=65535)
    GATEWAY_CONSOLE_PORT: int = Field(default=9001, gt=0, le=65535)
    MINIO_BROWSER_REDIRECT_URL: str = 'http://localhost:9001'
    NGINX_BACKEND_UPSTREAM: str = 'backend:8000'
    NGINX_FRONTEND_UPSTREAM: str = 'frontend:80'
    NGINX_MINIO_S3_UPSTREAM: str = 'minio:9000'
    NGINX_MINIO_CONSOLE_UPSTREAM: str = 'minio:9001'
    POSTGRES_DB: str = 'safescan'
    POSTGRES_USER: str = 'safescan'
    POSTGRES_PASSWORD: SecretStr = SecretStr('')
    POSTGRES_HOST_PORT: int = Field(default=5432, gt=0, le=65535)
    POSTGRES_POOL_SIZE: int = Field(default=5, gt=0)
    POSTGRES_MAX_OVERFLOW: int = Field(default=5, ge=0)
    POSTGRES_POOL_TIMEOUT: int = Field(default=10, gt=0)
    POSTGRES_TIMEZONE: str = 'Asia/Shanghai'
    VITE_ENABLE_LANGUAGE_SWITCH: bool = True

    @classmethod
    def from_sources(cls, *, environ: Mapping[str, str] | None = None,
                     env_file: Path | None = ROOT_DIR / '.env', **overrides):
        values = dict(dotenv_values(env_file)) if env_file and env_file.exists() else {}
        values.update(os.environ if environ is None else environ)
        values.update(overrides)
        return cls.model_validate(values)

    def require_secret(self, name: str) -> str:
        value = getattr(self, name).get_secret_value()
        if not value.strip():
            raise RuntimeError(f'Missing required configuration: {name}')
        return value

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_sources()
