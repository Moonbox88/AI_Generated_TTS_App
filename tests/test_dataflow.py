"""Tests for the streaming data flow: buffer, translator, synthesis sinks.

Run from the project root:
    python -m unittest discover -s tests -v

The Synthesis tests load real Kokoro/Piper models (Piper voices download on
first use). Set TTS_SKIP_SYNTH=1 to run only the fast, offline tests.
"""

import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

import translator  # noqa: E402
import tts  # noqa: E402
from tts import _ChunkBuffer  # noqa: E402


class ChunkBufferTests(unittest.TestCase):
    def test_volume_applied_and_underrun_filled_with_silence(self):
        buf = _ChunkBuffer(max_queued=2)
        buf.put(np.ones(4, np.float32))
        out = np.full((6, 1), 9.0, np.float32)
        self.assertFalse(buf.read(out, 6, volume=0.5))  # not closed: keep playing
        np.testing.assert_allclose(out[:, 0], [0.5] * 4 + [0.0] * 2)

    def test_exhausted_once_closed_and_drained(self):
        buf = _ChunkBuffer()
        buf.put(np.ones(2, np.float32))
        buf.close()
        out = np.zeros((4, 1), np.float32)
        self.assertTrue(buf.read(out, 4))

    def test_full_buffer_put_returns_when_cancelled(self):
        buf = _ChunkBuffer(max_queued=1)
        buf.put(np.ones(1, np.float32))
        cancelled = threading.Event()
        threading.Timer(0.3, cancelled.set).start()
        start = time.monotonic()
        self.assertFalse(buf.put(np.ones(1, np.float32), cancelled))
        self.assertGreaterEqual(time.monotonic() - start, 0.25)


class _FakeClient:
    def __init__(self, name, log, fail_after=None):
        self.name, self.log, self.fail_after, self.calls = name, log, fail_after, 0

    def translate(self, text):
        self.calls += 1
        self.log.append(self.name)
        if self.fail_after is not None and self.calls > self.fail_after:
            raise RuntimeError("blocked")
        return f"[{self.name}]{text[:3]}"


class TranslatorTests(unittest.TestCase):
    def setUp(self):
        self._saved = (translator.BACKENDS, translator.CHUNK_DELAY_SECONDS,
                       translator._preferred, dict(translator._results))
        self.log = []
        google = _FakeClient("g", self.log, fail_after=1)
        mymemory = _FakeClient("m", self.log)
        translator.BACKENDS = [
            translator.Backend("g", 50, lambda _t: google, "google_code"),
            translator.Backend("m", 50, lambda _t: mymemory, "mymemory_code"),
        ]
        translator.CHUNK_DELAY_SECONDS = 0
        translator._preferred = None
        translator._results.clear()
        self.text = "\n\n".join(f"Paragraph number {i} here." * 2 for i in range(3))

    def tearDown(self):
        (translator.BACKENDS, translator.CHUNK_DELAY_SECONDS,
         translator._preferred, results) = self._saved
        translator._results.clear()
        translator._results.update(results)

    def test_falls_back_per_piece_and_keeps_finished_work(self):
        pieces = list(translator.iter_translate(self.text, "f"))
        self.assertEqual(len(pieces), 3)
        self.assertTrue(pieces[0].startswith("[g]"))  # kept despite later failure
        self.assertTrue(pieces[1].startswith("[m]"))
        self.assertEqual(self.log, ["g", "g", "m", "m"])  # 3rd goes straight to m

    def test_complete_result_is_cached(self):
        pieces = list(translator.iter_translate(self.text, "f"))
        calls = len(self.log)
        self.assertEqual(translator.translate(self.text, "f"), "\n\n".join(pieces))
        self.assertEqual(len(self.log), calls)

    def test_partial_consumption_is_not_cached(self):
        gen = translator.iter_translate(self.text, "f")
        next(gen)
        gen.close()
        self.assertEqual(translator._results, {})

    def test_english_passes_through(self):
        self.assertEqual(list(translator.iter_translate("hi", "a")), ["hi"])
        self.assertEqual(self.log, [])


@unittest.skipIf(os.environ.get("TTS_SKIP_SYNTH"), "TTS_SKIP_SYNTH set")
class SynthesisTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_synthesise_accepts_segments_and_skips_blank(self):
        audio, rate = tts.synthesise(iter(["Hello there.", "", "Second segment."]),
                                     voice="af_heart")
        self.assertGreater(audio.size, 0)
        self.assertEqual(rate, 24000)

    def test_save_streams_to_file_without_keeping_audio(self):
        import soundfile as sf
        wav = self.dir / "out.wav"
        playback = tts.speak(["One.", "Two."], voice="af_heart",
                             output_file=str(wav), play=False)
        playback.wait()
        self.assertTrue(wav.is_file())
        self.assertFalse((self.dir / "out.wav.part").exists())
        self.assertEqual(playback.audio().size, 0)
        self.assertEqual(sf.info(str(wav)).samplerate, 24000)

    def test_failed_source_leaves_no_file(self):
        def failing():
            yield "Fine."
            raise translator.TranslationError("all failed")
        wav = self.dir / "bad.wav"
        playback = tts.speak(failing(), voice="af_heart",
                             output_file=str(wav), play=False)
        with self.assertRaises(translator.TranslationError):
            playback.wait()
        self.assertFalse(wav.exists())
        self.assertFalse((self.dir / "bad.wav.part").exists())

    def test_piper_voice_keeps_its_own_sample_rate(self):
        import soundfile as sf
        wav = self.dir / "pl.wav"
        tts.speak("Dzień dobry.", voice="pl_PL-gosia-medium",
                  output_file=str(wav), play=False).wait()
        self.assertEqual(sf.info(str(wav)).samplerate, 22050)


if __name__ == "__main__":
    unittest.main()
