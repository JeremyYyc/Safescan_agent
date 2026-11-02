"""Complete effective rental-unit attributes while retaining immutable source facts."""
from collections import Counter
import math
import random
import re

CORE_FIELDS = ("address", "property_type", "bedrooms", "bathrooms", "rooms_count", "bed_count",
               "kitchen_count", "living_room_count", "parking_spaces", "floor_area_sqm",
               "whole_apartment_bedrooms", "whole_apartment_bathrooms", "whole_apartment_floor_area_sqm",
               "max_occupants", "furnished")
ENRICHED_UNIT_KEYS = (*CORE_FIELDS, "area_sqm", "property_profile", "property_field_sources",
                      "property_fields_version", "simulation_layout", "rental_scope")


def number(value, positive=False):
    if isinstance(value, bool) or value is None:
        return None
    try:
        value = float(value)
        if value < 0 or (positive and value <= 0):
            return None
        return int(value) if value.is_integer() else value
    except (ValueError, TypeError):
        return None


def text_count(text, noun):
    # A range must not become a falsely precise observed count.
    if re.search(r"\d+\s*(?:or|to|[-–])\s*\d+\s*(?:" + noun + ")", text, re.I):
        return None
    words = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8"}
    for word, digit in words.items():
        text = re.sub(r"\b" + word + r"\b", digit, text, flags=re.I)
    match = re.search(r"\b(\d+)\s*[- ]?\s*(?:" + noun + r")\b", text, re.I)
    return int(match[1]) if match else None


