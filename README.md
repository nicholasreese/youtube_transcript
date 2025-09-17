A small command line helper for downloading the transcript of a YouTube video.

## Prerequisites

Install the dependency:

```bash
pip install youtube-transcript-api
```

## Usage

```bash
python download_transcript.py <video-url-or-id> [options]
```

Common options:

- `-l/--language <code>` – Preferred transcript language(s). You can provide the flag multiple times to set a priority list.
- `-t/--translate <code>` – Translate a transcript to the given language when possible.
- `-o/--output <path>` – Save the transcript to a file instead of printing it.
- `--json` – Output the raw transcript JSON data.
- `--timestamps` – Include timestamps in the text output.

Example:

```bash
python download_transcript.py https://www.youtube.com/watch?v=dQw4w9WgXcQ -l en --timestamps -o transcript.txt
```

The script prints helpful error messages if a transcript cannot be retrieved.