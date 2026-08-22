"""Resume-safe whisper.cpp transcription into Markdown, SRT, VTT, and JSON."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    ROOT,
    TRADING_PROMPT,
    TRANSCRIPTS_DIR,
    audio_path,
    default_model_path,
    find_whisper_cli,
    format_hms,
    read_json,
    write_json,
)
from extract_audio import extract_one


def load_lessons(index_path: Path, course: str | None, lesson_ids: set[str] | None) -> list[dict]:
    index = read_json(index_path)
    lessons = index["lessons"]
    if course:
        lessons = [item for item in lessons if item["course"] == course]
    if lesson_ids:
        lessons = [item for item in lessons if item["lesson_id"] in lesson_ids]
    return lessons


def done_path(out_dir: Path) -> Path:
    return out_dir / ".done"


def is_complete(out_dir: Path) -> bool:
    required = [
        done_path(out_dir),
        out_dir / "transcript.md",
        out_dir / "transcript.txt",
        out_dir / "transcript.srt",
        out_dir / "transcript.vtt",
        out_dir / "segments.json",
        out_dir / "source.json",
    ]
    return all(path.is_file() and path.stat().st_size > 0 for path in required)


def srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def vtt_timestamp(seconds: float) -> str:
    return srt_timestamp(seconds).replace(",", ".")


def wrap_text(text: str, width: int = 42) -> str:
    words = text.split()
    if not words:
        return text
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = " ".join(current + [word])
        if current and len(trial) > width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def segments_to_srt(segments: list[dict]) -> str:
    blocks = []
    for i, seg in enumerate(segments, start=1):
        text = wrap_text(seg["text"].strip())
        if not text:
            continue
        blocks.append(
            f"{i}\n{srt_timestamp(seg['start'])} --> {srt_timestamp(seg['end'])}\n{text}\n"
        )
    return "\n".join(blocks).rstrip() + "\n"


def segments_to_vtt(segments: list[dict]) -> str:
    blocks = ["WEBVTT\n"]
    for seg in segments:
        text = wrap_text(seg["text"].strip())
        if not text:
            continue
        blocks.append(f"{vtt_timestamp(seg['start'])} --> {vtt_timestamp(seg['end'])}\n{text}\n")
    return "\n".join(blocks).rstrip() + "\n"


def clean_paragraphs(segments: list[dict]) -> str:
    chunks: list[str] = []
    current: list[str] = []
    last_end = 0.0
    for seg in segments:
        text = " ".join(seg["text"].strip().split())
        if not text:
            continue
        gap = seg["start"] - last_end
        if current and (gap >= 2.5 or (text[:1].isupper() and current[-1].endswith((".", "?", "!")))):
            chunks.append(" ".join(current))
            current = [text]
        else:
            current.append(text)
        last_end = seg["end"]
    if current:
        chunks.append(" ".join(current))
    return "\n\n".join(chunks).strip() + "\n"


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def write_markdown(lesson: dict, out_dir: Path, body: str, model_name: str) -> None:
    docs = lesson.get("related_documents") or []
    docs_yaml = "\n".join(f"  - {yaml_quote(item)}" for item in docs) if docs else "  []"
    frontmatter = "\n".join(
        [
            "---",
            f"course: {lesson['course']}",
            f"lesson_id: {yaml_quote(lesson['lesson_id'])}",
            f"title: {yaml_quote(lesson['title'])}",
            f"module: {lesson['module']}",
            f"module_title: {yaml_quote(lesson['module_title'])}",
            f"duration: {lesson['duration']}",
            f"duration_seconds: {lesson['duration_seconds']}",
            f"source: {yaml_quote(lesson['source'])}",
            f"model: {yaml_quote(model_name)}",
            "related_documents:",
            docs_yaml,
            "---",
            "",
            f"# {lesson['lesson_id']} — {lesson['title']}",
            "",
            body.strip(),
            "",
        ]
    )
    (out_dir / "transcript.md").write_text(frontmatter, encoding="utf-8")


def parse_whisper_json(raw: dict) -> list[dict]:
    transcription = raw.get("transcription") or raw.get("segments") or []
    segments = []
    for item in transcription:
        offsets = item.get("offsets") or {}
        start_ms = offsets.get("from", item.get("start", 0))
        end_ms = offsets.get("to", item.get("end", 0))
        if isinstance(start_ms, (int, float)) and start_ms > 1000 and "start" not in item:
            start = start_ms / 1000.0
            end = end_ms / 1000.0
        elif "offsets" in item:
            start = float(start_ms) / 1000.0
            end = float(end_ms) / 1000.0
        else:
            start = float(item.get("start", 0))
            end = float(item.get("end", 0))
        text = item.get("text") or item.get("timestamps", {}).get("text") or ""
        text = str(text).strip()
        if text:
            segments.append({"start": start, "end": end, "text": text})
    return segments


def run_whisper(cli: Path, model: Path, wav: Path, work_dir: Path) -> dict:
    prefix = work_dir / "out"
    cmd = [
        str(cli),
        "-m",
        str(model),
        "-f",
        str(wav),
        "-l",
        "en",
        "--prompt",
        TRADING_PROMPT,
        "-otxt",
        "-osrt",
        "-ovtt",
        "-oj",
        "-of",
        str(prefix),
        "-pp",
        "-sns",
        "-t",
        "8",
        "-mc",
        "224",
    ]
    print("  " + " ".join(cmd[:8]) + " ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise RuntimeError(f"whisper-cli failed with exit {result.returncode}")
    json_path = Path(str(prefix) + ".json")
    if not json_path.is_file():
        raise RuntimeError(f"whisper-cli did not write {json_path}")
    return json.loads(json_path.read_text(encoding="utf-8"))


def transcribe_lesson(
    lesson: dict,
    cli: Path,
    model: Path,
    force: bool = False,
    keep_wav: bool = False,
) -> None:
    out_dir = ROOT / lesson["output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    if not force and is_complete(out_dir):
        print(f"SKIP  {lesson['course']} {lesson['lesson_id']}  already done")
        return

    wav = extract_one(lesson)
    print(f"TRANSCRIBE  {lesson['course']} {lesson['lesson_id']}  {lesson['duration']}  {lesson['title']}")
    with tempfile.TemporaryDirectory(prefix="whisper-") as tmp:
        raw = run_whisper(cli, model, wav, Path(tmp))

    segments = parse_whisper_json(raw)
    if not segments:
        raise RuntimeError(f"No segments produced for {lesson['lesson_id']}")

    body = clean_paragraphs(segments)
    write_json(out_dir / "source.json", lesson)
    write_json(out_dir / "segments.json", {"segments": segments, "model": model.name})
    (out_dir / "transcript.txt").write_text(body, encoding="utf-8")
    (out_dir / "transcript.srt").write_text(segments_to_srt(segments), encoding="utf-8")
    (out_dir / "transcript.vtt").write_text(segments_to_vtt(segments), encoding="utf-8")
    write_markdown(lesson, out_dir, body, model.name)
    done_path(out_dir).write_text(f"{lesson['course']} {lesson['lesson_id']}\n", encoding="utf-8")

    if not keep_wav:
        wav_file = audio_path(lesson["course"], lesson["lesson_id"])
        if wav_file.is_file():
            wav_file.unlink()
            print(f"  deleted {wav_file.name}")
    print(f"  wrote {out_dir.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe course lessons with whisper.cpp.")
    parser.add_argument("--index", type=Path, default=TRANSCRIPTS_DIR / "index.json")
    parser.add_argument("--course", choices=["ptm2", "instutrade"])
    parser.add_argument("--lesson", action="append", dest="lessons")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--whisper-cli", type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-wav", action="store_true")
    args = parser.parse_args()

    if not args.index.is_file():
        raise SystemExit("index.json missing. Run scripts/inventory.py first.")

    cli = args.whisper_cli or find_whisper_cli()
    if not cli or not Path(cli).is_file():
        raise SystemExit("whisper-cli not found. Build whisper.cpp with Vulkan first.")
    model = args.model or default_model_path()
    if not Path(model).is_file():
        raise SystemExit(f"Model not found: {model}")

    lessons = load_lessons(args.index, args.course, set(args.lessons) if args.lessons else None)
    print(f"Queue: {len(lessons)} lessons, model={Path(model).name}, cli={cli}")
    failures: list[str] = []
    for lesson in lessons:
        label = f"{lesson['course']} {lesson['lesson_id']}"
        try:
            transcribe_lesson(lesson, Path(cli), Path(model), force=args.force, keep_wav=args.keep_wav)
        except Exception as exc:
            failures.append(label)
            print(f"FAIL  {label}  {type(exc).__name__}: {exc}")
    remaining = [item for item in lessons if not is_complete(ROOT / item["output_dir"])]
    print(f"Finished. {len(lessons) - len(remaining)} complete, {len(remaining)} remaining")
    if failures:
        print("Failures: " + ", ".join(failures))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
