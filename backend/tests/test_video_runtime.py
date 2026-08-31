"""Run with pytest or stdlib unittest inside the actual backend image.

Only the object-storage boundary is replaced; OpenCV, Haar data and the real
frame filtering implementation run on synthetic images, without user assets.
"""
from io import BytesIO
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image
from app.tools import video_tools


class VideoRuntimeTests(unittest.TestCase):
    def filter_images(self, images):
        objects = {}
        for ref, pixels in images.items():
            stream = BytesIO()
            Image.fromarray(pixels).save(stream, format='PNG')
            objects[ref] = stream.getvalue()
        with patch.object(video_tools.storage, 'read', side_effect=objects.__getitem__), \
             patch.object(video_tools.storage, 'remove_unreferenced') as remove:
            frames, stats = video_tools.filter_frames_with_stats(list(objects))
        return frames, stats, [call.args[0] for call in remove.call_args_list]

    def test_haar_cascade_loads_and_runs(self):
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.assertFalse(cascade.empty())
        self.assertEqual(len(cascade.detectMultiScale(np.zeros((128, 128), dtype=np.uint8))), 0)

    def test_real_filter_retains_sharp_image_and_removes_duplicate(self):
        pixels = np.random.default_rng(42).integers(0, 256, (256, 256, 3), dtype=np.uint8)
        frames, stats, deleted = self.filter_images({'sharp': pixels, 'duplicate': pixels})
        self.assertEqual(frames, ['sharp'])
        self.assertEqual(stats, {'similar': 1, 'blurry': 0, 'dark': 0, 'sensitive': 0})
        self.assertEqual(deleted, ['duplicate'])

    def test_real_filter_removes_blurry_image(self):
        frames, stats, deleted = self.filter_images({'blurry': np.full((128, 128, 3), 200, dtype=np.uint8)})
        self.assertEqual(frames, [])
        self.assertEqual(stats, {'similar': 0, 'blurry': 1, 'dark': 0, 'sensitive': 0})
        self.assertEqual(deleted, ['blurry'])

    def test_real_filter_removes_dark_sharp_image(self):
        pixels = np.random.default_rng(42).integers(0, 50, (256, 256, 3), dtype=np.uint8)
        frames, stats, deleted = self.filter_images({'dark': pixels})
        self.assertEqual(frames, [])
        self.assertEqual(stats, {'similar': 0, 'blurry': 0, 'dark': 1, 'sensitive': 0})
        self.assertEqual(deleted, ['dark'])


if __name__ == '__main__':
    unittest.main()
