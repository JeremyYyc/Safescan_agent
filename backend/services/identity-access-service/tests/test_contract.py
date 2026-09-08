from pydantic import SecretStr
from app.core.config import Settings, get_settings
from app.core.pagination import decode_cursor, encode_cursor, get_cursor_codec
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.main import app


def settings() -> Settings:
    return Settings(
        database_url=SecretStr("postgresql+psycopg://unused:unused@db/unused"),
        jwt_secret=SecretStr("identity-unit-test-secret-value"),
    )


def test_openapi_exposes_the_51_planned_operations():
    schema = app.openapi()
    operations = sum(
        method.lower() in {"get", "post", "put", "patch", "delete"}
        for path in schema["paths"].values()
        for method in path
    )
    assert operations == 51
    assert "/api/v1/auth/register" in schema["paths"]
    assert "/api/v1/me" in schema["paths"]
    assert "/internal/v1/tokens/exchange" in schema["paths"]


def test_access_token_is_scoped_signed_and_audience_checked():
    config = settings()
    token, lifetime = create_access_token(
        config, subject="subject", session_id="session", account_type="customer",
        auth_version=3, scopes=["b", "a", "a"],
    )
    claims = decode_access_token(config, token)
    assert lifetime == config.access_token_seconds
    assert claims["scopes"] == ["a", "b"]
    assert claims["av"] == 3
    assert claims["aud"] == config.jwt_audience


def test_passwords_are_argon2id_hashes_and_cursors_are_opaque(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused:unused@db/unused")
    monkeypatch.setenv("AUTH_SECRET", "identity-unit-test-secret-value")
    get_settings.cache_clear()
    get_cursor_codec.cache_clear()
    password_hash = hash_password("LongPassword123")
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password_hash, "LongPassword123")
    assert not verify_password(password_hash, "incorrect")
    cursor = encode_cursor(42)
    assert cursor != "42"
    assert decode_cursor(cursor) == 42
    assert "." in cursor
    get_cursor_codec.cache_clear()
    get_settings.cache_clear()
