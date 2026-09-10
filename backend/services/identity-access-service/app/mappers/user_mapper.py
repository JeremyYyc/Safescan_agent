from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.tables import (
    customer_profiles,
    permissions,
    role_permissions,
    roles,
    staff,
    user_credentials,
    users,
)


SELF_SCOPES = [
    "iam:self:password_change",
    "iam:self:read",
    "iam:self:sessions_manage",
    "iam:self:update",
]


class UserMapper:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_email(self, email: str, *, for_update: bool = False):
        statement = sa.select(users).where(users.c.email == email)
        if for_update:
            statement = statement.with_for_update()
        return self.session.execute(statement).mappings().first()

    def get_by_public_id(self, public_id: UUID | str, *, for_update: bool = False):
        statement = sa.select(users).where(users.c.public_id == public_id)
        if for_update:
            statement = statement.with_for_update()
        return self.session.execute(statement).mappings().first()

    def get_by_internal_id(self, user_id: int, *, for_update: bool = False):
        statement = sa.select(users).where(users.c.id == user_id)
        if for_update:
            statement = statement.with_for_update()
        return self.session.execute(statement).mappings().first()

    def create_user(self, *, email: str, username: str, account_type: str, status: str,
                    locale: str = "zh-CN") -> dict:
        now = datetime.now().astimezone()
        return dict(
            self.session.execute(
                users.insert()
                .values(
                    public_id=uuid4(), email=email, username=username, account_type=account_type,
                    avatar="", locale=locale, status=status, auth_version=1, version=1,
                    created_at=now, updated_at=now,
                )
                .returning(users)
            ).mappings().one()
        )

    def create_password(self, *, user_id: int, secret_hash: str) -> None:
        now = datetime.now().astimezone()
        self.session.execute(
            user_credentials.insert().values(
                user_id=user_id, credential_type="password", secret_hash=secret_hash,
                algorithm="argon2id", changed_at=now, failed_attempts=0, status="active",
                created_at=now, updated_at=now,
            )
        )

    def get_password(self, user_id: int, *, for_update: bool = False):
        statement = sa.select(user_credentials).where(
            user_credentials.c.user_id == user_id,
            user_credentials.c.credential_type == "password",
            user_credentials.c.status == "active",
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.execute(statement).mappings().first()

    def replace_password(self, credential_id: int, secret_hash: str) -> None:
        now = datetime.now().astimezone()
        self.session.execute(
            user_credentials.update().where(user_credentials.c.id == credential_id).values(
                secret_hash=secret_hash, algorithm="argon2id", changed_at=now,
                failed_attempts=0, locked_until=None, updated_at=now,
            )
        )

    def record_login_failure(self, credential_id: int, failed_attempts: int, locked_until=None) -> None:
        self.session.execute(
            user_credentials.update().where(user_credentials.c.id == credential_id).values(
                failed_attempts=failed_attempts, locked_until=locked_until,
                updated_at=datetime.now().astimezone(),
            )
        )

    def clear_login_failures(self, credential_id: int) -> None:
        self.session.execute(
            user_credentials.update().where(user_credentials.c.id == credential_id).values(
                failed_attempts=0, locked_until=None, updated_at=datetime.now().astimezone()
            )
        )

    def create_customer_profile(self, user_id: int) -> dict:
        now = datetime.now().astimezone()
        return dict(
            self.session.execute(
                customer_profiles.insert().values(
                    user_id=user_id, customer_status="prospect", status_version=1,
                    tenancy_version=0,
                    first_prospect_at=now, created_at=now, updated_at=now,
                ).returning(customer_profiles)
            ).mappings().one()
        )

    def get_customer_profile(self, user_id: int, *, for_update: bool = False):
        statement = sa.select(customer_profiles).where(customer_profiles.c.user_id == user_id)
        if for_update:
            statement = statement.with_for_update()
        return self.session.execute(statement).mappings().first()

    def get_staff_profile(self, user_id: int, *, for_update: bool = False):
        statement = (
            sa.select(
                staff,
                roles.c.public_id.label("role_public_id"),
                roles.c.code.label("role_code"),
                roles.c.name.label("role_name"),
                roles.c.status.label("role_status"),
                roles.c.version.label("role_version"),
            )
            .join(roles, roles.c.id == staff.c.role_id)
            .where(staff.c.user_id == user_id)
        )
        if for_update:
            statement = statement.with_for_update(of=staff)
        return self.session.execute(statement).mappings().first()

    def get_permissions_for_role(self, role_id: int) -> list[str]:
        statement = (
            sa.select(permissions.c.code)
            .join(role_permissions, role_permissions.c.permission_id == permissions.c.id)
            .where(role_permissions.c.role_id == role_id)
            .order_by(permissions.c.code)
        )
        return list(self.session.scalars(statement))

    def update_profile(self, user_id: int, *, username: str | None, avatar: str | None,
                       locale: str | None, version: int):
        values = {"version": users.c.version + 1, "updated_at": datetime.now().astimezone()}
        if username is not None:
            values["username"] = username
        if avatar is not None:
            values["avatar"] = avatar
        if locale is not None:
            values["locale"] = locale
        return self.session.execute(
            users.update().where(users.c.id == user_id, users.c.version == version)
            .values(**values).returning(users)
        ).mappings().first()

    def update_user_status(self, user_id: int, *, status: str, version: int, revoke: bool = True):
        values = {
            "status": status,
            "version": users.c.version + 1,
            "updated_at": datetime.now().astimezone(),
        }
        if revoke:
            values["auth_version"] = users.c.auth_version + 1
        return self.session.execute(
            users.update().where(users.c.id == user_id, users.c.version == version)
            .values(**values).returning(users)
        ).mappings().first()

    def bump_auth_version(self, user_id: int) -> dict:
        return dict(
            self.session.execute(
                users.update().where(users.c.id == user_id).values(
                    auth_version=users.c.auth_version + 1,
                    version=users.c.version + 1,
                    updated_at=datetime.now().astimezone(),
                ).returning(users)
            ).mappings().one()
        )

    def mark_email_verified(self, user_id: int) -> dict:
        now = datetime.now().astimezone()
        return dict(
            self.session.execute(
                users.update().where(users.c.id == user_id).values(
                    email_verified_at=now, version=users.c.version + 1,
                    updated_at=now,
                ).returning(users)
            ).mappings().one()
        )

    def build_view(self, user: dict) -> dict:
        data = dict(user)
        result = {
            "id": str(data["public_id"]), "email": data["email"], "username": data["username"],
            "avatar": data.get("avatar") or "", "account_type": data["account_type"],
            "locale": data["locale"],
            "status": data["status"], "email_verified": data.get("email_verified_at") is not None,
            "portal": "staff" if data["account_type"] == "staff" else "tenant",
            "version": data["version"], "created_at": data["created_at"], "updated_at": data["updated_at"],
            "staff": None, "customer": None,
        }
        if data["account_type"] == "staff":
            profile = self.get_staff_profile(data["id"])
            if profile:
                result["staff"] = {
                    "id": str(profile["public_id"]), "staff_code": profile["staff_code"],
                    "display_name": profile["display_name"],
                    "employment_status": profile["employment_status"],
                    "hired_at": profile["hired_at"], "ended_at": profile["ended_at"],
                    "role": {
                        "id": str(profile["role_public_id"]), "code": profile["role_code"],
                        "name": profile["role_name"], "version": profile["role_version"],
                    },
                }
        else:
            profile = self.get_customer_profile(data["id"])
            if profile:
                result["customer"] = {
                    "status": profile["customer_status"], "status_version": profile["status_version"],
                    "tenancy_version": profile["tenancy_version"],
                    "first_prospect_at": profile["first_prospect_at"],
                    "tenant_since": profile["tenant_since"],
                    "former_tenant_at": profile["former_tenant_at"],
                }
        return result

    def scopes_for(self, user: dict) -> tuple[list[str], dict]:
        scopes = list(SELF_SCOPES)
        extra: dict = {}
        if user["account_type"] == "staff":
            profile = self.get_staff_profile(user["id"])
            if profile:
                scopes.extend(self.get_permissions_for_role(profile["role_id"]))
                extra = {
                    "staff_id": str(profile["public_id"]), "role": profile["role_code"],
                    "rv": profile["role_version"],
                }
        else:
            profile = self.get_customer_profile(user["id"])
            if profile:
                scopes.extend([
                    "application:self:read",
                    "knowledge:read_public",
                    "property:read_market",
                ])
                if profile["customer_status"] == "tenant":
                    scopes.extend([
                        "lease:self:read",
                        "maintenance:self:create",
                        "report:self:create",
                        "report:self:read",
                    ])
                else:
                    scopes.extend([
                        "application:self:create",
                        "application:self:submit",
                        "prospect:self:manage",
                    ])
                    if profile["customer_status"] == "former_tenant":
                        scopes.extend([
                            "lease:self:read_history",
                            "report:self:read_history",
                        ])
                extra = {"customer_status": profile["customer_status"], "cv": profile["status_version"]}
        return sorted(set(scopes)), extra
