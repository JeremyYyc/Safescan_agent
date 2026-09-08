from uuid import UUID

from sqlalchemy.orm import Session

from safescan_common.http.errors import conflict, forbidden, not_found, unauthorized
from app.core.pagination import decode_cursor, page
from app.core.security import hash_password, verify_password
from app.domain.principal import Principal
from app.mappers.audit_mapper import AuditMapper
from app.mappers.auth_mapper import AuthMapper
from app.mappers.user_mapper import UserMapper


class ProfileService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserMapper(session)
        self.auth = AuthMapper(session)
        self.audit = AuditMapper(session)

    def me(self, principal: Principal) -> dict:
        user = self.users.get_by_internal_id(principal.user_id)
        if not user:
            raise not_found("user_not_found", "User was not found")
        scopes, _ = self.users.scopes_for(user)
        return {"user": self.users.build_view(user), "scopes": scopes}

    def update_profile(self, principal: Principal, *, username: str | None, avatar: str | None,
                       locale: str | None, version: int) -> dict:
        if username is None and avatar is None and locale is None:
            raise conflict("profile_no_changes", "No supported profile changes were supplied")
        updated = self.users.update_profile(
            principal.user_id, username=username.strip() if username is not None else None,
            avatar=avatar, locale=locale, version=version,
        )
        if not updated:
            self.session.rollback()
            raise conflict("version_conflict", "Profile was changed by another request")
        self.session.commit()
        return self.users.build_view(updated)

    def change_password(self, principal: Principal, current_password: str, new_password: str,
                        correlation_id: UUID) -> None:
        credential = self.users.get_password(principal.user_id, for_update=True)
        if not credential or not verify_password(credential["secret_hash"], current_password):
            self.session.rollback()
            raise unauthorized("invalid_credentials", "Current password is invalid")
        self.users.replace_password(credential["id"], hash_password(new_password))
        self.auth.revoke_all_for_user(
            principal.user_id, "password_changed", except_session_id=principal.session_internal_id
        )
        self.audit.add("password_changed", correlation_id=correlation_id, user_id=principal.user_id,
                       session_id=principal.session_internal_id)
        self.session.commit()

    def list_sessions(self, principal: Principal, cursor: str | None, limit: int):
        rows = self.auth.list_sessions(principal.user_id, after_id=decode_cursor(cursor), limit=limit)
        return page(rows, limit, lambda row: {
            "id": str(row["public_id"]), "device_label": row["device_label"], "status": row["status"],
            "current": str(row["public_id"]) == principal.session_id,
            "last_seen_at": row["last_seen_at"], "expires_at": row["expires_at"],
        })

    def revoke_session(self, principal: Principal, session_public_id: UUID) -> None:
        target = self.auth.get_session(session_public_id, principal.user_id)
        if target:
            self.auth.revoke_session(target["id"], "user_revoked")
            self.session.commit()

    def list_events(self, principal: Principal, cursor: str | None, event_type: str | None, limit: int):
        rows = self.audit.list_events(user_id=principal.user_id, event_type=event_type,
                                      after_id=decode_cursor(cursor), limit=limit)
        return page(rows, limit, lambda row: {
            "id": row["id"], "event_type": row["event_type"], "occurred_at": row["occurred_at"],
            "correlation_id": str(row["correlation_id"]), "details": row["details_redacted"],
        })

    def delete_account(self, principal: Principal, current_password: str, reason: str | None,
                       version: int, correlation_id: UUID) -> None:
        if principal.account_type != "customer":
            raise forbidden("staff_self_delete_forbidden", "Staff accounts must be managed by an administrator")
        credential = self.users.get_password(principal.user_id)
        if not credential or not verify_password(credential["secret_hash"], current_password):
            raise unauthorized("invalid_credentials", "Current password is invalid")
        updated = self.users.update_user_status(principal.user_id, status="deleted", version=version)
        if not updated:
            self.session.rollback()
            raise conflict("version_conflict", "Account was changed by another request")
        self.auth.revoke_all_for_user(principal.user_id, "account_deleted")
        self.audit.add("account_deleted", correlation_id=correlation_id, user_id=principal.user_id,
                       details={"reason": reason or "self_requested"})
        self.session.commit()

    def permissions(self, principal: Principal) -> dict:
        user = self.users.get_by_internal_id(principal.user_id)
        scopes, extra = self.users.scopes_for(user)
        return {"scopes": scopes, **extra, "auth_version": user["auth_version"]}
