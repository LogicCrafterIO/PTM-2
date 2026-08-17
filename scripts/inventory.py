"""Scan both course video trees and write transcripts/index.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    INSTUTRADE_DIR,
    ROOT,
    TRANSCRIPTS_DIR,
    clean_title,
    format_hms,
    lesson_dir,
    lesson_sort_key,
    module_for,
    parse_instutrade_filename,
    parse_ptm2_filename,
    probe_duration_seconds,
    related_documents,
    slugify,
    write_json,
)


def collect_ptm2() -> list[dict]:
    lessons = []
    for path in sorted(ROOT.glob("*.mp4")):
        lesson_id, title = parse_ptm2_filename(path.name)
        title = clean_title(title)
        duration = probe_duration_seconds(path)
        module_slug, module_title = module_for("ptm2", lesson_id)
        out_dir = lesson_dir("ptm2", lesson_id, title)
        lessons.append(
            {
                "course": "ptm2",
                "lesson_id": lesson_id,
                "title": title,
                "slug": slugify(title),
                "module": module_slug,
                "module_title": module_title,
                "source": str(path.relative_to(ROOT)).replace("\\", "/"),
                "duration_seconds": round(duration, 3),
                "duration": format_hms(duration),
                "bytes": path.stat().st_size,
                "related_documents": related_documents(lesson_id),
                "output_dir": str(out_dir.relative_to(ROOT)).replace("\\", "/"),
            }
        )
    lessons.sort(key=lambda item: lesson_sort_key(item["lesson_id"]))
    return lessons


def collect_instutrade() -> list[dict]:
    lessons = []
    for path in sorted(INSTUTRADE_DIR.rglob("*.mp4")):
        lesson_id, title = parse_instutrade_filename(path.name)
        title = clean_title(title)
        duration = probe_duration_seconds(path)
        module_slug, module_title = module_for("instutrade", lesson_id)
        out_dir = lesson_dir("instutrade", lesson_id, title)
        lessons.append(
            {
                "course": "instutrade",
                "lesson_id": lesson_id,
                "title": title,
                "slug": slugify(title),
                "module": module_slug,
                "module_title": module_title,
                "source": str(path.relative_to(ROOT)).replace("\\", "/"),
                "duration_seconds": round(duration, 3),
                "duration": format_hms(duration),
                "bytes": path.stat().st_size,
                "related_documents": [],
                "output_dir": str(out_dir.relative_to(ROOT)).replace("\\", "/"),
            }
        )
    lessons.sort(key=lambda item: lesson_sort_key(item["lesson_id"]))
    return lessons


def build_index() -> dict:
    ptm2 = collect_ptm2()
    instutrade = collect_instutrade()
    lessons = ptm2 + instutrade
    return {
        "courses": {
            "ptm2": {
                "title": "Professional Trading Masterclass 2",
                "lesson_count": len(ptm2),
                "duration_seconds": round(sum(item["duration_seconds"] for item in ptm2), 3),
                "duration": format_hms(sum(item["duration_seconds"] for item in ptm2)),
            },
            "instutrade": {
                "title": "Anton Kreil Professional Trading Masterclass Instutrade",
                "lesson_count": len(instutrade),
                "duration_seconds": round(sum(item["duration_seconds"] for item in instutrade), 3),
                "duration": format_hms(sum(item["duration_seconds"] for item in instutrade)),
            },
        },
        "lesson_count": len(lessons),
        "duration_seconds": round(sum(item["duration_seconds"] for item in lessons), 3),
        "duration": format_hms(sum(item["duration_seconds"] for item in lessons)),
        "lessons": lessons,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build transcripts/index.json from course videos.")
    parser.add_argument("--out", type=Path, default=TRANSCRIPTS_DIR / "index.json")
    args = parser.parse_args()
    index = build_index()
    write_json(args.out, index)
    print(f"Wrote {args.out} with {index['lesson_count']} lessons ({index['duration']})")
    for course, meta in index["courses"].items():
        print(f"  {course}: {meta['lesson_count']} lessons, {meta['duration']}")


if __name__ == "__main__":
    main()
