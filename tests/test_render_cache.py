"""Tests for RenderCache: Save after Speak reuses the finished render."""

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from render_cache import RenderCache, RenderKey  # noqa: E402

KEY = RenderKey(text="Hello.", lang="f", voice="ff_siwis", speed=1.0, translate=True)


class RenderCacheTests(unittest.TestCase):
    def setUp(self):
        self._out = tempfile.TemporaryDirectory()
        self.out = pathlib.Path(self._out.name)
        self.cache = RenderCache()

    def tearDown(self):
        self.cache.close()
        self._out.cleanup()

    def render(self, value=0.25):
        path = self.cache.new_path()
        sf.write(str(path), np.full(100, value, np.float32), 24000)
        return path

    def test_miss_when_empty(self):
        self.assertFalse(self.cache.export(KEY, str(self.out / "a.wav")))
        self.assertFalse((self.out / "a.wav").exists())

    def test_hit_copies_audio_and_translated_text(self):
        self.cache.store(KEY, self.render(), "Bonjour.")
        self.assertTrue(self.cache.export(KEY, str(self.out / "a.wav")))
        data, rate = sf.read(str(self.out / "a.wav"), dtype="float32")
        self.assertEqual((data.size, rate), (100, 24000))
        self.assertEqual((self.out / "a.txt").read_text(encoding="utf-8"), "Bonjour.")

    def test_no_txt_without_translation(self):
        key = RenderKey("Hello.", "a", "af_heart", 1.0, translate=False)
        self.cache.store(key, self.render(), None)
        self.assertTrue(self.cache.export(key, str(self.out / "a.wav")))
        self.assertFalse((self.out / "a.txt").exists())

    def test_any_input_change_is_a_miss(self):
        self.cache.store(KEY, self.render(), "Bonjour.")
        for field, value in [("text", "Bye."), ("voice", "af_heart"),
                             ("speed", 1.5), ("translate", False), ("lang", "e")]:
            with self.subTest(field=field):
                changed = RenderKey(**{**KEY.__dict__, field: value})
                self.assertFalse(self.cache.export(changed, str(self.out / "x.wav")))

    def test_new_render_replaces_and_deletes_old(self):
        first = self.render(0.1)
        self.cache.store(KEY, first, "Bonjour.")
        second = self.render(0.9)
        self.cache.store(KEY, second, "Bonjour.")
        self.assertFalse(first.exists())
        self.cache.export(KEY, str(self.out / "a.wav"))
        data, _ = sf.read(str(self.out / "a.wav"), dtype="float32")
        self.assertAlmostEqual(float(data[0]), 0.9, places=3)

    def test_converts_to_other_format_by_extension(self):
        self.cache.store(KEY, self.render(), None)
        self.cache.export(KEY, str(self.out / "a.flac"))
        self.assertEqual(sf.info(str(self.out / "a.flac")).format, "FLAC")

    def test_close_removes_renders(self):
        path = self.render()
        self.cache.store(KEY, path, None)
        self.cache.close()
        self.assertFalse(path.exists())
        self.assertFalse(self.cache.export(KEY, str(self.out / "a.wav")))


if __name__ == "__main__":
    unittest.main()
