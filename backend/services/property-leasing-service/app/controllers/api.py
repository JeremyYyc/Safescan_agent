from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status

from app.dependencies import current_principal, leasing_service
from app.domain.principal import Principal
from app.schemas.commands import (ApplicationCreate, ApplicationUpdate, AuthorizationCheck,
                                  CancelLease, CaseAssignment, CaseUpdate, ContactRequest, DecisionCommand,
                                  LeaseAuthorizationCheck, LeaseCreate, LeaseUpdate, MessageCreate,
                                  RejectCommand, SendForSignature, SignatureCommand,
                                  SubmitApplication, TimedLeaseCommand, VersionCommand,
                                  WithdrawCommand)
from app.services.leasing_service import LeasingService


router = APIRouter(prefix="/internal/v1")
Actor = Annotated[Principal, Depends(current_principal)]
Service = Annotated[LeasingService, Depends(leasing_service)]
IdempotencyKey = Annotated[UUID, Header(alias="Idempotency-Key")]


def correlation(request: Request) -> UUID:
    return UUID(request.state.request_id)


@router.get("/market-properties")
def market_properties(service: Service, q: str | None = None, bedrooms: int | None = Query(None, ge=0),
                      min_rent: Decimal | None = Query(None, ge=0),
                      max_rent: Decimal | None = Query(None, ge=0), cursor: str | None = None,
                      limit: int = Query(20, ge=1, le=100)):
    return service.market_properties(q=q, bedrooms=bedrooms, min_rent=min_rent,
                                     max_rent=max_rent, cursor=cursor, limit=limit)


@router.get("/market-properties/{property_id}")
def market_property(property_id: UUID, service: Service):
    return service.market_property(property_id)


@router.get("/properties")
def properties(actor: Actor, service: Service, property_status: str | None = Query(None, alias="status"),
               building_id: UUID | None = None, cursor: str | None = None,
               limit: int = Query(20, ge=1, le=100)):
    return service.staff_properties(actor, status=property_status, building_id=building_id,
                                    cursor=cursor, limit=limit)


@router.get("/properties/{property_id}")
def property_detail(property_id: UUID, actor: Actor, service: Service):
    return service.staff_property(actor, property_id)


@router.get("/buildings")
def buildings(actor: Actor, service: Service):
    return service.buildings(actor)


@router.post("/contact-requests", status_code=status.HTTP_201_CREATED)
def contact(payload: ContactRequest, actor: Actor, service: Service, key: IdempotencyKey,
            request: Request):
    return service.contact(actor, payload.model_dump(), key, correlation(request))


@router.get("/prospect-cases")
def cases(actor: Actor, service: Service, stage: str | None = None,
          case_status: str | None = Query(None, alias="status"), cursor: str | None = None,
          limit: int = Query(20, ge=1, le=100)):
    return service.cases(actor, stage=stage, status=case_status, cursor=cursor, limit=limit)


@router.get("/prospect-cases/{case_id}")
def case(case_id: UUID, actor: Actor, service: Service):
    return service.get_case(actor, case_id)


@router.patch("/prospect-cases/{case_id}")
def update_case(case_id: UUID, payload: CaseUpdate, actor: Actor, service: Service, request: Request):
    return service.update_case(actor, case_id, payload.model_dump(), correlation(request))


@router.post("/prospect-cases/{case_id}/assignments")
def assign_case(case_id: UUID, payload: CaseAssignment, actor: Actor, service: Service,
                key: IdempotencyKey, request: Request):
    return service.assign_case(actor, case_id, payload.model_dump(), key, correlation(request))


