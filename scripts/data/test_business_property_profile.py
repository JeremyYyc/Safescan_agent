import copy
import unittest

from integrate_execution_dataset import business_property_profile


class BusinessPropertyProfileTests(unittest.TestCase):
    def test_studio_uses_one_room_without_changing_source_or_other_attributes(self):
        source = {"rental_scope": "studio", "bedrooms": 0, "whole_apartment_bedrooms": 0,
                  "rooms_count": 2, "bathrooms": 1, "floor_area_sqm": 18,
                  "field_sources": {"bedrooms": {"origin": "observed"}}}
        original = copy.deepcopy(source)
        result = business_property_profile(source)
        self.assertEqual(source, original)
        self.assertEqual((result["bedrooms"], result["whole_apartment_bedrooms"], result["rooms_count"]), (1, 1, 1))
        self.assertEqual((result["bathrooms"], result["floor_area_sqm"]), (1, 18))
        self.assertEqual(result["field_sources"]["bedrooms"]["origin"], "simulated")

    def test_shared_apartment_room_and_whole_apartment_counts_are_preserved(self):
        source = {"rental_scope": "private_room", "bedrooms": 1, "whole_apartment_bedrooms": 5,
                  "rooms_count": 2, "field_sources": {}}
        self.assertEqual(business_property_profile(source), source)


if __name__ == "__main__":
    unittest.main()
