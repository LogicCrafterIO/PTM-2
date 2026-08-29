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
(`OLLAMA_API_KEY`, `NVIDIA_API_KEY`, or `OPENAI_API_KEY`); Ollama Cloud is used
first when present. Without an LLM key, run with `--skip-llm`.
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

Six per side in screen-rank order, subject to three constraints:

* **`max_per_sector = 2`** per side — six shorts from one sector is one bet, not
  six. The cap is never silently relaxed; a short side is reported as such.
* **Conviction ordering** — inside the book, names are ordered by how well
  evidenced they are, not by earnings growth. Each reason from the qualitative
  verdict is weighed by the magnitude it moves (earnings > revenue > margin) where
  the filing states one, so "backlog up 22%" outranks "management sounds
  confident". Every idea's JSON carries the score and its full arithmetic in
  `extra.conviction_detail`. See [docs/EG-CASES.md](docs/EG-CASES.md) §7.
* **Size bands** — longs are held to $3-10bn, which is the process. Shorts have
  **no** size floor: `mcap_ok` is the first ranking key, so the $20bn floor once
  set there demoted every smaller short beneath every large cap whatever its
  idea quality, and with 3 of 23 ready shorts clearing it the side came back at
  4 of 6 every run. Borrow and squeeze risk do not bind on an options-expressed
  book, but **options liquidity** is modelled nowhere and small-cap shorts can
  carry thin chains — a manual check. See
  [docs/FEATURE-LIMITATIONS.md](docs/FEATURE-LIMITATIONS.md) §5.
* **Beta-aware selection** — a P/E-outlier screen is beta-long by construction
  (growth longs ~1.5 beta, value shorts ~0.24), so a dollar-neutral book still
  breached ±0.30. Rank leads; only if the book breaches does it swap the worst
  offender for the best-ranked eligible replacement, and every swap is reported.

## What the market already expects

Every idea states what consensus and the options market currently imply, how its
evidence differs, and whether that difference is already priced. Four measures,
in `ptm/ingest/expectations.py`: **implied move** from the option chain (the
hurdle an options-expressed thesis has to clear), **estimate revisions**,
**price reaction to the last ~4 prints**, and **surprise history**.

Conviction is docked when a thesis only restates what the market has already
moved to — true, but not news. The chain fetch also reports open interest and
spread, which is the one risk that still binds a small-cap short book once
borrow and squeeze stop applying.

**Backdated runs get none of this**: no option chain or revisions table has a
point-in-time archive, so all four are refused rather than served stale. See
[docs/FEATURE-LIMITATIONS.md](docs/FEATURE-LIMITATIONS.md) §5b.

## Group cross-read

After the per-name work, a second LLM pass reads every idea in a sector — and
every idea in an earnings window — against the others, looking for duplicated
theses, longs and shorts resting on opposite readings of one driver, and weak
cases next to their peers.

It uses **no price data of any kind**, and it is commentary, not a gate: no name
enters or leaves the book on its verdict, and it cannot overturn the per-name
qualitative judgement. There is no technical analysis anywhere in the screening
process — no SMA, EMA, MACD or timing lights, and no ATR stop, range target or
R-score. Those three went with the move to options: a stop distance on the
underlying does not manage a defined-risk position, and none of them gated or
ranked anything. Beta survives, because the book swaps names on it to stay
inside its limit.

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

## Deep single-ticker dives

The weekly pipeline answers "which names should I look at?". The deep dive
answers the follow-up: **"what is really going on at THIS one?"**

```powershell
.\.venv\Scripts\python.exe -m ptm deepdive run PLTR
.\.venv\Scripts\python.exe -m ptm deepdive show PLTR
```

One ticker in, a full qualitative dossier out, written to
`ideas/deepdive/<TICKER>/REPORT.md`. The pipeline:

1. Pulls the company's own filings from EDGAR as grounding
2. **Plans 6-10 web queries** with an LLM against that filing context — deliberately
   including a bear query and a competitor query, the angles filings never cover
3. Runs them through the **Ollama web search API** (`ollama.com/api/web_search`,
   same `OLLAMA_API_KEY`), then full-fetches the pages most likely to carry numbers
   (press releases, transcripts, filings)
4. Extracts dated, **source-cited findings** from every snippet and page, in chunks
   so one truncated response cannot zero out the research base
5. Identifies the 3-5 **drivers** the thesis hinges on, then runs a structured
   **bull-vs-bear debate per driver** — both sides arguing from the same evidence
   base, with a moderator verdict per round
6. Synthesises a stance (constructive / cautious / balanced), a thesis, and
   **falsifiers** — the observable numbers or events that would flip the call
7. Projects the **PTM macro dashboard onto the ticker**: ISM PMI/NMI, new orders,
   the curve, VIX and sector tilt from `data/curated/` are read into every
   analysis prompt, and a dedicated pass maps **how the backdrop transmits into
   this company's fundamentals** (demand, pricing, input costs, backlog,
   financing), flagging any contradiction between the ISM sector tilt and the
   company-specific findings
8. Lists catalysts with windows and what each outcome would do

Every claim in the report links to its source. Heavy passes (drivers, cases,
debate, synthesis) run on the verdict model; extraction and catalysts run on the
default. Results cache in `data/raw/deepsearch/runs/` — `--force` refetches.

Flags: `--max-queries`, `--max-results`, `--max-fetches` cap API usage for a
cheaper, shallower pass; defaults live on the `DEEPSEARCH_*` env vars.

The macro/ISM section is read from `data/curated/macro_snapshot.json` and
`data/curated/ism.json` — whatever `ptm weekly` last curated. Without those
files the dive still runs and the section renders as unavailable.

### In the viewer

Serve `python -m ptm viewer --port 8765` (replaces the raw `http.server`; all
existing tabs work the same) and open the **Deep dives** tab. It lists every
cached dive, renders `REPORT.md` in place, and can **generate new dives from the
browser**: enter one ticker or a comma-separated batch (e.g. `PLTR, TSLA, NVDA`)
and they run one at a time, in order, with live progress. Ticks Force to ignore
cache. Reports render without any build step through a small markdown renderer
in `viewer/index.html`; generation needs the `ptm viewer` server (a plain
`http.server` still browses cached reports, minus the generate form).

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
