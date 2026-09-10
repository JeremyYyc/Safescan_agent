from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.controllers.common import data
from app.dependencies import internal_service, require_service
from app.domain.principal import Principal
from app.schemas.internal import (CustomerStatusEventRequest, SubjectBatchRequest,
                                  TokenExchangeRequest, TokenIntrospectionRequest)
from app.services.internal_service import InternalService


router = APIRouter(prefix="/internal/v1", tags=["internal"])


def service_access(scope: str):
    return Annotated[Principal, Depends(require_service(scope))]


@router.post("/tokens/exchange")
def exchange(payload: TokenExchangeRequest, principal: service_access("identity:token_exchange"),
             service: Annotated[InternalService, Depends(internal_service)]):
    return data(service.exchange(principal, user_token=payload.user_token,
                                 target_audience=payload.target_audience,
                                 requested_scopes=payload.requested_scopes))


@router.post("/tokens/introspect")
def introspect(payload: TokenIntrospectionRequest,
               principal: service_access("identity:token_introspect"),
               service: Annotated[InternalService, Depends(internal_service)]):
    return data(service.introspect(payload.token, payload.required_audience))


@router.get("/subjects/{subject_id}")
def subject(subject_id: UUID, principal: service_access("identity:subject_read"),
            service: Annotated[InternalService, Depends(internal_service)],
            fields: Annotated[list[str] | None, Query()] = None):
    projection = service.subject(subject_id)
    if fields:
        projection = {key: value for key, value in projection.items()
                      if key in set(fields) | {"subject_id"}}
    return data(projection)


@router.post("/subjects/batch")
def subjects(payload: SubjectBatchRequest, principal: service_access("identity:subject_read"),
             service: Annotated[InternalService, Depends(internal_service)]):
    return data(service.subjects(payload.subject_ids))


@router.get("/staff/leasing-consultants")
def leasing_consultants(principal: service_access("identity:subject_read"),
                        service: Annotated[InternalService, Depends(internal_service)]):
    return data({"items": service.active_leasing_consultants()})


@router.get("/staff/leasing-consultants/{staff_id}")
def leasing_consultant(staff_id: UUID, principal: service_access("identity:subject_read"),
                       service: Annotated[InternalService, Depends(internal_service)]):
    return data(service.active_leasing_consultant(staff_id))


@router.post("/customer-status-events", status_code=status.HTTP_202_ACCEPTED)
def customer_status(payload: CustomerStatusEventRequest,
                    principal: service_access("identity:customer_status_write"),
                    service: Annotated[InternalService, Depends(internal_service)]):
    return data(service.apply_customer_event(principal, payload.model_dump()))
