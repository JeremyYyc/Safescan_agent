from collections import Counter
from pathlib import Path
import unittest
from unittest.mock import patch

from unilodge_acceptance import analyze, media_package, offer_key, validate_asset


class AcceptanceTests(unittest.TestCase):
    def test_gallery_count_not_package(self):
        self.assertFalse(media_package(Counter(layout=1, lifestyle=9)))
        self.assertFalse(media_package(Counter(layout=1, interior=1)))
        self.assertFalse(media_package(Counter(cropped_plan=1, interior=2)))
        self.assertTrue(media_package(Counter(layout=1, interior=2)))

    def test_default_date_change_not_price_change(self):
        a = dict(lease_label='Year',amount='509',period='week',basis=None,currency=None,default_start='2027-01-04')
        self.assertEqual(offer_key(a), offer_key({**a,'default_start':'2027-02-01'}))
        self.assertNotEqual(offer_key(a), offer_key({**a,'amount':'529'}))

    def test_tampered_image_rejected(self):
        with patch('unilodge_acceptance.sha',return_value='different'):
            with self.assertRaisesRegex(ValueError,'media_hash_mismatch'):
                validate_asset({'sha256':'expected','id':'fixture'},Path('fixture'))

    def test_stale_review_rejected(self):
        with patch('unilodge_acceptance.read',return_value={'snapshot_outcomes_sha256':'expected'}):
            with patch('unilodge_acceptance.sha',return_value='changed'):
                with self.assertRaisesRegex(ValueError,'review_snapshot_mismatch'):
                    analyze(Path('fixture'))


if __name__ == '__main__':
    unittest.main()
