import httpx
import pytest
from test_contract import handler

from app.cache import MemoryCache
from app.client import Clients
from app.main import create_app


@pytest.mark.asyncio
async def test_property_image_proxy_preserves_image_bytes_and_visibility():
    calls = []

    def image_handler(request):
        if "/images/" in request.url.path:
            calls.append(request)
            assert request.headers["accept"] == "image/*"
            if "hidden" in request.url.path:
                return httpx.Response(
                    404,
                    json={
                        "error": {
                            "code": "resource_not_found",
                            "message": "Not visible",
                        }
                    },
                )
            return httpx.Response(
                200, content=b"\x89PNG\r\nimage", headers={"content-type": "image/png"}
            )
        return handler(request)

    clients = Clients(transport=httpx.MockTransport(image_handler))
    app = create_app(clients=clients, cache=MemoryCache())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        headers = {}
        response = await client.get(
            "/api/v1/tenant/properties/p1/images/i1", headers=headers
        )
        assert response.status_code == 200 and response.content == b"\x89PNG\r\nimage"
        assert response.headers["content-type"] == "image/png"
        assert response.headers["x-content-type-options"] == "nosniff"
        denied = await client.get(
            "/api/v1/tenant/properties/hidden/images/i1", headers=headers
        )
        assert denied.status_code == 404
        assert len(calls) == 2
