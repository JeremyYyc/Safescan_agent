from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.pool import QueuePool

from safescan_common.auth import JWTVerifier, Principal, require_scope
from safescan_common.database import (
    DatabaseConfig,
    create_engine_from_config,
    create_session_factory,
    session_scope,
)
from safescan_common.http import ApiError, CursorCodec, decode_cursor, encode_cursor, page
from safescan_common.http.middleware import install_http_infrastructure


def test_cursor_codec_and_page_support_generic_rows():
    codec = CursorCodec("cursor-test-secret")
    value = {"created_at": "2026-09-08T00:00:00Z", "id": 42}
    assert codec.decode(codec.encode(value)) == value
    encoded = codec.encode(value)
    tampered = encoded[:-1] + ("A" if encoded[-1] != "A" else "B")
    try:
        codec.decode(tampered)
        assert False, "tampered cursor must fail"
    except ApiError as exc:
        assert exc.code == "cursor_invalid"
    assert decode_cursor(encode_cursor(42)) == 42
    result = page([{"id": 1}, {"id": 2}], 1, lambda row: {"id": row["id"]})
    assert result["data"] == [{"id": 1}]
    assert decode_cursor(result["meta"]["next_cursor"]) == 1


def test_http_contract_and_permission_dependency():
    app = FastAPI()
    install_http_infrastructure(app)

    def principal() -> Principal:
        return Principal(subject="test", scopes=frozenset({"report:read"}), claims={})

    @app.get("/allowed")
    def allowed(_: Principal = Depends(require_scope("report:read", principal))):
        return {"data": True}

    @app.get("/error")
    def error():
        raise ApiError(409, "version_conflict", "Version conflict")

    client = TestClient(app)
    allowed_response = client.get("/allowed", headers={"X-Request-ID": "not-a-uuid"})
    assert allowed_response.status_code == 200
    assert allowed_response.headers["X-Request-ID"] != "not-a-uuid"
    error_response = client.get("/error")
    assert error_response.status_code == 409
    assert error_response.json()["error"]["code"] == "version_conflict"


def test_jwt_verifier_checks_issuer_and_audience():
    import jwt
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    claims = {
        "sub": "subject",
        "iss": "issuer",
        "aud": "audience",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "jti": "token-id",
    }
    token = jwt.encode(claims, "a-secret-long-enough-for-tests", algorithm="HS256")
    verifier = JWTVerifier("a-secret-long-enough-for-tests", "issuer", "audience")
    assert verifier.decode(token)["sub"] == "subject"


def test_database_factory_and_transactional_session_scope():
    engine = create_engine_from_config(
        DatabaseConfig("sqlite+pysqlite:///:memory:"),
        poolclass=QueuePool,
    )
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)"))
    factory = create_session_factory(engine)
    with session_scope(factory) as session:
        session.execute(text("INSERT INTO sample (value) VALUES ('stored')"))
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT value FROM sample")) == "stored"
    engine.dispose()
