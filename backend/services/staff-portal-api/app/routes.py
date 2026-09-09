from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from .auth import (
    Principal,
    principal_from_request,
    require_permission,
    require_report_generation,
    require_roles,
)
from .models import (
    ApplicationView,
    ApproveApplicationRequest,
    AssignmentRequest,
    BootstrapView,
    CancelLeaseRequest,
    CompanySignatureRequest,
    CreateLeaseRequest,
    DashboardView,
    DataEnvelope,
    EndLeaseRequest,
    ErrorEnvelope,
    LeaseTermsRequest,
    LeaseView,
    MaintenanceOrderView,
    MessageRequest,
    NavigationItem,
    Page,
    PropertyDetailView,
    PropertyView,
    ProspectCaseView,
    RejectApplicationRequest,
    ReportCreateRequest,
    ReportJobRequest,
    ReportJobView,
    ReportView,
    ResourceSummary,
    Role,
    SendForSignatureRequest,
    StaffAdminDetailView,
    StaffAdminView,
    StaffIdentity,
    StaffTopbarView,
    StageUpdateRequest,
    TerminateLeaseRequest,
    TransitionRequest,
    VersionRequest,
)
from .service import PortalService, context_from_request

ERROR_RESPONSES = {
    status: {"model": ErrorEnvelope}
    for status in (400, 401, 403, 404, 409, 413, 415, 422, 429, 500, 502, 503, 504)
}
router = APIRouter(prefix="/api/v1/staff", responses=ERROR_RESPONSES)


def envelope(
    request: Request, data: Any, *, partial: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "data": data,
        "meta": {
            "correlation_id": request.state.correlation_id,
            "partial_errors": partial or [],
        },
    }


def principal(request: Request) -> Principal:
    return principal_from_request(request)


def svc(request: Request) -> PortalService:
    return request.app.state.portal


async def call(
    request: Request,
    client_name: str,
    method: str,
    path: str,
    *,
    body: Any = None,
    params: dict[str, Any] | None = None,
    roles: tuple[Role, ...] = (),
    cache: tuple[str, int] | None = None,
) -> dict[str, Any]:
    actor = principal(request)
    if roles:
        require_roles(actor, *roles)
    client = getattr(svc(request).clients, client_name)
    operation = lambda: client.request(
        method,
        path,
        principal=actor,
        context=context_from_request(request),
        params=params,
        json=body,
    )
    if cache and method == "GET":
        data = await svc(request).cached(
            cache[0], actor, str(sorted((params or {}).items())), cache[1], operation
        )
    else:
        data = await operation()
    if method != "GET":
        await svc(request).invalidate_after_write(actor)
    return envelope(request, data)


@router.get(
    "/bootstrap",
    response_model=DataEnvelope[BootstrapView],
    operation_id="getStaffBootstrap",
)
async def bootstrap(request: Request):
    actor = principal(request)
    cached = await svc(request).cached(
        "bootstrap",
        actor,
        "",
        30,
        lambda: svc(request).clients.identity.request(
            "GET", "/api/v1/me", principal=actor, context=context_from_request(request)
        ),
    )
    menu = [
        NavigationItem(code="properties", href="/staff/properties"),
        NavigationItem(code="agent", href="/staff/agent"),
    ]
    if actor.role in (Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN):
        menu.append(NavigationItem(code="orders", href="/staff/orders"))
    if actor.role in (Role.PROPERTY_MANAGER, Role.MAINTAINER, Role.MANAGER_ADMIN):
        menu.append(NavigationItem(code="maintenance", href="/staff/maintenance"))
    if actor.role is Role.MANAGER_ADMIN:
        menu.append(NavigationItem(code="staff_admin", href="/staff/admin/staff"))
    staff_profile = cached.get("staff") if isinstance(cached.get("staff"), dict) else {}
    identity = StaffIdentity(
        id=actor.subject,
        display_name=str(
            staff_profile.get("display_name") or cached.get("username") or actor.subject
        ),
        role=actor.role,
        permissions=sorted(actor.permissions),
        scopes=list(actor.scopes),
        auth_version=actor.auth_version,
        role_version=actor.role_version,
    )
    view = BootstrapView(
        staff=identity, menu=menu, capabilities=sorted(actor.permissions)
    )
    return envelope(request, view.model_dump(mode="json"))


