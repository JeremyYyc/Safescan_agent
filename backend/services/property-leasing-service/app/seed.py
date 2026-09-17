import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa

from app.core.database import get_session_factory
from app.models.tables import Building, Property, StaffBuildingScope


BUILDINGS = (
    ("B-SYD-01", "Harbour House", "10 Harbour Street, Sydney NSW", "Australia/Sydney"),
    ("B-MEL-01", "Laneway Court", "20 Collins Street, Melbourne VIC", "Australia/Melbourne"),
    ("B-BNE-01", "River Place", "30 Queen Street, Brisbane QLD", "Australia/Brisbane"),
    ("B-PER-01", "West Coast Apartments", "40 Hay Street, Perth WA", "Australia/Perth"),
)


def seed() -> None:
    db = get_session_factory()()
    try:
        manager_ids = [UUID(value.strip()) for value in
                       os.getenv("PROPERTY_MANAGER_STAFF_IDS", "").split(",") if value.strip()]
        for building_index, (reference, name, address, timezone) in enumerate(BUILDINGS, start=1):
            building = db.scalar(sa.select(Building).where(Building.reference == reference))
            if not building:
                building = Building(reference=reference, name=name, address=address,
                                    timezone=timezone, status="active", attributes={})
                db.add(building)
                db.flush()
            for room in (1, 2):
                property_reference = f"P-{building_index:02d}-{room:02d}"
                if db.scalar(sa.select(Property.id).where(Property.reference == property_reference)):
                    continue
                db.add(Property(
                    building_id=building.id, reference=property_reference,
                    address=f"Unit {room}, {address}", bedrooms=room,
                    bathrooms=Decimal("1.0" if room == 1 else "2.0"),
                    parking_spaces=1, floor_area_sqm=Decimal(45 + room * 20),
                    latitude=None, longitude=None, display_image_urls=[], floorplan_url=None,
                    weekly_rent=Decimal(500 + building_index * 50 + room * 25),
                    currency="AUD", status="marketing", listing_visibility="public",
                    attributes={"room_number": str(room)},
                ))
            if building_index <= len(manager_ids):
                manager_id = manager_ids[building_index - 1]
                exists = db.scalar(sa.select(StaffBuildingScope.id).where(
                    StaffBuildingScope.staff_id == manager_id,
                    StaffBuildingScope.building_id == building.id,
                    StaffBuildingScope.scope_role == "primary_manager"))
                if not exists:
                    db.add(StaffBuildingScope(
                        staff_id=manager_id, building_id=building.id, scope_role="primary_manager",
                        valid_from=datetime.now(UTC), valid_until=None,
                        assigned_by_subject_id=manager_id,
                    ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
