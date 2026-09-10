from uuid import UUID

import jwt
from sqlalchemy.orm import Session

from app.core.config import Settings
from safescan_common.http.errors import ApiError, bad_request, forbidden, not_found, unauthorized
from app.core.security import create_access_token, decode_access_token
from app.domain.principal import Principal
from app.mappers.admin_mapper import AdminMapper
from app.mappers.user_mapper import UserMapper
from app.services.auth_service import AuthService


class InternalService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.admin = AdminMapper(session)
        self.users = UserMapper(session)
        self.auth_service = AuthService(session, settings)

    def authenticate_service(self, token: str) -> Principal:
        try:
            claims = decode_access_token(self.settings, token, audience=self.settings.internal_audience)
        except jwt.PyJWTError as exc:
            raise unauthorized("service_token_invalid", "Service authentication required") from exc
        subject = claims.get("sub", "")
        if not subject.startswith("service:"):
            raise unauthorized("service_token_invalid", "Service authentication required")
        code = subject.removeprefix("service:")
        client = self.admin.get_service_client(code)
        if not client or client["status"] != "active":
            raise unauthorized("service_client_inactive", "Service client is not active")
        claimed = set(claims.get("scopes", []))
        allowed = set(client["allowed_scopes"] or [])
        if not claimed.issubset(allowed):
            raise unauthorized("service_scope_invalid", "Service token exceeds configured scopes")
        return Principal(subject=subject, user_id=None, session_internal_id=None, session_id=None,
                         account_type=None, scopes=frozenset(claimed), claims=claims)

    def exchange(self, principal: Principal, *, user_token: str, target_audience: str,
                 requested_scopes: list[str]) -> dict:
        client = self.admin.get_service_client(principal.subject.removeprefix("service:"))
        if target_audience not in (client["allowed_audiences"] or []):
            raise forbidden("audience_not_allowed", "Target audience is not allowed")
        user = self.auth_service.authenticate(user_token)
        scopes = sorted(set(requested_scopes) & set(user.scopes) & set(principal.scopes))
        if set(requested_scopes) - set(scopes):
            raise forbidden("scope_not_delegable", "One or more requested scopes cannot be delegated")
        token, expires = create_access_token(
            self.settings, subject=user.subject, session_id=user.session_id,
            account_type=user.account_type, auth_version=user.claims.get("av"), scopes=scopes,
            audience=target_audience, extra={key: user.claims[key] for key in ("rv", "cv") if key in user.claims},
            actor={"sub": user.subject, "client": principal.subject}, lifetime_seconds=300,
        )
        return {"access_token": token, "token_type": "Bearer", "expires_in": expires,
                "audience": target_audience, "scopes": scopes}

    def introspect(self, token: str, required_audience: str | None) -> dict:
        try:
            claims = decode_access_token(self.settings, token,
                                         audience=required_audience or self.settings.jwt_audience)
            active = True
            if claims.get("account_type") in {"staff", "customer"} and claims.get("aud") == self.settings.jwt_audience:
                self.auth_service.authenticate(token)
        except (jwt.PyJWTError, ApiError):
            return {"active": False}
        return {"active": active, "subject": claims.get("sub"), "actor": claims.get("act"),
                "audience": claims.get("aud"), "auth_version": claims.get("av"),
                "role_version": claims.get("rv"), "customer_status_version": claims.get("cv"),
                "scopes": claims.get("scopes", []), "expires_at": claims.get("exp")}

    def subject(self, subject_id: UUID) -> dict:
        user = self.users.get_by_public_id(subject_id)
        if not user:
            raise not_found("subject_not_found", "Subject was not found")
        scopes, extra = self.users.scopes_for(user)
        return {"subject_id": str(user["public_id"]), "account_type": user["account_type"],
                "status": user["status"], "auth_version": user["auth_version"],
                "scopes": scopes, **extra}

    def subjects(self, subject_ids: list[UUID]) -> list[dict]:
        return [self.subject(subject_id) for subject_id in subject_ids]

    def active_leasing_consultants(self) -> list[dict]:
        return [{"id": str(row["public_id"]), "display_name": row["display_name"],
                 "staff_code": row["staff_code"], "role": row["role_code"]}
                for row in self.admin.active_staff_for_role("leasing_consultant")]

    def active_leasing_consultant(self, staff_id: UUID) -> dict:
        row = self.admin.get_staff(staff_id)
        if (not row or row["user_status"] != "active"
                or row["employment_status"] != "active"
                or row["role_code"] != "leasing_consultant"):
            raise not_found("leasing_consultant_not_found",
                            "An active Leasing Consultant was not found")
        return {"id": str(row["public_id"]), "display_name": row["display_name"],
                "staff_code": row["staff_code"], "role": row["role_code"]}

    def apply_customer_event(self, principal: Principal, data: dict) -> dict:
        if principal.subject != "service:property-leasing":
            raise forbidden("service_not_allowed", "Only property-leasing may update customer status")
        status_by_event = {
            "prospect.created": "prospect", "lease.activated": "tenant", "lease.ended": "former_tenant"
        }
        to_status = status_by_event.get(data["event_type"])
        if not to_status:
            raise bad_request("event_type_invalid", "Customer status event type is not supported")
        customer = self.admin.get_customer(data["customer_subject_id"], for_update=True)
        if not customer:
            raise not_found("customer_not_found", "Customer was not found")
        accepted = self.admin.apply_customer_status_event(
            event_id=data["event_id"], customer_id=customer["id"], to_status=to_status,
            reason_code=data["event_type"], occurred_at=data["occurred_at"], actor_subject_id=None,
            details={**data["details_redacted"], "lease_id": str(data["lease_id"])},
        )
        self.session.commit()
        return {"accepted": accepted, "duplicate": not accepted}
