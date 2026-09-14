from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
import httpx
from sqlalchemy import text
from sqlalchemy.pool import QueuePool

from safescan_common.auth import JWTVerifier, Principal, require_scope
from safescan_common.auth import AsyncServiceTokenProvider, ServiceTokenProvider
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


def test_service_token_provider_refreshes_once_under_concurrency():
    calls = 0
    now = [100.0]

    def handler(request: httpx.Request):
        nonlocal calls
        assert request.url.path == "/internal/v1/service-tokens"
        assert request.headers["authorization"].startswith("Basic ")
        calls += 1
        time.sleep(0.02)
        return httpx.Response(200, json={"data": {
            "access_token": f"service-token-value-{calls:02d}", "expires_in": 60,
        }})

    provider = ServiceTokenProvider(
        "http://identity", "client", "secret", ["identity:token_exchange"],
        transport=httpx.MockTransport(handler), clock=lambda: now[0],
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert len(set(pool.map(lambda _: provider.get(), range(16)))) == 1
    assert calls == 1
    now[0] += 60
    with ThreadPoolExecutor(max_workers=8) as pool:
        refreshed = set(pool.map(lambda _: provider.get(), range(16)))
    assert refreshed == {"service-token-value-02"}
    assert calls == 2
    provider.close()


def test_async_service_token_provider_refreshes_once_under_concurrency():
    async def exercise():
        calls = 0
        now = [100.0]

        async def handler(request: httpx.Request):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return httpx.Response(200, json={"data": {
                "access_token": f"async-service-token-{calls:02d}", "expires_in": 60,
            }})

        provider = AsyncServiceTokenProvider(
            "http://identity", "client", "secret", ["identity:token_exchange"],
            transport=httpx.MockTransport(handler), clock=lambda: now[0],
        )
        assert len(set(await asyncio.gather(*(provider.get() for _ in range(16))))) == 1
        assert calls == 1
        now[0] += 60
        assert set(await asyncio.gather(*(provider.get() for _ in range(16)))) == {
            "async-service-token-02"
        }
        assert calls == 2
        await provider.close()

    asyncio.run(exercise())


def test_service_token_errors_do_not_expose_client_secret():
    secret = "never-log-this-client-secret"
    provider = ServiceTokenProvider(
        "http://identity", "client", secret, ["identity:token_exchange"],
        transport=httpx.MockTransport(lambda request: httpx.Response(401)),
    )
    try:
        provider.get()
        assert False, "invalid credentials must fail"
    except Exception as exc:
        assert secret not in str(exc)
        assert secret not in repr(exc)
    finally:
        provider.close()
