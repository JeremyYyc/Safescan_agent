import unittest

from flagstaff_collect import media_candidates, parse_rooms


SOURCE = {'url': 'https://www.reserve.unilodge.com.au/categoryInfo.html?category=490',
          'retrieved_at': '2026-09-29T00:00:00+00:00', 'sha256': 'fixture'}


class FlagstaffTests(unittest.TestCase):
    def test_room_scoping_and_price_basis(self):
        body = '''<div class="ul_room"><h2>4 Bedroom Apartment</h2>
          <p>Each 8m² bedroom. Weekly Rent is per person</p>
          <div class="ul_stay"><div class="ul_rateTitle">Example lease</div>
          <div class="ul_stayPrice">$<span class="price">429</span> / week</div>
          <input class="fromDateCustom" value="2027-02-01"></div></div>
          <div class="ul_room"><h2>Other</h2><span class="price">999</span></div>'''
        rooms = parse_rooms(body, SOURCE)
        self.assertEqual(len(rooms), 1)
        self.assertEqual(rooms[0]['area_scope'], 'bedroom')
        self.assertEqual(rooms[0]['area_sqm'], 8)
        self.assertEqual(rooms[0]['offers'][0]['basis'], 'person')
        self.assertEqual(rooms[0]['offers'][0]['amount'], '429')
        self.assertIsNone(rooms[0]['offers'][0]['currency'])

    def test_empty_stays_are_not_free_rent(self):
        room = parse_rooms('<div class="ul_room"><h2>Studio Queen</h2></div>', SOURCE)[0]
        self.assertEqual(room['offers'], [])
        self.assertIn('no_stay_period_offered', room['missing'])
        self.assertIsNone(room['area_sqm'])

    def test_css_gallery_and_queen_area(self):
        body = '''<div class="ul_room"><h2>Studio Queen</h2>
          <div class="ul_description">The 16m² studio</div>
          <div class="roomImages"><div style="background-image:url('/data/room.jpg')"></div>
          <div style="background-image:url(/data/room.jpg)"></div>
          <div style="background-image:url(https://other.test/x.jpg)"></div></div></div>'''
        room = parse_rooms(body, SOURCE)[0]
        self.assertEqual(room['area_sqm'], 16)
        self.assertEqual(len(room['photos']), 1)
        self.assertEqual(room['photos'][0]['association'], 'room_section_unverified')

    def test_changed_structure_fails(self):
        with self.assertRaisesRegex(ValueError, 'no_target'):
            parse_rooms('<h2>Studio Standard</h2>', SOURCE)

    def test_missing_price_is_not_silently_dropped(self):
        with self.assertRaisesRegex(ValueError, 'missing_price'):
            parse_rooms('<div class="ul_room"><h2>Studio Standard</h2><div class="ul_stay"></div></div>', SOURCE)

    def test_floorplan_links_are_unverified_and_deduplicated(self):
        tag = '<img alt="Standard floor plan" src="https://image-tc.galaxy.tf/a.png">'
        assets = media_candidates(tag + tag + '<img src="https://other.test/logo.png">', SOURCE)
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]['kind'], 'floorplan_candidate')
        self.assertIsNone(assets[0]['room_id'])
        self.assertFalse(assets[0]['downloaded'])


if __name__ == '__main__':
    unittest.main()
