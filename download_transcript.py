#!/usr/bin/env python3
"""Command line tool to download YouTube video transcripts."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence
from urllib.parse import parse_qs, urlparse

try:
    from youtube_transcript_api import (
        YouTubeTranscriptApi,
        CouldNotRetrieveTranscript,
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
    )
except ImportError as exc:  # pragma: no cover - import error path
    print(
        "The 'youtube-transcript-api' package is required to run this script. "
        "Install it with 'pip install youtube-transcript-api'.",
        file=sys.stderr,
    )
    raise

try:
    from youtube_transcript_api import TranslationLanguageNotAvailable  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - best-effort fallback
    try:
        from youtube_transcript_api._errors import TranslationLanguageNotAvailable  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - library without translation support
        class TranslationLanguageNotAvailable(Exception):
            """Raised when translation to the requested language is not available."""

            pass


@dataclass
class TranscriptRequest:
    """Configuration describing how to download a transcript."""

    video_id: str
    languages: Sequence[str] | None
    translate_to: str | None


def extract_video_id(value: str) -> str:
    """Extract the YouTube video identifier from a URL or raw ID."""

    parsed = urlparse(value)

    if parsed.scheme and parsed.netloc:
        host = parsed.netloc.lower()
        if host in {"www.youtube.com", "youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parsed.path == "/watch":
                query = parse_qs(parsed.query)
                if "v" in query and query["v"]:
                    return query["v"][0]
            if parsed.path.startswith("/embed/"):
                return parsed.path.split("/", maxsplit=2)[2]
            if parsed.path.startswith("/shorts/"):
                return parsed.path.split("/", maxsplit=2)[2]
        if host == "youtu.be":
            stripped = parsed.path.lstrip("/")
            if stripped:
                return stripped.split("/", maxsplit=1)[0]
        raise ValueError(f"Could not extract a video id from URL: {value}")

    # Not a URL; assume the provided string already is the id.
    candidate = value.strip()
    if not candidate:
        raise ValueError("An empty string is not a valid video id")
    return candidate


def fetch_transcript(config: TranscriptRequest) -> list[dict]:
    """Fetch transcript entries according to the provided configuration."""

    video_id = config.video_id
    languages = list(config.languages or []) or None

    try:
        if config.translate_to:
            transcripts = YouTubeTranscriptApi.list_transcripts(video_id)

            preferred_languages: Iterable[str]
            if languages:
                preferred_languages = languages
            else:
                preferred_languages = []

            # Try to translate a preferred language transcript first.
            for language in preferred_languages:
                try:
                    transcript = transcripts.find_transcript([language])
                    if transcript.is_translatable:
                        return transcript.translate(config.translate_to).fetch()
                except (NoTranscriptFound, TranslationLanguageNotAvailable):
                    continue

            # Fall back to the first translatable transcript available.
            for transcript in transcripts:
                if transcript.is_translatable:
                    try:
                        return transcript.translate(config.translate_to).fetch()
                    except TranslationLanguageNotAvailable:
                        continue

            raise NoTranscriptFound("No transcript could be translated to the requested language.")

        # No translation requested - fetch a transcript directly.
        return YouTubeTranscriptApi.get_transcript(video_id, languages=languages)

    except (TranscriptsDisabled, VideoUnavailable) as error:
        raise RuntimeError(str(error)) from error
    except NoTranscriptFound as error:
        if languages:
            raise RuntimeError(
                "Could not find a transcript for the requested video "
                f"using the preferred languages: {', '.join(languages)}"
            ) from error
        raise RuntimeError("No transcript is available for this video.") from error
    except CouldNotRetrieveTranscript as error:
        raise RuntimeError("Failed to retrieve the transcript. Try again later.") from error


def format_timestamp(seconds: float) -> str:
    """Format a float representing seconds into hh:mm:ss.mmm."""

    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def format_transcript(entries: Sequence[dict], include_timestamps: bool) -> str:
    """Return the transcript as a formatted string."""

    lines: list[str] = []
    for entry in entries:
        text = entry.get("text", "").replace("\n", " ").strip()
        if not text:
            continue
        if include_timestamps:
            start = format_timestamp(entry.get("start", 0.0))
            end = format_timestamp(entry.get("start", 0.0) + entry.get("duration", 0.0))
            lines.append(f"[{start} - {end}] {text}")
        else:
            lines.append(text)
    return "\n".join(lines)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a YouTube transcript.")
    parser.add_argument("video", help="YouTube video URL or ID")
    parser.add_argument(
        "-l",
        "--language",
        dest="languages",
        action="append",
        help=(
            "Preferred language codes (e.g. en, es). "
            "You can pass the flag multiple times to provide a priority list."
        ),
    )
    parser.add_argument(
        "-t",
        "--translate",
        dest="translate_to",
        help="Translate the transcript to the given language code if possible.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="File to write the transcript to. Defaults to stdout.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output the raw transcript JSON instead of formatted text.",
    )
    parser.add_argument(
        "--timestamps",
        action="store_true",
        help="Include timestamps when writing formatted text output.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    try:
        video_id = extract_video_id(args.video)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    config = TranscriptRequest(
        video_id=video_id,
        languages=args.languages,
        translate_to=args.translate_to,
    )

    try:
        entries = fetch_transcript(config)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        output = json.dumps(entries, ensure_ascii=False, indent=2)
    else:
        output = format_transcript(entries, include_timestamps=args.timestamps)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
