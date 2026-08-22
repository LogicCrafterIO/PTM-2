"""Extract 16 kHz mono WAV files from course videos."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    AUDIO_DIR,
    FFMPEG,
    TRANSCRIPTS_DIR,
    audio_path,
    format_hms,
    probe_duration_seconds,
    read_json,
)

DURATION_TOLERANCE_SEC = 1.5


def load_lessons(index_path: Path, course: str | None, lesson_ids: set[str] | None) -> list[dict]:
    index = read_json(index_path)
    lessons = index["lessons"]
    if course:
        lessons = [item for item in lessons if item["course"] == course]
    if lesson_ids:
        lessons = [item for item in lessons if item["lesson_id"] in lesson_ids]
    return lessons


def wav_is_current(wav: Path, expected_seconds: float) -> bool:
    if not wav.is_file() or wav.stat().st_size < 1000:
        return False
    try:
        actual = probe_duration_seconds(wav)
    except Exception:
        return False
    return abs(actual - expected_seconds) <= DURATION_TOLERANCE_SEC


def extract_one(lesson: dict, force: bool = False) -> Path:
    source = Path(__file__).resolve().parent.parent / lesson["source"]
    wav = audio_path(lesson["course"], lesson["lesson_id"])
    wav.parent.mkdir(parents=True, exist_ok=True)
    if not force and wav_is_current(wav, lesson["duration_seconds"]):
        print(f"SKIP  {lesson['course']} {lesson['lesson_id']}  {wav.name}")
        return wav

    import subprocess

    cmd = [
        FFMPEG,
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-hide_banner",
        "-loglevel",
        "error",
        str(wav),
    ]
    print(f"EXTRACT  {lesson['course']} {lesson['lesson_id']}  {lesson['duration']}  -> {wav.name}")
    subprocess.run(cmd, check=True)
    return wav


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract 16 kHz mono WAVs for transcription.")
    parser.add_argument("--index", type=Path, default=TRANSCRIPTS_DIR / "index.json")
    parser.add_argument("--course", choices=["ptm2", "instutrade"])
    parser.add_argument("--lesson", action="append", dest="lessons", help="Lesson id, repeatable")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.index.is_file():
        raise SystemExit("index.json missing. Run scripts/inventory.py first.")

    lessons = load_lessons(args.index, args.course, set(args.lessons) if args.lessons else None)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    for lesson in lessons:
        extract_one(lesson, force=args.force)
    print(f"Audio ready for {len(lessons)} lessons ({format_hms(sum(item['duration_seconds'] for item in lessons))})")


if __name__ == "__main__":
    main()
