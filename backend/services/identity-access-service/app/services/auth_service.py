from datetime import timedelta
from uuid import UUID, uuid4

import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from safescan_common.http.errors import ApiError, bad_request, conflict, forbidden, unauthorized
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    new_opaque_token,
    normalize_email,
    password_needs_rehash,
    privacy_hash,
    token_hash,
    utcnow,
    verify_password,
)
from app.domain.principal import Principal
from app.mappers.admin_mapper import AdminMapper
from app.mappers.audit_mapper import AuditMapper
from app.mappers.auth_mapper import AuthMapper
from app.mappers.user_mapper import UserMapper

DUMMY_PASSWORD_HASH = hash_password("ThisIsOnlyForConstantTimeChecks123")


class AuthService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.users = UserMapper(session)
        self.auth = AuthMapper(session)
        self.audit = AuditMapper(session)
        self.admin = AdminMapper(session)

    def _privacy(self, value: str | None) -> str | None:
        return privacy_hash(value, self.settings.jwt_secret.get_secret_value())

    def _issue_login(self, user: dict, *, device_label: str | None, user_agent: str | None,
                     ip: str | None, remember_me: bool, correlation_id: UUID) -> dict:
        now = utcnow()
        refresh_seconds = self.settings.refresh_token_seconds if remember_me else min(
            self.settings.refresh_token_seconds, self.settings.session_idle_seconds
        )
        refresh = new_opaque_token()
        session_row, _ = self.auth.create_session_with_refresh(
            user_id=user["id"], device_label=device_label,
            user_agent_hash=self._privacy(user_agent), ip_hash=self._privacy(ip),
            session_expires_at=now + timedelta(seconds=refresh_seconds),
            refresh_hash=token_hash(refresh), refresh_expires_at=now + timedelta(seconds=refresh_seconds),
        )
        scopes, extra = self.users.scopes_for(user)
        access, expires_in = create_access_token(
            self.settings, subject=str(user["public_id"]), session_id=str(session_row["public_id"]),
            account_type=user["account_type"], auth_version=user["auth_version"], scopes=scopes,
            extra=extra,
        )
        self.audit.add("login_succeeded", correlation_id=correlation_id, user_id=user["id"],
                       session_id=session_row["id"], ip_hash=self._privacy(ip),
                       user_agent_hash=self._privacy(user_agent))
        return {
            "access_token": access, "token_type": "Bearer", "expires_in": expires_in,
            "refresh_token": refresh, "user": self.users.build_view(user), "scopes": scopes,
            "portal": "staff" if user["account_type"] == "staff" else "tenant",
        }

    def register(self, *, email: str, username: str, password: str, guest_session_id: str | None,
                 locale: str | None, accepted_terms_version: str,
                 device_label: str | None, user_agent: str | None, ip: str | None,
                 correlation_id: UUID) -> dict:
        normalized = normalize_email(email)
        try:
            user = self.users.create_user(
                email=normalized, username=username.strip(), account_type="customer", status="active",
                locale=locale or self.settings.default_locale,
            )
            self.users.create_password(user_id=user["id"], secret_hash=hash_password(password))
            self.users.create_customer_profile(user["id"])
            if guest_session_id:
                try:
                    claimed = self.auth.claim_guest(UUID(guest_session_id), user["id"])
                except ValueError:
                    claimed = False
                if not claimed:
                    raise bad_request("guest_session_invalid", "Guest session is invalid or expired")
            result = self._issue_login(
                user, device_label=device_label, user_agent=user_agent, ip=ip,
                remember_me=False, correlation_id=correlation_id,
            )
            self.audit.add("customer_registered", correlation_id=correlation_id, user_id=user["id"],
                           details={"accepted_terms_version": accepted_terms_version,
                                    "locale": locale or self.settings.default_locale})
            self.session.commit()
            return result
        except IntegrityError as exc:
            self.session.rollback()
            raise conflict("email_already_exists", "Email already exists") from exc
        except Exception:
            self.session.rollback()
            raise

    def login(self, *, email: str, password: str, device_label: str | None,
              remember_me: bool, user_agent: str | None, ip: str | None,
              correlation_id: UUID) -> dict:
        normalized = normalize_email(email)
        user = self.users.get_by_email(normalized, for_update=True)
        if not user:
            verify_password(DUMMY_PASSWORD_HASH, password)
            self.audit.add("login_failed", correlation_id=correlation_id,
                           ip_hash=self._privacy(ip), details={"reason": "invalid_credentials"})
            self.session.commit()
            raise unauthorized("invalid_credentials", "Invalid email or password")
        credential = self.users.get_password(user["id"], for_update=True)
        now = utcnow()
        if credential and credential["locked_until"] and credential["locked_until"] > now:
            self.session.rollback()
            raise ApiError(423, "account_temporarily_locked", "Account is temporarily locked")
        if not credential or not verify_password(credential["secret_hash"], password):
            if credential:
                failures = credential["failed_attempts"] + 1
                locked_until = now + timedelta(minutes=15) if failures >= 5 else None
                self.users.record_login_failure(credential["id"], failures, locked_until)
            self.audit.add("login_failed", correlation_id=correlation_id, user_id=user["id"],
                           ip_hash=self._privacy(ip), details={"reason": "invalid_credentials"})
            self.session.commit()
            raise unauthorized("invalid_credentials", "Invalid email or password")
        if user["status"] != "active":
            self.session.rollback()
            raise forbidden("account_unavailable", "Account is not active")
        if user["account_type"] == "staff":
            profile = self.users.get_staff_profile(user["id"])
            if not profile or profile["employment_status"] != "active" or profile["role_status"] != "active":
                self.session.rollback()
                raise forbidden("staff_account_unavailable", "Staff account is not active")
        if password_needs_rehash(credential["secret_hash"]):
            self.users.replace_password(credential["id"], hash_password(password))
        else:
            self.users.clear_login_failures(credential["id"])
        result = self._issue_login(
            dict(user), device_label=device_label, user_agent=user_agent, ip=ip,
            remember_me=remember_me, correlation_id=correlation_id,
        )
        self.session.commit()
        return result

    def refresh(self, value: str, *, correlation_id: UUID) -> dict:
        current = self.auth.get_refresh_for_update(token_hash(value))
        if not current:
            self.session.rollback()
            raise unauthorized("invalid_refresh_token", "Refresh token is invalid")
        now = utcnow()
        if current["status"] != "active":
            self.auth.revoke_family(current["family_id"], current["session_id"], "refresh_token_reused")
            self.audit.add("refresh_token_reused", correlation_id=correlation_id,
                           user_id=current["user_id"], session_id=current["session_id"])
            self.session.commit()
            raise unauthorized("refresh_token_reused", "Refresh token reuse detected")
        if current["expires_at"] <= now or current["session_status"] != "active" or current["session_expires_at"] <= now:
            self.auth.revoke_session(current["session_id"], "expired")
            self.session.commit()
            raise unauthorized("refresh_token_expired", "Refresh token has expired")
        user = self.users.get_by_internal_id(current["user_id"], for_update=True)
        if not user or user["status"] != "active":
            self.auth.revoke_session(current["session_id"], "account_unavailable")
            self.session.commit()
            raise unauthorized("account_unavailable", "Account is not active")
        if user["account_type"] == "staff":
            profile = self.users.get_staff_profile(user["id"])
            if (not profile or profile["employment_status"] != "active"
                    or profile["role_status"] != "active"):
                self.auth.revoke_session(current["session_id"], "staff_account_unavailable")
                self.session.commit()
                raise unauthorized("staff_account_unavailable", "Staff account is not active")
        new_refresh = new_opaque_token()
        self.auth.rotate_refresh(
            current, new_hash=token_hash(new_refresh),
            expires_at=min(current["session_expires_at"], now + timedelta(seconds=self.settings.refresh_token_seconds)),
        )
        scopes, extra = self.users.scopes_for(user)
        access, expires_in = create_access_token(
            self.settings, subject=str(user["public_id"]), session_id=str(current["session_public_id"]),
            account_type=user["account_type"], auth_version=user["auth_version"], scopes=scopes, extra=extra,
        )
        self.audit.add("token_refreshed", correlation_id=correlation_id, user_id=user["id"],
                       session_id=current["session_id"])
        self.session.commit()
        return {
            "access_token": access, "token_type": "Bearer", "expires_in": expires_in,
            "refresh_token": new_refresh, "user": self.users.build_view(user), "scopes": scopes,
            "portal": "staff" if user["account_type"] == "staff" else "tenant",
        }

    def authenticate(self, token: str) -> Principal:
        try:
            claims = decode_access_token(self.settings, token)
        except jwt.PyJWTError as exc:
            raise unauthorized("invalid_token", "Access token is invalid") from exc
        if claims.get("account_type") not in {"staff", "customer"} or not claims.get("sid"):
            raise unauthorized("invalid_token", "Access token is invalid")
        try:
            public_id = UUID(claims["sub"])
            session_public_id = UUID(claims["sid"])
        except (ValueError, TypeError) as exc:
            raise unauthorized("invalid_token", "Access token is invalid") from exc
        user = self.users.get_by_public_id(public_id)
        if not user or user["status"] != "active" or user["auth_version"] != claims.get("av"):
            raise unauthorized("token_stale", "Token is no longer valid")
        session = self.auth.get_session(session_public_id, user["id"])
        if not session or session["status"] != "active" or session["expires_at"] <= utcnow():
            raise unauthorized("session_inactive", "Session is not active")
        scopes, extra = self.users.scopes_for(user)
        if claims.get("rv") != extra.get("rv") or claims.get("cv") != extra.get("cv"):
            raise unauthorized("token_stale", "Token permissions have changed")
        return Principal(
            subject=str(user["public_id"]), user_id=user["id"], session_internal_id=session["id"],
            session_id=str(session["public_id"]), account_type=user["account_type"],
            scopes=frozenset(scopes), claims=claims,
        )

    def logout(self, refresh_value: str | None, principal: Principal | None, correlation_id: UUID) -> None:
        if refresh_value:
            current = self.auth.get_refresh_for_update(token_hash(refresh_value))
            if current:
                self.auth.revoke_session(current["session_id"], "logout")
                self.audit.add("logout", correlation_id=correlation_id, user_id=current["user_id"],
                               session_id=current["session_id"])
        elif principal and principal.session_internal_id:
            self.auth.revoke_session(principal.session_internal_id, "logout")
        self.session.commit()

    def logout_all(self, principal: Principal, password: str, correlation_id: UUID) -> None:
        credential = self.users.get_password(principal.user_id)
        if not credential or not verify_password(credential["secret_hash"], password):
            raise unauthorized("invalid_credentials", "Invalid password")
        self.auth.revoke_all_for_user(principal.user_id, "logout_all")
        self.users.bump_auth_version(principal.user_id)
        self.audit.add("logout_all", correlation_id=correlation_id, user_id=principal.user_id)
        self.session.commit()

    def create_guest(self) -> dict:
        guest = self.auth.create_guest(expires_at=utcnow() + timedelta(minutes=30))
        token, expires = create_access_token(
            self.settings, subject=f"guest:{guest['public_id']}", session_id=None,
            account_type=None, auth_version=None,
            scopes=["property:read_market", "knowledge:read_public"], lifetime_seconds=1800,
        )
        self.session.commit()
        return {"guest_access_token": token, "expires_in": expires,
                "guest_session_id": str(guest["public_id"]),
                "scopes": ["knowledge:read_public", "property:read_market"]}

    def request_action(self, *, email: str, purpose: str, ip: str | None,
                       correlation_id: UUID) -> dict:
        user = self.users.get_by_email(normalize_email(email))
        result = {"accepted": True}
        if user:
            value = new_opaque_token()
            self.auth.issue_action_token(
                user_id=user["id"], purpose=purpose, value_hash=token_hash(value),
                expires_at=utcnow() + timedelta(seconds=self.settings.action_token_seconds),
                requested_ip_hash=self._privacy(ip),
            )
            self.audit.add(f"{purpose}_requested", correlation_id=correlation_id, user_id=user["id"])
            if self.settings.expose_action_tokens:
                result["debug_action_token"] = value
        self.session.commit()
        return result

    def confirm_email(self, value: str, correlation_id: UUID) -> None:
        action = self.auth.consume_action_token(value_hash=token_hash(value), purpose="email_verify")
        if not action:
            self.session.rollback()
            raise bad_request("action_token_invalid", "Action token is invalid or expired")
        self.users.mark_email_verified(action["user_id"])
        self.audit.add("email_verified", correlation_id=correlation_id, user_id=action["user_id"])
        self.session.commit()

    def confirm_password(self, value: str, new_password: str, correlation_id: UUID) -> None:
        action = self.auth.consume_action_token(value_hash=token_hash(value), purpose="password_reset")
        if not action:
            self.session.rollback()
            raise bad_request("action_token_invalid", "Action token is invalid or expired")
        credential = self.users.get_password(action["user_id"], for_update=True)
        if not credential:
            self.session.rollback()
            raise bad_request("credential_missing", "Password credential is unavailable")
        self.users.replace_password(credential["id"], hash_password(new_password))
        self.auth.revoke_all_for_user(action["user_id"], "password_reset")
        self.users.bump_auth_version(action["user_id"])
        self.audit.add("password_reset", correlation_id=correlation_id, user_id=action["user_id"])
        self.session.commit()

    def confirm_staff_activation(self, value: str, new_password: str, *, device_label: str | None,
                                 user_agent: str | None, ip: str | None, correlation_id: UUID) -> dict:
        action = self.auth.consume_action_token(value_hash=token_hash(value), purpose="staff_activate")
        if not action:
            self.session.rollback()
            raise bad_request("action_token_invalid", "Action token is invalid or expired")
        user = self.users.get_by_internal_id(action["user_id"], for_update=True)
        if not user or user["account_type"] != "staff" or user["status"] != "pending":
            self.session.rollback()
            raise conflict("staff_activation_invalid", "Staff account cannot be activated")
        credential = self.users.get_password(user["id"], for_update=True)
        if credential:
            self.users.replace_password(credential["id"], hash_password(new_password))
        else:
            self.users.create_password(user_id=user["id"], secret_hash=hash_password(new_password))
        user = self.users.update_user_status(user["id"], status="active", version=user["version"], revoke=False)
        self.admin.activate_staff(user["id"])
        result = self._issue_login(
            dict(user), device_label=device_label, user_agent=user_agent, ip=ip,
            remember_me=False, correlation_id=correlation_id,
        )
        self.audit.add("staff_activated", correlation_id=correlation_id, user_id=user["id"])
        self.session.commit()
        return result
