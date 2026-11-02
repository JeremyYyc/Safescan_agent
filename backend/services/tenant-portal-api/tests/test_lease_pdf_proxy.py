import httpx
import pytest
from test_contract import handler, token

from app.cache import MemoryCache
from app.client import Clients
from app.main import create_app


@pytest.mark.asyncio
async def test_pdf_proxy_requires_customer_and_preserves_private_bytes():
    calls = []

    def pdf_handler(request):
        if request.url.path.endswith("/documents/current/pdf"):
            calls.append(request)
            assert request.headers["authorization"] == "Bearer delegated"
            return httpx.Response(
                200,
                content=b"%PDF-1.7\nprivate-lease",
                headers={
                    "content-type": "application/pdf",
                    "content-disposition": 'inline; filename="lease.pdf"',
                },
            )
        return handler(request)

    clients = Clients(transport=httpx.MockTransport(pdf_handler))
    app = create_app(clients=clients, cache=MemoryCache())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client,
    ):
        assert (
            await client.get("/api/v1/tenant/leases/l1/document/pdf")
        ).status_code == 401
        response = await client.get(
            "/api/v1/tenant/leases/l1/document/pdf",
            headers={"Authorization": f"Bearer {token()}"},
        )
        assert (
            response.status_code == 200
            and response.content == b"%PDF-1.7\nprivate-lease"
        )
        assert response.headers["cache-control"] == "private, no-store"
        assert len(calls) == 1
