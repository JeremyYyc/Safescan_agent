from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.controllers.common import data
from app.dependencies import admin_service, correlation_id, require
from app.domain.principal import Principal
from app.schemas.admin import (OptionalReasonRequest, ReasonRequest, RolePermissionsRequest,
                               RoleStatusRequest, ServiceClientCreateRequest,
                               ServiceClientRotateRequest, ServiceClientUpdateRequest,
                               StaffCreateRequest, StaffEmploymentRequest, StaffRoleRequest,
                               UserStatusRequest)
from app.services.admin_service import AdminService


router = APIRouter(prefix="/api/v1/iam", tags=["iam"])


def access(permission: str):
    return Annotated[Principal, Depends(require(permission))]


@router.get("/users")
def list_users(principal: access("iam:user:read"), service: Annotated[AdminService, Depends(admin_service)],
               account_type: str | None = None, status: str | None = None, q: str | None = None,
               cursor: str | None = None, limit: int = 50):
    return service.list_users(account_type=account_type, status=status, query=q, cursor=cursor,
                              limit=min(max(limit, 1), 200))


@router.get("/users/{user_id}")
def get_user(user_id: UUID, principal: access("iam:user:read"),
             service: Annotated[AdminService, Depends(admin_service)]):
    return data(service.get_user(user_id))


@router.patch("/users/{user_id}/status")
def user_status(user_id: UUID, payload: UserStatusRequest,
                principal: access("iam:user:status_manage"),
                service: Annotated[AdminService, Depends(admin_service)], cid=Depends(correlation_id)):
    return data(service.update_user_status(user_id, status=payload.status, reason=payload.reason,
                                           version=payload.version, actor=principal, correlation_id=cid))


@router.get("/users/{user_id}/auth-events")
def user_events(user_id: UUID, principal: access("iam:audit:read"),
                service: Annotated[AdminService, Depends(admin_service)], event_type: str | None = None,
                cursor: str | None = None, limit: int = 50):
    return service.list_audit_events(user_public_id=user_id, event_type=event_type, cursor=cursor,
                                     limit=min(max(limit, 1), 200))


@router.post("/users/{user_id}/revoke-sessions", status_code=status.HTTP_204_NO_CONTENT)
def revoke_user_sessions(user_id: UUID, payload: ReasonRequest,
                         principal: access("iam:user:status_manage"),
                         service: Annotated[AdminService, Depends(admin_service)], cid=Depends(correlation_id)):
    service.revoke_user_sessions(user_id, reason=payload.reason, actor=principal, correlation_id=cid)


@router.post("/staff", status_code=status.HTTP_201_CREATED)
def create_staff(payload: StaffCreateRequest, principal: access("iam:staff:create"),
                 service: Annotated[AdminService, Depends(admin_service)], cid=Depends(correlation_id)):
    return data(service.create_staff(payload.model_dump(), correlation_id=cid))


@router.get("/staff")
def list_staff(principal: access("iam:staff:read"), service: Annotated[AdminService, Depends(admin_service)],
               role: str | None = None, employment_status: str | None = None, q: str | None = None,
               cursor: str | None = None, limit: int = 50):
    return service.list_staff(role_code=role, employment_status=employment_status, query=q,
                              cursor=cursor, limit=min(max(limit, 1), 200))


@router.get("/staff/{staff_id}")
def get_staff(staff_id: UUID, principal: access("iam:staff:read"),
              service: Annotated[AdminService, Depends(admin_service)]):
    return data(service.get_staff(staff_id))


@router.post("/staff/{staff_id}/activation", status_code=status.HTTP_202_ACCEPTED)
def activate_staff(staff_id: UUID, _: OptionalReasonRequest,
                   principal: access("iam:staff:create"),
                   service: Annotated[AdminService, Depends(admin_service)], cid=Depends(correlation_id)):
    return data(service.resend_activation(staff_id, cid))


@router.patch("/staff/{staff_id}/employment")
def employment(staff_id: UUID, payload: StaffEmploymentRequest,
               principal: access("iam:staff:employment_manage"),
               service: Annotated[AdminService, Depends(admin_service)], cid=Depends(correlation_id)):
    return data(service.change_employment(staff_id, status=payload.employment_status,
                                          effective_at=payload.effective_at, reason=payload.reason,
                                          version=payload.version, actor=principal, correlation_id=cid))


@router.patch("/staff/{staff_id}/role")
def change_role(staff_id: UUID, payload: StaffRoleRequest,
                principal: access("iam:staff:role_manage"),
                service: Annotated[AdminService, Depends(admin_service)], cid=Depends(correlation_id)):
    return data(service.change_role(staff_id, role_public_id=payload.role_id, reason=payload.reason,
                                    version=payload.version, actor=principal, correlation_id=cid))


