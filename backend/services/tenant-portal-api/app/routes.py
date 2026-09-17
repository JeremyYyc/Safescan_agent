from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from .auth import (
    Principal,
    principal_from_request,
    require_application_eligible,
    require_permission,
    require_status,
)
from .models import (
    ApplicationView,
    BootstrapView,
    ContactRequest,
    CreateApplicationRequest,
    CreateMaintenanceRequest,
    CustomerIdentity,
    CustomerStatus,
    DataEnvelope,
    DeclineLeaseRequest,
    ErrorEnvelope,
    HomeView,
    LeaseDocumentView,
    LeaseView,
    MaintenanceOrderView,
    MessageRequest,
    MyPropertyView,
    NavigationItem,
    Page,
    PropertyView,
    ProspectCaseView,
    ReportCreateRequest,
    ReportJobRequest,
    ReportJobView,
    ReportView,
    ResourceSummary,
    SubmitApplicationRequest,
    TenantSignatureRequest,
    TenantTopbarView,
    UpdateApplicationRequest,
    UpdateMaintenanceRequest,
    VersionReasonRequest,
)
from .service import PortalService, request_context

ERROR_RESPONSES = {
    status: {"model": ErrorEnvelope}
    for status in (400, 401, 403, 404, 409, 413, 415, 422, 429, 500, 502, 503, 504)
}
router = APIRouter(prefix="/api/v1/tenant", responses=ERROR_RESPONSES)


def env(request: Request, data: Any, partial=None):
    return {
        "data": data,
        "meta": {
            "correlation_id": request.state.correlation_id,
            "partial_errors": partial or [],
        },
    }


def svc(request: Request) -> PortalService:
    return request.app.state.portal


def actor(request: Request, optional: bool = False) -> Principal:
    return principal_from_request(request, optional=optional)


async def call(
    request: Request,
    client_name: str,
    method: str,
    path: str,
    *,
    body=None,
    params=None,
    optional=False,
    cache=None,
):
    principal = actor(request, optional)
    client = getattr(svc(request).clients, client_name)
    operation = lambda: client.request(
        method,
        path,
        principal=principal,
        context=request_context(request),
        params=params,
        json=body,
    )
    data = (
        await svc(request).cached(
            cache[0],
            principal,
            str(sorted((params or {}).items())),
            cache[1],
            operation,
        )
        if cache and method == "GET"
        else await operation()
    )
    if method != "GET":
        await svc(request).invalidate(principal)
    return env(request, data)


async def active_lease(request: Request, principal: Principal) -> dict[str, Any]:
    from .errors import ApiError

    result = await svc(request).clients.leasing.request(
        "GET",
        "/internal/v1/leases",
        principal=principal,
        context=request_context(request),
        params={
            "mine": "true",
            "status": "active",
            "limit": 1,
            "projection": "customer",
        },
    )
    items = result.get("items", result if isinstance(result, list) else [])
    if not items:
        raise ApiError(
            403,
            "current_lease_required",
            "An active lease is required",
            details={"required_lease_status": "active"},
        )
    return items[0]


@router.get(
    "/bootstrap",
    response_model=DataEnvelope[BootstrapView],
    operation_id="getTenantBootstrap",
)
async def bootstrap(request: Request):
    principal = actor(request, optional=True)
    if principal.authenticated:
        me = await svc(request).cached(
            "bootstrap",
            principal,
            "",
            30,
            lambda: svc(request).clients.identity.request(
                "GET",
                "/api/v1/me",
                principal=principal,
                context=request_context(request),
            ),
        )
        customer = CustomerIdentity(
            id=principal.subject,
            username=me.get("username"),
            status=principal.status,
            authenticated=True,
            auth_version=principal.auth_version,
            status_version=principal.status_version,
        )
    else:
        customer = CustomerIdentity(authenticated=False)
    menu = [NavigationItem(code="properties", href="/tenant/properties")]
    if principal.authenticated:
        menu.extend(
            [
                NavigationItem(code="applications", href="/tenant/applications"),
                NavigationItem(code="agent", href="/tenant/agent"),
            ]
        )
    if principal.status in (CustomerStatus.TENANT, CustomerStatus.FORMER_TENANT):
        menu.append(NavigationItem(code="my_property", href="/tenant/my-property"))
    view = BootstrapView(
        customer=customer, menu=menu, capabilities=sorted(principal.permissions)
    )
    return env(request, view.model_dump(mode="json"))


