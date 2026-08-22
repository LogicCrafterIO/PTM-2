"""Build module packs, glossary, and agent brief from completed transcripts."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT, TRANSCRIPTS_DIR, format_hms, module_catalog, read_json, write_json

GLOSSARY = """# PTM glossary

Domain terms that appear throughout the course. Use these spellings in specs and summaries.

## Macro and leading indicators

- **GDP** — Gross Domestic Product
- **ISM Manufacturing / ISM Non-Manufacturing** — Institute for Supply Management PMI-style surveys
- **NFIB** — National Federation of Independent Business Small Business Optimism Index
- **UMCSI** — University of Michigan Consumer Sentiment Index
- **M2** — Broad money supply
- **CPI / PPI** — Consumer / Producer Price Index
- **COT** — Commitment of Traders
- **FOMC / Fed** — Federal Open Market Committee / Federal Reserve
- **Coincident indicators** — Employment situation, industrial production, jobless claims, durable goods
- **China PMIs / real rates** — Used when drilling international/macro ideas

## Portfolio construction

- **GICS** — Global Industry Classification Standard
- **Long/short portfolio** — Market-neutral-leaning book of longs and shorts
- **Beta** — Sensitivity of a name or book to the benchmark
- **Volatility / correlation** — Inputs to position sizing and risk
- **Earnings yield** — Earnings over price; compared with bond yields in the framework

## Trade idea generation

- **Quantitative processing** — Screening/ranking sectors and names from data
- **Qualitative processing** — Narrative, business quality, and non-numeric filters
- **Catalysts** — Dated events expected to reprice a name
- **ADRs** — American Depositary Receipts for international idea generation
- **Technical analysis / price action** — Timing overlay, not the core idea engine
- **SMA / EMA** — Simple / exponential moving averages
- **Trade idea template** — Structured write-up before risking capital

## Risk and psychology

- **PRM** — Preventative Risk Management
- **ATRP** — Average True Range Percentage stops/targets
- **DoR** — Degree of Risk stops/targets
- **PEG ratio** — Price/earnings-to-growth
- **WISH framework** — Perspective framework from the Instutrade course
- **Kelly criterion** — Position-sizing simulation in later Documents (Video 42)
"""

AGENT_BRIEF = """# Agent brief: how to use these transcripts

This corpus is for extracting a **methodology summary** and a **system spec** that could automate the process taught in the videos. It is not a dump of the course for redistribution.

## Load order

1. Read `transcripts/index.json` first. It is the catalog: lesson ids, durations, modules, source videos, and related Excel/PDF files.
2. Read this file and `transcripts/GLOSSARY.md`.
3. Work **one module at a time**. Do not load all ~79 hours of text in a single prompt.
4. For each module, open the numbered files in `transcripts/modules/<course>/` in filename order (`01-` then `02-`, and so on). The number is the implementation sequence, not alphabetical. Then drill into individual `transcript.md` files as needed.
5. When a lesson lists `related_documents`, treat those spreadsheets/PDFs as the operational artifacts the system must reproduce or ingest.

## What to extract per module

- Process steps (ordered)
- Data sources and refresh cadence
- Formulas and decision rules
- Risk limits, stops, targets, and portfolio constraints
- Required inputs/outputs for software
- Mapping from each step to a file under `Documents/`
- Open questions or instructor caveats

Cite claims as `course:lesson_id @ HH:MM:SS` using timestamps from `transcript.srt` or `segments.json` so a human can jump back to the video.

## Suggested later artifacts

1. `methodology.md` — narrative of the full process, module by module
2. `system-spec.md` — pipelines, data model, calculations, UI, and risk engine
3. Optional RAG chunks: split `transcript.md` on paragraphs, keep frontmatter ids and nearby timestamps

## Output locations

| Path | Purpose |
| --- | --- |
| `transcripts/index.json` | Machine-readable catalog |
| `transcripts/ptm2/<id>-<slug>/` | Per-lesson clean text + SRT/VTT/JSON |
| `transcripts/instutrade/<id>-<slug>/` | Older course, same layout |
| `transcripts/modules/<course>/NN-<slug>.md` | Module packs in course order (`01-` first) |
| `transcripts/modules/README.md` | Ordered map of every module |
| `transcripts/GLOSSARY.md` | Canonical spellings |

