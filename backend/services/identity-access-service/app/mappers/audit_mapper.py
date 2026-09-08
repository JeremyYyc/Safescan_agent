from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.tables import auth_events


class AuditMapper:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, event_type: str, *, correlation_id: UUID, user_id: int | None = None,
            session_id: int | None = None, ip_hash: str | None = None,
            user_agent_hash: str | None = None, details: dict | None = None) -> None:
        now = datetime.now().astimezone()
        self.session.execute(auth_events.insert().values(
            user_id=user_id, session_id=session_id, event_type=event_type, occurred_at=now,
            ip_hash=ip_hash, user_agent_hash=user_agent_hash,
            correlation_id=correlation_id, details_redacted=details or {}, created_at=now,
        ))

    def list_events(self, *, user_id: int | None = None, event_type: str | None = None,
                    after_id: int | None = None, limit: int = 50):
        statement = sa.select(auth_events)
        if user_id is not None:
            statement = statement.where(auth_events.c.user_id == user_id)
        if event_type:
            statement = statement.where(auth_events.c.event_type == event_type)
        if after_id is not None:
            statement = statement.where(auth_events.c.id < after_id)
        return list(self.session.execute(
            statement.order_by(auth_events.c.id.desc()).limit(limit + 1)
        ).mappings())
