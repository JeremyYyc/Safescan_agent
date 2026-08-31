"""Live gateway contract tests, opt in with TEST_GATEWAY_URL/TEST_CONSOLE_URL.

The fixture API must use isolated PG and MINIO_ENDPOINT pointing at Nginx S3.
No model calls, user data, filesystem media, or public bucket policies.
"""
import os
import json
import time
from io import BytesIO
from uuid import uuid4
from datetime import timedelta
import httpx
import pytest
from app import storage
from test_end_to_end import textured_video

pytestmark = pytest.mark.skipif(not os.environ.get('TEST_GATEWAY_URL'), reason='Live Nginx gateway required')


def test_same_origin_api_and_private_report():
    with httpx.Client(base_url=os.environ['TEST_GATEWAY_URL'], timeout=60, trust_env=False) as client:
        assert client.get('/').status_code == 200
        assert client.get('/reports/deep-link').status_code == 200
        assert client.get('/gateway-health').text == 'ok\n'
        assert client.get('/health').json() == {'status': 'ok'}
        response = client.post('/api/auth/register', json={
            'email': uuid4().hex+'@test.invalid', 'username': 'Gateway test', 'password': 'fixture-password'})
        assert response.status_code == 200, response.text
        token = response.json()['token']
        client.headers['Authorization'] = 'Bearer '+token
        chat = client.post('/api/chats', json={'title': 'New Chat'}).json()
        cid = chat['chat']['id'] if 'chat' in chat else chat['id']
        upload = client.post('/api/uploadVideo', headers={'Content-Type': 'video/mp4'}, content=textured_video())
        assert upload.status_code == 200, upload.text
        analysis = client.post('/api/processVideoStream', json={'chat_id': cid, **upload.json()})
        events = [json.loads(line) for line in analysis.text.splitlines()]
        assert not any(e['type'] == 'error' for e in events), events
        result = next(e['result'] for e in events if e['type'] == 'complete')
        assert result['report_id']
        image = result['representativeImages'][0]
        assert client.get(image).status_code == 200
        assert httpx.get(os.environ['TEST_GATEWAY_URL']+image, trust_env=False).status_code == 401
        export = client.post(f'/api/reports/{cid}/export-pdf')
        assert export.status_code == 200, export.text
        assert client.get(export.json()['download_url']).content.startswith(b'%PDF-')
        probe = client.options('/api/chats', headers={'Origin':'https://other.invalid',
                    'Access-Control-Request-Method':'GET'})
        assert 'access-control-allow-origin' not in probe.headers


def test_ndjson_is_not_buffered():
    start = time.monotonic()
    with httpx.stream('GET', os.environ['TEST_GATEWAY_URL']+'/api/gateway-stream-probe', timeout=10, trust_env=False) as response:
        lines = response.iter_lines()
        assert next(lines) == 'first'
        assert time.monotonic()-start < 1.2
        assert next(lines) == 'last'
        assert time.monotonic()-start >= 1.5


def test_s3_signed_multipart_presigned_and_range():
    client = storage.client()
    bucket = storage.get_settings().MINIO_MEDIA_BUCKET
    key = 'gateway-test/'+uuid4().hex+'/中文 +%/a/b.bin'
    data = b'01234567'*(768*1024)  # 6 MiB: multipart upload through Nginx
    try:
        client.put_object(bucket, key, BytesIO(data), len(data), part_size=5*1024*1024)
        assert client.stat_object(bucket, key).size == len(data)
        url = client.presigned_get_object(bucket, key, expires=timedelta(minutes=1))
        response = httpx.get(url, headers={'Range':'bytes=3-10'}, trust_env=False)
        assert response.status_code == 206, response.text[:200]
        assert response.content == data[3:11]
        # Signing identity and token parameters must not be written to proxy logs.
    finally:
        client.remove_object(bucket, key)


def test_console_proxy():
    url = os.environ.get('TEST_CONSOLE_URL')
    if not url: pytest.skip('Console gateway URL required')
    response = httpx.get(url, follow_redirects=True, trust_env=False)
    assert response.status_code == 200
    assert 'text/html' in response.headers['content-type']
