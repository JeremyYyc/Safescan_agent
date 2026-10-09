import unittest

from general_batch import select_media


class MediaSelectionTests(unittest.TestCase):
    def setUp(self):
        self.listing = {
            'associatedMedia': [
                {'name': 'Floorplans ground', 'contentUrl': 'https://example.org/ground.jpg'},
                {'name': 'Floorplans first', 'contentUrl': 'https://example.org/first.jpg'},
                {'name': 'Brochure', 'contentUrl': 'https://example.org/info.pdf'}],
            'image': [{'url': 'https://example.org/' + str(i) + '.jpg'} for i in range(8)]}

    def test_light_retains_all_plan_pages(self):
        assets, full_count = select_media(self.listing, 2)
        self.assertEqual(full_count, 10)
        self.assertEqual(len(assets), 4)
        self.assertEqual([a[0] for a in assets], ['layout_candidate'] * 2 + ['gallery_candidate'] * 2)

    def test_full_mode_unchanged(self):
        assets, full_count = select_media(self.listing)
        self.assertEqual(len(assets), full_count)
        self.assertEqual(len(assets), 10)

    def test_gallery_not_mislabeled_interior(self):
        assets, _ = select_media(self.listing, 1)
        self.assertEqual(assets[-1][0], 'gallery_candidate')

    def test_missing_plan_stays_missing(self):
        assets, count = select_media({'image': [{'url': 'https://example.org/a.jpg'}]}, 2)
        self.assertEqual(count, 1)
        self.assertEqual(assets[0][0], 'gallery_candidate')


if __name__ == '__main__':
    unittest.main()