@router.get(
    "/topbar",
    response_model=DataEnvelope[TenantTopbarView],
    operation_id="getTenantTopbar",
)
async def topbar(request: Request):
    return await call(request, "identity", "GET", "/api/v1/me", cache=("topbar", 30))


@router.get(
    "/home", response_model=DataEnvelope[HomeView], operation_id="getTenantHome"
)
async def home(request: Request):
    principal = actor(request)
    data, partial = await svc(request).home(principal, request_context(request))
    return env(request, data, partial)


@router.get(
    "/properties",
    response_model=DataEnvelope[Page[PropertyView]],
    operation_id="listTenantProperties",
)
async def properties(request: Request):
    return await call(
        request,
        "leasing",
        "GET",
        "/internal/v1/market-properties",
        params=dict(request.query_params),
        optional=True,
        cache=("market-properties", 60),
    )


@router.get(
    "/properties/{property_id}",
    response_model=DataEnvelope[PropertyView],
    operation_id="getTenantProperty",
)
async def property_detail(property_id: str, request: Request):
    return await call(
        request,
        "leasing",
        "GET",
        f"/internal/v1/market-properties/{property_id}",
        optional=True,
        cache=(f"market-property:{property_id}", 60),
    )


@router.post(
    "/properties/{property_id}/contact",
    response_model=DataEnvelope[ProspectCaseView],
    status_code=201,
    operation_id="contactTenantProperty",
)
async def contact(property_id: str, command: ContactRequest, request: Request):
    return await call(
        request,
        "leasing",
        "POST",
        "/internal/v1/contact-requests",
        body={
            "property_id": property_id,
            "content": command.message,
            "client_message_id": command.client_message_id,
        },
    )


@router.get(
    "/prospect-cases",
    response_model=DataEnvelope[Page[ProspectCaseView]],
    operation_id="listTenantProspectCases",
)
async def cases(request: Request):
    return await call(
        request,
        "leasing",
        "GET",
        "/internal/v1/prospect-cases",
        params={**dict(request.query_params), "mine": "true"},
        cache=("cases", 10),
    )


@router.get(
    "/prospect-cases/{case_id}",
    response_model=DataEnvelope[ProspectCaseView],
    operation_id="getTenantProspectCase",
)
async def case(case_id: str, request: Request):
    return await call(
        request, "leasing", "GET", f"/internal/v1/prospect-cases/{case_id}"
    )


@router.get(
    "/contact-threads/{thread_id}/messages",
    response_model=DataEnvelope[Page[ResourceSummary]],
    operation_id="listTenantContactMessages",
)
async def messages(thread_id: str, request: Request):
    return await call(
        request,
        "leasing",
        "GET",
        f"/internal/v1/contact-threads/{thread_id}/messages",
        params=dict(request.query_params),
    )


@router.post(
    "/contact-threads/{thread_id}/messages",
    response_model=DataEnvelope[ResourceSummary],
    status_code=201,
    operation_id="createTenantContactMessage",
)
async def create_message(thread_id: str, command: MessageRequest, request: Request):
    return await call(
        request,
        "leasing",
        "POST",
        f"/internal/v1/contact-threads/{thread_id}/messages",
        body=command.model_dump(),
    )


@router.post(
    "/applications",
    response_model=DataEnvelope[ApplicationView],
    status_code=201,
    operation_id="createTenantApplication",
)
async def create_application(command: CreateApplicationRequest, request: Request):
    principal = actor(request)
    require_application_eligible(principal)
    require_permission(principal, "application:self:create")
    return await call(
        request,
        "leasing",
        "POST",
        "/internal/v1/applications",
        body=command.model_dump(exclude_none=True),
    )