@router.get(
    "/topbar",
    response_model=DataEnvelope[StaffTopbarView],
    operation_id="getStaffTopbar",
)
async def topbar(request: Request):
    return await call(request, "identity", "GET", "/api/v1/me", cache=("topbar", 30))


@router.get(
    "/dashboard",
    response_model=DataEnvelope[DashboardView],
    operation_id="getStaffDashboard",
)
async def dashboard(request: Request):
    actor = principal(request)
    data, partial = await svc(request).dashboard(actor, context_from_request(request))
    return envelope(request, data, partial=partial)


@router.get(
    "/properties",
    response_model=DataEnvelope[Page[PropertyView]],
    operation_id="listStaffProperties",
)
async def properties(request: Request):
    require_roles(
        principal(request),
        Role.LEASING_CONSULTANT,
        Role.PROPERTY_MANAGER,
        Role.MANAGER_ADMIN,
    )
    return await call(
        request,
        "leasing",
        "GET",
        "/internal/v1/properties",
        params=dict(request.query_params),
        cache=("properties", 20),
    )


@router.get(
    "/properties/{property_id}",
    response_model=DataEnvelope[PropertyDetailView],
    operation_id="getStaffProperty",
)
async def property_detail(property_id: str, request: Request):
    principal = principal_from_request(request)
    require_roles(
        principal,
        Role.LEASING_CONSULTANT,
        Role.PROPERTY_MANAGER,
        Role.MANAGER_ADMIN,
    )

    async def load():
        context = context_from_request(request)
        base = await svc(request).clients.leasing.request(
            "GET",
            f"/internal/v1/properties/{property_id}",
            principal=principal,
            context=context,
            params={"projection": "management"},
        )
        optional = {
            "leases": svc(request).clients.leasing.request(
                "GET",
                "/internal/v1/leases",
                principal=principal,
                context=context,
                params={
                    "property_id": property_id,
                    "status": "executed,active",
                    "limit": 5,
                },
            ),
            "open_maintenance": svc(request).clients.maintenance.request(
                "GET",
                "/internal/v1/maintenance-orders",
                principal=principal,
                context=context,
                params={
                    "property_id": property_id,
                    "status": "open,assigned,in_progress,blocked",
                    "limit": 20,
                },
            ),
            "recent_reports": svc(request).clients.report.request(
                "GET",
                f"/internal/v1/properties/{property_id}/reports",
                principal=principal,
                context=context,
                params={"limit": 5},
            ),
        }
        import asyncio

        results = await asyncio.gather(*optional.values(), return_exceptions=True)
        partial = []
        data = {"property": base}
        from .errors import ApiError

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

    packed = await svc(request).cached(
        f"property:{property_id}", principal, "management", 15, load
    )
    return envelope(request, packed["data"], partial=packed["partial"])


@router.get(
    "/orders",
    response_model=DataEnvelope[Page[ResourceSummary]],
    operation_id="listStaffOrders",
)
async def orders(request: Request):
    actor = principal(request)
    require_roles(actor, Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN)
    return await call(
        request,
        "leasing",
        "GET",
        "/internal/v1/leases",
        params=dict(request.query_params),
        cache=("orders", 10),
    )


@router.get(
    "/prospects",
    response_model=DataEnvelope[Page[ProspectCaseView]],
    operation_id="listStaffProspects",
)
async def prospects(request: Request):
    return await call(
        request,
        "leasing",
        "GET",
        "/internal/v1/prospect-cases",
        params={**dict(request.query_params), "mine": "true"},
        roles=(Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN),
        cache=("prospects", 10),
    )


@router.get(
    "/prospects/{case_id}",
    response_model=DataEnvelope[ProspectCaseView],
    operation_id="getStaffProspect",
)
async def prospect(case_id: str, request: Request):
    return await call(
        request,
        "leasing",
        "GET",
        f"/internal/v1/prospect-cases/{case_id}",
        roles=(Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN),
    )


