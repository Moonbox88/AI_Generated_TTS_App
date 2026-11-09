"""Tests for CLI argument validation. Fast and offline."""

import contextlib
import io
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import main  # noqa: E402


class SpeedVolumeValidationTests(unittest.TestCase):
    def parse(self, *extra):
        return main.build_parser().parse_args(["-t", "hi", *extra])

    def assert_rejected(self, *extra, message):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as ctx:
            self.parse(*extra)
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn(message, stderr.getvalue())

    def test_defaults(self):
        args = self.parse()
        self.assertEqual((args.speed, args.volume), (1.0, 1.0))

    def test_bounds_are_inclusive(self):
        args = self.parse("-s", "0.5", "--volume", "0")
        self.assertEqual((args.speed, args.volume), (0.5, 0.0))
        args = self.parse("-s", "2", "--volume", "1")
        self.assertEqual((args.speed, args.volume), (2.0, 1.0))

    def test_out_of_range(self):
        for bad in ("0", "-1", "0.49", "2.01"):
            with self.subTest(speed=bad):
                self.assert_rejected("-s", bad, message="speed must be between")
        for bad in ("-0.1", "1.5"):
            with self.subTest(volume=bad):
                self.assert_rejected("--volume", bad, message="volume must be between")

    def test_non_numbers(self):
        self.assert_rejected("-s", "fast", message="speed must be a number")
        for bad in ("nan", "inf"):
            with self.subTest(speed=bad):
                self.assert_rejected("-s", bad, message="speed must be between")


if __name__ == "__main__":
    unittest.main()
