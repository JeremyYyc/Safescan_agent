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
    APP_LOG_LEVEL: str = 'INFO'
    DATABASE_URL: SecretStr = SecretStr('')
    AUTH_SECRET: SecretStr = SecretStr('')
    PUBLIC_ID_SECRET: SecretStr = SecretStr('')
    AUTH_EXPIRE_HOURS: int = Field(default=8, gt=0)
    DASHSCOPE_API_KEY: SecretStr = SecretStr('')
    QWEN_BASE_URL: str = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    ALIBABA_MODEL_L1: str = 'qwen-turbo-latest'
    ALIBABA_MODEL_L2: str = 'qwen-plus-latest'
    ALIBABA_MODEL_L3: str = 'qwen-max-latest'
    ALIBABA_MODEL_VL: str = 'qwen3-vl-plus'
    AGENT_MAX_CONCURRENCY: int = Field(default=5, gt=0)
    OUTPUT_DIR: str = 'uploads'  # Removed when MinIO replaces filesystem I/O.
    CORS_ORIGINS: str = 'http://localhost:5173,http://127.0.0.1:5173'
    CORS_ORIGIN_REGEX: str = ''
    UUID7_FORCE_FALLBACK: bool = False
    VITE_API_BASE: str = ''
    GATEWAY_PORT: int = Field(default=8080, gt=0, le=65535)
    MYSQL_DATABASE: str = 'safescan_agent'
    MYSQL_ROOT_PASSWORD: SecretStr = SecretStr('')

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

    @property
    def output_path(self) -> Path:
        path = Path(self.OUTPUT_DIR)
        return path if path.is_absolute() else ROOT_DIR / 'backend' / path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_sources()
