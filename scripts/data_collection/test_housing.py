import json
import unittest

from housing_collect import parse_property


class HousingTests(unittest.TestCase):
    def fixture(self):
        business = {"@type": "LocalBusiness", "name": "Test residence", "address": {"streetAddress": "Example Street"}}
        return ("<script type='application/ld+json'>" + json.dumps(business) + "</script>" + '''
        <div class="thumb"><a href="/room"><h3 class="thumb__title">1 Bedroom Apartment</h3></a>
        <span class="thumb_price">From $1,200*</span><img data-src="https://image-tc.galaxy.tf/test/a.jpg"></div>
        <div class="thumb"><a href="/studio"><h3 class="thumb__title">Studio Apartment</h3></a>
        <img data-src="https://image-tc.galaxy.tf/test/b.jpg"></div>
        <img alt="Studio Apartment" data-src="https://image-tc.galaxy.tf/test/studio.jpg">
        <img alt="Studio Premium" data-src="https://image-tc.galaxy.tf/test/premium.jpg">
        <a href="https://my.matterport.com/show/?m=abc">Studio Apartment</a>
        <a href="https://my.matterport.com/show/?m=abc&amp;ss=1">Studio Apartment</a>
        <a href="https://my.matterport.com/show/?m=def">Common Areas</a>
        <a href="https://www.youtube.com/c/company">Youtube channel</a>
        <div id="facility-1"><h2 class="popup__title">Laundry</h2></div>
        <div id="offer-1"><h2 class="popup__title">Sale offer</h2></div>
        ''').encode()

    def parse(self):
        return parse_property(self.fixture(), {"id": "example", "url": "https://www.unilodge.com.au/example", "retrieved_at": "2026-09-28"})

    def test_prices_do_not_invent_period_or_inventory(self):
        _, rooms, _ = self.parse()
        self.assertEqual(rooms[0]['price_amount'], 1200)
        self.assertEqual(rooms[0]['bedrooms'], 1)
        self.assertIsNone(rooms[0]['price_period'])
        self.assertIsNone(rooms[0]['unit_number'])
        self.assertEqual(rooms[0]['availability'], 'not_confirmed')
        self.assertIsNone(rooms[1]['price_amount'])

    def test_exact_photo_scope(self):
        _, rooms, assets = self.parse()
        photo = next(a for a in assets if a['id'] == rooms[1]['photo_ids'][0])
        self.assertTrue(photo['url'].endswith('/studio.jpg'))
        self.assertEqual(photo['scope'], 'room_type_marketing')
        self.assertFalse(any(a['url'].endswith('/premium.jpg') for a in assets))

    def test_tours_deduplicate_without_claiming_video(self):
        _, rooms, assets = self.parse()
        tours = [a for a in assets if a['kind'] == 'virtual_tour']
        self.assertEqual(len(tours), 2)
        self.assertEqual(len(rooms[1]['virtual_tour_ids']), 1)
        self.assertIsNone(next(a for a in tours if a['label'] == 'Common Areas')['room_type_id'])
        self.assertFalse(any(a['kind'] == 'video' for a in assets))

    def test_stable_ids_and_facilities(self):
        first = self.parse()
        self.assertEqual(first, self.parse())
        self.assertEqual(first[0]['facilities'], ['Laundry'])
        self.assertIsNone(first[0]['legal_owner'])

    def test_missing_structured_data_fails(self):
        with self.assertRaisesRegex(ValueError, 'missing_property'):
            parse_property(b'<h1>Not a property page</h1>', {})


if __name__ == '__main__':
    unittest.main()
