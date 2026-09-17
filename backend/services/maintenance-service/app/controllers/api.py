from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status

from app.dependencies import current_principal, maintenance_service, privacy_caller
from app.domain.principal import Principal
from app.schemas.commands import (
    AssignmentCreate,
    CommentCreate,
    DeletionCheck,
    DeletionProcess,
    OrderAccessCheck,
    OrderBatchProjection,
    OrderCreate,
    OrderUpdate,
    TransitionCreate,
)
from app.services.maintenance import MaintenanceService

router = APIRouter(prefix="/internal/v1")
Actor = Annotated[Principal, Depends(current_principal)]
Service = Annotated[MaintenanceService, Depends(maintenance_service)]
IdempotencyKey = Annotated[UUID, Header(alias="Idempotency-Key")]


def correlation(request: Request) -> UUID:
    try:
        return UUID(request.state.request_id)
    except (ValueError, TypeError, AttributeError):
        return UUID(int=0)


@router.post("/maintenance-orders", status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    actor: Actor,
    service: Service,
    key: IdempotencyKey,
    request: Request,
):
    return service.create(actor, payload.model_dump(), key, correlation(request))


@router.get("/maintenance-orders")
def list_orders(
    actor: Actor,
    service: Service,
    mine: bool = True,
    property_id: UUID | None = None,
    order_status: str | None = Query(None, alias="status"),
    assignee_id: UUID | None = None,
    priority: str | None = None,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
):
    return service.list(
        actor, property_id, order_status, assignee_id, priority, cursor, limit
    )


@router.get("/maintenance-orders/{order_id}")
def get_order(order_id: UUID, actor: Actor, service: Service):
    return service.get(actor, order_id)


@router.patch("/maintenance-orders/{order_id}")
def update_order(
    order_id: UUID,
    payload: OrderUpdate,
    actor: Actor,
    service: Service,
    key: IdempotencyKey,
    request: Request,
):
    return service.update(
        actor, order_id, payload.model_dump(), key, correlation(request)
    )


@router.post("/maintenance-orders/{order_id}/assignments")
def assign_order(
    order_id: UUID,
    payload: AssignmentCreate,
    actor: Actor,
    service: Service,
    key: IdempotencyKey,
    request: Request,
):
    return service.assign(
        actor, order_id, payload.model_dump(), key, correlation(request)
    )


@router.post("/maintenance-orders/{order_id}/transitions")
def transition_order(
    order_id: UUID,
    payload: TransitionCreate,
    actor: Actor,
    service: Service,
    key: IdempotencyKey,
    request: Request,
):
    return service.transition(
        actor, order_id, payload.model_dump(), key, correlation(request)
    )


@router.post(
    "/maintenance-orders/{order_id}/comments", status_code=status.HTTP_201_CREATED
)
def comment_order(
    order_id: UUID,
    payload: CommentCreate,
    actor: Actor,
    service: Service,
    key: IdempotencyKey,
):
    return service.comment(actor, order_id, payload.model_dump(), key)


@router.get("/maintenance-orders/{order_id}/events")
def order_events(
    order_id: UUID,
    actor: Actor,
    service: Service,
    projection: Literal["tenant", "staff"] = "staff",
    after_sequence: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    return service.events(actor, order_id, projection, after_sequence, limit)


@router.get("/maintenance-orders/{order_id}/work-context")
def work_context(order_id: UUID, actor: Actor, service: Service):
    return service.work_context(actor, order_id)


@router.post("/authorizations/order-access:check")
def order_access(payload: OrderAccessCheck, actor: Actor, service: Service):
    return service.order_access(actor, payload.model_dump())


@router.post("/projections/orders:batch")
def batch_orders(payload: OrderBatchProjection, actor: Actor, service: Service):
    return {"items": service.batch(actor, payload.ids)}


@router.post("/privacy/subject-deletions:check")
def deletion_check(
    payload: DeletionCheck,
    service: Service,
    caller: Annotated[dict, Depends(privacy_caller)],
):
    return service.deletion_check(payload.subject_id)


@router.post(
    "/privacy/subject-deletions/{request_id}", status_code=status.HTTP_202_ACCEPTED
)
def deletion_process(
    request_id: UUID,
    payload: DeletionProcess,
    service: Service,
    caller: Annotated[dict, Depends(privacy_caller)],
):
    return service.process_deletion(request_id, payload.subject_id)