@router.patch(
    "/prospects/{case_id}",
    response_model=DataEnvelope[ProspectCaseView],
    operation_id="updateStaffProspect",
)
async def update_prospect(case_id: str, command: StageUpdateRequest, request: Request):
    return await call(
        request,
        "leasing",
        "PATCH",
        f"/internal/v1/prospect-cases/{case_id}",
        body=command.model_dump(exclude_none=True),
        roles=(Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN),
    )


@router.post(
    "/prospects/{case_id}/assign",
    response_model=DataEnvelope[ProspectCaseView],
    operation_id="assignStaffProspect",
)
async def assign_prospect(case_id: str, command: AssignmentRequest, request: Request):
    return await call(
        request,
        "leasing",
        "POST",
        f"/internal/v1/prospect-cases/{case_id}/assignments",
        body={
            "consultant_staff_id": command.assigned_staff_id,
            "version": command.version,
            "reason": command.note,
        },
        roles=(Role.MANAGER_ADMIN,),
    )


@router.get(
    "/contact-threads/{thread_id}/messages",
    response_model=DataEnvelope[Page[ResourceSummary]],
    operation_id="listStaffContactMessages",
)
async def contact_messages(thread_id: str, request: Request):
    return await call(
        request,
        "leasing",
        "GET",
        f"/internal/v1/contact-threads/{thread_id}/messages",
        params=dict(request.query_params),
        roles=(Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN),
    )


@router.post(
    "/contact-threads/{thread_id}/messages",
    response_model=DataEnvelope[ResourceSummary],
    status_code=201,
    operation_id="createStaffContactMessage",
)
async def create_contact_message(
    thread_id: str, command: MessageRequest, request: Request
):
    return await call(
        request,
        "leasing",
        "POST",
        f"/internal/v1/contact-threads/{thread_id}/messages",
        body=command.model_dump(),
        roles=(Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN),
    )


@router.get(
    "/applications",
    response_model=DataEnvelope[Page[ApplicationView]],
    operation_id="listStaffApplications",
)
async def applications(request: Request):
    return await call(
        request,
        "leasing",
        "GET",
        "/internal/v1/applications",
        params=dict(request.query_params),
        roles=(Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN),
        cache=("applications", 10),
    )


@router.get(
    "/applications/{application_id}",
    response_model=DataEnvelope[ApplicationView],
    operation_id="getStaffApplication",
)
async def application(application_id: str, request: Request):
    return await call(
        request,
        "leasing",
        "GET",
        f"/internal/v1/applications/{application_id}",
        roles=(Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN),
    )


async def application_command(
    application_id: str,
    action: str,
    command: VersionRequest | ApproveApplicationRequest | RejectApplicationRequest,
    request: Request,
):
    return await call(
        request,
        "leasing",
        "POST",
        f"/internal/v1/applications/{application_id}/{action}",
        body=command.model_dump(exclude_none=True),
        roles=(Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN),
    )


@router.post(
    "/applications/{application_id}/start-review",
    response_model=DataEnvelope[ApplicationView],
    operation_id="startStaffApplicationReview",
)
async def start_review(application_id: str, command: VersionRequest, request: Request):
    return await application_command(application_id, "start-review", command, request)


@router.post(
    "/applications/{application_id}/approve",
    response_model=DataEnvelope[ApplicationView],
    operation_id="approveStaffApplication",
)
async def approve(
    application_id: str, command: ApproveApplicationRequest, request: Request
):
    return await application_command(application_id, "approve", command, request)


@router.post(
    "/applications/{application_id}/reject",
    response_model=DataEnvelope[ApplicationView],
    operation_id="rejectStaffApplication",
)
async def reject(
    application_id: str, command: RejectApplicationRequest, request: Request
):
    return await application_command(application_id, "reject", command, request)


