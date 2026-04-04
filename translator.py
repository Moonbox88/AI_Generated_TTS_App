"""Translation wrapper using deep-translator (Google Translate backend)."""

# Mapping from Kokoro language codes to deep-translator language codes
LANG_MAP = {
    "a": "en",       # American English
    "b": "en",       # British English
    "j": "ja",       # Japanese
    "z": "zh-CN",    # Mandarin Chinese
    "e": "es",       # Spanish
    "f": "fr",       # French
    "h": "hi",       # Hindi
    "i": "it",       # Italian
    "p": "pt",       # Brazilian Portuguese
}

ENGLISH_CODES = {"a", "b"}


def needs_translation(lang_code: str) -> bool:
    return lang_code not in ENGLISH_CODES


def translate(text: str, lang_code: str) -> str:
    """Translate text from English to the target Kokoro language.

    Returns the original text unchanged if the target is English.
    """
    if not needs_translation(lang_code):
        return text

    target = LANG_MAP.get(lang_code)
    if not target:
        raise ValueError(f"No translation mapping for language code '{lang_code}'")

    from deep_translator import GoogleTranslator
    return GoogleTranslator(source="en", target=target).translate(text)