@router.get(
    "/applications",
    response_model=DataEnvelope[Page[ApplicationView]],
    operation_id="listTenantApplications",
)
async def applications(request: Request):
    return await call(
        request,
        "leasing",
        "GET",
        "/internal/v1/applications",
        params={**dict(request.query_params), "mine": "true"},
        cache=("applications", 10),
    )


@router.get(
    "/applications/{application_id}",
    response_model=DataEnvelope[ApplicationView],
    operation_id="getTenantApplication",
)
async def application(application_id: str, request: Request):
    return await call(
        request, "leasing", "GET", f"/internal/v1/applications/{application_id}"
    )


@router.patch(
    "/applications/{application_id}",
    response_model=DataEnvelope[ApplicationView],
    operation_id="updateTenantApplication",
)
async def update_application(
    application_id: str, command: UpdateApplicationRequest, request: Request
):
    principal = actor(request)
    require_application_eligible(principal)
    require_permission(principal, "application:self:create")
    return await call(
        request,
        "leasing",
        "PATCH",
        f"/internal/v1/applications/{application_id}",
        body=command.model_dump(exclude_none=True),
    )


@router.post(
    "/applications/{application_id}/submit",
    response_model=DataEnvelope[ApplicationView],
    operation_id="submitTenantApplication",
)
async def submit_application(
    application_id: str, command: SubmitApplicationRequest, request: Request
):
    principal = actor(request)
    require_application_eligible(principal)
    require_permission(principal, "application:self:submit")
    return await call(
        request,
        "leasing",
        "POST",
        f"/internal/v1/applications/{application_id}/submit",
        body=command.model_dump(),
    )


@router.post(
    "/applications/{application_id}/withdraw",
    response_model=DataEnvelope[ApplicationView],
    operation_id="withdrawTenantApplication",
)
async def withdraw_application(
    application_id: str, command: VersionReasonRequest, request: Request
):
    return await call(
        request,
        "leasing",
        "POST",
        f"/internal/v1/applications/{application_id}/withdraw",
        body=command.model_dump(exclude_none=True),
    )


@router.get(
    "/leases",
    response_model=DataEnvelope[Page[LeaseView]],
    operation_id="listTenantLeases",
)
async def leases(request: Request):
    return await call(
        request,
        "leasing",
        "GET",
        "/internal/v1/leases",
        params={**dict(request.query_params), "mine": "true"},
        cache=("leases", 10),
    )


@router.get(
    "/leases/{lease_id}",
    response_model=DataEnvelope[LeaseView],
    operation_id="getTenantLease",
)
async def lease(lease_id: str, request: Request):
    return await call(
        request,
        "leasing",
        "GET",
        f"/internal/v1/leases/{lease_id}",
        params={"projection": "customer"},
    )


@router.post(
    "/leases/{lease_id}/signature",
    response_model=DataEnvelope[LeaseView],
    operation_id="signTenantLease",
)
async def sign_lease(lease_id: str, command: TenantSignatureRequest, request: Request):
    return await call(
        request,
        "leasing",
        "POST",
        f"/internal/v1/leases/{lease_id}/tenant-signatures",
        body=command.model_dump(),
    )


@router.post(
    "/leases/{lease_id}/decline",
    response_model=DataEnvelope[LeaseView],
    operation_id="declineTenantLease",
)
async def decline_lease(lease_id: str, command: DeclineLeaseRequest, request: Request):
    return await call(
        request,
        "leasing",
        "POST",
        f"/internal/v1/leases/{lease_id}/cancel",
        body=command.model_dump(),
    )


@router.get(
    "/leases/{lease_id}/document",
    response_model=DataEnvelope[LeaseDocumentView],
    operation_id="getTenantLeaseDocument",
)
async def lease_document(lease_id: str, request: Request):
    return await call(
        request, "leasing", "GET", f"/internal/v1/leases/{lease_id}/documents/current"
    )


