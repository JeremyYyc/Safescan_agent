"""Idempotently seed the twelve development staff accounts."""

import logging

import sqlalchemy as sa

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.security import hash_password, normalize_email
from app.mappers.admin_mapper import AdminMapper
from app.mappers.user_mapper import UserMapper


LOGGER = logging.getLogger(__name__)

STAFF_SEEDS = (
    ("LC001", "Ethan Carter", "EthanCarter", "EthanSafescan@outlook.com", "leasing_consultant"),
    ("LC002", "Olivia Bennett", "OliviaBennett", "OliviaSafescan@outlook.com", "leasing_consultant"),
    ("LC003", "Liam Foster", "LiamFoster", "LiamSafescan@outlook.com", "leasing_consultant"),
    ("LC004", "Sophia Reed", "SophiaReed", "SophiaSafescan@outlook.com", "leasing_consultant"),
    ("PM001", "Noah Mitchell", "NoahMitchell", "NoahSafescan@outlook.com", "property_manager"),
    ("PM002", "Emma Collins", "EmmaCollins", "EmmaSafescan@outlook.com", "property_manager"),
    ("PM003", "James Parker", "JamesParker", "JamesSafescan@outlook.com", "property_manager"),
    ("PM004", "Ava Richardson", "AvaRichardson", "AvaSafescan@outlook.com", "property_manager"),
    ("MT001", "Daniel Cooper", "DanielCooper", "DanielSafescan@outlook.com", "maintainer"),
    ("MT002", "Grace Turner", "GraceTurner", "GraceSafescan@outlook.com", "maintainer"),
    ("MT003", "Henry Walker", "HenryWalker", "HenrySafescan@outlook.com", "maintainer"),
    ("MA001", "Charlotte Morgan", "CharlotteMorgan", "CharlotteSafescan@outlook.com", "manager_admin"),
)


def initial_password(username: str) -> str:
    return f"staff{username}123456"


def seed() -> int:
    settings = get_settings()
    if not settings.seed_staff:
        return 0
    session = get_session_factory()()
    users = UserMapper(session)
    admin = AdminMapper(session)
    created = 0
    try:
        session.execute(sa.text("SELECT pg_advisory_xact_lock(hashtext('identity-p0-staff-seed'))"))
        for staff_code, display_name, username, email, role_code in STAFF_SEEDS:
            normalized_email = normalize_email(email)
            existing = users.get_by_email(normalized_email, for_update=True)
            if existing:
                profile = users.get_staff_profile(existing["id"])
                if (existing["account_type"] != "staff" or not profile
                        or profile["staff_code"] != staff_code
                        or profile["role_code"] != role_code):
                    raise RuntimeError(f"Seed identity conflict for {normalized_email}")
                continue
            role = admin.get_role_by_code(role_code)
            if not role:
                raise RuntimeError(f"Seed role is missing: {role_code}")
            user = users.create_user(
                email=normalized_email,
                username=username,
                account_type="staff",
                status="active",
                locale=settings.default_locale,
            )
            users.create_password(user_id=user["id"], secret_hash=hash_password(initial_password(username)))
            users.mark_email_verified(user["id"])
            admin.create_staff(
                user_id=user["id"],
                role_id=role["id"],
                staff_code=staff_code,
                display_name=display_name,
                hired_at=None,
            )
            admin.activate_staff(user["id"])
            created += 1
        session.commit()
        LOGGER.info("Identity development staff seed completed", extra={"created_count": created})
        return created
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed()
