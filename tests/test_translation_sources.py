"""Tests for translating from any language (not just English). Offline."""

import contextlib
import io
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import main  # noqa: E402
import translator  # noqa: E402
from render_cache import RenderKey  # noqa: E402
from voices import AUTO_DETECT, needs_translation, source_languages, source_name  # noqa: E402


class SourceLanguageTests(unittest.TestCase):
    def test_needs_translation_compares_source_and_target(self):
        self.assertTrue(needs_translation("a", "pl"))       # Polish -> English
        self.assertTrue(needs_translation("pl"))            # English (default) -> Polish
        self.assertFalse(needs_translation("a"))            # English -> English
        self.assertFalse(needs_translation("b", "a"))       # US and UK English are one language
        self.assertFalse(needs_translation("pl", "pl"))
        self.assertTrue(needs_translation("a", AUTO_DETECT))

    def test_source_list_has_auto_then_one_entry_per_language(self):
        codes = [code for code, _ in source_languages()]
        self.assertEqual(codes[0], AUTO_DETECT)
        self.assertIn("pl", codes)
        self.assertNotIn("b", codes)  # collapsed into English
        self.assertEqual(source_name("a"), "English")
        self.assertEqual(source_name("pl"), "Polish")


class _Client:
    def __init__(self, log, name, reply=None, fail=False):
        self.log, self.name, self.reply, self.fail = log, name, reply, fail

    def translate(self, text):
        self.log.append(self.name)
        if self.fail:
            raise RuntimeError("down")
        return self.reply if self.reply is not None else f"<{text}>"


class TranslatorSourceTests(unittest.TestCase):
    def setUp(self):
        self._saved = (translator.BACKENDS, translator.CHUNK_DELAY_SECONDS,
                       translator._preferred, dict(translator._results))
        translator.CHUNK_DELAY_SECONDS = 0
        translator._preferred = None
        translator._results.clear()
        self.log, self.built = [], []

    def tearDown(self):
        (translator.BACKENDS, translator.CHUNK_DELAY_SECONDS,
         translator._preferred, results) = self._saved
        translator._results.clear()
        translator._results.update(results)

    def backends(self, google: _Client, mymemory: _Client):
        def build(client, name):
            return lambda s, t: (self.built.append((name, s, t)), client)[1]
        translator.BACKENDS = [
            translator.Backend("google", 4000, build(google, "google"), "google_code",
                               supports_auto=True),
            translator.Backend("mymemory", 450, build(mymemory, "mymemory"), "mymemory_code",
                               rejects=translator._mymemory_error),
        ]

    def test_each_backend_gets_its_own_source_and_target_codes(self):
        self.backends(_Client(self.log, "g", fail=True), _Client(self.log, "m"))
        self.assertEqual(translator.translate("Dzień dobry.", "a", source="pl"),
                         "<Dzień dobry.>")
        self.assertEqual(self.built, [("google", "pl", "en"), ("mymemory", "pl-PL", "en-US")])

    def test_auto_detect_skips_backends_without_auto_and_says_why(self):
        self.backends(_Client(self.log, "g", fail=True), _Client(self.log, "m"))
        with self.assertRaises(translator.TranslationError) as ctx:
            translator.translate("Bună ziua.", "a", source=AUTO_DETECT)
        self.assertEqual(self.log, ["g"])  # MyMemory never asked
        self.assertIn("Auto-detect only works with Google", str(ctx.exception))
        self.assertEqual(self.built[0], ("google", "auto", "en"))

    def test_mymemory_error_text_is_a_failure_not_a_translation(self):
        refusal = "'AUTO' IS AN INVALID SOURCE LANGUAGE . EXAMPLE: LANGPAIR=EN|IT"
        quota = "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY."
        for reply in (refusal, quota):
            with self.subTest(reply=reply[:20]):
                translator._preferred = None
                self.backends(_Client(self.log, "g", fail=True),
                              _Client(self.log, "m", reply=reply))
                with self.assertRaises(translator.TranslationError):
                    translator.translate("Dzień dobry.", "a", source="pl")

    def test_cache_is_per_source_language(self):
        self.backends(_Client(self.log, "g"), _Client(self.log, "m"))
        translator.translate("Ciao.", "a", source="i")
        translator.translate("Ciao.", "a", source="i")
        translator.translate("Ciao.", "a", source="e")
        self.assertEqual(self.log, ["g", "g"])

    def test_same_language_passes_through_without_network(self):
        self.backends(_Client(self.log, "g"), _Client(self.log, "m"))
        self.assertEqual(translator.translate("Cześć.", "pl", source="pl"), "Cześć.")
        self.assertEqual(self.log, [])


class ChunkPackingTests(unittest.TestCase):
    def test_long_paragraph_packs_sentences_up_to_the_limit(self):
        paragraph = " ".join(f"Sentence {i}." for i in range(30))  # ~360 chars
        chunks = translator.chunk_text(paragraph, 100)
        self.assertTrue(all(len(c) <= 100 for c in chunks))
        self.assertLessEqual(len(chunks), 5)  # not one request per sentence
        self.assertEqual(" ".join(chunks), paragraph)

    def test_cjk_sentences_split_without_spaces(self):
        text = "これは文です。" * 30  # 210 chars, no spaces
        chunks = translator.chunk_text(text, 50)
        self.assertTrue(all(len(c) <= 50 for c in chunks))
        self.assertTrue(all(c.endswith("。") for c in chunks))


class CliSourceTests(unittest.TestCase):
    def parse(self, *extra):
        return main.build_parser().parse_args(["-t", "hi", *extra])

    def test_from_defaults_to_none_and_accepts_codes_and_auto(self):
        self.assertIsNone(self.parse().source)
        self.assertEqual(self.parse("--from", "pl").source, "pl")
        self.assertEqual(self.parse("--from", "auto").source, AUTO_DETECT)

    def test_unknown_source_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parse("--from", "xx")


class RenderKeySourceTests(unittest.TestCase):
    def test_source_is_part_of_the_key(self):
        polish = RenderKey("Ciao.", "a", "af_heart", 1.0, True, source="pl")
        italian = RenderKey("Ciao.", "a", "af_heart", 1.0, True, source="i")
        self.assertNotEqual(polish, italian)


if __name__ == "__main__":
    unittest.main()
