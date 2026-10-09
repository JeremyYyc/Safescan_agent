import unittest

from novus_collect import parse
from source_fit_probe import parse_home_index

SOURCE = {'url': 'https://www.novusaus.com/find-your-home/test/IRE123', 'retrieved_at': 'fixture'}
BODY = '''<section><h2 id="currentAddress">302/Example Street</h2>
<div><img alt="bed"><span class="ma">1</span></div>
<div><img alt="bath"><span class="ma">1</span></div>
<div><img alt="car"><span class="ma">0</span></div>
<span class="ma">50 m<sup>2</sup></span><strong>$1,675.50 per week</strong>
<p>Available 3rd November 2025</p></section>
<a class="floorplan" href="https://inspectre.blob.core.windows.net/plan.jpg">Plan</a>
<img src="https://inspectre.blob.core.windows.net/plan.jpg">
<img src="https://inspectre.blob.core.windows.net/interior.jpg">
<iframe src="https://www.youtube.com/embed/example"></iframe>
<section><strong>$999 per week</strong></section>'''


class NovusTests(unittest.TestCase):
    def test_scoped_price_and_zero_parking(self):
        item = parse(BODY, SOURCE)
        self.assertEqual(item['weekly_rent'], '1675.50')
        self.assertEqual(item['parking_spaces'], 0)
        self.assertEqual(item['source_listing_id'], 'IRE123')
        self.assertIsNone(item['currency'])

    def test_area_not_assumed_internal(self):
        item = parse(BODY, SOURCE)
        self.assertEqual(item['area_sqm'], '50')
        self.assertEqual(item['area_scope'], 'unspecified_listing_area')
        self.assertFalse(item['availability_verified'])

    def test_media_dedup_and_external_video(self):
        item = parse(BODY, SOURCE)
        self.assertEqual(len(item['assets']), 2)
        self.assertEqual(item['assets'][0]['kind'], 'floorplan')
        self.assertFalse(item['assets'][0]['downloaded'])
        self.assertEqual(len(item['video_links']), 1)

    def test_missing_price_or_address_fails(self):
        for body in (BODY.replace('id="currentAddress"', ''), BODY.replace('$1,675.50 per week', 'Contact us')):
            with self.assertRaises(ValueError):
                parse(body, SOURCE)

    def test_unknown_parking_not_zero(self):
        self.assertIsNone(parse(BODY.replace('alt="car"', 'alt="unknown"'), SOURCE)['parking_spaces'])

    def test_home_cards_not_detail_rows(self):
        card = '<div class="fp-container" id="a"><span class="fp-availability" data-original="3"></span></div>'
        result = parse_home_index(card + card)
        self.assertEqual(result['floorplan_card_count'], 1)
        self.assertEqual(result['availability_badge_sum'], 3)
        self.assertFalse(result['is_verified_unique_unit_count'])

    def test_home_structure_change_fails(self):
        with self.assertRaises(ValueError):
            parse_home_index('<div>No results</div>')


if __name__ == '__main__':
    unittest.main()
