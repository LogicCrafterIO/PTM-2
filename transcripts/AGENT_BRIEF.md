# Agent brief: how to use these transcripts

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
