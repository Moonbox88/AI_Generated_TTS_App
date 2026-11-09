"""Tests for Stop latency and clean shutdown.

These load the Kokoro model; set TTS_SKIP_SYNTH=1 to skip them.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tts  # noqa: E402
from engines.kokoro_engine import SENTENCE_SPLIT  # noqa: E402

LONG_TEXT = "This is a long sentence that keeps going for a while. " * 20


class SentenceSplitTests(unittest.TestCase):
    def split(self, text):
        return [s for s in re.split(SENTENCE_SPLIT, text) if s]

    def test_splits_each_script_at_sentence_ends(self):
        self.assertEqual(self.split("One. Two! Three?\n\nFour"),
                         ["One.", "Two!", "Three?", "Four"])
        self.assertEqual(self.split("こんにちは。元気ですか？はい"),
                         ["こんにちは。", "元気ですか？", "はい"])
        self.assertEqual(self.split("नमस्ते। आप कैसे हैं"), ["नमस्ते।", "आप कैसे हैं"])

    def test_decimal_point_is_not_a_sentence_end(self):
        self.assertEqual(self.split("Version 2.5 is out."), ["Version 2.5 is out."])


@unittest.skipIf(os.environ.get("TTS_SKIP_SYNTH"), "TTS_SKIP_SYNTH set")
class StopLatencyTests(unittest.TestCase):
    def tearDown(self):
        tts._shutting_down.clear()

    def test_stop_takes_effect_within_a_sentence(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "out.wav"
            playback = tts.speak(LONG_TEXT, voice="af_heart",
                                 output_file=str(out), play=False)
            deadline = time.monotonic() + 120  # first run may load the model
            while playback.sample_rate is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertIsNotNone(playback.sample_rate, "no audio was produced")

            start = time.monotonic()
            playback.stop()
            playback._producer.join(10)
            elapsed = time.monotonic() - start
            # Before sentence splitting a single chunk took ~17 s here.
            self.assertFalse(playback._producer.is_alive())
            self.assertLess(elapsed, 5.0)
            self.assertFalse(out.exists())  # cancelled: nothing published
            self.assertEqual(list(pathlib.Path(tmp).iterdir()), [])  # no .part

    def test_shutdown_waits_for_threads_and_blocks_new_jobs(self):
        playback = tts.speak(LONG_TEXT, voice="af_heart", play=False)
        while playback.sample_rate is None:
            time.sleep(0.02)
        self.assertTrue(tts.shutdown(timeout=10))
        self.assertTrue(playback.is_cancelled)
        self.assertEqual(tts._threads, set())
        with self.assertRaises(RuntimeError):
            tts.speak("Too late.", voice="af_heart", play=False)


@unittest.skipIf(os.environ.get("TTS_SKIP_SYNTH"), "TTS_SKIP_SYNTH set")
class ExitDuringSynthesisTests(unittest.TestCase):
    def test_exit_mid_synthesis_does_not_abort(self):
        # Exiting while a thread was inside torch used to end in
        # "terminate called without an active exception" (exit code 134).
        script = textwrap.dedent(f"""
            import sys, time
            sys.path.insert(0, {str(ROOT)!r})
            import tts
            p = tts.speak({LONG_TEXT!r}, voice="af_heart", play=False)
            while p.sample_rate is None:
                time.sleep(0.02)
            sys.exit(0 if tts.shutdown(timeout=10) else 3)
        """)
        for _ in range(2):  # the crash was timing-dependent
            result = subprocess.run([sys.executable, "-c", script],
                                    capture_output=True, text=True, timeout=180)
            self.assertNotIn("terminate called", result.stderr)
            self.assertEqual(result.returncode, 0, result.stderr[-500:])


if __name__ == "__main__":
    unittest.main()
