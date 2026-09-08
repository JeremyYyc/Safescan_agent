"""Idempotently create the first manager administrator from environment variables."""

from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.security import hash_password, normalize_email
from app.mappers.admin_mapper import AdminMapper
from app.mappers.user_mapper import UserMapper


def bootstrap() -> None:
    settings = get_settings()
    if not settings.bootstrap_admin_email:
        return
    password = settings.bootstrap_admin_password.get_secret_value()
    if len(password) < 12:
        raise RuntimeError("IDENTITY_BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters")
    session = get_session_factory()()
    users = UserMapper(session)
    admin = AdminMapper(session)
    email = normalize_email(settings.bootstrap_admin_email)
    try:
        existing = users.get_by_email(email, for_update=True)
        if existing:
            session.rollback()
            return
        role = admin.get_role_by_code("manager_admin")
        if not role:
            raise RuntimeError("manager_admin seed role is missing; run Alembic migrations first")
        user = users.create_user(email=email, username=settings.bootstrap_admin_name,
                                 account_type="staff", status="active", locale=settings.default_locale)
        users.create_password(user_id=user["id"], secret_hash=hash_password(password))
        admin.create_staff(user_id=user["id"], role_id=role["id"],
                           staff_code=settings.bootstrap_admin_staff_code,
                           display_name=settings.bootstrap_admin_name, hired_at=None)
        admin.activate_staff(user["id"])
        session.commit()
    except IntegrityError:
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    bootstrap()
