# PTM idea engine

Long/short equity research pipeline from the PTM process: macro dashboard, quant screen, qualitative pack, catalysts, timing/PRM, book, then a process audit.

## One command

From the repo root, with the project venv:

```powershell
.\.venv\Scripts\python.exe -m ptm weekly
```

That single command:

1. Ingests universe, prices, FRED, and ISM (live curl, else bundled July fixture)
2. Screens candidates and writes trade-idea markdown + JSON
3. Assembles the book
4. Writes `ideas/<today>/AUDIT.md` and `data/curated/audit.json`

The JSON summary includes a funnel so you can see how many names survived each cut, with long/short splits:

```text
universe 1506 → fundamentals 1506 → candidates 94 (52L/42S) → researched 16 (8L/8S) → book 11 (6L/5S)
```

Progress logs go to stderr with timestamps, including every Yahoo fundamental ticker and an ETA. A checkpoint is written every 25 names, so Ctrl+C does not throw away the backfill. Restart `weekly` to pick up the new logging if a run is already in progress.

If a prior `--max-tickers` run left a short Yahoo cache, the next weekly **backfills missing tickers** instead of reusing an A-only slice. That backfill is slow (one Yahoo `info` call per name). `--force` refetches everything.

A `warnings` entry appears when fundamentals cover less than 90% of the universe.

Useful flags:

```powershell
.\.venv\Scripts\python.exe -m ptm weekly --skip-llm
.\.venv\Scripts\python.exe -m ptm weekly --max-tickers 50 --max-candidates 8
.\.venv\Scripts\python.exe -m ptm weekly --force
.\.venv\Scripts\python.exe -m ptm weekly --pmi-html .\pmi.html --services-html .\services.html
```

`--pmi-html` / `--services-html` are for reports you saved while logged into ismworld.org. Without them, a blocked live fetch uses the July fixture and the audit will warn that the print is stale.

If `ptm` is not on PATH, keep using `python.exe -m ptm` from `.venv\Scripts` as above. Activate first only if you want the short `ptm weekly` form:

```powershell
.\.venv\Scripts\Activate.ps1
ptm weekly
```

## Tests (does not touch live files)

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Other commands

| Command | What it does |
|---|---|
| `ptm status` | Whether an LLM key is loaded |
| `ptm ingest-ism` | ISM only |
| `ptm ingest` | Universe / prices / macro / ISM |
| `ptm dashboard` | Macro snapshot + candidate count |
| `ptm ideas` | Ideas + book from already-ingested data |
| `ptm audit` | Score the latest (or `--ideas-dir`) run |

Substitutes vs the original research-fix plan are in [docs/implementation-notes.md](docs/implementation-notes.md).