@router.get(
    "/leases/{lease_id}/invoices",
    response_model=DataEnvelope[Page[ResourceSummary]],
    operation_id="listTenantLeaseInvoices",
)
async def invoices(lease_id: str, request: Request):
    return await call(
        request,
        "leasing",
        "GET",
        f"/internal/v1/leases/{lease_id}/invoices",
        params=dict(request.query_params),
        cache=(f"invoices:{lease_id}", 10),
    )


@router.get(
    "/my-property",
    response_model=DataEnvelope[MyPropertyView],
    operation_id="getTenantMyProperty",
)
async def my_property(request: Request):
    principal = actor(request)
    require_status(principal, CustomerStatus.TENANT)

    async def load():
        import asyncio

        from .errors import ApiError

        context = request_context(request)
        leases = await svc(request).clients.leasing.request(
            "GET",
            "/internal/v1/leases",
            principal=principal,
            context=context,
            params={
                "mine": "true",
                "status": "executed,active",
                "limit": 1,
                "projection": "customer",
            },
        )
        items = leases.get("items", leases if isinstance(leases, list) else [])
        if not items:
            raise ApiError(404, "resource_not_found", "Resource not found")
        lease = items[0]
        property_id = lease.get("property", {}).get("id") or lease.get("property_id")
        optional = {
            "invoices": svc(request).clients.leasing.request(
                "GET",
                f"/internal/v1/leases/{lease['id']}/invoices",
                principal=principal,
                context=context,
            ),
            "maintenance": svc(request).clients.maintenance.request(
                "GET",
                "/internal/v1/maintenance-orders",
                principal=principal,
                context=context,
                params={"mine": "true", "limit": 20},
            ),
        }
        if lease.get("status") == "active":
            optional["reports"] = svc(request).clients.report.request(
                "GET",
                f"/internal/v1/properties/{property_id}/reports",
                principal=principal,
                context=context,
                params={"mine": "true", "source_lease_id": lease["id"]},
            )
        results = await asyncio.gather(*optional.values(), return_exceptions=True)
        data = {"lease": lease, "property": lease.get("property")}
        partial = []
        for name, result in zip(optional, results):
            if isinstance(result, Exception):
                error = (
                    result
                    if isinstance(result, ApiError)
                    else ApiError(
                        503,
                        "dependency_unavailable",
                        "Dependency unavailable",
                        retryable=True,
                    )
                )
                partial.append(
                    {
                        "component": name,
                        "code": error.code,
                        "retryable": error.retryable,
                        "details": error.details,
                    }
                )
            else:
                data[name] = result
        return {"data": data, "partial": partial}

    packed = await svc(request).cached("my-property", principal, "", 10, load)
    return env(request, packed["data"], packed["partial"])


@router.get(
    "/rental-history",
    response_model=DataEnvelope[Page[LeaseView]],
    operation_id="listTenantRentalHistory",
)
async def rental_history(request: Request):
    require_status(actor(request), CustomerStatus.TENANT, CustomerStatus.FORMER_TENANT)
    return await call(
        request,
        "leasing",
        "GET",
        "/internal/v1/leases",
        params={"mine": "true", "status": "ended,terminated", "projection": "customer"},
        cache=("rental-history", 15),
    )


@router.get(
    "/leases/{lease_id}/property",
    response_model=DataEnvelope[LeaseView],
    operation_id="getTenantHistoricalProperty",
)
async def history_property(lease_id: str, request: Request):
    require_status(actor(request), CustomerStatus.TENANT, CustomerStatus.FORMER_TENANT)
    return await call(
        request,
        "leasing",
        "GET",
        f"/internal/v1/leases/{lease_id}",
        params={"projection": "customer", "include": "property,invoices"},
        cache=(f"history-property:{lease_id}", 15),
    )