@router.get(
    "/leases",
    response_model=DataEnvelope[Page[LeaseView]],
    operation_id="listStaffLeases",
)
async def leases(request: Request):
    return await call(
        request,
        "leasing",
        "GET",
        "/internal/v1/leases",
        params=dict(request.query_params),
        roles=(Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN),
        cache=("leases", 10),
    )


@router.get(
    "/leases/{lease_id}",
    response_model=DataEnvelope[LeaseView],
    operation_id="getStaffLease",
)
async def lease(lease_id: str, request: Request):
    actor = principal(request)
    projection = "admin" if actor.role is Role.MANAGER_ADMIN else "staff"
    return await call(
        request,
        "leasing",
        "GET",
        f"/internal/v1/leases/{lease_id}",
        params={"projection": projection},
        roles=(Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN),
    )


@router.post(
    "/leases",
    response_model=DataEnvelope[LeaseView],
    status_code=201,
    operation_id="createStaffLease",
)
async def create_lease(command: CreateLeaseRequest, request: Request):
    return await call(
        request,
        "leasing",
        "POST",
        "/internal/v1/leases",
        body=command.model_dump(),
        roles=(Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN),
    )


@router.patch(
    "/leases/{lease_id}",
    response_model=DataEnvelope[LeaseView],
    operation_id="updateStaffLease",
)
async def update_lease(lease_id: str, command: LeaseTermsRequest, request: Request):
    return await call(
        request,
        "leasing",
        "PATCH",
        f"/internal/v1/leases/{lease_id}",
        body=command.model_dump(exclude_none=True),
        roles=(Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN),
    )


@router.post(
    "/leases/{lease_id}/send-for-signature",
    response_model=DataEnvelope[LeaseView],
    operation_id="sendStaffLeaseForSignature",
)
async def send_signature(
    lease_id: str, command: SendForSignatureRequest, request: Request
):
    return await call(
        request,
        "leasing",
        "POST",
        f"/internal/v1/leases/{lease_id}/send-for-signature",
        body=command.model_dump(exclude_none=True),
        roles=(Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN),
    )


@router.post(
    "/leases/{lease_id}/company-signature",
    response_model=DataEnvelope[LeaseView],
    operation_id="signStaffLease",
)
async def company_signature(
    lease_id: str, command: CompanySignatureRequest, request: Request
):
    return await call(
        request,
        "leasing",
        "POST",
        f"/internal/v1/leases/{lease_id}/company-signature",
        body=command.model_dump(exclude_none=True),
        roles=(Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN),
    )


@router.post(
    "/leases/{lease_id}/execute",
    response_model=DataEnvelope[LeaseView],
    operation_id="executeStaffLease",
)
async def execute_lease(lease_id: str, command: VersionRequest, request: Request):
    return await call(
        request,
        "leasing",
        "POST",
        f"/internal/v1/leases/{lease_id}/execute",
        body=command.model_dump(),
        roles=(Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN),
    )


@router.post(
    "/leases/{lease_id}/cancel",
    response_model=DataEnvelope[LeaseView],
    operation_id="cancelStaffLease",
)
async def cancel_lease(lease_id: str, command: CancelLeaseRequest, request: Request):
    return await call(
        request,
        "leasing",
        "POST",
        f"/internal/v1/leases/{lease_id}/cancel",
        body=command.model_dump(exclude_none=True),
        roles=(Role.LEASING_CONSULTANT, Role.MANAGER_ADMIN),
    )


@router.post(
    "/leases/{lease_id}/terminate",
    response_model=DataEnvelope[LeaseView],
    operation_id="terminateStaffLease",
)
async def terminate_lease(
    lease_id: str, command: TerminateLeaseRequest, request: Request
):
    return await call(
        request,
        "leasing",
        "POST",
        f"/internal/v1/leases/{lease_id}/terminate",
        body=command.model_dump(exclude_none=True),
        roles=(Role.MANAGER_ADMIN,),
    )


@router.post(
    "/leases/{lease_id}/end",
    response_model=DataEnvelope[LeaseView],
    operation_id="endStaffLease",
)
async def end_lease(lease_id: str, command: EndLeaseRequest, request: Request):
    return await call(
        request,
        "leasing",
        "POST",
        f"/internal/v1/leases/{lease_id}/end",
        body=command.model_dump(exclude_none=True),
        roles=(Role.MANAGER_ADMIN,),
    )


