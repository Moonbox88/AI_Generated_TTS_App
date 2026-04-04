#!/usr/bin/env python3
"""Text-to-Speech CLI — Phase 1."""

import argparse
import sys

from parsers import extract_text
from translator import translate
from tts import DEFAULT_LANG, DEFAULT_VOICE, speak

VOICES = [
    # American English
    "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica",
    "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
    "am_michael", "am_onyx", "am_puck", "am_santa",
    # British English
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    # Japanese
    "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
    # Mandarin Chinese
    "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
    "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
    # Spanish
    "ef_dora", "em_alex", "em_santa",
    # French
    "ff_siwis",
    # Hindi
    "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
    # Italian
    "if_sara", "im_nicola",
    # Brazilian Portuguese
    "pf_dora", "pm_alex", "pm_santa",
]

LANGUAGES = {
    "a": "American English",
    "b": "British English",
    "j": "Japanese",
    "z": "Mandarin Chinese",
    "e": "Spanish",
    "f": "French",
    "h": "Hindi",
    "i": "Italian",
    "p": "Brazilian Portuguese",
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tts",
        description="Convert text or documents to speech using Kokoro-82M.",
    )

    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("-f", "--file", metavar="PATH",
                        help="Path to a .txt, .pdf, or .docx file")
    source.add_argument("-t", "--text", metavar="TEXT",
                        help="Text string to speak")
    source.add_argument("--stdin", action="store_true",
                        help="Read text from stdin")

    p.add_argument("-v", "--voice", default=DEFAULT_VOICE,
                   choices=VOICES, metavar="VOICE",
                   help=f"Voice ID (default: {DEFAULT_VOICE}). Choices: {', '.join(VOICES)}")
    p.add_argument("-l", "--lang", default=DEFAULT_LANG,
                   choices=list(LANGUAGES), metavar="LANG",
                   help="Language code. Choices: " +
                        ", ".join(f"{k}={v}" for k, v in LANGUAGES.items()) +
                        f" (default: {DEFAULT_LANG})")
    p.add_argument("-o", "--output", metavar="FILE",
                   help="Save audio to this .wav file (optional)")
    p.add_argument("-s", "--speed", type=float, default=1.0, metavar="SPEED",
                   help="Playback speed multiplier, e.g. 0.5 to 2.0 (default: 1.0)")
    p.add_argument("--volume", type=float, default=1.0, metavar="VOLUME",
                   help="Volume level 0.0 to 1.0 (default: 1.0)")
    p.add_argument("--translate", action="store_true",
                   help="Translate input text from English to the target language before speaking")
    p.add_argument("--list-voices", action="store_true",
                   help="List available voices and exit")
    p.add_argument("--list-langs", action="store_true",
                   help="List available language codes and exit")

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.list_voices:
        print("Available voices:")
        for v in VOICES:
            print(f"  {v}")
        sys.exit(0)

    if args.list_langs:
        print("Available language codes:")
        for code, name in LANGUAGES.items():
            print(f"  {code}  {name}")
        sys.exit(0)

    # Gather text
    if args.file:
        try:
            text = extract_text(args.file)
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.text:
        text = args.text
    else:  # stdin
        print("Reading from stdin (Ctrl+D to finish):")
        text = sys.stdin.read()

    if not text.strip():
        print("Error: no text to speak.", file=sys.stderr)
        sys.exit(1)

    if args.translate:
        print(f"Translating to {LANGUAGES[args.lang]}...")
        text = translate(text, args.lang)
        print(f"Translated: {text}")
        if args.output:
            txt_path = args.output.rsplit(".", 1)[0] + ".txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"Translated text saved to {txt_path}")

    ctrl = speak(text, voice=args.voice, lang=args.lang, speed=args.speed,
                 volume=args.volume, output_file=args.output)
    ctrl.wait()


if __name__ == "__main__":
    main()
