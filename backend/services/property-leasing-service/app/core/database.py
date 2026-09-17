from functools import lru_cache
from typing import Generator

from sqlalchemy.orm import Session
from safescan_common.database import DatabaseConfig, create_engine_from_config, create_session_factory

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_engine():
    settings = get_settings()
    return create_engine_from_config(DatabaseConfig(
        url=settings.database_url.get_secret_value(),
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout,
    ))


@lru_cache(maxsize=1)
def get_session_factory():
    return create_session_factory(get_engine())


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
