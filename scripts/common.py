"""Shared paths, lesson metadata, and helpers for the PTM transcription pipeline."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
TRANSCRIPTS_DIR = ROOT / "transcripts"
AUDIO_DIR = TRANSCRIPTS_DIR / "_audio"
MODELS_DIR = ROOT / "models"
TOOLS_DIR = ROOT / "tools"
INSTUTRADE_DIR = ROOT / "Anton Kreil - Professional Trading Masterclass Instutrade"
DOCUMENTS_DIR = ROOT / "Documents"

FFPROBE = shutil.which("ffprobe") or r"C:\Users\John\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffprobe.exe"
FFMPEG = shutil.which("ffmpeg") or r"C:\Users\John\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"

TRADING_PROMPT = (
    "Professional trading masterclass lecture. Vocabulary: GDP, ISM Manufacturing Index, "
    "ISM Non-Manufacturing Index, NFIB Small Business Optimism, UMCSI, leading indicators, "
    "coincident indicators, S&P 500, Federal Reserve, FOMC, M2 money supply, Commitment of Traders, "
    "PPI, CPI, GICS sectors, long short portfolio, beta, volatility, correlation, quantitative "
    "processing, qualitative processing, catalysts, ADRs, technical analysis, price action, "
    "SMA, EMA, ATRP, DoR, preventative risk management, PEG ratio, WISH framework, "
    "earnings yield, bond yields, industrial production, jobless claims, durable goods."
)

PTM2_MODULES = (
    (1, 3, "framework-and-market-structure", "Framework and market structure"),
    (4, 15, "leading-indicators", "Leading indicators"),
    (16, 21, "long-short-portfolio", "Long/short portfolio construction"),
    (22, 29, "quantitative-idea-generation", "Quantitative idea generation"),
    (30, 32, "qualitative-and-catalysts", "Qualitative processing and catalysts"),
    (33, 37, "trade-idea-methods", "Trade-idea template, macro, ADRs, TA, price action"),
    (38, 40, "psychology-and-prm", "Psychology and preventative risk management"),
)

INSTUTRADE_MODULES = (
    (1, 2, "professional-vs-retail", "Professional vs retail traders"),
    (3, 4, "distribution-and-odds", "Distribution and odds calculation"),
    (5, 7, "volatility-assessment", "Volatility assessment"),
    (8, 9, "wish-framework", "WISH framework"),
    (10, 17, "correlating-indicators", "Correlating indicators"),
    (18, 19, "drilling-top-down", "Drilling from the top down"),
    (20, 21, "gatekeeping", "Gatekeeping and deploying capital"),
    (22, 25, "discipline-and-risk", "Discipline and risk management"),
    (26, 26, "day-trading-approach", "Day trading approach"),
    (27, 27, "trading-plan", "Trading plan"),
    (28, 28, "examination-prep", "Examination preparation"),
)


def clean_title(text: str) -> str:
    text = text.replace("ΓÇô", "-").replace("ΓÇö", "-")
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")
    text = text.replace("'", "'").replace("'", "'")
    text = text.replace("'", "'").replace("`", "'")
    return re.sub(r"\s+", " ", text).strip(" _-")


def slugify(text: str) -> str:
    text = clean_title(text).lower()
    text = text.replace("&", " and ")
    text = text.replace("'", "")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:60]


def lesson_sort_key(lesson_id: str) -> tuple:
    match = re.match(r"^(\d+)([a-z]?)$", lesson_id)
    if not match:
        nums = re.findall(r"\d+", lesson_id)
        return (int(nums[0]) if nums else 999, lesson_id)
    return (int(match.group(1)), match.group(2) or "")


def primary_lesson_number(lesson_id: str) -> int:
    match = re.match(r"^(\d+)", lesson_id)
    return int(match.group(1)) if match else 0


def module_table(course: str) -> tuple[tuple[int, int, str, str], ...]:
    return PTM2_MODULES if course == "ptm2" else INSTUTRADE_MODULES


def module_catalog(course: str) -> list[dict]:
    rows = []
    table = module_table(course)
    for index, (start, end, slug, title) in enumerate(table, start=1):
        rows.append(
            {
                "index": index,
                "index_label": f"{index:02d}",
                "slug": slug,
                "title": title,
                "lesson_start": start,
                "lesson_end": end,
                "filename": f"{index:02d}-{slug}.md",
            }
        )
    return rows


def module_for(course: str, lesson_id: str) -> tuple[str, str]:
    number = primary_lesson_number(lesson_id)
    for start, end, slug, title in module_table(course):
        if start <= number <= end:
            return slug, title
    return "other", "Other"


def probe_duration_seconds(path: Path) -> float:
    result = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def format_hms(seconds: float) -> str:
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_ptm2_filename(name: str) -> tuple[str, str]:
    stem = Path(name).stem
    part = ""
    part_match = re.search(r"\bpart\s*([12])\b", stem, re.I)
    if part_match:
        part = "ab"[int(part_match.group(1)) - 1]

    numbered = re.match(r"^(\d{1,2})\.\s*(.+)$", stem)
    if numbered:
        lesson_id = f"{int(numbered.group(1)):02d}{part}"
        return lesson_id, numbered.group(2).strip(" _-")

    video = re.match(r"^Video[_\s]+(\d{1,2})\s*[_:\-–—]?\s*(.+)$", stem, re.I)
    if video:
        lesson_id = f"{int(video.group(1)):02d}{part}"
        title = re.sub(r"^\s*[-_–—]+\s*", "", video.group(2))
        title = re.sub(r"\s*\([^)]*\)\s*$", "", title)
        title = re.sub(r"_\d+_\d+_\d+$", "", title)
        title = title.replace("_", " ").strip(" _-")
        return lesson_id, title

    raise ValueError(f"Unrecognized PTM 2 filename: {name}")


def parse_instutrade_filename(name: str) -> tuple[str, str]:
    stem = Path(name).stem
    match = re.match(r"^(\d+)([a-z])?(?:-(\d+))?[.\s]+(.+)$", stem, re.I)
    if not match:
        raise ValueError(f"Unrecognized Instutrade filename: {name}")
    start = int(match.group(1))
    letter = (match.group(2) or "").lower()
    end = match.group(3)
    title = match.group(4).strip(" ;")
    if end:
        lesson_id = f"{start:02d}-{int(end):02d}"
    else:
        lesson_id = f"{start:02d}{letter}"
    return lesson_id, title


def related_documents(lesson_id: str) -> list[str]:
    number = primary_lesson_number(lesson_id)
    folder = DOCUMENTS_DIR / f"Video {number:02d}"
    if not folder.is_dir():
        return []
    files = []
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.name != ".DS_Store":
            files.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    return files


def lesson_dir(course: str, lesson_id: str, title: str) -> Path:
    return TRANSCRIPTS_DIR / course / f"{lesson_id}-{slugify(title)}"


def audio_path(course: str, lesson_id: str) -> Path:
    return AUDIO_DIR / course / f"{lesson_id}.wav"


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def find_whisper_cli() -> Path | None:
    candidates = [
        TOOLS_DIR / "whisper-vulkan" / "whisper-cli.exe",
        TOOLS_DIR / "whisper.cpp" / "build" / "bin" / "Release" / "whisper-cli.exe",
        TOOLS_DIR / "whisper.cpp" / "build" / "Release" / "whisper-cli.exe",
        TOOLS_DIR / "whisper.cpp" / "build" / "bin" / "whisper-cli.exe",
        TOOLS_DIR / "whisper-cli.exe",
    ]
    which = shutil.which("whisper-cli")
    if which:
        candidates.insert(0, Path(which))
    for path in candidates:
        if path.is_file():
            return path
    return None


def default_model_path() -> Path:
    turbo = MODELS_DIR / "ggml-large-v3-turbo.bin"
    large = MODELS_DIR / "ggml-large-v3.bin"
    if turbo.is_file():
        return turbo
    if large.is_file():
        return large
    return turbo
