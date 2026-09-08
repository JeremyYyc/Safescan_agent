from datetime import datetime, timedelta
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.tables import account_action_tokens, auth_sessions, guest_sessions, refresh_tokens


class AuthMapper:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_guest(self, *, expires_at: datetime) -> dict:
        now = datetime.now().astimezone()
        return dict(self.session.execute(
            guest_sessions.insert().values(
                public_id=uuid4(), status="active", expires_at=expires_at,
                created_at=now, updated_at=now,
            ).returning(guest_sessions)
        ).mappings().one())

    def claim_guest(self, public_id: UUID | str, user_id: int) -> bool:
        now = datetime.now().astimezone()
        result = self.session.execute(
            guest_sessions.update().where(
                guest_sessions.c.public_id == public_id,
                guest_sessions.c.status == "active",
                guest_sessions.c.expires_at > now,
            ).values(status="claimed", claimed_by_user_id=user_id, claimed_at=now, updated_at=now)
        )
        return result.rowcount == 1

    def create_session_with_refresh(
        self, *, user_id: int, device_label: str | None, user_agent_hash: str | None,
        ip_hash: str | None, session_expires_at: datetime, refresh_hash: str,
        refresh_expires_at: datetime,
    ) -> tuple[dict, UUID]:
        now = datetime.now().astimezone()
        session_row = dict(self.session.execute(
            auth_sessions.insert().values(
                public_id=uuid4(), user_id=user_id, device_label=device_label,
                user_agent_hash=user_agent_hash, ip_hash=ip_hash, status="active",
                last_seen_at=now, expires_at=session_expires_at, created_at=now, updated_at=now,
            ).returning(auth_sessions)
        ).mappings().one())
        family_id = uuid4()
        self.session.execute(refresh_tokens.insert().values(
            session_id=session_row["id"], family_id=family_id, token_hash=refresh_hash,
            status="active", issued_at=now, expires_at=refresh_expires_at, created_at=now,
        ))
        return session_row, family_id

    def get_refresh_for_update(self, refresh_hash: str):
        return self.session.execute(
            sa.select(refresh_tokens, auth_sessions.c.public_id.label("session_public_id"),
                      auth_sessions.c.user_id, auth_sessions.c.status.label("session_status"),
                      auth_sessions.c.expires_at.label("session_expires_at"))
            .join(auth_sessions, auth_sessions.c.id == refresh_tokens.c.session_id)
            .where(refresh_tokens.c.token_hash == refresh_hash).with_for_update(of=refresh_tokens)
        ).mappings().first()

    def rotate_refresh(self, current: dict, *, new_hash: str, expires_at: datetime) -> None:
        now = datetime.now().astimezone()
        # Retire the current row before inserting its replacement. The schema's
        # partial unique index permits exactly one active token per session.
        self.session.execute(
            refresh_tokens.update().where(
                refresh_tokens.c.id == current["id"], refresh_tokens.c.status == "active"
            ).values(status="rotated", used_at=now)
        )
        new_id = self.session.execute(
            refresh_tokens.insert().values(
                session_id=current["session_id"], family_id=current["family_id"],
                token_hash=new_hash, parent_token_id=current["id"], status="active",
                issued_at=now, expires_at=expires_at, created_at=now,
            ).returning(refresh_tokens.c.id)
        ).scalar_one()
        self.session.execute(
            refresh_tokens.update().where(refresh_tokens.c.id == current["id"]).values(
                replaced_by_token_id=new_id
            )
        )
        self.session.execute(
            auth_sessions.update().where(auth_sessions.c.id == current["session_id"]).values(
                last_seen_at=now, updated_at=now
            )
        )

    def revoke_session(self, session_id: int, reason: str) -> None:
        now = datetime.now().astimezone()
        self.session.execute(auth_sessions.update().where(auth_sessions.c.id == session_id).values(
            status="revoked", revoked_at=now, revoke_reason=reason, updated_at=now
        ))
        self.session.execute(refresh_tokens.update().where(
            refresh_tokens.c.session_id == session_id,
            refresh_tokens.c.status == "active",
        ).values(status="revoked"))

    def revoke_family(self, family_id: UUID, session_id: int, reason: str) -> None:
        self.session.execute(refresh_tokens.update().where(
            refresh_tokens.c.family_id == family_id,
            refresh_tokens.c.status.in_(["active", "rotated"]),
        ).values(status="reused"))
        self.revoke_session(session_id, reason)

    def revoke_all_for_user(self, user_id: int, reason: str, *, except_session_id: int | None = None) -> None:
        statement = sa.select(auth_sessions.c.id).where(
            auth_sessions.c.user_id == user_id, auth_sessions.c.status == "active"
        ).order_by(auth_sessions.c.id).with_for_update()
        ids = list(self.session.scalars(statement))
        for session_id in ids:
            if except_session_id is None or session_id != except_session_id:
                self.revoke_session(session_id, reason)

    def get_session(self, public_id: UUID | str, user_id: int | None = None):
        statement = sa.select(auth_sessions).where(auth_sessions.c.public_id == public_id)
        if user_id is not None:
            statement = statement.where(auth_sessions.c.user_id == user_id)
        return self.session.execute(statement).mappings().first()

    def list_sessions(self, user_id: int, *, after_id: int | None, limit: int):
        statement = sa.select(auth_sessions).where(auth_sessions.c.user_id == user_id)
        if after_id is not None:
            statement = statement.where(auth_sessions.c.id < after_id)
        return list(self.session.execute(
            statement.order_by(auth_sessions.c.id.desc()).limit(limit + 1)
        ).mappings())

    def issue_action_token(self, *, user_id: int, purpose: str, value_hash: str,
                           expires_at: datetime, requested_ip_hash: str | None) -> dict:
        now = datetime.now().astimezone()
        self.session.execute(account_action_tokens.update().where(
            account_action_tokens.c.user_id == user_id,
            account_action_tokens.c.purpose == purpose,
            account_action_tokens.c.used_at.is_(None),
            account_action_tokens.c.revoked_at.is_(None),
        ).values(revoked_at=now))
        return dict(self.session.execute(
            account_action_tokens.insert().values(
                public_id=uuid4(), user_id=user_id, purpose=purpose, token_hash=value_hash,
                expires_at=expires_at, requested_ip_hash=requested_ip_hash, created_at=now,
            ).returning(account_action_tokens)
        ).mappings().one())

    def consume_action_token(self, *, value_hash: str, purpose: str):
        now = datetime.now().astimezone()
        row = self.session.execute(
            sa.select(account_action_tokens).where(
                account_action_tokens.c.token_hash == value_hash,
                account_action_tokens.c.purpose == purpose,
            ).with_for_update()
        ).mappings().first()
        if not row or row["used_at"] is not None or row["revoked_at"] is not None or row["expires_at"] <= now:
            return None
        self.session.execute(account_action_tokens.update().where(
            account_action_tokens.c.id == row["id"]
        ).values(used_at=now))
        return row