@router.post(
    "/maintenance-orders",
    response_model=DataEnvelope[MaintenanceOrderView],
    status_code=201,
    operation_id="createTenantMaintenanceOrder",
)
async def create_order(command: CreateMaintenanceRequest, request: Request):
    principal = actor(request)
    require_status(principal, CustomerStatus.TENANT)
    require_permission(principal, "maintenance:self:create")
    lease = await active_lease(request, principal)
    property_id = lease.get("property", {}).get("id") or lease.get("property_id")
    return await call(
        request,
        "maintenance",
        "POST",
        "/internal/v1/maintenance-orders",
        body={
            **command.model_dump(exclude_none=True),
            "lease_id": lease["id"],
            "property_id": property_id,
        },
    )


@router.get(
    "/maintenance-orders",
    response_model=DataEnvelope[Page[MaintenanceOrderView]],
    operation_id="listTenantMaintenanceOrders",
)
async def maintenance_orders(request: Request):
    return await call(
        request,
        "maintenance",
        "GET",
        "/internal/v1/maintenance-orders",
        params={**dict(request.query_params), "mine": "true"},
        cache=("maintenance", 10),
    )


@router.get(
    "/maintenance-orders/{order_id}",
    response_model=DataEnvelope[MaintenanceOrderView],
    operation_id="getTenantMaintenanceOrder",
)
async def maintenance_order(order_id: str, request: Request):
    return await call(
        request, "maintenance", "GET", f"/internal/v1/maintenance-orders/{order_id}"
    )


@router.patch(
    "/maintenance-orders/{order_id}",
    response_model=DataEnvelope[MaintenanceOrderView],
    operation_id="updateTenantMaintenanceOrder",
)
async def update_order(
    order_id: str, command: UpdateMaintenanceRequest, request: Request
):
    return await call(
        request,
        "maintenance",
        "PATCH",
        f"/internal/v1/maintenance-orders/{order_id}",
        body=command.model_dump(exclude_none=True),
    )


@router.post(
    "/maintenance-orders/{order_id}/comments",
    response_model=DataEnvelope[ResourceSummary],
    status_code=201,
    operation_id="commentTenantMaintenanceOrder",
)
async def comment_order(order_id: str, command: MessageRequest, request: Request):
    return await call(
        request,
        "maintenance",
        "POST",
        f"/internal/v1/maintenance-orders/{order_id}/comments",
        body={**command.model_dump(), "visibility": "public"},
    )


@router.post(
    "/maintenance-orders/{order_id}/cancel",
    response_model=DataEnvelope[MaintenanceOrderView],
    operation_id="cancelTenantMaintenanceOrder",
)
async def cancel_order(order_id: str, command: VersionReasonRequest, request: Request):
    body = {"to_status": "cancelled", "version": command.version}
    if command.reason is not None:
        body["note"] = command.reason
    return await call(
        request,
        "maintenance",
        "POST",
        f"/internal/v1/maintenance-orders/{order_id}/transitions",
        body=body,
    )


@router.get(
    "/my-property/reports",
    response_model=DataEnvelope[Page[ReportView]],
    operation_id="listTenantCurrentReports",
)
async def current_reports(request: Request):
    principal = actor(request)
    require_status(principal, CustomerStatus.TENANT)
    lease = await active_lease(request, principal)
    property_id = lease.get("property", {}).get("id") or lease.get("property_id")
    return await call(
        request,
        "report",
        "GET",
        f"/internal/v1/properties/{property_id}/reports",
        params={"mine": "true", "source_lease_id": lease["id"]},
        cache=("current-reports", 10),
    )


@router.post(
    "/my-property/reports",
    response_model=DataEnvelope[ReportView],
    status_code=201,
    operation_id="createTenantReport",
)
async def create_report(command: ReportCreateRequest, request: Request):
    principal = actor(request)
    require_status(principal, CustomerStatus.TENANT)
    require_permission(principal, "report:self:create")
    lease = await active_lease(request, principal)
    property_id = lease.get("property", {}).get("id") or lease.get("property_id")
    return await call(
        request,
        "report",
        "POST",
        f"/internal/v1/properties/{property_id}/reports",
        body=command.model_dump(exclude_none=True),
    )


