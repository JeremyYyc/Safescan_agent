import httpx
import pytest
from test_contract import handler, token

from app.cache import MemoryCache
from app.client import Clients
from app.main import create_app


@pytest.mark.asyncio
async def test_pdf_proxy_preserves_bytes_and_authorization_errors():
    calls = []

    def pdf_handler(request):
        if request.url.path.endswith("/documents/current/pdf"):
            calls.append(request)
            assert request.headers["authorization"] == "Bearer delegated-token"
            assert request.headers["accept"] == "application/pdf"
            if "hidden" in request.url.path:
                return httpx.Response(
                    404,
                    json={
                        "error": {
                            "code": "lease_access_required",
                            "message": "Not visible",
                        }
                    },
                )
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
            await client.get("/api/v1/staff/leases/l1/document/pdf")
        ).status_code == 401
        headers = {"Authorization": f"Bearer {token()}"}
        response = await client.get(
            "/api/v1/staff/leases/l1/document/pdf", headers=headers
        )
        assert (
            response.status_code == 200
            and response.content == b"%PDF-1.7\nprivate-lease"
        )
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["cache-control"] == "private, no-store"
        denied = await client.get(
            "/api/v1/staff/leases/hidden/document/pdf", headers=headers
        )
        assert denied.status_code == 404
        assert len(calls) == 2
