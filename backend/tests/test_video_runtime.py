"""Run with pytest or stdlib unittest inside the actual backend image.

Only the object-storage boundary is replaced; OpenCV, Haar data and the real
frame filtering implementation run on synthetic images, without user assets.
"""
from io import BytesIO
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import av
import cv2
import numpy as np
from PIL import Image
from app.tools import video_tools
from app.settings import Settings


class VideoRuntimeTests(unittest.TestCase):
    def test_long_video_sampling_is_uniform_and_bounded(self):
        timestamps = video_tools._sample_timestamps(6000, 1.0, 1200)
        self.assertEqual(len(timestamps), 1200)
        self.assertEqual(timestamps[:3], [0.0, 5.0, 10.0])
        self.assertEqual(timestamps[-1], 5995.0)

    def test_short_video_keeps_requested_sample_rate(self):
        self.assertEqual(video_tools._sample_timestamps(3.2, 1.0, 1200), [0.0, 1.0, 2.0, 3.0])

    def test_real_decoder_adaptively_caps_long_video_samples(self):
        descriptor,path=tempfile.mkstemp(suffix='.mp4')
        os.close(descriptor)
        Path(path).unlink(missing_ok=True)
        try:
            with av.open(path,'w',format='mp4') as output:
                stream=output.add_stream('mpeg4',rate=2)
                stream.width=64;stream.height=64;stream.pix_fmt='yuv420p'
                for index in range(20):
                    pixels=np.full((64,64,3),index*10,dtype=np.uint8)
                    frame=av.VideoFrame.from_ndarray(pixels,format='rgb24')
                    for packet in stream.encode(frame): output.mux(packet)
                for packet in stream.encode(): output.mux(packet)

            @contextmanager
            def local_copy(*args,**kwargs):
                yield path

            settings=Settings(MAX_VIDEO_SECONDS=10,MAX_EXTRACTED_FRAMES=3,VIDEO_FRAME_SAMPLE_RATE=1)
            with patch.object(video_tools,'get_settings',return_value=settings), \
                 patch.object(video_tools.storage,'local_copy',side_effect=local_copy), \
                 patch.object(video_tools.storage,'put',side_effect=['frame-1','frame-2','frame-3']):
                self.assertEqual(video_tools.extract_frames('fixture'),['frame-1','frame-2','frame-3'])
        finally:
            Path(path).unlink(missing_ok=True)

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

    def test_4k_sharpness_uses_reference_scale(self):
        base = np.random.default_rng(42).integers(60, 220, (135, 240, 3), dtype=np.uint8)
        pixels = cv2.resize(base, (3840, 2160), interpolation=cv2.INTER_LINEAR)
        gray = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
        self.assertLess(cv2.Laplacian(gray, cv2.CV_64F).var(), 50)
        self.assertGreater(video_tools._sharpness_variance(gray), 50)
        # Isolate this test from Haar false positives on synthetic noise.
        with patch.object(video_tools.cv2, 'CascadeClassifier') as classifier:
            classifier.return_value.detectMultiScale.return_value = []
            frames, stats, deleted = self.filter_images({'4k': pixels})
        self.assertEqual(frames, ['4k'])
        self.assertEqual(stats['blurry'], 0)
        self.assertEqual(deleted, [])

    def test_rejected_dark_frame_does_not_suppress_clear_duplicate(self):
        pixels = np.random.default_rng(42).integers(0, 50, (256, 256, 3), dtype=np.uint8)
        with patch.object(video_tools.cv2, 'CascadeClassifier') as classifier:
            classifier.return_value.detectMultiScale.return_value = []
            frames, stats, deleted = self.filter_images({'dark': pixels, 'clear': pixels + 100})
        self.assertEqual(frames, ['clear'])
        self.assertEqual(stats, {'similar': 0, 'blurry': 0, 'dark': 1, 'sensitive': 0})
        self.assertEqual(deleted, ['dark'])

    def test_face_rejection_does_not_suppress_later_safe_view(self):
        pixels = np.random.default_rng(42).integers(60, 220, (256, 256, 3), dtype=np.uint8)
        with patch.object(video_tools.cv2, 'CascadeClassifier') as classifier:
            classifier.return_value.detectMultiScale.side_effect = [[(1, 1, 40, 40)], []]
            frames, stats, deleted = self.filter_images({'face': pixels, 'safe': pixels})
        self.assertEqual(frames, ['safe'])
        self.assertEqual(stats['sensitive'], 1)
        self.assertEqual(deleted, ['face'])

    def test_all_faces_remain_rejected_without_fallback(self):
        pixels = np.random.default_rng(42).integers(60, 220, (256, 256, 3), dtype=np.uint8)
        with patch.object(video_tools.cv2, 'CascadeClassifier') as classifier:
            classifier.return_value.detectMultiScale.return_value = [(1, 1, 40, 40)]
            frames, stats, deleted = self.filter_images({'face1': pixels, 'face2': pixels})
        self.assertEqual(frames, [])
        self.assertEqual(stats['sensitive'], 2)
        self.assertEqual(deleted, ['face1', 'face2'])


if __name__ == '__main__':
    unittest.main()
