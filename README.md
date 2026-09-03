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
3. Runs a **full deep research dive per candidate** (filings + web research + bull/bear
   debate — see [Deep single-ticker dives](#deep-single-ticker-dives)) and maps its
   stance onto the qualitative verdict, then runs the catalyst pass on **all** PE
   candidates. `--max-candidates` for a smoke run.
4. Assembles **book.json** plus one book per earnings window (`book_00-30d.json`,
   `book_31-60d.json`, `book_61-90d.json`, rendered to `BOOKS_BY_WINDOW.md`) from the
   strongest longs and shorts that pass the gates (max 6 long / 6 short), with beta
   swaps only if the portfolio breaches its limit
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
.\.venv\Scripts\python.exe -m ptm weekly --legacy-qual        # old one-passage EDGAR verdict instead of the dive
.\.venv\Scripts\python.exe -m ptm weekly --dd-force           # rerun every dive from scratch
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
answers the follow-up: **"what is really going on at THIS one?"** — and as of the
deep-dive qualitative mode, it is no longer a side report: it **replaced the old
EDGAR-pack qualitative pass for every candidate**. `ptm ideas` / `ptm weekly`
run the dive on each candidate instead of the single-passage pack verdict, and
structured gates/ranking consume the dive's mapped stance. Use `--legacy-qual`
for the old behaviour; on a backdated run the fallback is automatic, since web
research is not point-in-time.

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
default. Results cache in `data/raw/deepsearch/runs/` — `--force` (or the
pipeline's `--dd-force`) refetches, including the shared per-query web caches.
The idea pipeline additionally treats a dive older than `DEEPSEARCH_CACHE_DAYS`
(default 2) as stale and reruns it, so a weekly run sees this week's research
while the viewer keeps any cache.

Flags: `--max-queries`, `--max-results`, `--max-fetches` cap API usage for a
cheaper, shallower pass; defaults live on the `DEEPSEARCH_*` env vars.

The macro/ISM section is read from `data/curated/macro_snapshot.json` and
`data/curated/ism.json` — whatever `ptm weekly` last curated. Without those
files the dive still runs and the section renders as unavailable.

### The mapped verdict (ptm/deepsearch/verdict.py)

The pipeline needs a structured `supports_outlier` verdict, evidence items with
measured magnitudes, and a filings direction — the dive produces a stance, a
debate and sourced findings. One verdict-model call per name maps the latter
onto the former, with the same side-aware semantics as before (constructive
supports a long; cautious supports a short; balanced supports neither) and one
hard rule: a claim counts as **quantified only when its percentage appears
verbatim in the dive text**, so the conviction score and the
`min_quantified_for` gate can never be fed an invented number. Without an LLM
the mapping degrades to a deterministic stance read, and the idea is marked as
such.

### In the viewer

Serve `python -m ptm viewer --port 8765` (replaces the raw `http.server`; all
existing tabs work the same) and open the **Deep dives** tab. It lists every
cached dive, renders `REPORT.md` in place, and can **generate new dives from the
browser**: enter one ticker or a comma-separated batch (e.g. `PLTR, TSLA, NVDA`)
and they run one at a time, in order, with live progress. Ticks Force to ignore
cache. Reports render without any build step through a small markdown renderer
in `viewer/index.html`; generation needs the `ptm viewer` server (a plain
`http.server` still browses cached reports, minus the generate form).

The **Pipeline** tab runs the whole idea pipeline from the same browser: weekly
(ingest + screen + dives + books + audit) or ideas-only, with optional max
candidates, force-ingest, ignore-dive-cache and legacy-qualitative switches, a
live log tail while it runs, and the run summary — after which the Book,
Windows and Ideas tabs reload from the files the run just wrote. Opening any
idea's detail pane shows the dive's stance chip and a button that renders the
full REPORT.md inline. A pipeline run and a deep-dive batch are mutually
exclusive so the LLM provider is never hit by both at once.

## PTM-simple — the theme-first process

`ptm_simple` is a second, simpler generator built from the starter pack: the
unit of analysis is a **theme**, not a name. A weekly **theme radar**
(deterministic: revision breadth + print calendar) finds activating themes, a
deterministic ranking picks the 2-5 names that express one (long or short —
falling themes are the same signal ridden short), the deep-dive engine runs
only on that shortlist, and a four-gate pass (why-now / early-late /
getting-paid / listening — no price anywhere) keeps survivors and parks the
rest. See [docs/simple_idea_process.md](docs/simple_idea_process.md).

```powershell
.\.venv\Scripts\python.exe -m ptm_simple build-themes --map manual  # xlsx clusters
.\.venv\Scripts\python.exe -m ptm_simple build-themes --map wiki    # Wikipedia industries
.\\.venv\\Scripts\\python.exe -m ptm_simple radar --map manual --llm
.\.venv\Scripts\python.exe -m ptm_simple select --theme "Data centre REIT" --map manual
.\.venv\Scripts\python.exe -m ptm_simple run --theme "Data centre REIT" --map manual
.\.venv\Scripts\python.exe -m ptm_simple run --all --map manual   # sweep every non-COLD theme
```

**Theme maps.** `--map manual` clusters the starter-pack watchlist by hand.
`--map wiki` is the deterministic alternative: every ticker's company is
resolved to its Wikipedia article (Wikidata P452, the industry field the
infobox renders — no LLM), and industries with ≥3 members become themes.
Industries Wikipedia resolves to fewer than three names are **kept** and judged
in isolation: the ranking reads the same fundamental packet (revisions,
surprise record, consensus growth, absolute forward P/E / PEG / P/S) with no
peer median and no read-throughs, and the quant table marks those rows
`n/a — sole member of its theme`. Pass `build-themes --map wiki --min-members`
a higher value to drop them again. **One membership per ticker:** Wikidata
labels a broad company with several industries (Salesforce carries nine), and
each ticker keeps only its **largest** theme — biggest peer group wins,
alphabetical label on a tie — so no name is ranked twice and none appears twice
on one leaderboard. A theme every one of whose members belongs elsewhere
empties out and disappears (that is where most sub-3 label-spam themes die).
`scripts/dedupe_setups.py` applies the same rule to an existing run without
re-sweeping: it reuses the sweep's per-group judgements and re-runs only the
cross-industry final. Failed lookups are never cached; the map falls back to
yfinance industries per ticker and reports the count. Wikipedia
rate-limits, so the entity-search fallback runs under a wall-time budget —
rerun the build to resolve more.

**In the viewer** (same server): the **Simple** tab runs every step from the
browser — build either theme map, run the radar, **qual-analyze all
members**, or run the **group review** — with the live log, and shows each
step's outputs: both maps' build summaries, the radar table
(status/lean/breadth/bellwether/against-theme divergers), the quant table
with per-name Side (own 90d revisions) and theme-relative Flag, the group
review with per-member verdicts and watch KPIs, and every print qual /
coverage report rendered inline. There is no book and no watchlist: portfolio
construction is out of scope for this process — trade candidates come from
the group review instead.

**Full-universe coverage and the valuation flag.** `analyze-all` (CLI or the
**Qual-analyze all members** button) gives every
covered member of every non-COLD theme a coverage report: no selection, no
gates — each member takes the side its own 90d estimate direction implies and
gets a dive (cache-first), a forward brief and a report. The quant table adds a
theme-relative **valuation flag** (P/E and PEG vs the theme median: premium /
discount / mixed / fair) to every member, the book and every report — a
pointer, never a ranking or gate. `group-review` (CLI or the **Group review**
button) then runs ONE pass per non-COLD theme judging whether each flag is
justified — from the **print-focused qual** (`ptm_simple/print_qual.py`), a
dive-free layer built from the fresh EDGAR research pack (last earnings
exhibit, MD&A, consensus changes), two bounded Ollama web searches per name,
the consensus and revision data, and the computed quarter the next print
reports. Each review writes `ideas/simple/<theme>/_GROUP_REVIEW_<date>.md`
with per-member verdicts (justified / not justified / uncertain), the KPIs to
watch, and reads the whole theme against itself. Commentary, not a gate.

For the same theme-first front half with the per-name qualitative work replaced
by a single ranking pass per industry, see
[PTM-setups](#ptm-setups--the-group-only-ranking-the-setups-tab) below — it is a
separate tab and a separate module, and shares this process's theme map, radar
and quant table rather than copying them.

**Trade ideas** (deterministic — no LLM, no gate): every review row is tagged
by pure logic on side × flag × verdict. The four aligned combinations are the
trade candidates — long + premium justified and long + discount **not**
justified (the market is wrong), short + premium **not** justified and short +
discount justified (the market is right, ride it) — shown in the viewer's
Trade-ideas panel and in each review markdown, where clicking a ticker opens
that name's latest print qual.

## PTM-setups — the group-only ranking (the Setups tab)

`ptm_setups` is a second qualitative layer over the SAME theme-first front half
as `ptm_simple`. The deterministic stages are shared rather than copied — the
theme map, the weekly radar and the quant table are identical computations
writing identical artifacts under `data/simple/`, so both processes read one set
of numbers and there is only one place to fix them. Running the radar or
Refresh fundamentals from either tab updates both.

What differs is the whole qualitative half:

| | `ptm_simple` | `ptm_setups` |
|---|---|---|
| per name | deep dive → forward brief → print qual | **nothing** |
| per industry | one review: is each valuation flag justified? | **one ranking, plus a best long and a best short each with its own case** |
| across industries | — | one final over the per-industry winners |
| LLM calls for 13 industries / 63 names | ~63 dives + ~63 briefs + 13 reviews | **13 + 1** |
| web searches | 2 per name | 2 per industry + 1 per member, pooled |
| side | pinned by rule (90d revisions) | **the ranking's own call** |
| output | flag verdicts + trade tags | **ranked table, the case for each name, a long/short pair per industry (short-led when the group is not rising), and a cross-industry leaderboard** |

```powershell
.\.venv\Scripts\python.exe -m ptm_setups rank --map wiki            # every non-COLD industry
.\.venv\Scripts\python.exe -m ptm_setups rank --map wiki --theme "aerospace engineering"
.\.venv\Scripts\python.exe -m ptm_setups rank --map wiki --no-final # skip the leaderboard
.\.venv\Scripts\python.exe -m ptm_setups rank --map wiki --model gpt-oss:120b   # override the model
```

The deterministic prerequisites still come from `ptm_simple` (`build-themes`,
`radar`, `refresh-fundamentals`) — or from the Setups tab's own buttons, which
call the same functions.

**One pass per industry.** Each non-COLD industry gets ONE call over all of its
members at once, ordering them as long and short setups for the next print and
the 0–3 months around it. Every input is measured and cached: the last print's
EPS actual against consensus with the surprise percentage and the four-quarter
beat record, the name's own FY1 consensus change over 90 and 30 days with the
analyst up/down counts, consensus FY1/FY2 EPS and growth, the last filed
earnings exhibit and forward guidance language from EDGAR, and forward P/E, PEG
and P/S against the industry median. Then one **cross-industry final** ranks
each industry's best long and best short against each other. An **isolated
industry** (the wiki map's sub-3-member themes) gets the same one call with the
same packet, told there are no peers: no median, no read-throughs, judgement
from the name's own fundamentals and the absolute multiples alone.

**The best long and the best short are separate calls.** Each industry names one
of each and writes each its own thesis, catalyst, setup and risk — they are two
different trades and do not share reasoning. The **short leads wherever the
industry's estimate breadth is flat or negative**: in a group that is not rising
the useful answer is which member's expectations get cut, so that section comes
first and the tactical line leads with it. The prompt treats the short as the
harder and more valuable call rather than the leftover at the bottom of the long
list, and "none in this industry" is an accepted answer — an admitted absence
beats an invented short. A pick naming a ticker outside the industry is dropped
rather than displayed.

**The side is the pass's call.** `ptm_simple` pins it by hard rule; here the
90-day revision direction is a strong prior the ranking may override, so a short
is findable inside a rising industry. Overrides are detected deterministically
(never taken from the model's own claim) and marked ⚠ with the reason required
in the risk column.

**Fundamentals only — no price action.** No technicals, no moving averages, no
momentum or trend reads, no support or resistance, no price targets. The packets
carry no price, no price history and not even the post-print price reactions the
expectations cache stores, so the pass is never shown a price and cannot imply
one. Where a conventional setup table puts a trend column, this one puts the
**print setup**: how expectations are moving into the print. Valuation is the
only channel price enters through, already reduced to a ratio.

**Valuation is a hurdle and an asymmetry, never a score.** A premium multiple is
usually the market correctly paying for better growth, returns or durability,
and a discount is usually a correct mark-down — so the level of the multiple
carries almost no directional information over 0–3 months, and the prompt
forbids ranking a name up for being cheap or down for being expensive.
Cheapness is not a catalyst: a discount is interesting only when something
dated forces a re-mark, and a premium is a negative only when the coming print
is likely to break the growth it assumes. What the multiple does change is the
bar the print has to clear and the size of the move if the driver breaks.

**The factual columns are computed, not written.** The latest-surprise column,
the print-setup column and the multiples in the guidance/valuation cell are
rendered from the cached data in `ptm_setups/inputs.py`; the model supplies only
the guidance read, the ordering and the narrative. A percentage taken off a
near-zero or sign-crossing base is an artefact, not a magnitude, so it is
**withheld rather than footnoted** — HTLD's arithmetically true "+2445% beat"
renders as `$0.14 vs $-0.01 est (loss to profit)`, and a four-quarter average
containing such a quarter renders as `avg n/a`. Without that, a two-cent swing
outranks every genuine beat in its industry.

**Model and thinking budget.** Because the pass spends ~14 calls a run instead
of ~140, it can afford a much stronger model than the pipeline's verdict model,
and it needs one — on `gpt-oss:20b` a live pass ranked a name first for its low
P/E and called another "over-valued" while its own PEG said otherwise, the exact
bias the prompt forbids. The default is `glm-5.3-flash`
(`OLLAMA_SETUPS_MODEL`, or `rank --model`, or the tab's dropdown), with
`gpt-oss:120b` as the no-fuss fallback. Two things make a reasoning model usable
here: an output budget in `ptm_setups/rank.py` sized to cover thinking as well
(16k + 2.4k per member, ceiling 64k), and
`OLLAMA_SETUPS_REASONING_EFFORT` — because reasoning tokens come out of the same
allowance as the answer, and an unbounded thinker spends the lot and replies
with empty content and `finish_reason "length"`.

**More thinking did not mean better ranking here, and the default is `low` on
measured grounds.** At `low`, glm-5.3-flash produced the sharpest output of
anything tried — naming a one-off tariff claim that inflated a margin beat, and
a beat size decaying across four quarters — in about 11 seconds an industry.
Raised to `medium` for more depth it got slower (~85s an industry) and less
reliable: one five-name industry came back with no ranking at all, having spent
all 28k tokens deliberating. An empty result is now retried once at `low` with
the ceiling budget, so `medium` degrades instead of failing — but `low` is what
to run. The per-call deadline scales with the group too (180s + 45s per member):
the shared client's 120s is right for a per-name call and far too short for an
eight-member group, which stalled and burned its retry before this was fixed.

**In the viewer**: the **Setups** tab runs every step from the browser (both
theme maps, the radar, Refresh fundamentals, then Rank industries) with the live
log, and shows the cross-industry leaderboard, each industry's best-long and
best-short pair side by side in priority order, every per-industry ranking table
with the case for each name, and each ranking markdown rendered inline. A model
dropdown overrides the configured model per run. A ranking pass and any other
LLM consumer (deep-dive batch, idea pipeline, simple action) are mutually
exclusive.

Output: `data/setups/setups_<date>.json`,
`ideas/setups/<industry>/_RANKING_<date>.md` and
`ideas/setups/_LEADERBOARD_<date>.md`. Commentary, not a gate — nothing
downstream reads a ranking to include or drop a name. Without an LLM key the
pass degrades to the measured table, marked unranked.

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
