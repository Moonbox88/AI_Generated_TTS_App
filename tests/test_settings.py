"""Tests for persistent settings and the remembered GUI theme."""

import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import settings  # noqa: E402


class SettingsFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        self.path = self.dir / "sub" / "settings.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_is_empty(self):
        self.assertEqual(settings.load(self.path), {})

    def test_round_trip_creates_folder(self):
        self.assertTrue(settings.save({"theme": "dark"}, self.path))
        self.assertEqual(settings.load(self.path), {"theme": "dark"})

    def test_save_merges_with_existing_keys(self):
        settings.save({"theme": "dark", "other": 1}, self.path)
        settings.save({"theme": "light"}, self.path)
        self.assertEqual(settings.load(self.path), {"theme": "light", "other": 1})

    def test_corrupt_or_wrong_shape_file_is_ignored(self):
        self.path.parent.mkdir()
        for content in ("{not json", "[1, 2]", ""):
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                self.assertEqual(settings.load(self.path), {})

    def test_unwritable_location_returns_false_and_leaves_no_temp(self):
        blocker = self.dir / "file"
        blocker.write_text("x")
        self.assertFalse(settings.save({"theme": "dark"}, blocker / "settings.json"))
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["file"])

    def test_env_override_and_platform_defaults(self):
        with mock.patch.dict(os.environ, {"TTS_CONFIG_DIR": str(self.dir)}):
            self.assertEqual(settings.settings_path(), self.dir / "settings.json")
        env = {k: v for k, v in os.environ.items() if k not in ("TTS_CONFIG_DIR",)}
        env["XDG_CONFIG_HOME"] = "/cfg"
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(settings.config_dir(), pathlib.Path("/cfg/text-to-speech"))
        env["APPDATA"] = r"C:\Users\me\AppData\Roaming"
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(sys, "platform", "win32"):
            self.assertEqual(settings.config_dir().name, "TextToSpeech")


@unittest.skipIf(sys.platform.startswith("linux") and not os.environ.get("DISPLAY"),
                 "needs a display")
class RememberedThemeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"TTS_CONFIG_DIR": self._tmp.name})
        self._env.start()
        import gui
        self.gui = gui

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def open_app(self):
        app = self.gui.App()
        self.addCleanup(app.destroy)
        return app

    def test_first_launch_is_light(self):
        self.assertEqual(self.open_app()._theme, "light")

    def test_toggle_is_remembered_by_the_next_launch(self):
        app = self.open_app()
        app._toggle_theme()
        stored = json.loads(settings.settings_path().read_text(encoding="utf-8"))
        self.assertEqual(stored, {"theme": "dark"})

        reopened = self.open_app()
        self.assertEqual(reopened._theme, "dark")
        self.assertEqual(str(reopened._text_box["background"]),
                         self.gui.gui_theme.PALETTES["dark"]["field"])
        self.assertEqual(str(reopened._theme_btn["text"]), "☀  Light")

    def test_unknown_stored_theme_falls_back_to_light(self):
        settings.save({"theme": "neon"})
        self.assertEqual(self.open_app()._theme, "light")


if __name__ == "__main__":
    unittest.main()