@router.get("/staff/{staff_id}/role-history")
def role_history(staff_id: UUID, principal: access("iam:staff:read"),
                 service: Annotated[AdminService, Depends(admin_service)], cursor: str | None = None,
                 limit: int = 50):
    return service.role_history(staff_id, cursor, min(max(limit, 1), 200))


@router.get("/customers")
def customers(principal: access("iam:customer:read"), service: Annotated[AdminService, Depends(admin_service)],
              customer_status: str | None = None, q: str | None = None, cursor: str | None = None,
              limit: int = 50):
    return service.list_customers(status=customer_status, query=q, cursor=cursor,
                                  limit=min(max(limit, 1), 200))


@router.get("/customers/{customer_id}")
def customer(customer_id: UUID, principal: access("iam:customer:read"),
             service: Annotated[AdminService, Depends(admin_service)]):
    return data(service.get_customer(customer_id))


@router.get("/customers/{customer_id}/status-events")
def customer_events(customer_id: UUID, principal: access("iam:customer_status:read"),
                    service: Annotated[AdminService, Depends(admin_service)], cursor: str | None = None,
                    limit: int = 50):
    return service.customer_events(customer_id, cursor, min(max(limit, 1), 200))


@router.get("/roles")
def roles(principal: access("rbac:read"), service: Annotated[AdminService, Depends(admin_service)],
          status: str | None = None, cursor: str | None = None, limit: int = 50):
    return service.list_roles(status=status, cursor=cursor, limit=min(max(limit, 1), 200))


@router.get("/roles/{role_id}")
def role(role_id: UUID, principal: access("rbac:read"),
         service: Annotated[AdminService, Depends(admin_service)]):
    return data(service.get_role(role_id))


@router.get("/permissions")
def permissions(principal: access("rbac:read"), service: Annotated[AdminService, Depends(admin_service)],
                risk_level: str | None = None, cursor: str | None = None, limit: int = 50):
    return service.list_permissions(risk_level=risk_level, cursor=cursor, limit=min(max(limit, 1), 200))


@router.put("/roles/{role_id}/permissions")
def replace_permissions(role_id: UUID, payload: RolePermissionsRequest, principal: access("rbac:manage"),
                        service: Annotated[AdminService, Depends(admin_service)], cid=Depends(correlation_id)):
    return data(service.replace_role_permissions(role_id, codes=payload.permission_codes,
                                                 reason=payload.reason, version=payload.version,
                                                 actor=principal, correlation_id=cid))


@router.patch("/roles/{role_id}/status")
def role_status(role_id: UUID, payload: RoleStatusRequest, principal: access("rbac:manage"),
                service: Annotated[AdminService, Depends(admin_service)], cid=Depends(correlation_id)):
    return data(service.update_role_status(role_id, status=payload.status, reason=payload.reason,
                                           version=payload.version, actor=principal, correlation_id=cid))


@router.get("/service-clients")
def clients(principal: access("iam:service_client:manage"),
            service: Annotated[AdminService, Depends(admin_service)], status: str | None = None,
            cursor: str | None = None, limit: int = 50):
    return service.list_service_clients(status=status, cursor=cursor, limit=min(max(limit, 1), 200))


@router.post("/service-clients", status_code=status.HTTP_201_CREATED)
def create_client(payload: ServiceClientCreateRequest, principal: access("iam:service_client:manage"),
                  service: Annotated[AdminService, Depends(admin_service)], cid=Depends(correlation_id)):
    return data(service.create_service_client(payload.model_dump(), actor=principal, correlation_id=cid))


@router.patch("/service-clients/{client_code}")
def update_client(client_code: str, payload: ServiceClientUpdateRequest,
                  principal: access("iam:service_client:manage"),
                  service: Annotated[AdminService, Depends(admin_service)], cid=Depends(correlation_id)):
    values = payload.model_dump(exclude={"version"}, exclude_none=True)
    return data(service.update_service_client(client_code, values, version=payload.version,
                                              actor=principal, correlation_id=cid))


@router.post("/service-clients/{client_code}/rotate")
def rotate_client(client_code: str, payload: ServiceClientRotateRequest,
                  principal: access("iam:service_client:manage"),
                  service: Annotated[AdminService, Depends(admin_service)], cid=Depends(correlation_id)):
    values = payload.model_dump(exclude={"version"})
    return data(service.update_service_client(client_code, values, version=payload.version,
                                              actor=principal, correlation_id=cid))


@router.get("/audit-events")
def audit_events(principal: access("iam:audit:read"), service: Annotated[AdminService, Depends(admin_service)],
                 user_id: UUID | None = None, event_type: str | None = None,
                 cursor: str | None = None, limit: int = 50):
    return service.list_audit_events(user_public_id=user_id, event_type=event_type, cursor=cursor,
                                     limit=min(max(limit, 1), 200))
