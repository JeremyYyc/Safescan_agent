from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
import sqlalchemy as sa
from safescan_common.http.errors import ApiError

from app.services.auth_service import AuthService


pytestmark = pytest.mark.concurrency


def test_concurrent_registration_allows_exactly_one_email_owner(
    postgres_engine, session_factory, identity_settings
):
    email = f"identity-ci-race-{uuid4().hex}@example.test"
    barrier = Barrier(2)

    def attempt() -> tuple[str, str | None]:
        with session_factory() as session:
            barrier.wait()
            try:
                AuthService(session, identity_settings).register(
                    email=email,
                    username="Concurrent Customer",
                    password="IdentityTestPassword123",
                    guest_session_id=None,
                    locale="zh-CN",
                    accepted_terms_version="ci-v1",
                    device_label="pytest",
                    user_agent="identity-concurrency-tests",
                    ip="127.0.0.1",
                    correlation_id=uuid4(),
                )
                return "created", None
            except ApiError as exc:
                return "rejected", exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: attempt(), range(2)))

    assert sorted(outcomes) == [("created", None), ("rejected", "email_already_exists")]
    with postgres_engine.connect() as connection:
        count = connection.scalar(
            sa.text("SELECT count(*) FROM identity_access.users WHERE email=:email"),
            {"email": email},
        )
    assert count == 1


def test_concurrent_refresh_detects_replay_and_revokes_the_token_family(
    postgres_engine, session_factory, identity_settings, register_customer
):
    registered = register_customer()
    refresh_value = registered["refresh_token"]
    subject_id = registered["user"]["id"]
    barrier = Barrier(2)

    def attempt() -> tuple[str, str | None]:
        with session_factory() as session:
            barrier.wait()
            try:
                AuthService(session, identity_settings).refresh(
                    refresh_value, correlation_id=uuid4()
                )
                return "rotated", None
            except ApiError as exc:
                return "rejected", exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: attempt(), range(2)))

    assert sorted(outcomes) == [("rejected", "refresh_token_reused"), ("rotated", None)]
    with postgres_engine.connect() as connection:
        session_status = connection.scalar(
            sa.text(
                "SELECT s.status FROM identity_access.auth_sessions s "
                "JOIN identity_access.users u ON u.id=s.user_id "
                "WHERE u.public_id=CAST(:subject_id AS uuid)"
            ),
            {"subject_id": subject_id},
        )
        token_statuses = connection.scalars(
            sa.text(
                "SELECT t.status FROM identity_access.refresh_tokens t "
                "JOIN identity_access.auth_sessions s ON s.id=t.session_id "
                "JOIN identity_access.users u ON u.id=s.user_id "
                "WHERE u.public_id=CAST(:subject_id AS uuid) ORDER BY t.id"
            ),
            {"subject_id": subject_id},
        ).all()

    assert session_status == "revoked"
    assert token_statuses == ["reused", "reused"]
