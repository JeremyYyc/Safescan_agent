from uuid import UUID

import jwt
from sqlalchemy.orm import Session

from app.core.config import Settings
from safescan_common.http.errors import ApiError, bad_request, conflict, forbidden, not_found, unauthorized
from app.core.security import (create_access_token, decode_access_token, deletion_peppers,
                               subject_fingerprint)
from app.domain.principal import Principal
from app.mappers.admin_mapper import AdminMapper
from app.mappers.user_mapper import UserMapper
from app.mappers.deletion_mapper import DeletionMapper
from app.services.auth_service import AuthService


class InternalService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.admin = AdminMapper(session)
        self.users = UserMapper(session)
        self.deletions = DeletionMapper(session)
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
        if claims.get("aud") not in set(client["allowed_audiences"] or []):
            raise unauthorized("service_audience_invalid", "Service token audience is not allowed")
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
            actor={
                "sub": user.subject,
                "client": principal.subject,
                "account_type": user.account_type,
                **{
                    key: user.claims[key]
                    for key in ("staff_id", "role", "customer_status")
                    if key in user.claims
                },
            },
            lifetime_seconds=300,
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
        scopes, extra = self.users.scopes_for(user) if user["status"] == "active" else ([], {})
        return {"subject_id": str(user["public_id"]), "account_type": user["account_type"],
                "status": user["status"], "auth_version": user["auth_version"],
                "scopes": scopes, **extra}

    def subjects(self, subject_ids: list[UUID]) -> list[dict]:
        return [self.subject(subject_id) for subject_id in subject_ids]

    def apply_customer_event(self, principal: Principal, data: dict) -> dict:
        if principal.subject != "service:property-leasing":
            raise forbidden("service_not_allowed", "Only property-leasing may update customer status")
        if data["event_type"] != "customer.tenancy_status_changed.v1":
            raise bad_request("event_type_invalid", "Customer status event type is not supported")
        customer = self.admin.get_customer(data["customer_subject_id"], for_update=True)
        if not customer:
            tombstone = self.deletions.tombstone_exists([
                subject_fingerprint(str(data["customer_subject_id"]), pepper)
                for _, pepper in deletion_peppers(self.settings)
            ])
            if tombstone:
                raise conflict("subject_already_deleted", "Deleted subject cannot be recreated")
            raise not_found("customer_not_found", "Customer was not found")
        if self.admin.has_customer_status_event(data["event_id"]):
            self.session.rollback()
            return {"accepted": False, "duplicate": True, "stale": False}
        if data["aggregate_version"] <= customer["tenancy_version"]:
            self.session.rollback()
            return {"accepted": False, "duplicate": False, "stale": True}
        to_status = data["to_status"]
        allowed_transitions = {
            "prospect": {"tenant"},
            "former_tenant": {"tenant"},
            "tenant": {"former_tenant"},
        }
        if to_status not in allowed_transitions.get(customer["customer_status"], set()):
            raise bad_request("customer_status_transition_invalid", "Customer status transition is not allowed")
        accepted = self.admin.apply_customer_status_event(
            event_id=data["event_id"], customer_id=customer["id"], to_status=to_status,
            aggregate_version=data["aggregate_version"],
            reason_code=data["event_type"], occurred_at=data["occurred_at"], actor_subject_id=None,
            details={**data["details_redacted"], "lease_id": str(data["lease_id"])},
        )
        self.session.commit()
        return {"accepted": accepted, "duplicate": not accepted, "stale": False}
