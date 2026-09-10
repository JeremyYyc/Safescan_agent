from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.tables import (
    customer_profiles,
    customer_status_events,
    permissions,
    role_permissions,
    roles,
    service_clients,
    staff,
    staff_role_history,
    users,
)


class AdminMapper:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _page(statement, table, after_id: int | None, limit: int):
        if after_id is not None:
            statement = statement.where(table.c.id < after_id)
        return statement.order_by(table.c.id.desc()).limit(limit + 1)

    def list_users(self, *, account_type: str | None, status: str | None, query: str | None,
                   after_id: int | None, limit: int):
        statement = sa.select(users)
        if account_type:
            statement = statement.where(users.c.account_type == account_type)
        if status:
            statement = statement.where(users.c.status == status)
        if query:
            pattern = f"%{query.strip().lower()}%"
            statement = statement.where(sa.or_(users.c.email.ilike(pattern), users.c.username.ilike(pattern)))
        return list(self.session.execute(self._page(statement, users, after_id, limit)).mappings())

    def get_role(self, public_id: UUID | str, *, for_update: bool = False):
        statement = sa.select(roles).where(roles.c.public_id == public_id)
        if for_update:
            statement = statement.with_for_update()
        return self.session.execute(statement).mappings().first()

    def get_role_by_code(self, code: str):
        return self.session.execute(sa.select(roles).where(roles.c.code == code)).mappings().first()

    def create_staff(self, *, user_id: int, role_id: int, staff_code: str,
                     display_name: str, hired_at: datetime | None) -> dict:
        now = datetime.now().astimezone()
        return dict(self.session.execute(
            staff.insert().values(
                public_id=uuid4(), user_id=user_id, role_id=role_id, staff_code=staff_code,
                display_name=display_name, employment_status="pending", hired_at=hired_at,
                created_at=now, updated_at=now,
            ).returning(staff)
        ).mappings().one())

    def get_staff(self, public_id: UUID | str, *, for_update: bool = False):
        statement = (
            sa.select(staff, users.c.public_id.label("user_public_id"), users.c.email,
                      users.c.username, users.c.status.label("user_status"), users.c.version.label("user_version"),
                      roles.c.public_id.label("role_public_id"), roles.c.code.label("role_code"),
                      roles.c.name.label("role_name"), roles.c.version.label("role_version"))
            .join(users, users.c.id == staff.c.user_id)
            .join(roles, roles.c.id == staff.c.role_id)
            .where(staff.c.public_id == public_id)
        )
        if for_update:
            statement = statement.with_for_update(of=staff)
        return self.session.execute(statement).mappings().first()

    def list_staff(self, *, role_code: str | None, employment_status: str | None,
                   query: str | None, after_id: int | None, limit: int):
        statement = (
            sa.select(staff, users.c.public_id.label("user_public_id"), users.c.email,
                      users.c.username, users.c.status.label("user_status"),
                      users.c.version.label("user_version"),
                      roles.c.public_id.label("role_public_id"), roles.c.code.label("role_code"),
                      roles.c.name.label("role_name"), roles.c.version.label("role_version"))
            .join(users, users.c.id == staff.c.user_id).join(roles, roles.c.id == staff.c.role_id)
        )
        if role_code:
            statement = statement.where(roles.c.code == role_code)
        if employment_status:
            statement = statement.where(staff.c.employment_status == employment_status)
        if query:
            pattern = f"%{query.strip().lower()}%"
            statement = statement.where(sa.or_(staff.c.staff_code.ilike(pattern),
                                                 staff.c.display_name.ilike(pattern), users.c.email.ilike(pattern)))
        return list(self.session.execute(self._page(statement, staff, after_id, limit)).mappings())

    def active_staff_for_role(self, role_code: str) -> list:
        statement = (
            sa.select(staff.c.public_id, staff.c.display_name, staff.c.staff_code,
                      roles.c.code.label("role_code"))
            .join(users, users.c.id == staff.c.user_id)
            .join(roles, roles.c.id == staff.c.role_id)
            .where(roles.c.code == role_code, roles.c.status == "active",
                   users.c.status == "active", staff.c.employment_status == "active")
            .order_by(staff.c.public_id)
        )
        return list(self.session.execute(statement).mappings())

    def lock_active_manager_admins(self) -> list[int]:
        return list(self.session.scalars(
            sa.select(staff.c.id).join(users, users.c.id == staff.c.user_id).join(roles, roles.c.id == staff.c.role_id)
            .where(roles.c.code == "manager_admin", users.c.status == "active",
                   staff.c.employment_status == "active")
            .order_by(staff.c.id).with_for_update(of=staff)
        ))

    def update_staff_employment(self, staff_id: int, status: str, effective_at: datetime) -> None:
        self.session.execute(staff.update().where(staff.c.id == staff_id).values(
            employment_status=status, ended_at=effective_at if status == "ended" else None,
            updated_at=datetime.now().astimezone(),
        ))

    def activate_staff(self, user_id: int) -> None:
        now = datetime.now().astimezone()
        self.session.execute(staff.update().where(staff.c.user_id == user_id).values(
            employment_status="active", hired_at=sa.func.coalesce(staff.c.hired_at, now),
            ended_at=None, updated_at=now,
        ))

    def update_staff_role(self, *, staff_id: int, from_role_id: int, to_role_id: int,
                          actor_staff_id: int, reason: str, effective_at: datetime) -> None:
        now = datetime.now().astimezone()
        self.session.execute(staff.update().where(staff.c.id == staff_id).values(
            role_id=to_role_id, updated_at=now
        ))
        self.session.execute(staff_role_history.insert().values(
            staff_id=staff_id, from_role_id=from_role_id, to_role_id=to_role_id,
            changed_by_staff_id=actor_staff_id, reason=reason,
            effective_at=effective_at, created_at=now,
        ))

    def role_history(self, staff_id: int, *, after_id: int | None, limit: int):
        statement = (
            sa.select(staff_role_history, roles.c.public_id.label("to_role_public_id"),
                      roles.c.code.label("to_role_code"))
            .join(roles, roles.c.id == staff_role_history.c.to_role_id)
            .where(staff_role_history.c.staff_id == staff_id)
        )
        return list(self.session.execute(self._page(statement, staff_role_history, after_id, limit)).mappings())

    def list_customers(self, *, status: str | None, query: str | None,
                       after_id: int | None, limit: int):
        statement = sa.select(customer_profiles, users.c.public_id.label("user_public_id"),
                              users.c.email, users.c.username, users.c.status.label("user_status"))\
            .join(users, users.c.id == customer_profiles.c.user_id)
        if status:
            statement = statement.where(customer_profiles.c.customer_status == status)
        if query:
            pattern = f"%{query.strip().lower()}%"
            statement = statement.where(sa.or_(users.c.email.ilike(pattern), users.c.username.ilike(pattern)))
        return list(self.session.execute(self._page(statement, customer_profiles, after_id, limit)).mappings())

    def get_customer(self, public_user_id: UUID | str, *, for_update: bool = False):
        statement = sa.select(customer_profiles, users.c.public_id.label("user_public_id"),
                              users.c.email, users.c.username, users.c.status.label("user_status"),
                              users.c.auth_version, users.c.version.label("user_version"))\
            .join(users, users.c.id == customer_profiles.c.user_id)\
            .where(users.c.public_id == public_user_id)
        if for_update:
            statement = statement.with_for_update(of=customer_profiles)
        return self.session.execute(statement).mappings().first()

    def customer_status_events(self, customer_id: int, *, after_id: int | None, limit: int):
        statement = sa.select(customer_status_events).where(customer_status_events.c.customer_id == customer_id)
        return list(self.session.execute(self._page(statement, customer_status_events, after_id, limit)).mappings())

    def apply_customer_status_event(self, *, event_id: UUID, customer_id: int, to_status: str,
                                    reason_code: str, occurred_at: datetime, actor_subject_id: UUID | None,
                                    details: dict) -> bool:
        current = self.session.execute(sa.select(customer_profiles).where(
            customer_profiles.c.id == customer_id
        ).with_for_update()).mappings().one()
        now = datetime.now().astimezone()
        inserted = self.session.scalar(pg_insert(customer_status_events).values(
            customer_id=customer_id, from_status=current["customer_status"], to_status=to_status,
            reason_code=reason_code, effective_at=occurred_at, source_event_id=event_id,
            actor_subject_id=actor_subject_id, details_redacted=details, created_at=now,
        ).on_conflict_do_nothing(
            index_elements=[customer_status_events.c.source_event_id],
            index_where=customer_status_events.c.source_event_id.is_not(None),
        )
         .returning(customer_status_events.c.id))
        if inserted is None:
            return False
        self.session.execute(customer_profiles.update().where(customer_profiles.c.id == customer_id).values(
            customer_status=to_status, status_version=customer_profiles.c.status_version + 1,
            tenant_since=occurred_at if to_status == "tenant" else current["tenant_since"],
            former_tenant_at=occurred_at if to_status == "former_tenant" else None,
            updated_at=now,
        ))
        return True

    def list_roles(self, *, status: str | None, after_id: int | None, limit: int):
        statement = sa.select(roles)
        if status:
            statement = statement.where(roles.c.status == status)
        return list(self.session.execute(self._page(statement, roles, after_id, limit)).mappings())

    def list_permissions(self, *, risk_level: str | None, after_id: int | None, limit: int):
        statement = sa.select(permissions)
        if risk_level:
            statement = statement.where(permissions.c.risk_level == risk_level)
        return list(self.session.execute(self._page(statement, permissions, after_id, limit)).mappings())

    def role_permission_codes(self, role_id: int) -> list[str]:
        return list(self.session.scalars(sa.select(permissions.c.code)
            .join(role_permissions, role_permissions.c.permission_id == permissions.c.id)
            .where(role_permissions.c.role_id == role_id).order_by(permissions.c.code)))

    def replace_role_permissions(self, role_id: int, codes: list[str], expected_version: int):
        role = self.session.execute(sa.select(roles).where(
            roles.c.id == role_id, roles.c.version == expected_version
        ).with_for_update()).mappings().first()
        if not role:
            return None
        permission_rows = list(self.session.execute(sa.select(permissions).where(
            permissions.c.code.in_(codes)
        )).mappings()) if codes else []
        if len(permission_rows) != len(set(codes)):
            return False
        self.session.execute(role_permissions.delete().where(role_permissions.c.role_id == role_id))
        now = datetime.now().astimezone()
        if permission_rows:
            self.session.execute(role_permissions.insert(), [
                {"role_id": role_id, "permission_id": row["id"], "created_at": now}
                for row in permission_rows
            ])
        return self.session.execute(roles.update().where(roles.c.id == role_id).values(
            version=roles.c.version + 1, updated_at=now
        ).returning(roles)).mappings().one()

    def update_role_status(self, role_id: int, status: str, expected_version: int):
        return self.session.execute(roles.update().where(
            roles.c.id == role_id, roles.c.version == expected_version
        ).values(status=status, version=roles.c.version + 1,
                 updated_at=datetime.now().astimezone()).returning(roles)).mappings().first()

    def list_service_clients(self, *, status: str | None, after_id: int | None, limit: int):
        statement = sa.select(service_clients)
        if status:
            statement = statement.where(service_clients.c.status == status)
        return list(self.session.execute(self._page(statement, service_clients, after_id, limit)).mappings())

    def get_service_client(self, code: str, *, for_update: bool = False):
        statement = sa.select(service_clients).where(service_clients.c.client_code == code)
        if for_update:
            statement = statement.with_for_update()
        return self.session.execute(statement).mappings().first()

    def create_service_client(self, data: dict):
        now = datetime.now().astimezone()
        return self.session.execute(service_clients.insert().values(
            **data, status="active", version=1, created_at=now, updated_at=now
        ).returning(service_clients)).mappings().one()

    def update_service_client(self, code: str, data: dict, expected_version: int):
        return self.session.execute(service_clients.update().where(
            service_clients.c.client_code == code, service_clients.c.version == expected_version
        ).values(**data, version=service_clients.c.version + 1,
                 updated_at=datetime.now().astimezone()).returning(service_clients)).mappings().first()