@router.get(
    "/maintenance-orders",
    response_model=DataEnvelope[Page[MaintenanceOrderView]],
    operation_id="listStaffMaintenanceOrders",
)
async def maintenance_orders(request: Request):
    return await call(
        request,
        "maintenance",
        "GET",
        "/internal/v1/maintenance-orders",
        params=dict(request.query_params),
        roles=(Role.PROPERTY_MANAGER, Role.MAINTAINER, Role.MANAGER_ADMIN),
        cache=("maintenance", 10),
    )


@router.get(
    "/maintenance-orders/{order_id}",
    response_model=DataEnvelope[MaintenanceOrderView],
    operation_id="getStaffMaintenanceOrder",
)
async def maintenance_order(order_id: str, request: Request):
    return await call(
        request,
        "maintenance",
        "GET",
        f"/internal/v1/maintenance-orders/{order_id}",
        roles=(Role.PROPERTY_MANAGER, Role.MAINTAINER, Role.MANAGER_ADMIN),
    )


@router.post(
    "/maintenance-orders/{order_id}/assign",
    response_model=DataEnvelope[MaintenanceOrderView],
    operation_id="assignStaffMaintenanceOrder",
)
async def assign_order(order_id: str, command: AssignmentRequest, request: Request):
    return await call(
        request,
        "maintenance",
        "POST",
        f"/internal/v1/maintenance-orders/{order_id}/assignments",
        body=command.model_dump(),
        roles=(Role.PROPERTY_MANAGER, Role.MANAGER_ADMIN),
    )


@router.post(
    "/maintenance-orders/{order_id}/transitions",
    response_model=DataEnvelope[MaintenanceOrderView],
    operation_id="transitionStaffMaintenanceOrder",
)
async def transition_order(order_id: str, command: TransitionRequest, request: Request):
    return await call(
        request,
        "maintenance",
        "POST",
        f"/internal/v1/maintenance-orders/{order_id}/transitions",
        body=command.model_dump(exclude_none=True),
        roles=(Role.PROPERTY_MANAGER, Role.MAINTAINER, Role.MANAGER_ADMIN),
    )


@router.post(
    "/maintenance-orders/{order_id}/comments",
    response_model=DataEnvelope[ResourceSummary],
    status_code=201,
    operation_id="commentStaffMaintenanceOrder",
)
async def comment_order(order_id: str, command: MessageRequest, request: Request):
    return await call(
        request,
        "maintenance",
        "POST",
        f"/internal/v1/maintenance-orders/{order_id}/comments",
        body={**command.model_dump(), "visibility": "internal"},
        roles=(Role.PROPERTY_MANAGER, Role.MAINTAINER, Role.MANAGER_ADMIN),
    )


@router.get(
    "/properties/{property_id}/reports",
    response_model=DataEnvelope[Page[ReportView]],
    operation_id="listStaffPropertyReports",
)
async def property_reports(property_id: str, request: Request):
    require_roles(principal(request), Role.PROPERTY_MANAGER, Role.MANAGER_ADMIN)
    return await call(
        request,
        "report",
        "GET",
        f"/internal/v1/properties/{property_id}/reports",
        params=dict(request.query_params),
        cache=(f"property-reports:{property_id}", 15),
    )


@router.post(
    "/properties/{property_id}/reports",
    response_model=DataEnvelope[ReportView],
    status_code=201,
    operation_id="createStaffPropertyReport",
)
async def create_report(
    property_id: str, command: ReportCreateRequest, request: Request
):
    require_report_generation(principal(request))
    return await call(
        request,
        "report",
        "POST",
        f"/internal/v1/properties/{property_id}/reports",
        body=command.model_dump(exclude_none=True),
    )


