import unittest

from unilodge_regional_media import media_complete


def asset(role, category, status='assistant_reviewed'):
    return {'role': role, 'review': {'status': status, 'category': category}}


class RegionalCompletenessTests(unittest.TestCase):
    def test_complete_plan_and_interior(self):
        self.assertTrue(media_complete([asset('layout', 'layout_complete'), asset('interior_candidate', 'interior')]))

    def test_cropped_plan_and_thumbnail_cannot_qualify(self):
        self.assertFalse(media_complete([asset('layout', 'layout_cropped'), asset('interior_candidate', 'interior')]))
        self.assertFalse(media_complete([asset('layout', 'layout_complete'), asset('interior_candidate', 'interior_low_resolution')]))

    def test_people_are_explicit_supplementary_tier(self):
        items = [asset('layout', 'layout_complete'), asset('interior_candidate', 'interior_with_people')]
        self.assertFalse(media_complete(items))
        self.assertTrue(media_complete(items, include_people=True))

    def test_pending_or_wrong_role_does_not_qualify(self):
        self.assertFalse(media_complete([asset('layout', 'layout_complete', 'pending'), asset('interior_candidate', 'interior')]))
        self.assertFalse(media_complete([asset('interior_candidate', 'layout_complete'), asset('layout', 'interior')]))


if __name__ == '__main__':
    unittest.main()