Keep audio, videos, and transcripts local. Do not upload course media to a cloud STT or public repo.
"""


def lesson_complete(lesson: dict) -> bool:
    out_dir = ROOT / lesson["output_dir"]
    return (out_dir / "transcript.md").is_file() and (out_dir / ".done").is_file()


def write_module_pack(course: str, meta: dict, lessons: list[dict], catalog: list[dict]) -> Path:
    index = meta["index"]
    prev_meta = catalog[index - 2] if index > 1 else None
    next_meta = catalog[index] if index < len(catalog) else None
    prev_line = (
        f"Previous: `{prev_meta['filename']}` — {prev_meta['title']}"
        if prev_meta
        else "Previous: none (start here)"
    )
    next_line = (
        f"Next: `{next_meta['filename']}` — {next_meta['title']}"
        if next_meta
        else "Next: none (end of this course)"
    )
    lesson_ids = ", ".join(item["lesson_id"] for item in lessons)
    lines = [
        f"# {meta['index_label']} — {meta['title']}",
        "",
        f"Course: `{course}`  ",
        f"Sequence: {index} of {len(catalog)}  ",
        f"Module: `{meta['slug']}`  ",
        f"Lessons: {lesson_ids}  ",
        f"Duration: {format_hms(sum(item['duration_seconds'] for item in lessons))}  ",
        prev_line + "  ",
        next_line,
        "",
    ]
    for lesson in lessons:
        out_dir = ROOT / lesson["output_dir"]
        md_path = out_dir / "transcript.md"
        lines.append(f"## {lesson['lesson_id']} — {lesson['title']}")
        lines.append("")
        lines.append(f"Source: `{lesson['source']}`  ")
        lines.append(f"Duration: {lesson['duration']}  ")
        if lesson.get("related_documents"):
            lines.append("Documents:")
            for doc in lesson["related_documents"]:
                lines.append(f"- `{doc}`")
        lines.append("")
        if md_path.is_file():
            text = md_path.read_text(encoding="utf-8")
            if text.startswith("---"):
                text = text.split("---", 2)[-1].strip()
            # Drop the duplicate H1 from the per-lesson file.
            body_lines = text.splitlines()
            if body_lines and body_lines[0].startswith("# "):
                text = "\n".join(body_lines[1:]).strip()
            lines.append(text)
        else:
            lines.append("_Transcript not generated yet._")
        lines.append("")
        lines.append("---")
        lines.append("")
    dest = TRANSCRIPTS_DIR / "modules" / course / meta["filename"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return dest


def write_modules_readme(written_by_course: dict[str, list[dict]]) -> Path:
    lines = [
        "# Module sequence",
        "",
        "Files are numbered in course order so later implementation follows the same sequence.",
        "",
    ]
    course_titles = {
        "ptm2": "PTM 2 (implement this course first)",
        "instutrade": "Instutrade (older supporting course)",
    }
    for course in ("ptm2", "instutrade"):
        catalog = written_by_course.get(course) or []
        lines.append(f"## {course_titles.get(course, course)}")
        lines.append("")
        for meta in catalog:
            lesson_span = f"{meta['lesson_start']:02d}–{meta['lesson_end']:02d}"
            lines.append(
                f"{meta['index_label']}. [`{meta['filename']}`]({course}/{meta['filename']}) — "
                f"{meta['title']} (lessons {lesson_span})"
            )
        lines.append("")
    dest = TRANSCRIPTS_DIR / "modules" / "README.md"
    dest.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="Package transcripts for later agent work.")
    parser.add_argument("--index", type=Path, default=TRANSCRIPTS_DIR / "index.json")
    args = parser.parse_args()
    if not args.index.is_file():
        raise SystemExit("index.json missing. Run scripts/inventory.py first.")

    index = read_json(args.index)
    (TRANSCRIPTS_DIR / "GLOSSARY.md").write_text(GLOSSARY, encoding="utf-8")
    (TRANSCRIPTS_DIR / "AGENT_BRIEF.md").write_text(AGENT_BRIEF, encoding="utf-8")

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for lesson in index["lessons"]:
        grouped[(lesson["course"], lesson["module"])].append(lesson)

    written = []
    written_meta: dict[str, list[dict]] = {}
    for course in ("ptm2", "instutrade"):
        catalog = module_catalog(course)
        written_meta[course] = catalog
        course_dir = TRANSCRIPTS_DIR / "modules" / course
        if course_dir.is_dir():
            for old in course_dir.glob("*.md"):
                old.unlink()
        for meta in catalog:
            lessons = grouped.get((course, meta["slug"]), [])
            written.append(write_module_pack(course, meta, lessons, catalog))
    write_modules_readme(written_meta)

    complete = [item for item in index["lessons"] if lesson_complete(item)]
    status = {
        "lesson_count": len(index["lessons"]),
        "complete_count": len(complete),
        "complete_lesson_ids": [f"{item['course']}:{item['lesson_id']}" for item in complete],
        "module_packs": [str(path.relative_to(ROOT)).replace("\\", "/") for path in written],
    }
    write_json(TRANSCRIPTS_DIR / "status.json", status)
    print(f"Packaged {len(written)} module files. {len(complete)}/{len(index['lessons'])} lessons complete.")


if __name__ == "__main__":
    main()
