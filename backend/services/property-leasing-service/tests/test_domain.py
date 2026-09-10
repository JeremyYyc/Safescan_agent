from decimal import Decimal
from uuid import UUID

from app.models.tables import Building, Property
from app.services.leasing_service import LeasingService


def test_terms_digest_is_stable_for_key_order() -> None:
    assert LeasingService._terms_digest({"b": 2, "a": 1}) == LeasingService._terms_digest(
        {"a": 1, "b": 2}
    )


def test_terms_digest_changes_with_terms() -> None:
    assert LeasingService._terms_digest({"rent": 10}) != LeasingService._terms_digest({"rent": 11})


def test_stable_consultant_selection_is_order_independent_and_empty_safe() -> None:
    customer_id = UUID("10000000-0000-0000-0000-000000000001")
    property_id = UUID("20000000-0000-0000-0000-000000000001")
    consultants = [UUID("30000000-0000-0000-0000-000000000002"),
                   UUID("30000000-0000-0000-0000-000000000001")]
    selected = LeasingService._stable_consultant(customer_id, property_id, consultants)
    assert selected == LeasingService._stable_consultant(customer_id, property_id,
                                                          list(reversed(consultants)))
    assert selected in consultants
    assert LeasingService._stable_consultant(customer_id, property_id, []) is None


def test_property_read_projection_contains_structured_metadata_and_building() -> None:
    building = Building(public_id=UUID("40000000-0000-0000-0000-000000000001"),
                        reference="B-1", name="Harbour House", address="10 Harbour Street",
                        timezone="Australia/Sydney", status="active", attributes={})
    prop = Property(public_id=UUID("50000000-0000-0000-0000-000000000001"),
                    reference="P-1", address="Unit 2, 10 Harbour Street", bedrooms=2,
                    bathrooms=Decimal("1.5"), parking_spaces=1,
                    floor_area_sqm=Decimal("82.50"), latitude=Decimal("-33.868800"),
                    longitude=Decimal("151.209300"),
                    display_image_urls=["https://cdn.example/front.jpg"],
                    floorplan_url="https://cdn.example/plan.jpg", weekly_rent=Decimal("750"),
                    currency="AUD", status="marketing", listing_visibility="public",
                    attributes={}, building=building)
    view = LeasingService._property_view(prop)
    assert view["building_id"] == str(building.public_id)
    assert view["building"]["reference"] == "B-1"
    assert view["location"] == {"address": prop.address, "latitude": "-33.868800",
                                "longitude": "151.209300"}
    assert view["parking_spaces"] == 1 and view["has_parking"] is True
    assert view["floor_area_sqm"] == "82.50"
    assert view["display_image_urls"] == ["https://cdn.example/front.jpg"]
    assert view["floorplan_url"] == "https://cdn.example/plan.jpg"
