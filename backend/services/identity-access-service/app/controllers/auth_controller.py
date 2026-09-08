from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.controllers.common import clear_auth_cookies, data, token_response
from app.core.config import Settings, get_settings
from safescan_common.http.errors import bad_request
from app.dependencies import (auth_service, correlation_id, optional_principal,
                              current_principal, validate_csrf)
from app.domain.principal import Principal
from app.schemas.auth import (ActionPasswordRequest, ActionTokenRequest, EmailRequest,
                              GuestSessionRequest, LoginRequest, LogoutAllRequest,
                              PasswordResetRequest, RegisterRequest)
from app.services.auth_service import AuthService


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def request_context(request: Request) -> tuple[str | None, str | None]:
    return request.headers.get("user-agent"), request.client.host if request.client else None


@router.post("/guest-sessions", status_code=status.HTTP_201_CREATED)
def guest_session(_: GuestSessionRequest, service: Annotated[AuthService, Depends(auth_service)]):
    return data(service.create_guest())


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, response: Response,
             service: Annotated[AuthService, Depends(auth_service)],
             settings: Annotated[Settings, Depends(get_settings)],
             cid=Depends(correlation_id)):
    ua, ip = request_context(request)
    result = service.register(email=str(payload.email), username=payload.username, password=payload.password,
                              guest_session_id=payload.guest_session_id, locale=payload.locale,
                              accepted_terms_version=payload.accepted_terms_version, device_label=None,
                              user_agent=ua, ip=ip, correlation_id=cid)
    return token_response(response, settings, result)


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response,
          service: Annotated[AuthService, Depends(auth_service)],
          settings: Annotated[Settings, Depends(get_settings)], cid=Depends(correlation_id)):
    ua, ip = request_context(request)
    result = service.login(email=str(payload.email), password=payload.password,
                           device_label=payload.device_label, remember_me=payload.remember_me,
                           user_agent=ua, ip=ip, correlation_id=cid)
    return token_response(response, settings, result)


@router.post("/refresh", dependencies=[Depends(validate_csrf)])
def refresh(request: Request, response: Response, service: Annotated[AuthService, Depends(auth_service)],
            settings: Annotated[Settings, Depends(get_settings)], cid=Depends(correlation_id),
            ):
    refresh_value = request.cookies.get(settings.cookie_name)
    if not refresh_value:
        raise bad_request("refresh_cookie_missing", "Refresh cookie is required")
    return token_response(response, settings, service.refresh(refresh_value, correlation_id=cid))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(validate_csrf)])
def logout(request: Request, response: Response, service: Annotated[AuthService, Depends(auth_service)],
           settings: Annotated[Settings, Depends(get_settings)], cid=Depends(correlation_id),
           principal: Annotated[Principal | None, Depends(optional_principal)] = None):
    refresh_value = request.cookies.get(settings.cookie_name)
    service.logout(refresh_value, principal, cid)
    clear_auth_cookies(response, settings)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(validate_csrf)])
def logout_all(payload: LogoutAllRequest, response: Response,
               principal: Annotated[Principal, Depends(current_principal)],
               service: Annotated[AuthService, Depends(auth_service)],
               settings: Annotated[Settings, Depends(get_settings)], cid=Depends(correlation_id)):
    service.logout_all(principal, payload.current_password, cid)
    clear_auth_cookies(response, settings)


@router.post("/email-verification/request", status_code=status.HTTP_202_ACCEPTED)
def request_email(payload: EmailRequest, request: Request,
                  service: Annotated[AuthService, Depends(auth_service)],
                  principal: Annotated[Principal | None, Depends(optional_principal)] = None,
                  cid=Depends(correlation_id)):
    email = str(payload.email) if payload.email else None
    if principal and not email:
        email = service.users.get_by_internal_id(principal.user_id)["email"]
    if not email:
        raise bad_request("email_required", "Email is required")
    return data(service.request_action(email=email, purpose="email_verify",
                                       ip=request.client.host if request.client else None,
                                       correlation_id=cid))


@router.post("/email-verification/confirm")
def confirm_email(payload: ActionTokenRequest, service: Annotated[AuthService, Depends(auth_service)],
                  cid=Depends(correlation_id)):
    service.confirm_email(payload.token, cid)
    return data({"email_verified": True})


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def request_password(payload: PasswordResetRequest, request: Request,
                     service: Annotated[AuthService, Depends(auth_service)], cid=Depends(correlation_id)):
    return data(service.request_action(email=str(payload.email), purpose="password_reset",
                                       ip=request.client.host if request.client else None,
                                       correlation_id=cid))


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password(payload: ActionPasswordRequest,
                     service: Annotated[AuthService, Depends(auth_service)], cid=Depends(correlation_id)):
    service.confirm_password(payload.token, payload.new_password, cid)


@router.post("/staff-activation/confirm")
def confirm_staff(payload: ActionPasswordRequest, request: Request, response: Response,
                  service: Annotated[AuthService, Depends(auth_service)],
                  settings: Annotated[Settings, Depends(get_settings)], cid=Depends(correlation_id)):
    ua, ip = request_context(request)
    result = service.confirm_staff_activation(payload.token, payload.new_password,
                                               device_label=payload.device_label,
                                               user_agent=ua, ip=ip, correlation_id=cid)
    return token_response(response, settings, result)