@router.get(
    "/leases/{lease_id}/property/reports",
    response_model=DataEnvelope[Page[ReportView]],
    operation_id="listTenantHistoricalReports",
)
async def historical_reports(lease_id: str, request: Request):
    require_status(actor(request), CustomerStatus.TENANT, CustomerStatus.FORMER_TENANT)
    lease = await svc(request).clients.leasing.request(
        "GET",
        f"/internal/v1/leases/{lease_id}",
        principal=actor(request),
        context=request_context(request),
        params={"projection": "customer"},
    )
    property_id = lease.get("property", {}).get("id") or lease.get("property_id")
    return await call(
        request,
        "report",
        "GET",
        f"/internal/v1/properties/{property_id}/reports",
        params={"source_lease_id": lease_id, "mine": "true"},
        cache=(f"history-reports:{lease_id}", 15),
    )


@router.get(
    "/reports/{report_id}",
    response_model=DataEnvelope[ReportView],
    operation_id="getTenantReport",
)
async def report(report_id: str, request: Request):
    return await call(
        request,
        "report",
        "GET",
        f"/internal/v1/reports/{report_id}",
        params={"projection": "tenant"},
    )


@router.post(
    "/reports/{report_id}/jobs",
    response_model=DataEnvelope[ReportJobView],
    status_code=202,
    operation_id="createTenantReportJob",
)
async def create_job(report_id: str, command: ReportJobRequest, request: Request):
    principal = actor(request)
    require_status(principal, CustomerStatus.TENANT)
    require_permission(principal, "report:self:create")
    return await call(
        request,
        "report",
        "POST",
        f"/internal/v1/reports/{report_id}/jobs",
        body=command.model_dump(),
    )


@router.get(
    "/report-jobs/{job_id}",
    response_model=DataEnvelope[ReportJobView],
    operation_id="getTenantReportJob",
)
async def job(job_id: str, request: Request):
    return await call(request, "report", "GET", f"/internal/v1/report-jobs/{job_id}")


@router.get(
    "/report-jobs/{job_id}/events",
    responses={200: {"content": {"text/event-stream": {}, "application/x-ndjson": {}}}},
    operation_id="streamTenantReportJobEvents",
)
async def events(job_id: str, request: Request):
    response = await svc(request).clients.report.open_stream(
        f"/internal/v1/report-jobs/{job_id}/events",
        principal=actor(request),
        context=request_context(request),
        params=dict(request.query_params),
        accept=request.headers.get("accept", "text/event-stream"),
    )
    return StreamingResponse(
        response.aiter_bytes(),
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "text/event-stream"),
        background=response.aclose,
    )


@router.post(
    "/reports/{report_id}/files/videos",
    status_code=201,
    operation_id="uploadTenantReportVideo",
)
async def upload(
    report_id: str,
    request: Request,
    x_file_name: str = Header(alias="X-File-Name"),
    x_content_sha256: str | None = Header(default=None, alias="X-Content-SHA256"),
):
    principal = actor(request)
    require_status(principal, CustomerStatus.TENANT)
    require_permission(principal, "report:self:create")
    headers = {
        "Content-Type": request.headers.get("content-type", "application/octet-stream"),
        "X-File-Name": x_file_name,
    }
    if x_content_sha256:
        headers["X-Content-SHA256"] = x_content_sha256
    response = await svc(request).clients.report.stream(
        "POST",
        f"/internal/v1/reports/{report_id}/files/videos",
        principal=principal,
        context=request_context(request),
        body=request.stream(),
        headers=headers,
    )
    await svc(request).invalidate(principal)
    return StreamingResponse(
        response.aiter_bytes(),
        status_code=response.status_code,
        media_type=response.headers.get("content-type"),
        background=response.aclose,
    )