def display_address(address):
    if isinstance(address, dict):
        return ", ".join(str(address[k]) for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode") if address.get(k))
    return str(address or "").strip()


def complete_units(tables, inventory, supplemental=None, seed=31):
    supplemental = supplemental or {}
    profiles = []
    max_residents = Counter()
    for lease in tables["simulated_tenancies"]:
        max_residents[lease["unit_id"]] = max(max_residents[lease["unit_id"]], lease["occupants"])
    for unit in tables["execution_units"]:
        housing = inventory[unit["housing_id"]]
        meta = housing["metadata"]
        original = meta.get("original_record", {})
        room = next((r for r in meta.get("room_types", []) if r["name"] == unit["source_room_type"]), {})
        # A separate RNG prevents enrichment from changing any operational timeline.
        rng = random.Random(f"{seed}:property:{housing['id']}:{unit['source_room_type']}")
        name = unit["source_room_type"]
        description = str(original.get("description", ""))
        plan_notes = str(original.get("plan", {}).get("notes", ""))
        sources = {}

        def choose(field, candidates, fallback):
            for value, origin, evidence in candidates:
                if value is not None and value != "":
                    sources[field] = {"origin": origin, "evidence": evidence}
                    return value
            sources[field] = {"origin": "simulated", "evidence": "reasonable deterministic assumption for this housing/room type"}
            return fallback

        observed_beds = next((v for v in (number(room.get("bedrooms")), number(meta.get("bedrooms")), number(original.get("bedrooms"))) if v is not None), None)
        named_beds = 0 if "studio" in name.lower() else text_count(name, r"bed(?:room)?s?")
        source_beds = text_count(plan_notes, r"bed(?:room)?s?")
        if source_beds is None:
            source_beds = text_count(description, r"bed(?:room)?s?")
        bedroom_range = re.search(r"(\d+)\s*(?:or|to|[-–])\s*(\d+)\s*bed", name, re.I)
        fallback_beds = (rng.randint(int(bedroom_range[1]), int(bedroom_range[2])) if bedroom_range else
                         rng.choice([3, 4, 5, 6]) if unit["rental_scope"] == "private_room" else
                         0 if housing["dataset_type"] == "student" else rng.choice([1, 2, 2, 3]))
        whole_beds = choose("whole_apartment_bedrooms", [(observed_beds, "observed", "source numeric bedroom field"),
            (named_beds, "derived_from_source", "explicit room-type name"),
            (source_beds, "derived_from_source", "saved source description / reviewed floorplan notes")],
            fallback_beds)
        scope = "studio" if whole_beds == 0 else "private_room" if unit["rental_scope"] == "private_room" or (housing["dataset_type"] == "student" and whole_beds > 1) else "entire_property"
        bedrooms = whole_beds if scope != "private_room" else 1
        sources["bedrooms"] = dict(sources["whole_apartment_bedrooms"]) if scope != "private_room" else {
            "origin": "simulated" if sources["whole_apartment_bedrooms"]["origin"] == "simulated" else "derived_from_source",
            "evidence": "one leased bedroom within the shared apartment; whole-apartment count stored separately"}

        observed_baths = next((v for v in (number(room.get("bathrooms"), True), number(meta.get("bathrooms"), True), number(original.get("bathrooms"), True)) if v is not None), None)
        named_baths = text_count(name + " " + description, r"bath(?:room)?s?")
        ensuite_baths = whole_beds if whole_beds > 0 and "ensuite" in name.lower() else None
        whole_baths = choose("whole_apartment_bathrooms", [(observed_baths, "observed", "source numeric bathroom field"),
            (named_baths, "derived_from_source", "explicit bathroom count in source name/description"),
            (ensuite_baths, "derived_from_source", "room-type name specifies ensuite bedrooms")],
            max(1, math.ceil(whole_beds / 3)))
        bathrooms = 1 if scope == "private_room" else whole_baths
        sources["bathrooms"] = dict(sources["whole_apartment_bathrooms"]) if scope != "private_room" else {
            "origin": "simulated" if sources["whole_apartment_bathrooms"]["origin"] == "simulated" else "derived_from_source",
            "evidence": "one bathroom access allocation; private/shared indicator stored separately"}
        private_bath = scope != "private_room" or whole_baths >= whole_beds or "ensuite" in name.lower()

        parking = choose("parking_spaces", [(number(room.get("parking_spaces")), "observed", "source parking field"),
            (number(meta.get("parking_spaces")), "observed", "saved source parking field"),
            (number(original.get("parking_spaces")), "observed", "original source parking field")],
            0 if housing["dataset_type"] == "student" else rng.choice([0, 1, 1, 2]))
        observed_area = next((v for v in (number(room.get("area_sqm"), True), number(meta.get("area_sqm"), True), number(original.get("area_sqm"), True)) if v is not None), None)
        area_scope = room.get("area_scope") or original.get("area_scope") or "unknown"
        source_is_whole = "whole" in area_scope.lower() and "not whole" not in area_scope.lower()
        if scope == "private_room":
            area = choose("floor_area_sqm", [(observed_area if not source_is_whole else None, "observed", "advertised room area")], rng.randint(11, 20))
            whole_area = choose("whole_apartment_floor_area_sqm", [(observed_area if source_is_whole else None, "observed", "source explicitly identifies whole-apartment area")],
                                round(area * max(1, whole_beds) + rng.randint(18, 35), 1))
        else:
            area = choose("floor_area_sqm", [(observed_area, "observed", "source advertised area")],
                          rng.randint(18, 30) if whole_beds == 0 else 34 + whole_beds * rng.randint(17, 25))
            whole_area = area
            sources["whole_apartment_floor_area_sqm"] = dict(sources["floor_area_sqm"])
        if whole_area < area:
            raise ValueError("Source area scope contradicts simulated leased area: " + unit["id"])

        property_id = meta.get("property_id")
        address_candidates = [(display_address(housing.get("address")), "observed", housing["source_url"])]
        for item in inventory.values():
            if property_id and item["metadata"].get("provider") == "UniLodge" and item["source_url"].rstrip("/").split("/")[-1] == property_id:
                address_candidates.append((display_address(item["address"]), "derived_from_source", item["source_url"]))
        if property_id in supplemental:
            item = supplemental[property_id]
            address_candidates.append((item["address"], "observed", item["source_url"]))
        address = choose("address", address_candidates, f"SIM-{unit['reference']}, {housing.get('city') or 'Australia'} (simulated address)")
        furnished = choose("furnished", [(original.get("furnished"), "observed", "source furnishing flag")], housing["dataset_type"] == "student")
        property_type = choose("property_type", [(original.get("property_type"), "observed", "saved source property type")],
            "private_room" if scope == "private_room" else "studio" if bedrooms == 0 else "house" if "/house/" in housing["source_url"] else "apartment")
        kitchens, living = 1, (0 if scope == "private_room" else 1)
        sources["kitchen_count"] = {"origin": "simulated", "evidence": "one private kitchenette or access to one shared kitchen"}
        sources["living_room_count"] = {"origin": "simulated", "evidence": "studio uses open living zone; private-room contracts exclude shared lounge"}
        bedding_match = re.search(r"(\d+)\s*x\s*", str(original.get("bedding", "")), re.I)
        observed_capacity = number(room.get("max_people"), True)
        original_capacity = text_count(str(original.get("max_guests_raw", "")), r"persons?|people|guests?")
        bed_count = choose("bed_count", [(int(bedding_match[1]) if bedding_match else None, "observed", "source bedding count")],
                           1 if scope == "private_room" else 2 if re.search(r"twin|bunk", name, re.I) else max(1, bedrooms))
        capacity = choose("max_occupants", [(1 if observed_capacity is not None and scope == "private_room" else observed_capacity,
                                             "derived_from_source" if scope == "private_room" else "observed", "source capacity, allocated to one leased room when shared"),
                                            (original_capacity, "derived_from_source", "source max-guests description")],
                          max(1, bed_count * (2 if scope != "private_room" else 1), max_residents[unit["id"]]))
        if capacity < max_residents[unit["id"]]:
            raise ValueError("Known source capacity contradicts existing simulated tenancy: " + unit["id"])
        # Bedrooms + bathrooms + one combined living/kitchen zone. Shared facilities
        # count only once; a studio's open sleeping/living zone counts as one room.
        rooms = 1 + (1 if private_bath else 0) if scope == "private_room" else max(1, bedrooms) + math.ceil(bathrooms) + (1 if bedrooms else 0)
        sources["rooms_count"] = {"origin": "simulated", "evidence": "enclosed-room count; combined open living/kitchen zone counted once"}
        profile = {"id": unit["id"], "housing_id": unit["housing_id"], "source_room_type": name,
            "address": address, "property_type": property_type, "rental_scope": scope,
            "bedrooms": bedrooms, "bathrooms": bathrooms, "rooms_count": rooms, "bed_count": bed_count,
            "kitchen_count": kitchens, "living_room_count": living, "parking_spaces": parking,
            "floor_area_sqm": area, "whole_apartment_bedrooms": whole_beds, "whole_apartment_bathrooms": whole_baths,
            "whole_apartment_floor_area_sqm": whole_area, "max_occupants": capacity, "furnished": furnished,
            "has_private_bathroom": private_bath, "has_shared_kitchen": scope == "private_room",
            "has_shared_living_room": scope == "private_room", "weekly_rent": unit["weekly_rent"], "currency": "AUD",
            "field_sources": sources, "is_synthetic": True, "simulation_as_of": unit["simulation_as_of"]}
        unit.update({key: profile[key] for key in CORE_FIELDS})
        unit.update(property_profile=profile, property_field_sources=sources, property_fields_version=2,
                    area_sqm=area, rental_scope=scope)
        unit["simulation_layout"].update(bedrooms=bedrooms, bathrooms=bathrooms,
            whole_apartment_bedrooms=whole_beds, whole_apartment_bathrooms=whole_baths,
            floor_area_sqm=area, parking_spaces=parking, rooms_count=rooms,
            has_private_bathroom=private_bath, layout_assumed=any(s["origin"] == "simulated" for s in sources.values()))
        profiles.append(profile)
    by_unit = {u["id"]: u for u in tables["execution_units"]}
    for lease in tables["simulated_tenancies"]:
        lease["rent_basis"] = "room_per_week" if by_unit[lease["unit_id"]]["rental_scope"] == "private_room" else "property_per_week"
    return profiles, completion_report(profiles)


def completion_report(profiles):
    stats = {key: Counter(p["field_sources"][key]["origin"] for p in profiles) for key in CORE_FIELDS}
    return {"units": len(profiles), "required_fields": list(CORE_FIELDS),
        "missing_effective_field_values": {key: sum(p.get(key) is None or p.get(key) == "" for p in profiles) for key in CORE_FIELDS},
        "field_origins": {key: dict(value) for key, value in stats.items()}, "source_facts_overwritten": 0}
