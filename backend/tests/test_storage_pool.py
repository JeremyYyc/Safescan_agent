from unittest.mock import MagicMock

from app import storage
from app.settings import Settings


def test_minio_client_uses_reusable_bounded_connection_pool(monkeypatch):
    settings = Settings(
        MINIO_ACCESS_KEY='access',
        MINIO_SECRET_KEY='secret',
        MINIO_POOL_MAXSIZE=17,
    )
    pool = MagicMock(return_value=object())
    minio = MagicMock(return_value=object())
    monkeypatch.setattr(storage, 'get_settings', lambda: settings)
    monkeypatch.setattr(storage.urllib3, 'PoolManager', pool)
    monkeypatch.setattr(storage, 'Minio', minio)
    storage.client.cache_clear()
    try:
        first = storage.client()
        second = storage.client()
    finally:
        storage.client.cache_clear()

    assert first is second
    pool.assert_called_once()
    kwargs = pool.call_args.kwargs
    assert kwargs['num_pools'] == 1
    assert kwargs['maxsize'] == 17
    assert kwargs['block'] is True
    minio.assert_called_once_with(
        settings.MINIO_ENDPOINT,
        access_key='access',
        secret_key='secret',
        secure=settings.MINIO_SECURE,
        region=settings.MINIO_REGION,
        http_client=pool.return_value,
    )
