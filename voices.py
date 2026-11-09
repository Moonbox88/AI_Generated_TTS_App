"""Single source of truth for languages and voices across all TTS engines.

Both the CLI and the GUI read from here, so adding a voice or a language
means editing one table rather than three modules.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    google_code: str    # Google Translate / deep-translator code
    mymemory_code: str  # MyMemory wants full locales, e.g. "pl-PL"


@dataclass(frozen=True)
class Voice:
    id: str       # engine-native voice id, e.g. "af_heart", "pl_PL-gosia-medium"
    label: str    # human-readable name shown in the GUI
    lang: str     # key into LANGUAGES
    engine: str   # key into engines.get_engine()


# ----------------------------------------------------------------------
# Languages
# ----------------------------------------------------------------------
# Kokoro uses single-letter codes; Piper languages get their ISO code.
# Note 'p' is Brazilian Portuguese (Kokoro), so Polish must be 'pl'.

_LANGUAGES = [
    Language("a", "American English", "en", "en-US"),
    Language("b", "British English", "en", "en-GB"),
    Language("j", "Japanese", "ja", "ja-JP"),
    Language("z", "Mandarin Chinese", "zh-CN", "zh-CN"),
    Language("e", "Spanish", "es", "es-ES"),
    Language("f", "French", "fr", "fr-FR"),
    Language("h", "Hindi", "hi", "hi-IN"),
    Language("i", "Italian", "it", "it-IT"),
    Language("p", "Brazilian Portuguese", "pt", "pt-BR"),
    Language("pl", "Polish", "pl", "pl-PL"),
    Language("ro", "Romanian", "ro", "ro-RO"),
]

LANGUAGES: dict[str, Language] = {lang.code: lang for lang in _LANGUAGES}

ENGLISH_CODES = {code for code, lang in LANGUAGES.items() if lang.google_code == "en"}


# ----------------------------------------------------------------------
# Kokoro voices (24 kHz, model auto-downloaded by the kokoro package)
# ----------------------------------------------------------------------
# Kokoro ids follow <lang><gender>_<name>, so labels are derived rather
# than written out 54 times.

_KOKORO_VOICES: dict[str, list[str]] = {
    "a": ["af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica",
          "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
          "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
          "am_michael", "am_onyx", "am_puck", "am_santa"],
    "b": ["bf_alice", "bf_emma", "bf_isabella", "bf_lily",
          "bm_daniel", "bm_fable", "bm_george", "bm_lewis"],
    "j": ["jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo"],
    "z": ["zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
          "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang"],
    "e": ["ef_dora", "em_alex", "em_santa"],
    "f": ["ff_siwis"],
    "h": ["hf_alpha", "hf_beta", "hm_omega", "hm_psi"],
    "i": ["if_sara", "im_nicola"],
    "p": ["pf_dora", "pm_alex", "pm_santa"],
}


def _kokoro_label(voice_id: str) -> str:
    """'af_heart' -> 'Heart (F)'."""
    gender, _, name = voice_id.partition("_")
    suffix = {"f": " (F)", "m": " (M)"}.get(gender[-1:], "")
    return name.replace("_", " ").title() + suffix


# ----------------------------------------------------------------------
# Piper voices (ONNX models downloaded on first use from rhasspy/piper-voices)
# ----------------------------------------------------------------------

_PIPER_VOICES = [
    ("pl_PL-gosia-medium", "Gosia (medium)", "pl"),
    ("pl_PL-darkman-medium", "Darkman (medium)", "pl"),
    ("pl_PL-mc_speech-medium", "MC Speech (medium)", "pl"),
    ("pl_PL-bass-high", "Bass (high)", "pl"),
    ("pl_PL-mls_6892-low", "MLS 6892 (low)", "pl"),
    ("ro_RO-mihai-medium", "Mihai (medium)", "ro"),
]


# ----------------------------------------------------------------------
# Combined registry
# ----------------------------------------------------------------------

def _build_registry() -> dict[str, Voice]:
    registry: dict[str, Voice] = {}
    for lang, ids in _KOKORO_VOICES.items():
        for voice_id in ids:
            registry[voice_id] = Voice(voice_id, _kokoro_label(voice_id), lang, "kokoro")
    for voice_id, label, lang in _PIPER_VOICES:
        registry[voice_id] = Voice(voice_id, label, lang, "piper")
    return registry


VOICES: dict[str, Voice] = _build_registry()
VOICE_IDS: list[str] = list(VOICES)

_BY_LANG: dict[str, list[Voice]] = {}
for _voice in VOICES.values():
    _BY_LANG.setdefault(_voice.lang, []).append(_voice)

DEFAULT_VOICE = "af_heart"
DEFAULT_LANG = "a"


def get_voice(voice_id: str) -> Voice:
    try:
        return VOICES[voice_id]
    except KeyError:
        raise ValueError(f"Unknown voice '{voice_id}'") from None


def voices_for_lang(lang_code: str) -> list[Voice]:
    """Voices available for a language, in registry order."""
    return list(_BY_LANG.get(lang_code, ()))


def default_voice_for_lang(lang_code: str) -> str | None:
    matches = voices_for_lang(lang_code)
    return matches[0].id if matches else None


def get_language(lang_code: str) -> Language:
    try:
        return LANGUAGES[lang_code]
    except KeyError:
        raise ValueError(f"Unknown language code '{lang_code}'") from None


# ----------------------------------------------------------------------
# Translation source languages
# ----------------------------------------------------------------------

AUTO_DETECT = "auto"   # let the translator work out the input language
DEFAULT_SOURCE = "a"   # English: the input language before sources existed


def source_languages() -> list[tuple[str, str]]:
    """(code, name) pairs for a "translate from" picker.

    Auto-detect first, then one entry per distinct language: the two
    English variants translate identically, so they collapse to "English".
    """
    out = [(AUTO_DETECT, "Auto-detect")]
    seen: set[str] = set()
    for lang in LANGUAGES.values():
        if lang.google_code in seen:
            continue
        seen.add(lang.google_code)
        out.append((lang.code, "English" if lang.google_code == "en" else lang.name))
    return out


def source_name(code: str) -> str:
    return dict(source_languages()).get(code) or get_language(code).name


def needs_translation(target: str, source: str = DEFAULT_SOURCE) -> bool:
    """True if text in `source` must be translated to be read in `target`.

    Auto-detect always translates; the service passes text that is already
    in the target language through unchanged.
    """
    if source == AUTO_DETECT:
        return True
    return get_language(source).google_code != get_language(target).google_code
