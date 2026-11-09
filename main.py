#!/usr/bin/env python3
"""Text-to-Speech CLI."""

import argparse
import os
import pathlib
import sys

import tts
from parsers import extract_text
from translator import iter_translate
from tts import speak
from voices import (DEFAULT_LANG, DEFAULT_VOICE, LANGUAGES, VOICE_IDS,
                    default_voice_for_lang, get_voice, needs_translation,
                    voices_for_lang)


SPEED_RANGE = (0.5, 2.0)   # matches the GUI slider
VOLUME_RANGE = (0.0, 1.0)


def _bounded_float(name: str, low: float, high: float):
    """argparse type: a finite float within [low, high]."""
    def parse(value: str) -> float:
        try:
            number = float(value)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{name} must be a number, got '{value}'")
        # `not low <= number <= high` also rejects nan, which fails every comparison.
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(
                f"{name} must be between {low} and {high}, got {value}")
        return number
    return parse


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tts",
        description="Convert text or documents to speech using Kokoro-82M and Piper.",
    )

    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("-f", "--file", metavar="PATH",
                        help="Path to a .txt, .pdf, or .docx file")
    source.add_argument("-t", "--text", metavar="TEXT",
                        help="Text string to speak")
    source.add_argument("--stdin", action="store_true",
                        help="Read text from stdin")

    p.add_argument("-v", "--voice", default=None,
                   choices=VOICE_IDS, metavar="VOICE",
                   help="Voice ID (default: the first voice for the chosen language). "
                        "See --list-voices")
    p.add_argument("-l", "--lang", default=DEFAULT_LANG,
                   choices=list(LANGUAGES), metavar="LANG",
                   help="Language code. Choices: " +
                        ", ".join(f"{k}={v.name}" for k, v in LANGUAGES.items()) +
                        f" (default: {DEFAULT_LANG})")
    p.add_argument("-o", "--output", metavar="FILE",
                   help="Save audio to this .wav file (optional)")
    p.add_argument("-s", "--speed", type=_bounded_float("speed", *SPEED_RANGE),
                   default=1.0, metavar="SPEED",
                   help="Speech speed multiplier, %s to %s (default: 1.0)" % SPEED_RANGE)
    p.add_argument("--volume", type=_bounded_float("volume", *VOLUME_RANGE),
                   default=1.0, metavar="VOLUME",
                   help="Volume level %s to %s (default: 1.0)" % VOLUME_RANGE)
    p.add_argument("--translate", action="store_true",
                   help="Translate input text from English to the target language first")
    p.add_argument("--no-play", action="store_true",
                   help="Synthesise to --output without playing audio")
    p.add_argument("--list-voices", action="store_true",
                   help="List available voices and exit")
    p.add_argument("--list-langs", action="store_true",
                   help="List available language codes and exit")

    return p


def _list_voices() -> None:
    print("Available voices:")
    for code, lang in LANGUAGES.items():
        matches = voices_for_lang(code)
        if not matches:
            continue
        print(f"\n  {lang.name} (-l {code})")
        for voice in matches:
            print(f"    {voice.id:<24} {voice.label}  [{voice.engine}]")


def _resolve_voice(args, parser) -> str:
    """Pick the voice, defaulting per language and rejecting mismatches."""
    if args.voice is None:
        voice = default_voice_for_lang(args.lang)
        if voice is None:
            parser.error(f"No voices available for language '{args.lang}'")
        return voice

    selected = get_voice(args.voice)
    if selected.lang != args.lang:
        # An explicit voice wins, but say so rather than silently disagreeing.
        if args.lang != DEFAULT_LANG:
            print(f"Note: voice '{args.voice}' is {LANGUAGES[selected.lang].name}; "
                  f"using that instead of {LANGUAGES[args.lang].name}.", file=sys.stderr)
        args.lang = selected.lang
    return selected.id


def main():
    parser = build_parser()

    if "--list-voices" in sys.argv:
        _list_voices()
        sys.exit(0)
    if "--list-langs" in sys.argv:
        print("Available language codes:")
        for code, lang in LANGUAGES.items():
            print(f"  {code:<3} {lang.name}")
        sys.exit(0)

    args = parser.parse_args()
    voice = _resolve_voice(args, parser)

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
        if sys.stdin.isatty():
            print("Reading from stdin (Ctrl+D to finish):")
        text = sys.stdin.read()

    if not text.strip():
        print("Error: no text to speak.", file=sys.stderr)
        sys.exit(1)

    # Validate before any network or synthesis work is done.
    if args.no_play and not args.output:
        print("Error: --no-play requires --output.", file=sys.stderr)
        sys.exit(1)

    segments = [text]
    translated: list[str] = []
    if args.translate:
        if not needs_translation(args.lang):
            print(f"Target is {LANGUAGES[args.lang].name}; nothing to translate.")
        else:
            print(f"Translating to {LANGUAGES[args.lang].name}...")

            def translated_segments():
                # Each piece is spoken as soon as it arrives.
                for piece in iter_translate(text, args.lang):
                    translated.append(piece)
                    print(f"Translated: {piece}")
                    yield piece

            segments = translated_segments()

    playback = speak(segments, voice=voice, speed=args.speed, volume=args.volume,
                     output_file=args.output, play=not args.no_play,
                     on_status=print)
    try:
        playback.wait()
    except KeyboardInterrupt:
        # Let synthesis leave torch before exiting; exiting mid-call aborts
        # the process. If it's stuck (e.g. downloading), skip teardown.
        if not tts.shutdown(timeout=5):
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(130)
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        print(f"Saved to {args.output}")
    if translated and args.output:
        txt_path = pathlib.Path(args.output).with_suffix(".txt")
        txt_path.write_text("\n\n".join(translated), encoding="utf-8")
        print(f"Translated text saved to {txt_path}")


if __name__ == "__main__":
    main()
