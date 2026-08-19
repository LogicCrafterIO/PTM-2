# PTM idea engine

Long/short equity research pipeline from the PTM process: macro dashboard, quant screen, qualitative pack, catalysts, book, then a process audit. SMA/MACD timing lights are not used.

## Setup

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

Use `requirements-dev.txt` instead to get `pytest` as well. Runtime deps mirror
`[project].dependencies` in `pyproject.toml`.

Optional `.env` at the repo root enables the LLM qualitative/catalyst passes
(`NVIDIA_API_KEY` or `OPENAI_API_KEY`); without one, run with `--skip-llm`.
Check with `python -m ptm status`.

## One command

From the repo root, with the project venv:

```powershell
.\.venv\Scripts\python.exe -m ptm weekly
```

That single command:

1. Ingests universe, prices, FRED, and ISM (live curl, else bundled July fixture)
2. Ranks every PE-outlier candidate (`ideas/<today>/RANKING.md`)
3. Runs qualitative + catalysts on **all** PE candidates (slow with LLM; `--max-candidates` for a smoke run)
4. Assembles the book from top names that pass gates (max 6 long / 6 short)
5. Writes `ideas/<today>/AUDIT.md` and `data/curated/audit.json`

The JSON summary includes a funnel so you can see how many names survived each cut, with long/short splits:

```text
universe 1506 → fundamentals 1506 → candidates 94 (52L/42S) → researched 94 (52L/42S) → book 11 (6L/5S)
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

Live ISM fetch uses HTTP/1.1 plus a homepage warmup (Cloudflare empty-replies HTTP/2). `--pmi-html` / `--services-html` override that with reports you saved in the browser. If the live fetch still fails, the July fixture is used and the audit warns that the print is stale.

```powershell
.\.venv\Scripts\python.exe -m ptm weekly --pmi-html .\pmi.html --services-html .\services.html
```

If `ptm` is not on PATH, keep using `python.exe -m ptm` from `.venv\Scripts` as above. Activate first only if you want the short `ptm weekly` form:

```powershell
.\.venv\Scripts\Activate.ps1
ptm weekly
```

## Where the data comes from

**Reported fundamentals come from SEC EDGAR. yfinance supplies prices and analyst
consensus estimates.**
Shares, trailing EPS, revenue, EBIT, cash and debt are XBRL facts; market cap is
EDGAR shares times the run-date close; the next earnings date is projected from
the company's own filing cadence. Yahoo's `info` snapshot, its earnings
calendar, analyst targets and news are no longer used anywhere.

Trailing P/E is therefore **exact** (EDGAR GAAP over the run-date close). Forward
EPS comes from analyst consensus on live runs — 94% coverage — which is what makes
`eg1`/`eg2` and PEG independent and the EG taxonomy work.

A name **without** consensus is excluded from the screen rather than estimated
around: adjusted consensus EPS runs ~18% above GAAP trailing, so mixing the two
would misprice those names *and* drag the sector median every other name is judged
against. Consensus has no history, so backdated runs refuse it outright and put the
whole universe on one consistent extrapolated basis instead. See
[docs/FEATURE-LIMITATIONS.md](docs/FEATURE-LIMITATIONS.md) before leaning on a
forward multiple.

The screen classifies every candidate into a PTM **EG case** (acceleration,
stable-above, turnaround, worsening decline, and so on); a name fitting no case
is not a candidate. See [docs/EG-CASES.md](docs/EG-CASES.md) for every case, how
it is determined, and which ones are currently unreachable without analyst
consensus.

## Where ideas land

Ideas are filed by sector, then by how soon the name reports, in **calendar
days** — the same units as the 30-90 day catalyst window, so a name in `31-60d`
or `61-90d` can actually satisfy the gate:

```
ideas/2026-08-18/
  INDEX.md                       map of the tree, by sector and by window
  RANKING.md  AUDIT.md
  EARNINGS_REVIEW.md             cross-read, by earnings window
  Information-Technology/
    _SECTOR_REVIEW.md            cross-read, by sector
    00-30d/     long_ACLS.md + .json
    31-60d/
    61-90d/
```

Every idea gets a window. When no future earnings date is published, the next
report is projected from filing cadence and the reasoning travels with it:

> no future earnings date published; last reported 2026-08-05, so the next
> report is estimated 2026-11-06 (93-day cadence over 4 prior gaps), which
> places it 93 calendar days out → 61-90d.

EDGAR publishes no forward earnings calendar, so **every** date is a projection
and every idea says so. The catalyst gate necessarily runs on them. Edges live
in `[earnings_buckets]`, the window in `[filters] catalyst_window_days`.

## The book

Six per side in screen-rank order, subject to two constraints:

* **`max_per_sector = 2`** per side — six shorts from one sector is one bet, not
  six. The cap is never silently relaxed; a short side is reported as such.
* **Conviction ordering** — inside the book, names are ordered by how well
  evidenced they are, not by earnings growth. Each reason from the qualitative
  verdict is weighed by the magnitude it moves (earnings > revenue > margin) where
  the filing states one, so "backlog up 22%" outranks "management sounds
  confident". Every idea's JSON carries the score and its full arithmetic in
  `extra.conviction_detail`. See [docs/EG-CASES.md](docs/EG-CASES.md) §7.
* **Beta-aware selection** — a P/E-outlier screen is beta-long by construction
  (growth longs ~1.5 beta, value shorts ~0.24), so a dollar-neutral book still
  breached ±0.30. Rank leads; only if the book breaches does it swap the worst
  offender for the best-ranked eligible replacement, and every swap is reported.

## Group cross-read

After the per-name work, a second LLM pass reads every idea in a sector — and
every idea in an earnings window — against the others, looking for duplicated
theses, longs and shorts resting on opposite readings of one driver, and weak
cases next to their peers.

It uses **no price data of any kind**, and it is commentary, not a gate: no name
enters or leaves the book on its verdict, and it cannot overturn the per-name
qualitative judgement. There is no technical analysis anywhere in the screening
process — no SMA, EMA, MACD or timing lights. (ATR-based stops and beta remain
as a post-selection risk footnote, which gates nothing.)

## Backdating a run

```powershell
.\.venv\Scripts\python.exe -m ptm as-of-range --probe     # which months ISM still serves
.\.venv\Scripts\python.exe -m ptm weekly --as-of 2026-07-20
```

The run date bounds every source: prices, FRED (true ALFRED vintages), the ISM
month, SEC filings and XBRL facts — the latter by *filing* date, not period end,
so a quarter filed after the run date stays invisible.

How far back you can go is decided by a **live probe**, not a calendar: old ISM
month URLs return a navigation stub rather than a 404, so the run fetches the
month it needs and requires a parsed headline before starting. Use
`--allow-stale-ism` to accept an older print, or `--pmi-html` / `--services-html`
to supply saved reports.

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
| `ptm as-of-range` | How far back a backdated run can reach (`--probe` to verify live) |

Substitutes vs the original research-fix plan are in [docs/implementation-notes.md](docs/implementation-notes.md).
