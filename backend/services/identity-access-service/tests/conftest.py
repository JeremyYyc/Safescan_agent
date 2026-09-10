import os
import re
from uuid import uuid4

import pytest
import sqlalchemy as sa
from pydantic import SecretStr
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.services.auth_service import AuthService


@pytest.fixture(scope="session")
def postgres_url() -> str:
    value = os.getenv("TEST_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("TEST_DATABASE_URL is required for Identity PostgreSQL tests")
    url = make_url(value)
    if url.get_backend_name() != "postgresql":
        pytest.fail("Identity PostgreSQL tests require a PostgreSQL TEST_DATABASE_URL")
    if not url.database or not re.search(r"(^|[_-])(ci|test)([_-]|$)", url.database.lower()):
        pytest.fail("Identity PostgreSQL tests require a disposable database with a ci or test segment")
    return value


@pytest.fixture(scope="session")
def postgres_engine(postgres_url: str):
    engine = sa.create_engine(
        postgres_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        connect_args={"options": "-c statement_timeout=10000 -c lock_timeout=5000"},
    )
    with engine.connect() as connection:
        revision = connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
    if revision != "20260908_0003":
        pytest.fail(f"Identity PostgreSQL tests require migration 20260908_0003, got {revision!r}")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def identity_settings(postgres_url: str) -> Settings:
    return Settings(
        app_env="ci",
        database_url=SecretStr(postgres_url),
        jwt_secret=SecretStr("identity-postgres-test-secret-value"),
    )


@pytest.fixture(scope="session")
def session_factory(postgres_engine):
    return sessionmaker(bind=postgres_engine, expire_on_commit=False)


@pytest.fixture
def register_customer(session_factory, identity_settings):
    def register(*, email: str | None = None, username: str = "CI Customer") -> dict:
        email = email or f"identity-ci-{uuid4().hex}@example.test"
        with session_factory() as session:
            result = AuthService(session, identity_settings).register(
                email=email,
                username=username,
                password="IdentityTestPassword123",
                guest_session_id=None,
                locale="zh-CN",
                accepted_terms_version="ci-v1",
                device_label="pytest",
                user_agent="identity-postgres-tests",
                ip="127.0.0.1",
                correlation_id=uuid4(),
            )
        return result

    return register
