import os
import time
from datetime import UTC, datetime, timedelta

import httpx
import sqlalchemy as sa

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.models.tables import OutboxEvent


def _target(event: OutboxEvent) -> tuple[str | None, str]:
    settings = get_settings()
    if event.event_type == "customer.tenancy_status_changed.v1":
        return (f"{settings.identity_base_url.rstrip('/')}/internal/v1/customer-status-events",
                settings.identity_service_token.get_secret_value())
    return os.getenv("PROPERTY_EVENT_SINK_URL") or None, os.getenv("PROPERTY_EVENT_SINK_TOKEN", "")


def dispatch_once(batch_size: int = 50) -> int:
    factory = get_session_factory()
    now = datetime.now(UTC)
    claimed_ids: list[int] = []
    with factory() as db:
        events = list(db.scalars(sa.select(OutboxEvent).where(
            sa.or_(
                sa.and_(OutboxEvent.status == "pending", OutboxEvent.available_at <= now),
                sa.and_(OutboxEvent.status == "delivering",
                        OutboxEvent.updated_at < now - timedelta(seconds=60)),
            )).order_by(OutboxEvent.available_at, OutboxEvent.id)
            .with_for_update(skip_locked=True).limit(batch_size)))
        for event in events:
            event.status = "delivering"
            event.updated_at = now
            claimed_ids.append(event.id)
        db.commit()

    delivered = 0
    for event_id in claimed_ids:
        with factory() as db:
            event = db.get(OutboxEvent, event_id)
            url, token = _target(event)
            if not url:
                event.status = "pending"
                event.available_at = datetime.now(UTC) + timedelta(seconds=30)
                event.updated_at = datetime.now(UTC)
                db.commit()
                continue
            body = {"event_id": str(event.event_id), "event_type": event.event_type,
                    **event.payload}
            try:
                response = httpx.post(url, json=body,
                                      headers={"Authorization": f"Bearer {token}"} if token else {},
                                      timeout=5.0)
                response.raise_for_status()
            except httpx.HTTPError:
                event.attempts += 1
                event.status = "failed" if event.attempts >= 20 else "pending"
                event.available_at = datetime.now(UTC) + timedelta(
                    seconds=min(300, 2 ** min(event.attempts, 8)))
            else:
                event.status = "delivered"
                event.delivered_at = datetime.now(UTC)
                delivered += 1
            event.updated_at = datetime.now(UTC)
            db.commit()
    return delivered


def main() -> None:
    interval = float(os.getenv("PROPERTY_OUTBOX_POLL_SECONDS", "1"))
    while True:
        dispatch_once()
        time.sleep(interval)


if __name__ == "__main__":
    main()
