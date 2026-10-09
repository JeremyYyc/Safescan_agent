import unittest

from home_collect import parse


class HomeTests(unittest.TestCase):
    def setUp(self):
        self.source = {'url': 'https://www.homeapartments.com.au/example',
                       'retrieved_at': '2026-09-28', 'rights_status': 'unverified'}
        self.body = '''<div class="floorplan-section" data-id="123" data-name="East | 2 Bed | 2 Bath | C04">
        <span name="less-info">Mar</span><span name="more-info">vel</span>
        <table><tr class="unit-container" id="unit-12">
        <td class="td-card-name"><p>Apartment:</p> #2108.687</td>
        <td class="td-card-sqft"><p>Sq.M.:</p> 80</td>
        <td class="td-card-rent"><p>Rent:</p>$875.00<span>/Week</span></td>
        </tr></table><h2>Floor Plan Video</h2></div>'''

    def test_units_and_split_description(self):
        room, units, assets = parse(self.body, '', self.source)
        self.assertEqual(room['description'], 'Marvel')
        self.assertEqual((room['bedrooms'], room['bathrooms']), (2, 2))
        self.assertEqual(units[0]['unit_number_raw'], '#2108.687')
        self.assertEqual(units[0]['price_amount'], 875)
        self.assertEqual(units[0]['area_sqm'], 80)
        self.assertEqual(units[0]['price_period'], 'week')
        self.assertEqual(assets, [])

    def test_gallery_scope_dedupe_and_allowlist(self):
        gallery = '''<div class="carousel-item">
        <img alt="Floor Plan" src="https://resource.rentcafe.com/plan.jpg">
        <img alt="Floor Plan" src="https://resource.rentcafe.com/plan.jpg">
        <img alt="Lobby" src="https://resource.rentcafe.com/lobby.jpg">
        <img alt="Floor Plan" src="https://invalid.example/plan.jpg"></div>'''
        _, _, assets = parse(self.body, gallery, self.source)
        self.assertEqual(len(assets), 2)
        self.assertEqual(assets[0]['kind'], 'floorplan')
        self.assertEqual(assets[1]['kind'], 'marketing_image')
        self.assertTrue(all(a['unit_id'] is None for a in assets))

    def test_layout_change_fails(self):
        with self.assertRaisesRegex(ValueError, 'missing_floorplan_section'):
            parse('<html></html>', '', self.source)


if __name__ == '__main__':
    unittest.main()
