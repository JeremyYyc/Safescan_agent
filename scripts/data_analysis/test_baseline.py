import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from baseline import (CORE, audit_assets, evaluate, home_address, money, offer_complete,
                      ratio, safe_path, sha, write_database)
from PIL import Image


def fixture():
    sample = {k: 'present' for k in CORE}
    sample.update(id='s', source_id='test', property_id='p')
    return {'samples': [sample], 'offers': [], 'units': [], 'assets': [], 'issues': []}


def asset(key, category='interior', human=False):
    return {'id': key, 'sample_id': 's', 'source_id': 'home', 'local_path': 'media/' + key,
            'integrity': 'verified', 'content_key': key, 'kind': 'photo', 'category': category,
            'human_approved': human, 'usable': True, 'association': 'room_type_marketing'}


class BaselineTests(unittest.TestCase):
    def test_zero_denominator(self):
        self.assertIsNone(ratio(0, 0)['value'])
        self.assertEqual(ratio(0, 2)['value'], 0)

    def test_zero_price_is_present(self):
        row = {'amount': '0', 'currency': 'AUD', 'period': 'week', 'basis': 'unit', 'lease_condition': '52 weeks'}
        self.assertTrue(offer_complete(row))
        row['basis'] = 'unknown'
        self.assertFalse(offer_complete(row))

    def test_decimal_and_invalid_price(self):
        self.assertEqual(money(875.1), '875.1')
        for v in ('NaN', '-1', 'Infinity'):
            with self.assertRaises(ValueError):
                money(v)

    def test_paths_cannot_escape(self):
        with self.assertRaises(ValueError):
            safe_path(Path.cwd(), '../outside')

    def test_assistant_review_cannot_pass_human_gate(self):
        data = fixture()
        data['assets'] = [asset('a'), asset('b'), asset('c', 'floorplan')]
        checks, summary = evaluate(data)
        self.assertFalse(checks[0]['quality_pass'])
        self.assertEqual(summary['metrics']['verified_interior_coverage']['numerator'], 0)
        self.assertIsNone(summary['metrics']['human_association_accuracy']['value'])

    def test_duplicate_media_does_not_inflate_coverage(self):
        data = fixture()
        a = asset('a', human=True)
        b = copy.deepcopy(a)
        b['id'] = 'different_url_same_content'
        data['assets'] = [a, b]
        checks, summary = evaluate(data)
        self.assertEqual(checks[0]['interior_count'], 1)
        self.assertEqual(summary['metrics']['exact_image_duplicate_rate']['value'], 0.5)

    def test_units_do_not_inflate_sample_denominator(self):
        data = fixture()
        data['units'] = [{'id': str(i), 'sample_id': 's'} for i in range(3)]
        checks, summary = evaluate(data)
        self.assertEqual(summary['counts']['samples'], 1)
        self.assertEqual(summary['counts']['units'], 3)
        self.assertEqual(len(checks), 1)

    def test_full_quality_can_pass_without_rights(self):
        data = fixture()
        data['assets'] = [asset('a', human=True), asset('b', human=True), asset('c', 'floorplan', True)]
        data['offers'] = [{'id': 'o', 'sample_id': 's', 'amount': '20', 'currency': 'AUD',
                           'period': 'week', 'basis': 'person', 'lease_condition': '52 weeks'}]
        checks, summary = evaluate(data)
        self.assertTrue(checks[0]['quality_pass'])
        self.assertFalse(checks[0]['approved_for_use'])
        self.assertEqual(summary['metrics']['use_admission_rate']['value'], 0)

    def test_address_extraction_ignores_other_property(self):
        wrong = '<script type="application/ld+json">{"name":"Other","address":"wrong"}</script>'
        right = '<script type="application/ld+json">{"name":"Home Docklands","address":{"streetAddress":"Example"}}</script>'
        self.assertIsNone(home_address(wrong))
        self.assertEqual(home_address(wrong + right)['streetAddress'], 'Example')

    def test_hash_failure_quarantined(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new('RGB', (4, 4)).save(root / 'test.png')
            row = {'id': 'a', 'url': 'https://example.test/a', 'kind': 'photo', 'local_path': 'test.png',
                   'sha256': 'incorrect', 'width': 4, 'height': 4}
            assets, issues = audit_assets(root, 'test', [row], {}, True)
            self.assertEqual(assets[0]['integrity'], 'failed')
            self.assertEqual(len(issues), 1)
            row['sha256'] = sha(root / 'test.png')
            assets, issues = audit_assets(root, 'test', [row], {}, True)
            self.assertEqual(assets[0]['integrity'], 'verified')
            self.assertEqual(issues, [])

    def test_sql_counts_match_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            data = fixture()
            checks, summary = evaluate(data)
            path = Path(directory) / 'audit.sqlite'
            write_database(path, data, checks)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM samples').fetchone()[0], summary['counts']['samples'])
                self.assertEqual(db.execute('SELECT SUM(quality_pass) FROM checks').fetchone()[0], 0)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_empty_location_is_missing(self):
        data = fixture()
        data['samples'][0]['location'] = {}
        checks, _ = evaluate(data)
        self.assertIn('missing_core:location', checks[0]['reasons'])

    def test_empty_cohort_all_ratios_are_na(self):
        data = fixture()
        data['samples'] = []
        checks, summary = evaluate(data)
        self.assertEqual(checks, [])
        self.assertIsNone(summary['metrics']['quality_pass_rate']['value'])

    def test_assistant_config_cannot_grant_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new('RGB', (4, 4)).save(root / 'test.png')
            checksum = sha(root / 'test.png')
            row = {'id': 'a', 'url': 'https://example.test/a', 'kind': 'photo', 'local_path': 'test.png',
                   'sha256': checksum, 'width': 4, 'height': 4}
            reviews = {checksum: {'category': 'interior', 'usable': True, 'human_approved': True}}
            assets, _ = audit_assets(root, 'home', [row], reviews, True)
            self.assertFalse(assets[0]['human_approved'])


if __name__ == '__main__':
    unittest.main()
