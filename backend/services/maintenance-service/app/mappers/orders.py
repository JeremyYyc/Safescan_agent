from app.models.tables import MaintenanceEvent, MaintenanceOrder


def _time(value):
    return value.isoformat() if value else None


def event_view(event: MaintenanceEvent, tenant: bool = False) -> dict:
    result = {
        "id": str(event.public_id),
        "sequence_no": event.sequence_no,
        "event_type": event.event_type,
        "actor": {"type": event.actor_type},
        "message": event.message,
        "occurred_at": _time(event.created_at),
        "from_status": event.from_status,
        "to_status": event.to_status,
    }
    if not tenant:
        result.update(
            {
                "visibility": event.visibility,
                "actor_subject_id": str(event.actor_subject_id)
                if event.actor_subject_id
                else None,
                "actor_staff_id": str(event.actor_staff_id)
                if event.actor_staff_id
                else None,
                "details": event.details,
            }
        )
    return result


def order_view(
    order: MaintenanceOrder,
    events: list[MaintenanceEvent] | None = None,
    projection: str = "staff",
) -> dict:
    result = {
        "id": str(order.public_id),
        "reference": order.reference,
        "property": {"id": str(order.property_id)},
        "lease_id": str(order.lease_id) if order.lease_id else None,
        "summary": order.summary,
        "description": order.description,
        "priority": order.priority,
        "status": order.status,
        "reported_by": {"subject_id": str(order.reported_by_subject_id)}
        if order.reported_by_subject_id
        else None,
        "assigned_staff": {"id": str(order.assigned_staff_id)}
        if order.assigned_staff_id
        else None,
        "version": order.version,
        "created_at": _time(order.created_at),
        "updated_at": _time(order.updated_at),
        "completed_at": _time(order.completed_at),
        "cancelled_at": _time(order.cancelled_at),
    }
    if events is not None:
        visible = [
            event
            for event in events
            if projection != "tenant" or event.visibility == "public"
        ]
        result["timeline"] = [
            event_view(event, tenant=projection == "tenant") for event in visible
        ]
    return result
