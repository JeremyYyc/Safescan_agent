import copy
from pathlib import Path
import tempfile
import unittest

from dataset_io import canonical_address, read_export, write_jsonl
from generate_execution_dataset import generate
from validate_execution_dataset import load_tables, TABLES, validate_tables
from complete_property_fields import complete_units, text_count, CORE_FIELDS


class DatasetTests(unittest.TestCase):
    def setUp(self):
        housing = {"student:a": {"id": "student:a", "dataset_type": "student", "name": "Studio", "city": "Brisbane", "region": "QLD", "address": "1 Example St",
                                "source_url": "https://example.invalid/a", "metadata": {"record_type": "room_type", "bedrooms": 0, "bathrooms": 1}}}
        self.tables = {"housing_records": list(housing.values()), "media_assets": [], "housing_media": [], **generate(housing, [], 20, 31)}

    def test_fixture_invariants(self):
        self.assertTrue(validate_tables(self.tables)["checks_passed"])

    def test_overlapping_lease_rejected(self):
        leases = self.tables["simulated_tenancies"]
        leases[1]["starts_on"] = leases[0]["starts_on"]
        with self.assertRaises(ValueError):
            validate_tables(self.tables)

    def test_cross_unit_inspection_rejected(self):
        self.tables["simulated_inspections"][0]["unit_id"] = self.tables["execution_units"][1]["id"]
        with self.assertRaisesRegex(ValueError, "cross-unit"):
            validate_tables(self.tables)

    def test_event_status_mismatch_rejected(self):
        self.tables["simulated_work_order_events"][0]["to_status"] = "completed"
        with self.assertRaisesRegex(ValueError, "transition"):
            validate_tables(self.tables)

    def test_future_signed_contract_rejected(self):
        self.tables["simulated_tenancies"][0]["signed_at"] = "2028-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "future"):
            validate_tables(self.tables)

    def test_marketing_as_evidence_rejected(self):
        self.tables["simulated_work_orders"][0]["evidence_media_ids"] = ["marketing_photo"]
        with self.assertRaisesRegex(ValueError, "evidence"):
            validate_tables(self.tables)

    def test_answer_key_mismatch_rejected(self):
        self.tables["execution_scenarios"][0]["expected_tenancy_ids"] = []
        with self.assertRaisesRegex(ValueError, "oracle"):
            validate_tables(self.tables)

    def test_growth_preserves_previous_units(self):
        housing = {r["id"]: r for r in self.tables["housing_records"]}
        bigger = generate(housing, [], 30, 31)
        for key in bigger:
            self.assertEqual(bigger[key][:len(self.tables[key])], self.tables[key])

    def test_multiline_and_escaped_sql_literals(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "baseline.sql"
            p.write_text("INSERT INTO collected_data.housing_records (id, name, address, metadata) VALUES ('a', 'A''Beckett\nStreet', NULL, '{\"bedrooms\":2}') ON CONFLICT (id) DO NOTHING;\n")
            rows = read_export(p, "housing_records")
            self.assertEqual(rows[0]["name"], "A'Beckett\nStreet")
            self.assertEqual(rows[0]["metadata"]["bedrooms"], 2)

    def test_unicode_line_separator_in_jsonl(self):
        with tempfile.TemporaryDirectory() as root:
            for name in TABLES:
                write_jsonl(Path(root) / (name + ".jsonl"), [{"value": "before\u2028after"}])
            self.assertEqual(load_tables(Path(root))["housing_records"][0]["value"], "before\u2028after")

    def test_address_aliases(self):
        self.assertEqual(canonical_address("10 Queen Street, Brisbane, QLD 4000, Australia"), canonical_address("10 Queen St Brisbane QLD 4000"))

    def test_all_effective_property_fields_present(self):
        for unit in self.tables["execution_units"]:
            for key in CORE_FIELDS:
                self.assertIsNotNone(unit[key])
            self.assertEqual(unit["bedrooms"], 0)  # Studio zero is a valid known count.

    def test_missing_effective_property_rejected(self):
        self.tables["execution_units"][0]["bathrooms"] = None
        with self.assertRaisesRegex(ValueError, "Missing effective property"):
            validate_tables(self.tables)

    def test_shared_apartment_counts_are_separate(self):
        housing = {"student:shared": {"id": "student:shared", "dataset_type": "student", "name": "5 Bedroom Apartment (Ensuite)",
            "city": "Brisbane", "region": "QLD", "address": "1 Example St", "source_url": "https://example.invalid/shared",
            "metadata": {"name": "5 Bedroom Apartment (Ensuite)", "bedrooms": 5, "bathrooms": 5, "area_sqm": 12}}}
        rows = generate(housing, [], 1, 31)
        unit = rows["execution_units"][0]
        self.assertEqual((unit["bedrooms"], unit["bathrooms"]), (1, 1))
        self.assertEqual((unit["whole_apartment_bedrooms"], unit["whole_apartment_bathrooms"]), (5, 5))
        self.assertEqual(unit["floor_area_sqm"], 12)
        self.assertGreater(unit["whole_apartment_floor_area_sqm"], 60)

    def test_source_counts_cannot_be_overwritten(self):
        unit = self.tables["execution_units"][0]
        unit["whole_apartment_bedrooms"] = 3
        unit["property_profile"]["whole_apartment_bedrooms"] = 3
        with self.assertRaisesRegex(ValueError, "Known source count overwritten"):
            validate_tables(self.tables)

    def test_source_title_counts_recovered_without_changing_history(self):
        housing = {r["id"]: copy.deepcopy(r) for r in self.tables["housing_records"]}
        housing["student:a"]["metadata"].update(bedrooms=None, bathrooms=None)
        housing["student:a"]["metadata"]["name"] = "2 Bedroom Apartment (Ensuite)"
        for unit in self.tables["execution_units"]:
            unit["source_room_type"] = "2 Bedroom Apartment (Ensuite)"
        before = [{k: v for k, v in row.items() if k != "rent_basis"} for row in self.tables["simulated_tenancies"]]
        profiles, report = complete_units(self.tables, housing)
        self.assertEqual(profiles[0]["whole_apartment_bedrooms"], 2)
        self.assertEqual(profiles[0]["whole_apartment_bathrooms"], 2)
        self.assertFalse(any(report["missing_effective_field_values"].values()))
        self.assertEqual(before, [{k: v for k, v in row.items() if k != "rent_basis"} for row in self.tables["simulated_tenancies"]])

    def test_source_range_is_not_falsely_precise(self):
        self.assertIsNone(text_count("7 or 8 Bedroom Shared Apartment", r"bed(?:room)?s?"))

    def test_known_occupancy_capacity_preserved(self):
        housing = {"student:a": {"id": "student:a", "dataset_type": "student", "name": "Studio", "city": "Brisbane",
            "region": "QLD", "address": "1 Example St", "source_url": "https://example.invalid/a",
            "metadata": {"room_types": [{"name": "Studio", "bedrooms": 0, "bathrooms": 1, "max_people": 1}]}}}
        unit = generate(housing, [], 1, 31)["execution_units"][0]
        self.assertEqual(unit["max_occupants"], 1)
        self.assertEqual(unit["property_field_sources"]["max_occupants"]["origin"], "observed")
        self.assertEqual(text_count("2 People", r"persons?|people|guests?"), 2)


if __name__ == "__main__":
    unittest.main()
