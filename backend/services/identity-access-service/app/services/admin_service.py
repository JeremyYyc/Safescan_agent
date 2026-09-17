from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from safescan_common.http.errors import bad_request, conflict, not_found
from app.core.pagination import decode_cursor, page
from app.core.security import normalize_email, utcnow
from app.domain.principal import Principal
from app.mappers.admin_mapper import AdminMapper
from app.mappers.audit_mapper import AuditMapper
from app.mappers.auth_mapper import AuthMapper
from app.mappers.user_mapper import UserMapper


class AdminService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.admin = AdminMapper(session)
        self.users = UserMapper(session)
        self.auth = AuthMapper(session)
        self.audit = AuditMapper(session)

    @staticmethod
    def _user_summary(row):
        return {"id": str(row["public_id"]), "email": row["email"], "username": row["username"],
                "account_type": row["account_type"], "status": row["status"],
                "version": row["version"], "created_at": row["created_at"]}

    @staticmethod
    def _staff_view(row):
        return {
            "id": str(row["public_id"]), "user_id": str(row["user_public_id"]),
            "email": row["email"], "username": row["username"], "user_status": row["user_status"],
            "staff_code": row["staff_code"], "display_name": row["display_name"],
            "employment_status": row["employment_status"], "hired_at": row["hired_at"],
            "ended_at": row["ended_at"], "version": row["user_version"],
            "role": {"id": str(row["role_public_id"]), "code": row["role_code"],
                     "name": row["role_name"], "version": row["role_version"]},
        }

    def list_users(self, *, account_type, status, query, cursor, limit):
        rows = self.admin.list_users(account_type=account_type, status=status, query=query,
                                     after_id=decode_cursor(cursor), limit=limit)
        return page(rows, limit, self._user_summary)

    def get_user(self, public_id: UUID):
        user = self.users.get_by_public_id(public_id)
        if not user:
            raise not_found("user_not_found", "User was not found")
        return self.users.build_view(user)

    def update_user_status(self, public_id: UUID, *, status: str, reason: str, version: int,
                           actor: Principal, correlation_id: UUID):
        user = self.users.get_by_public_id(public_id, for_update=True)
        if not user:
            raise not_found("user_not_found", "User was not found")
        if user["account_type"] == "staff" and status != "active":
            profile = self.users.get_staff_profile(user["id"])
            if profile and profile["role_code"] == "manager_admin" and profile["employment_status"] == "active":
                if len(self.admin.lock_active_manager_admins()) <= 1:
                    raise conflict("last_manager_admin", "The last active manager admin cannot be disabled")
        updated = self.users.update_user_status(user["id"], status=status, version=version)
        if not updated:
            self.session.rollback()
            raise conflict("version_conflict", "User was changed by another request")
        if status != "active":
            self.auth.revoke_all_for_user(user["id"], f"account_{status}")
        self.audit.add("user_status_changed", correlation_id=correlation_id, user_id=user["id"],
                       details={"status": status, "reason": reason, "actor": actor.subject})
        self.session.commit()
        return self.users.build_view(updated)

    def revoke_user_sessions(self, public_id: UUID, *, reason: str, actor: Principal,
                             correlation_id: UUID) -> None:
        user = self.users.get_by_public_id(public_id, for_update=True)
        if not user:
            raise not_found("user_not_found", "User was not found")
        self.auth.revoke_all_for_user(user["id"], reason)
        self.users.bump_auth_version(user["id"])
        self.audit.add("sessions_revoked_by_admin", correlation_id=correlation_id, user_id=user["id"],
                       details={"reason": reason, "actor": actor.subject})
        self.session.commit()

    def create_staff(self, data: dict, *, correlation_id: UUID):
        role = self.admin.get_role(data["role_id"])
        if not role or role["status"] != "active":
            raise bad_request("role_invalid", "Role is not active")
        try:
            user = self.users.create_user(email=normalize_email(data["email"]),
                                          username=data["username"].strip(),
                                          account_type="staff", status="pending")
            self.admin.create_staff(user_id=user["id"], role_id=role["id"],
                                    staff_code=data["staff_code"], display_name=data["display_name"].strip(),
                                    hired_at=data.get("hired_at"))
            action = self._issue_activation(user["id"])
            self.audit.add("staff_created", correlation_id=correlation_id, user_id=user["id"],
                           details={"role": role["code"]})
            self.session.commit()
            result = self.users.build_view(user)
            if self.settings.expose_action_tokens:
                result["debug_action_token"] = action
            return result
        except IntegrityError as exc:
            self.session.rollback()
            raise conflict("staff_identity_conflict", "Email or staff code already exists") from exc

    def _issue_activation(self, user_id: int) -> str:
        from datetime import timedelta
        from app.core.security import new_opaque_token, token_hash
        token = new_opaque_token()
        self.auth.issue_action_token(user_id=user_id, purpose="staff_activate",
                                     value_hash=token_hash(token), expires_at=utcnow() + timedelta(hours=24),
                                     requested_ip_hash=None)
        return token

    def resend_activation(self, staff_public_id: UUID, correlation_id: UUID) -> dict:
        row = self.admin.get_staff(staff_public_id, for_update=True)
        if not row:
            raise not_found("staff_not_found", "Staff member was not found")
        if row["user_status"] != "pending" or row["employment_status"] != "pending":
            raise conflict("staff_not_pending", "Only pending staff can be activated")
        token = self._issue_activation(row["user_id"])
        self.audit.add("staff_activation_requested", correlation_id=correlation_id, user_id=row["user_id"])
        self.session.commit()
        result = {"accepted": True}
        if self.settings.expose_action_tokens:
            result["debug_action_token"] = token
        return result

    def list_staff(self, *, role_code, employment_status, query, cursor, limit):
        rows = self.admin.list_staff(role_code=role_code, employment_status=employment_status,
                                     query=query, after_id=decode_cursor(cursor), limit=limit)
        return page(rows, limit, self._staff_view)

    def get_staff(self, public_id: UUID):
        row = self.admin.get_staff(public_id)
        if not row:
            raise not_found("staff_not_found", "Staff member was not found")
        return self._staff_view(row)

    def change_employment(self, public_id: UUID, *, status: str, effective_at: datetime,
                          reason: str, version: int, actor: Principal, correlation_id: UUID):
        row = self.admin.get_staff(public_id, for_update=True)
        if not row:
            raise not_found("staff_not_found", "Staff member was not found")
        if row["user_version"] != version:
            raise conflict("version_conflict", "Staff member was changed by another request")
        if row["role_code"] == "manager_admin" and row["employment_status"] == "active" and status != "active":
            if len(self.admin.lock_active_manager_admins()) <= 1:
                raise conflict("last_manager_admin", "The last active manager admin cannot be ended")
        self.admin.update_staff_employment(row["id"], status, effective_at)
        self.users.bump_auth_version(row["user_id"])
        self.auth.revoke_all_for_user(row["user_id"], "employment_changed")
        self.audit.add("staff_employment_changed", correlation_id=correlation_id, user_id=row["user_id"],
                       details={"status": status, "reason": reason, "actor": actor.subject})
        self.session.commit()
        return self.get_staff(public_id)

    def change_role(self, public_id: UUID, *, role_public_id: UUID, reason: str, version: int,
                    actor: Principal, correlation_id: UUID):
        row = self.admin.get_staff(public_id, for_update=True)
        target = self.admin.get_role(role_public_id)
        actor_staff = self.users.get_staff_profile(actor.user_id)
        if not row:
            raise not_found("staff_not_found", "Staff member was not found")
        if not target or target["status"] != "active":
            raise bad_request("role_invalid", "Role is not active")
        if row["user_version"] != version:
            raise conflict("version_conflict", "Staff member was changed by another request")
        if row["role_code"] == "manager_admin" and target["code"] != "manager_admin" and row["employment_status"] == "active":
            if len(self.admin.lock_active_manager_admins()) <= 1:
                raise conflict("last_manager_admin", "The last active manager admin cannot change role")
        self.admin.update_staff_role(staff_id=row["id"], from_role_id=row["role_id"],
                                     to_role_id=target["id"], actor_staff_id=actor_staff["id"],
                                     reason=reason, effective_at=utcnow())
        self.users.bump_auth_version(row["user_id"])
        self.auth.revoke_all_for_user(row["user_id"], "role_changed")
        self.audit.add("staff_role_changed", correlation_id=correlation_id, user_id=row["user_id"],
                       details={"role": target["code"], "reason": reason, "actor": actor.subject})
        self.session.commit()
        return self.get_staff(public_id)

    def role_history(self, public_id: UUID, cursor, limit):
        row = self.admin.get_staff(public_id)
        if not row:
            raise not_found("staff_not_found", "Staff member was not found")
        rows = self.admin.role_history(row["id"], after_id=decode_cursor(cursor), limit=limit)
        return page(rows, limit, lambda item: {
            "id": item["id"], "to_role": {"id": str(item["to_role_public_id"]), "code": item["to_role_code"]},
            "reason": item["reason"], "effective_at": item["effective_at"], "created_at": item["created_at"],
        })

    def list_customers(self, *, status, query, cursor, limit):
        rows = self.admin.list_customers(status=status, query=query, after_id=decode_cursor(cursor), limit=limit)
        return page(rows, limit, lambda row: {
            "id": str(row["user_public_id"]), "email": row["email"], "username": row["username"],
            "user_status": row["user_status"], "customer_status": row["customer_status"],
            "status_version": row["status_version"], "tenancy_version": row["tenancy_version"],
            "created_at": row["created_at"],
        })

    def get_customer(self, public_id: UUID):
        row = self.admin.get_customer(public_id)
        if not row:
            raise not_found("customer_not_found", "Customer was not found")
        return {"id": str(row["user_public_id"]), "email": row["email"], "username": row["username"],
                "user_status": row["user_status"], "customer_status": row["customer_status"],
                "status_version": row["status_version"], "tenancy_version": row["tenancy_version"],
                "first_prospect_at": row["first_prospect_at"],
                "tenant_since": row["tenant_since"], "former_tenant_at": row["former_tenant_at"]}

    def customer_events(self, public_id: UUID, cursor, limit):
        row = self.admin.get_customer(public_id)
        if not row:
            raise not_found("customer_not_found", "Customer was not found")
        rows = self.admin.customer_status_events(row["id"], after_id=decode_cursor(cursor), limit=limit)
        return page(rows, limit, lambda item: {
            "id": item["id"], "from_status": item["from_status"], "to_status": item["to_status"],
            "reason_code": item["reason_code"], "effective_at": item["effective_at"],
            "source_event_id": str(item["source_event_id"]) if item["source_event_id"] else None,
            "source_aggregate_version": item["source_aggregate_version"],
            "details": item["details_redacted"],
        })

    @staticmethod
    def _role_view(row, permission_codes: list[str] | None = None):
        result = {"id": str(row["public_id"]), "code": row["code"], "name": row["name"],
                  "status": row["status"], "version": row["version"]}
        if permission_codes is not None:
            result["permission_codes"] = permission_codes
        return result

    def list_roles(self, *, status, cursor, limit):
        rows = self.admin.list_roles(status=status, after_id=decode_cursor(cursor), limit=limit)
        return page(rows, limit, self._role_view)

    def get_role(self, public_id: UUID):
        role = self.admin.get_role(public_id)
        if not role:
            raise not_found("role_not_found", "Role was not found")
        return self._role_view(role, self.admin.role_permission_codes(role["id"]))

    def list_permissions(self, *, risk_level, cursor, limit):
        rows = self.admin.list_permissions(risk_level=risk_level, after_id=decode_cursor(cursor), limit=limit)
        return page(rows, limit, lambda row: {"code": row["code"], "description": row["description"],
                                               "risk_level": row["risk_level"]})

    def replace_role_permissions(self, public_id: UUID, *, codes: list[str], reason: str,
                                 version: int, actor: Principal, correlation_id: UUID):
        role = self.admin.get_role(public_id, for_update=True)
        if not role:
            raise not_found("role_not_found", "Role was not found")
        updated = self.admin.replace_role_permissions(role["id"], codes, version)
        if updated is None:
            raise conflict("version_conflict", "Role was changed by another request")
        if updated is False:
            raise bad_request("permission_invalid", "One or more permission codes are invalid")
        self.audit.add("role_permissions_changed", correlation_id=correlation_id,
                       details={"role": role["code"], "reason": reason, "actor": actor.subject,
                                "permission_codes": sorted(set(codes))})
        self.session.commit()
        return self._role_view(updated, self.admin.role_permission_codes(role["id"]))

    def update_role_status(self, public_id: UUID, *, status: str, reason: str, version: int,
                           actor: Principal, correlation_id: UUID):
        role = self.admin.get_role(public_id, for_update=True)
        if not role:
            raise not_found("role_not_found", "Role was not found")
        if role["code"] == "manager_admin" and status != "active":
            raise conflict("protected_system_role", "The manager_admin role cannot be disabled")
        updated = self.admin.update_role_status(role["id"], status, version)
        if not updated:
            raise conflict("version_conflict", "Role was changed by another request")
        self.audit.add("role_status_changed", correlation_id=correlation_id,
                       details={"role": role["code"], "status": status, "reason": reason,
                                "actor": actor.subject})
        self.session.commit()
        return self._role_view(updated, self.admin.role_permission_codes(role["id"]))

    @staticmethod
    def _client_view(row):
        return {"client_code": row["client_code"], "allowed_audiences": row["allowed_audiences"],
                "allowed_scopes": row["allowed_scopes"], "status": row["status"],
                "key_id": row["key_id"], "version": row["version"],
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def list_service_clients(self, *, status, cursor, limit):
        rows = self.admin.list_service_clients(status=status, after_id=decode_cursor(cursor), limit=limit)
        return page(rows, limit, self._client_view)

    def create_service_client(self, data: dict, *, actor: Principal, correlation_id: UUID):
        try:
            row = self.admin.create_service_client(data)
            self.audit.add("service_client_created", correlation_id=correlation_id,
                           details={"client_code": row["client_code"], "actor": actor.subject})
            self.session.commit()
            return self._client_view(row)
        except IntegrityError as exc:
            self.session.rollback()
            raise conflict("service_client_exists", "Service client already exists") from exc

    def update_service_client(self, code: str, data: dict, *, version: int,
                              actor: Principal, correlation_id: UUID):
        if not self.admin.get_service_client(code):
            raise not_found("service_client_not_found", "Service client was not found")
        row = self.admin.update_service_client(code, data, version)
        if not row:
            raise conflict("version_conflict", "Service client was changed by another request")
        self.audit.add("service_client_changed", correlation_id=correlation_id,
                       details={"client_code": code, "actor": actor.subject})
        self.session.commit()
        return self._client_view(row)

    def list_audit_events(self, *, user_public_id: UUID | None, event_type, cursor, limit):
        user_id = None
        if user_public_id:
            user = self.users.get_by_public_id(user_public_id)
            if not user:
                raise not_found("user_not_found", "User was not found")
            user_id = user["id"]
        rows = self.audit.list_events(user_id=user_id, event_type=event_type,
                                      after_id=decode_cursor(cursor), limit=limit)
        return page(rows, limit, lambda row: {
            "id": row["id"], "event_type": row["event_type"], "occurred_at": row["occurred_at"],
            "correlation_id": str(row["correlation_id"]), "details": row["details_redacted"],
        })
