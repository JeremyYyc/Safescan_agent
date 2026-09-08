from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


@dataclass(frozen=True)
class DatabaseConfig:
    url: str
    pool_size: int = 5
    max_overflow: int = 5
    pool_timeout: int = 10
    pool_pre_ping: bool = True


def create_engine_from_config(config: DatabaseConfig, **overrides) -> Engine:
    options = {
        "pool_pre_ping": config.pool_pre_ping,
        "pool_size": config.pool_size,
        "max_overflow": config.max_overflow,
        "pool_timeout": config.pool_timeout,
        **overrides,
    }
    return create_engine(config.url, **options)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def session_dependency(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = factory()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