@router.get(
    "/reports",
    response_model=DataEnvelope[Page[ReportView]],
    operation_id="listStaffReports",
)
async def reports(request: Request):
    require_roles(principal(request), Role.PROPERTY_MANAGER, Role.MANAGER_ADMIN)
    return await call(
        request,
        "report",
        "GET",
        "/internal/v1/reports",
        params=dict(request.query_params),
        cache=("reports", 15),
    )


@router.get(
    "/reports/{report_id}",
    response_model=DataEnvelope[ReportView],
    operation_id="getStaffReport",
)
async def report(report_id: str, request: Request):
    require_roles(principal(request), Role.PROPERTY_MANAGER, Role.MANAGER_ADMIN)
    return await call(
        request,
        "report",
        "GET",
        f"/internal/v1/reports/{report_id}",
        params={"projection": "staff"},
    )


@router.post(
    "/reports/{report_id}/jobs",
    response_model=DataEnvelope[ReportJobView],
    status_code=202,
    operation_id="createStaffReportJob",
)
async def report_job(report_id: str, command: ReportJobRequest, request: Request):
    require_report_generation(principal(request))
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
    operation_id="getStaffReportJob",
)
async def get_report_job(job_id: str, request: Request):
    require_roles(principal(request), Role.PROPERTY_MANAGER, Role.MANAGER_ADMIN)
    return await call(request, "report", "GET", f"/internal/v1/report-jobs/{job_id}")


@router.get(
    "/report-jobs/{job_id}/events",
    responses={200: {"content": {"text/event-stream": {}, "application/x-ndjson": {}}}},
    operation_id="streamStaffReportJobEvents",
)
async def report_job_events(job_id: str, request: Request):
    require_roles(principal(request), Role.PROPERTY_MANAGER, Role.MANAGER_ADMIN)
    response = await svc(request).clients.report.open_stream(
        f"/internal/v1/report-jobs/{job_id}/events",
        principal=principal(request),
        context=context_from_request(request),
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
    operation_id="uploadStaffReportVideo",
)
async def upload_video(
    report_id: str,
    request: Request,
    x_file_name: str = Header(alias="X-File-Name"),
    x_content_sha256: str | None = Header(default=None, alias="X-Content-SHA256"),
):
    actor = principal(request)
    require_report_generation(actor)
    headers = {
        "Content-Type": request.headers.get("content-type", "application/octet-stream"),
        "X-File-Name": x_file_name,
    }
    if x_content_sha256:
        headers["X-Content-SHA256"] = x_content_sha256
    response = await svc(request).clients.report.stream(
        "POST",
        f"/internal/v1/reports/{report_id}/files/videos",
        principal=actor,
        context=context_from_request(request),
        body=request.stream(),
        headers=headers,
    )
    await svc(request).invalidate_after_write(actor)
    return StreamingResponse(
        response.aiter_bytes(),
        status_code=response.status_code,
        media_type=response.headers.get("content-type"),
        background=response.aclose,
    )


@router.get(
    "/admin/staff",
    response_model=DataEnvelope[Page[StaffAdminView]],
    operation_id="listAdminStaff",
)
async def admin_staff(request: Request):
    require_permission(principal(request), "iam:staff:read")
    return await call(
        request,
        "identity",
        "GET",
        "/api/v1/iam/staff",
        params=dict(request.query_params),
        roles=(Role.MANAGER_ADMIN,),
        cache=("admin-staff", 20),
    )


@router.get(
    "/admin/staff/{staff_id}",
    response_model=DataEnvelope[StaffAdminDetailView],
    operation_id="getAdminStaff",
)
async def admin_staff_detail(staff_id: str, request: Request):
    principal = principal_from_request(request)
    require_roles(principal, Role.MANAGER_ADMIN)
    require_permission(principal, "iam:staff:read")
    context = context_from_request(request)
    import asyncio

    staff, history = await asyncio.gather(
        svc(request).clients.identity.request(
            "GET", f"/api/v1/iam/staff/{staff_id}", principal=principal, context=context
        ),
        svc(request).clients.identity.request(
            "GET",
            f"/api/v1/iam/staff/{staff_id}/role-history",
            principal=principal,
            context=context,
        ),
    )
    return envelope(request, {"staff": staff, "role_history": history})
