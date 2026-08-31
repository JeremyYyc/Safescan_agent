from fastapi.testclient import TestClient
from main import create_app
from app.settings import Settings


def test_no_cors_middleware_or_public_api_configuration():
    app = create_app()
    assert all(m.cls.__name__ != 'CORSMiddleware' for m in app.user_middleware)
    assert not {'CORS_ORIGINS', 'CORS_ORIGIN_REGEX', 'VITE_API_BASE'} & Settings.model_fields.keys()
    response = TestClient(app).options('/api/chats', headers={
        'Origin':'https://foreign.invalid','Access-Control-Request-Method':'GET'})
    assert 'access-control-allow-origin' not in response.headers
