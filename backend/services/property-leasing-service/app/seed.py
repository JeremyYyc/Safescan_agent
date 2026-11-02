import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa

from app.core.database import get_session_factory
from app.core.config import get_settings
from app.clients.identity import IdentityClient
from safescan_common.cities import same_city
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
        managers = IdentityClient(get_settings()).active_staff("property_manager")
        if manager_ids:
            managers = [m for m in managers if UUID(m["id"]) in manager_ids]
        city_by_reference = {"B-SYD-01": "sydney", "B-MEL-01": "melbourne",
                             "B-BNE-01": "brisbane", "B-PER-01": "perth"}
        for building_index, (reference, name, address, timezone) in enumerate(BUILDINGS, start=1):
            building = db.scalar(sa.select(Building).where(Building.reference == reference))
            if not building:
                building = Building(reference=reference, name=name, address=address,
                                    city_id=city_by_reference[reference],
                                    timezone=timezone, status="active", attributes={})
                db.add(building)
                db.flush()
            if building.city_id is None:
                building.city_id = city_by_reference[reference]
            for room in (1, 2):
                property_reference = f"P-{building_index:02d}-{room:02d}"
                if db.scalar(sa.select(Property.id).where(Property.reference == property_reference)):
                    continue
                db.add(Property(
                    building_id=building.id, reference=property_reference, city_id=building.city_id,
                    address=f"Unit {room}, {address}", bedrooms=room,
                    bathrooms=Decimal("1.0" if room == 1 else "2.0"),
                    parking_spaces=1, floor_area_sqm=Decimal(45 + room * 20),
                    latitude=None, longitude=None, display_image_urls=[], floorplan_url=None,
                    weekly_rent=Decimal(500 + building_index * 50 + room * 25),
                    currency="AUD", status="marketing", listing_visibility="public",
                    attributes={"room_number": str(room)},
                ))
            candidates = [m for m in managers if same_city(m.get("city_id"), building.city_id)]
            if candidates:
                manager_id = UUID(sorted(candidates, key=lambda m: m["staff_code"])[0]["id"])
                exists = db.scalar(sa.select(StaffBuildingScope.id).where(
                    StaffBuildingScope.staff_id == manager_id,
                    StaffBuildingScope.building_id == building.id,
                    StaffBuildingScope.scope_role == "primary_manager",
                    StaffBuildingScope.valid_from <= datetime.now(UTC),
                    sa.or_(StaffBuildingScope.valid_until.is_(None),
                           StaffBuildingScope.valid_until > datetime.now(UTC))))
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
