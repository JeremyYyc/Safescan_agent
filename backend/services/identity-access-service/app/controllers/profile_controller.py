from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.controllers.common import data
from app.dependencies import correlation_id, profile_service, require
from app.domain.principal import Principal
from app.schemas.me import AccountDeleteRequest, PasswordChangeRequest, ProfileUpdateRequest
from app.services.profile_service import ProfileService


router = APIRouter(prefix="/api/v1/me", tags=["me"])
SelfRead = Annotated[Principal, Depends(require("iam:self:read"))]
SelfUpdate = Annotated[Principal, Depends(require("iam:self:update"))]
SelfPassword = Annotated[Principal, Depends(require("iam:self:password_change"))]
SelfSessions = Annotated[Principal, Depends(require("iam:self:sessions_manage"))]


@router.get("")
def me(principal: SelfRead, service: Annotated[ProfileService, Depends(profile_service)]):
    return data(service.me(principal))


@router.patch("/profile")
def update_profile(payload: ProfileUpdateRequest, principal: SelfUpdate,
                   service: Annotated[ProfileService, Depends(profile_service)]):
    return data(service.update_profile(principal, username=payload.username,
                                       avatar=payload.avatar, locale=payload.locale,
                                       version=payload.version))


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(payload: PasswordChangeRequest, principal: SelfPassword,
                    service: Annotated[ProfileService, Depends(profile_service)], cid=Depends(correlation_id)):
    service.change_password(principal, payload.current_password, payload.new_password, cid)


@router.get("/sessions")
def sessions(principal: SelfSessions, service: Annotated[ProfileService, Depends(profile_service)],
             cursor: str | None = None, limit: int = 50):
    return service.list_sessions(principal, cursor, min(max(limit, 1), 200))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(session_id: UUID, principal: SelfSessions,
                   service: Annotated[ProfileService, Depends(profile_service)]):
    service.revoke_session(principal, session_id)


@router.get("/auth-events")
def events(principal: SelfRead, service: Annotated[ProfileService, Depends(profile_service)],
           cursor: str | None = None, event_type: str | None = None, limit: int = 50):
    return service.list_events(principal, cursor, event_type, min(max(limit, 1), 200))


@router.delete("/account", status_code=status.HTTP_202_ACCEPTED)
def delete_account(payload: AccountDeleteRequest, principal: SelfUpdate,
                   service: Annotated[ProfileService, Depends(profile_service)], cid=Depends(correlation_id)):
    service.delete_account(principal, payload.current_password, payload.reason, payload.version, cid)


@router.get("/permissions")
def permissions(principal: SelfRead, service: Annotated[ProfileService, Depends(profile_service)]):
    return data(service.permissions(principal))
