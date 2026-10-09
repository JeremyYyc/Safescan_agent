from pathlib import Path
import unittest
from unittest.mock import patch

from unilodge_preview import link, targets


class PreviewTests(unittest.TestCase):
    def test_unsafe_link_not_rendered(self):
        self.assertEqual(link('javascript:alert(1)', '<unsafe>'), '&lt;unsafe&gt;')

    def test_link_values_escaped(self):
        html = link('https://example.test/?a="&b=1', '<source>')
        self.assertIn('&quot;&amp;b=1', html)
        self.assertIn('&lt;source&gt;', html)
        self.assertNotIn('<source>', html)

    def test_dedup_and_no_queen_deluxe_assumption(self):
        rooms = [{'photos': [{'url': 'https://example.test/a.jpg'}, {'url': 'https://example.test/a.jpg'}]}]
        plans = [{'kind': 'floorplan_candidate', 'url': 'https://example.test/studio-deluxe-queen-fp.jpg'},
                 {'kind': 'floorplan_candidate', 'url': 'https://example.test/studio-standard-fp.jpg'}]
        with patch('unilodge_preview.read', side_effect=[rooms, plans]):
            result = targets(Path('fixture'))
        self.assertEqual(len(result), 2)
        self.assertNotIn('deluxe', str(result))

    def test_scope_limit(self):
        rooms = [{'photos': [{'url': 'https://example.test/' + str(n)} for n in range(24)]}]
        with patch('unilodge_preview.read', side_effect=[rooms, []]):
            with self.assertRaisesRegex(ValueError, 'scope_exceeded'):
                targets(Path('fixture'))


if __name__ == '__main__':
    unittest.main()
