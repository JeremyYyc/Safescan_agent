import pytest
from fastapi.testclient import TestClient
from safescan_common.http.errors import ApiError

import app.main as main


pytestmark = pytest.mark.unit


class Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, statement):
        return statement


class Engine:
    def connect(self):
        return Connection()


class Identity:
    def __init__(self, failure=None):
        self.failure = failure
        self.called = False

    def identity_ready(self):
        self.called = True
        if self.failure:
            raise self.failure


def test_readiness_checks_database_and_identity_credential(monkeypatch):
    identity = Identity()
    monkeypatch.setattr(main, "get_engine", lambda: Engine())
    monkeypatch.setattr(main, "dependency_client", lambda: identity)

    main.readiness()

    assert identity.called is True


def test_readiness_fails_when_identity_credential_is_unavailable(monkeypatch):
    identity = Identity(ApiError(503, "dependency_unavailable", "unavailable"))
    monkeypatch.setattr(main, "get_engine", lambda: Engine())
    monkeypatch.setattr(main, "dependency_client", lambda: identity)

    response = TestClient(main.app).get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