@router.get("/prospect-cases/{case_id}/events")
def case_events(case_id: UUID, actor: Actor, service: Service,
                after_sequence: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return service.case_events(actor, case_id, after_sequence, limit)


@router.get("/contact-threads/{thread_id}/messages")
def messages(thread_id: UUID, actor: Actor, service: Service,
             after_sequence: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return service.messages(actor, thread_id, after_sequence, limit)


@router.post("/contact-threads/{thread_id}/messages", status_code=status.HTTP_201_CREATED)
def post_message(thread_id: UUID, payload: MessageCreate, actor: Actor, service: Service):
    return service.post_message(actor, thread_id, payload.model_dump())


@router.post("/applications", status_code=status.HTTP_201_CREATED)
def create_application(payload: ApplicationCreate, actor: Actor, service: Service,
                       key: IdempotencyKey, request: Request):
    return service.create_application(actor, payload.model_dump(), key, correlation(request))


@router.get("/applications")
def applications(actor: Actor, service: Service, application_status: str | None = Query(None, alias="status"),
                 cursor: str | None = None, limit: int = Query(20, ge=1, le=100)):
    return service.applications(actor, status=application_status, cursor=cursor, limit=limit)


@router.get("/applications/{application_id}")
def application(application_id: UUID, actor: Actor, service: Service):
    return service.get_application(actor, application_id)


@router.patch("/applications/{application_id}")
def update_application(application_id: UUID, payload: ApplicationUpdate, actor: Actor, service: Service):
    return service.update_application(actor, application_id, payload.model_dump())


@router.post("/applications/{application_id}/submit")
def submit_application(application_id: UUID, payload: SubmitApplication, actor: Actor, service: Service,
                       request: Request, key: IdempotencyKey):
    return service.transition_application(actor, application_id, payload.model_dump(), "submit", key,
                                          correlation(request))


@router.post("/applications/{application_id}/start-review")
def start_review(application_id: UUID, payload: VersionCommand, actor: Actor, service: Service,
                 request: Request):
    return service.transition_application(actor, application_id, payload.model_dump(), "start-review", None,
                                          correlation(request))


@router.post("/applications/{application_id}/approve")
def approve_application(application_id: UUID, payload: DecisionCommand, actor: Actor, service: Service,
                        request: Request, key: IdempotencyKey):
    return service.transition_application(actor, application_id, payload.model_dump(), "approve", key,
                                          correlation(request))


@router.post("/applications/{application_id}/reject")
def reject_application(application_id: UUID, payload: RejectCommand, actor: Actor, service: Service,
                       request: Request, key: IdempotencyKey):
    return service.transition_application(actor, application_id, payload.model_dump(), "reject", key,
                                          correlation(request))


@router.post("/applications/{application_id}/withdraw")
def withdraw_application(application_id: UUID, payload: WithdrawCommand, actor: Actor, service: Service,
                         request: Request):
    return service.transition_application(actor, application_id, payload.model_dump(), "withdraw", None,
                                          correlation(request))


@router.post("/leases", status_code=status.HTTP_201_CREATED)
def create_lease(payload: LeaseCreate, actor: Actor, service: Service, key: IdempotencyKey,
                 request: Request):
    return service.create_lease(actor, payload.model_dump(), key, correlation(request))


@router.get("/leases")
def leases(actor: Actor, service: Service, lease_status: str | None = Query(None, alias="status"),
           property_id: UUID | None = None, cursor: str | None = None,
           limit: int = Query(20, ge=1, le=100)):
    return service.leases(actor, status=lease_status, property_id=property_id, cursor=cursor, limit=limit)


@router.get("/leases/{lease_id}")
def lease(lease_id: UUID, actor: Actor, service: Service):
    return service.get_lease(actor, lease_id)


@router.get("/leases/{lease_id}/documents/current")
def lease_document(lease_id: UUID, actor: Actor, service: Service):
    return service.get_document(actor, lease_id)


@router.patch("/leases/{lease_id}")
def update_lease(lease_id: UUID, payload: LeaseUpdate, actor: Actor, service: Service):
    return service.update_lease(actor, lease_id, payload.model_dump())


@router.post("/leases/{lease_id}/send-for-signature")
def send_for_signature(lease_id: UUID, payload: SendForSignature, actor: Actor, service: Service,
                       key: IdempotencyKey, request: Request):
    return service.send_for_signature(actor, lease_id, payload.model_dump(), key, correlation(request))


@router.post("/leases/{lease_id}/tenant-signatures")
def tenant_signature(lease_id: UUID, payload: SignatureCommand, actor: Actor, service: Service,
                     key: IdempotencyKey, request: Request):
    return service.sign_lease(actor, lease_id, payload.model_dump(), key, correlation(request), side="tenant")


@router.post("/leases/{lease_id}/company-signature")
def company_signature(lease_id: UUID, payload: SignatureCommand, actor: Actor, service: Service,
                      key: IdempotencyKey, request: Request):
    return service.sign_lease(actor, lease_id, payload.model_dump(), key, correlation(request), side="company")


@router.post("/leases/{lease_id}/execute")
def execute_lease(lease_id: UUID, payload: VersionCommand, actor: Actor, service: Service,
                  key: IdempotencyKey, request: Request):
    return service.execute_lease(actor, lease_id, payload.model_dump(), key, correlation(request))


@router.post("/leases/{lease_id}/cancel")
def cancel_lease(lease_id: UUID, payload: CancelLease, actor: Actor, service: Service,
                 key: IdempotencyKey, request: Request):
    return service.cancel_or_expire(actor, lease_id, payload.model_dump(), key,
                                    correlation(request), action="cancel")


@router.post("/leases/{lease_id}/expire")
def expire_lease(lease_id: UUID, payload: TimedLeaseCommand, actor: Actor, service: Service,
                 key: IdempotencyKey, request: Request):
    return service.cancel_or_expire(actor, lease_id, payload.model_dump(), key,
                                    correlation(request), action="expire")


@router.post("/leases/{lease_id}/activate")
def activate_lease(lease_id: UUID, payload: TimedLeaseCommand, actor: Actor, service: Service,
                   key: IdempotencyKey, request: Request):
    return service.activate(actor, lease_id, payload.model_dump(), key, correlation(request))


@router.get("/leases/{lease_id}/invoices")
def invoices(lease_id: UUID, actor: Actor, service: Service, invoice_status: str | None = Query(None, alias="status"),
             cursor: str | None = None, limit: int = Query(20, ge=1, le=100)):
    return service.invoices(actor, lease_id, invoice_status, cursor, limit)


@router.post("/authorizations/property-access:check")
def property_access(payload: AuthorizationCheck, actor: Actor, service: Service):
    return service.property_authorization(actor, payload.model_dump())


@router.post("/authorizations/lease-action:check")
def lease_access(payload: LeaseAuthorizationCheck, actor: Actor, service: Service):
    return service.lease_authorization(actor, payload.model_dump())
