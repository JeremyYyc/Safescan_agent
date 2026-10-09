from copy import deepcopy
import unittest

from source_fit import blockers, contract, validate

VALID = {'reference': 'DEMO-001', 'address': 'Example', 'bedrooms': 0, 'bathrooms': '1',
         'parking_spaces': 0, 'floor_area_sqm': '44', 'weekly_rent': '675', 'currency': 'AUD',
         'status': 'draft', 'listing_visibility': 'private', 'attributes': {},
         'display_image_urls': ['https://example.test/interior.jpg'], 'floorplan_url': 'https://example.test/plan.jpg'}


class SourceFitTests(unittest.TestCase):
    def test_valid_zero_parking_and_studio(self):
        self.assertEqual(validate(VALID), [])

    def test_unknown_parking_fails_insert(self):
        item = {**VALID, 'parking_spaces': None}
        self.assertIn('parking_spaces:required_nonnegative_integer', validate(item))

    def test_boolean_not_integer(self):
        self.assertIn('bedrooms:required_nonnegative_integer', validate({**VALID, 'bedrooms': True}))

    def test_invalid_decimal_precision_and_nonfinite(self):
        for value in ('NaN', 'Infinity', '-1', '1.001', '1000000000000'):
            self.assertIn('weekly_rent:invalid_decimal', validate({**VALID, 'weekly_rent': value}))

    def test_nullable_area_but_not_zero(self):
        self.assertEqual(validate({**VALID, 'floor_area_sqm': None}), [])
        self.assertIn('floor_area_sqm:invalid_decimal', validate({**VALID, 'floor_area_sqm': '0'}))

    def test_missing_media_and_invalid_enums(self):
        item = deepcopy(VALID)
        item.update(display_image_urls=[], floorplan_url='javascript:x', status='available', currency='$')
        errors = validate(item)
        self.assertIn('display_image_urls:pilot_requires_images', errors)
        self.assertIn('floorplan_url:pilot_requires_plan', errors)
        self.assertIn('status:invalid_enum', errors)
        self.assertIn('currency:unconfirmed_or_invalid', errors)

    def test_room_type_not_unit_and_link_not_video(self):
        self.assertIn('room_type_is_not_a_real_unit', blockers('room_type'))
        self.assertIn('no_inspection_video_file', blockers('unit_listing'))
        self.assertNotIn('room_type_is_not_a_real_unit', blockers('unit_listing'))

    def test_actual_schema_and_parking_migration(self):
        schema = contract()
        self.assertTrue(schema['parking_required_on_insert'])
        self.assertEqual(schema['fields']['parking_spaces'], 'Mapped[int | None]')
        self.assertTrue(set(VALID) <= set(schema['fields']))


if __name__ == '__main__':
    unittest.main()
