# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "youtube-transcript-api",
# ]
# ///
"""CLI tool to download YouTube video transcripts using youtube-transcript-api."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

_VIDEO_ID_LENGTH = 11


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a YouTube transcript and write it to stdout or a file.",
    )
    parser.add_argument(
        "video",
        help="YouTube video URL or 11-character video id",
    )
    parser.add_argument(
        "--languages",
        nargs="*",
        default=None,
        metavar="CODE",
        help="Preferred language codes in priority order (e.g. en, es).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the transcript to (defaults to stdout).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the full transcript JSON instead of plain text.",
    )
    parser.add_argument(
        "--timestamps",
        action="store_true",
        help="Include start timestamp (seconds) before each line in plain text output.",
    )
    return parser.parse_args(argv)


def extract_video_id(value: str) -> str:
    """Return the YouTube video id from a URL or raw id."""
    candidate = value.strip()
    if _looks_like_video_id(candidate):
        return candidate

    parsed = urlparse(candidate)
    if not parsed.scheme:
        raise ValueError(f"Cannot parse YouTube video id from: {value}")

    if parsed.hostname in {"youtu.be"}:
        video_id = parsed.path.lstrip("/")
        if _looks_like_video_id(video_id):
            return video_id

    if parsed.hostname and parsed.hostname.endswith("youtube.com"):
        query = parse_qs(parsed.query)
        video_id = query.get("v", [""])[0]
        if _looks_like_video_id(video_id):
            return video_id

    raise ValueError(f"Cannot parse YouTube video id from: {value}")


def _looks_like_video_id(value: str) -> bool:
    return len(value) == _VIDEO_ID_LENGTH and all(
        ch.isalnum() or ch in {"-", "_"} for ch in value
    )


def fetch_transcript(video_id: str, languages: Optional[Iterable[str]] = None) -> list[dict]:
    api = YouTubeTranscriptApi()
    requested_languages = tuple(languages) if languages else ("en",)
    try:
        fetched = api.fetch(video_id, languages=requested_languages)
    except TranscriptsDisabled as exc:  # pragma: no cover - depends on external API
        raise RuntimeError("Transcripts are disabled for this video.") from exc
    except NoTranscriptFound as exc:  # pragma: no cover - depends on external API
        raise RuntimeError("No transcript found for the requested languages.") from exc
    except VideoUnavailable as exc:  # pragma: no cover - depends on external API
        raise RuntimeError("The requested video is unavailable.") from exc

    return fetched.to_raw_data()


def transcript_to_text(transcript: list[dict], include_timestamps: bool) -> str:
    lines: list[str] = []
    for entry in transcript:
        text = entry.get("text", "").strip()
        if not text:
            continue
        if include_timestamps:
            start = entry.get("start", 0.0)
            lines.append(f"{start:.3f}\t{text}")
        else:
            lines.append(text)
    return "\n".join(lines)


def write_output(content: str, destination: Optional[Path]) -> None:
    if destination is None:
        print(content)
        return

    destination.write_text(content, encoding="utf-8")


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    try:
        video_id = extract_video_id(args.video)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        transcript = fetch_transcript(video_id, languages=args.languages)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        payload = json.dumps(transcript, indent=2, ensure_ascii=False)
    else:
        payload = transcript_to_text(transcript, include_timestamps=args.timestamps)

    try:
        write_output(payload, args.output)
    except OSError as exc:
        print(f"Failed to write transcript: {exc}", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
