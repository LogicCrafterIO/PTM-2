# Feature limitations and substitutions

What the features do, what they cannot do, and exactly what stands in for the
missing part. Read the **Forward EPS** section before trusting any P/E-based
screen output, live or backdated.

Last updated 2026-08-18.

---

## 0. Where data comes from

**All fundamental data comes from SEC EDGAR. yfinance supplies price history and
nothing else.**

| Field | Source |
|---|---|
| daily OHLC, index/macro prices | yfinance |
| shares outstanding | XBRL (`dei:EntityCommonStockSharesOutstanding`) |
| trailing EPS (TTM diluted) | XBRL (`us-gaap:EarningsPerShareDiluted`) |
| revenue, net income, EBIT, cash, debt | XBRL |
| market cap | EDGAR shares x run-date close |
| trailing P/E | run-date close / EDGAR TTM EPS — **exact** |
| next earnings date | projected from the company's own 10-K/10-Q cadence |
| sector / industry | index constituent tables, not a data vendor |
| macro series | FRED (ALFRED vintages when a key is set) |
| ISM PMI / Services | ismworld.org |

Removed outright: Yahoo `info` (`forwardEps`, `trailingEps`, `forwardPE`,
`marketCap`, `earningsGrowth`, `revenueGrowth`, `beta`), Yahoo's earnings
calendar, `targetMeanPrice`, `recommendationMean`, and the Yahoo business
summary and news headlines that used to pad the research pack. All were a live
snapshot with no history: unusable in a backdated run, and opaque in a live one.
Beta is now computed from price history instead.

`tests/test_backdate_lookahead.py::test_no_vendor_fundamentals_anywhere` fails
the build if any of them come back.

**Cost.** EDGAR is one companyfacts document plus one submissions call per
ticker, so a full-universe build is slow on first run (comparable to the Yahoo
backfill it replaced) and fast afterwards — small per-ticker extracts are
cached, and the multi-megabyte source payloads deliberately are not.

---

## 1. Forward EPS — the one real gap

**EDGAR does not contain analyst consensus, and never will.** It holds what
companies file; consensus is a proprietary product (I/B/E/S, FactSet, Zacks,
Visible Alpha). No free point-in-time source exists either.

So the PTM screen's forward multiple cannot be built the way the process
assumes. What is used instead, in order:

1. **Realized TTM growth, extrapolated one year** — `forward_eps = TTM x (1 + g)`
   where `g` is TTM over prior TTM from filings. This is arithmetic, not a
   forecast.
2. **Held flat** at trailing when there is no usable growth signal.

### The growth clamp

Raw realized growth is frequently distorted by a small or one-off prior-year
base. Alcoa came out at **+300%**, extrapolating to a forward EPS four times
trailing, which would have screened as spectacularly cheap and pulled a fake
long into the book. Growth is therefore clamped to
`[edgar] max_extrapolated_growth` (default ±50%), and those rows are marked
`extrapolated_clamped` so the intervention is visible. On a 20-name sample, 7 of
20 needed clamping — this is common, not a corner case.

### Why company guidance is OFF by default

Management guidance *is* in EDGAR, as free text in the Exhibit 99.1 earnings
release, and a parser for it ships in `ptm/ingest/edgar.py: parse_eps_guidance`.
It is disabled (`[edgar] fetch_guidance = false`) for a structural reason, not a
tuning one:

> **Guidance is almost always non-GAAP / adjusted EPS. XBRL trailing EPS is
> GAAP.** Dividing price by an adjusted forward number, then computing growth
> against a GAAP trailing number, produces a ratio that means nothing.

AbbVie is the clean illustration: ~$14 adjusted guidance against ~$3.54 GAAP
TTM — a 296% "growth rate" that is purely a basis mismatch.

Free-text extraction is also fragile. The first version of the parser matched an
exhibit *header* for Agilent, a **reported** Q3'20 figure for BrightSphere, and
revenue prose for AbbVie. It has since been tightened to require forward-looking
framing, a full-year scope, and the absence of comparative language, and it now
rejects all of those while still accepting genuine full-year guidance. It is
still off by default, because being right on the sentences it matches does not
fix the GAAP/non-GAAP problem.

Turn it on only if you intend to reconcile the basis yourself.

### What *is* exact

**Trailing P/E needs no caveat**: run-date close over EPS from filings public on
that date. Both halves are observed. Marked `trailing_pe_exact` in the
fundamentals table. If you want a screen you can fully defend on backdated data,
build it on trailing P/E rather than forward.

Closing the forward gap properly needs a paid point-in-time estimates feed;
`ptm/fundamentals.py: row_for` is the single function to change.

---

## 2. Sector / earnings-window folders

`ideas/<run-date>/<Sector>/<bucket>/<side>_<TICKER>.md`, plus the matching
`.json`.

```
ideas/2026-08-18/
  INDEX.md                       map of the tree, by sector and by window
  RANKING.md  AUDIT.md
  EARNINGS_REVIEW.md             cross-read, by earnings window
  Information-Technology/
    _SECTOR_REVIEW.md            cross-read, by sector
    00-30d/    long_ACLS.md + .json
    31-60d/
    61-90d/
```

### Calendar days, matching the catalyst window

Windows are **calendar days** from the run date. The PTM catalyst window is
stated as 20-60 *trading* days, which is 30-90 calendar days, and the buckets use
the same units so a name in `31-60d` or `61-90d` can actually satisfy the gate.
An earlier version used trading days for the buckets while the gate used 20-60
calendar days; the two could not both be satisfied, and 88% of ideas were
blocked as "investment idea only" by construction. Correcting the window to
30-90 calendar days dropped that to 12%.

```toml
[filters]
catalyst_window_days = [30, 90]
[earnings_buckets]
edges = [30, 60, 90]
```

Both the gate and the buckets now measure in whole calendar days.
`earnings_in_window` used to subtract datetimes, so a date exactly 30 days out
measured as 29 depending on the time of day - harmless when the two were
unrelated, wrong once they had to agree at a boundary.

### Every idea gets a date, and every date is a projection

EDGAR publishes no forward earnings calendar, so with EDGAR-only fundamentals
there is no such thing as a confirmed next-earnings date here. Every one is
projected from the company's own filing cadence, and every idea says so:

> no future earnings date published; last reported 2026-08-05, so the next
> report is estimated 2026-11-06 (93-day cadence measured over 4 prior gaps),
> which places it 93 calendar days out -> 61-90d.

This bit once: the pipeline read the already-projected date out of the
fundamentals table, where a future date is indistinguishable from a published
one, and relabelled all 154 ideas `estimated=false, basis="published earnings
date"`. The pipeline now resolves the date itself so provenance survives.

**The catalyst gate therefore runs on projected dates.** There is no confirmed
alternative to fall back on. Treat a name near a window boundary as uncertain.

---

## 3. Group cross-read (second LLM layer)

After the per-name work, one further LLM pass reads every idea sharing a sector,
and every idea sharing an earnings window, **against each other** — looking for
the same thesis repeated across names, a long and a short resting on opposite
readings of one driver, a weak case next to its peers, inconsistent use of the
ISM tilt.

Output: `<Sector>/_SECTOR_REVIEW.md` and `EARNINGS_REVIEW.md`.

### No price input, anywhere

This layer originally carried price momentum. It no longer does. There are no
returns, no 52-week position, no volatility, no direction labels, and no "tape"
section. `ptm/momentum.py` is deleted. The prompt explicitly forbids reasoning
about price action, and `test_no_price_or_technical_input_reaches_the_prompt`
fails the build if a price field reappears in the payload.

### Technical analysis is gone from the repository

For the record, since it came up: **the momentum layer never gated anything.**
`apply_process_gates` has exactly two blocks — qualitative denial and the
catalyst window — and nothing in `gates.py`, `book.py`, `quant.py` or
`ranking.py` ever read it.

What *was* still present was dead TA code, now removed:

| Removed | Was |
|---|---|
| `timing_prm.time_idea()` | SMA20/60, EMA20/60, MACD, red/amber/green light |
| `formulas.sma()`, `formulas.ema()` | only used by the above |
| `TimingLight` enum | the light itself |
| `TimingResult.sma20/sma60/ema20/ema60/macd` | now carries a comment only |
| `IdeaState.TIMED` | a timing stage that no longer exists |

`test_no_technical_analysis_surface_remains` asserts none of it comes back.

**What was kept, deliberately:** the ATR-based stop, range target and beta in
`prm_for`. That is position risk sizing applied *after* a name is selected, it
gates nothing, and removing it would break the risk footnote and the book's beta
limit. If you want it gone too, say so — it is a separate call from removing
entry signals.

### The model cannot revise the first pass

`qual_verdict` is the per-name pass's verdict, written over whatever the group
model returns. It may add prose, not overturn a judgement. Counts in the summary
line are computed, not modelled.

### Degradation

No key, `--skip-llm`, or an LLM error all fall back to a deterministic review
ordered by qualitative verdict, with the reason recorded. A failed group review
never aborts the run.

---

## 4. Backdating (`--as-of`)

```powershell
.\.venv\Scripts\python.exe -m ptm as-of-range --probe
.\.venv\Scripts\python.exe -m ptm weekly --as-of 2026-07-20
```

### The PMI window is enforced by a live probe, not a calendar guess

**Calendar gate.** ISM publishes month M's Manufacturing report on business day
1 of M+1 and Services on business day 3, so `ptm/asof.py` derives which report a
run date is entitled to.

**Live probe — the one that decides.** Old month URLs are *not removed*; they
rotate to a navigation-only stub and still return HTTP 200, so a status check
would "succeed" on an empty page. A backdated run fetches the month it needs and
requires a parsed headline before starting. Probed on 2026-08-18:

| Report month | Page | Parses | PMI |
|---|---|---|---|
| July 2026 | full report, 43 KB | yes | 55.6 |
| June 2026 | full report, 43 KB | yes | 53.3 |
| May 2026 | navigation stub, 3.7 KB | **no** | — |

So although the calendar suggests May is reachable, **ISM currently serves only
two months**, and the true earliest run date is **2026-07-04**. A run whose month
has rotated off exits with code 2 naming what it needed and what still works.
`--allow-stale-ism` accepts an older print; `--pmi-html` / `--services-html`
accept reports you saved, the only way further back.

### What is point-in-time

| Input | How it is bounded |
|---|---|
| Equity prices | `yf.download(start=…, end=run_date+1)`; `_bound_prices` re-clips any cached CSV |
| FRED | true ALFRED vintage via `realtime_start`/`realtime_end` (API key), else a 45-day publication-lag haircut |
| ISM | month derived from the run date, probed for a real headline; a bundled fixture is **refused** if newer than the run date allows |
| SEC filings | filtered on `filingDate <= run date` |
| XBRL facts | filtered on **`filed`**, not `end` — a quarter ending in June but filed in August is invisible to a July run |
| Trailing EPS, shares, market cap | rebuilt from those filed-bounded facts |
| Caches | keyed by run date, so vintages never mix |

FRED vintages are verified, not assumed: a 2026-07-20 run sees CPI through June
at **332.568** versus **332.813** in today's vintage, and payrolls at 158,881
versus 158,858.

### Remaining substitutions

| Input | Substitute | Effect |
|---|---|---|
| **Forward EPS consensus** | extrapolated realized growth (clamped) — see §1 | Largest gap. The screen becomes *realized* vs *expected* growth: different names, not just different ordering. |
| **Next earnings date** | projected from filing cadence | Usually within a week. Filing/reporting only; the catalyst gate is unaffected. |
| **Index membership** | today's constituent lists | Survivorship and membership drift. Small over 2-3 months, real over years. |
| **Sector / industry** | today's classification | Rarely changes inside the supported window. |
| **Beta, targets, recommendations** | dropped or price-derived | Portfolio beta comes from price history; analyst fields are gone entirely. |

Every backdated run's JSON carries `BACKDATED RUN:` warnings and the audit adds
a `worldview.backdated_run` finding. None of it is silent.

### This is not a backtest

It is an honest re-run of the screen on data available at the time. The
forward-EPS substitution means hit rates computed from it are not the strategy's
edge.

---

## 5. Book construction

`max_positions = 12`, so six per side, taken in screen-rank order — but two
constraints now shape the selection, because rank alone produced an untradeable
book.

### Sector cap

`[filters] max_per_sector = 2`, per side. Six shorts drawn from one sector is
one bet, not six, and nothing previously prevented it.

The cap is **not** relaxed to fill the book. Quietly topping up from a full
sector would make the setting meaningless and hide correlated risk, so the side
comes back short and `limit_breaches` records why:
`"short side held to 4 of 6 available by the 2-per-sector cap"`.

### Beta-aware selection

A P/E-outlier screen is **beta-long by construction**. Premium-multiple longs
are growth names carrying high beta; discount-multiple shorts are value and
defensive names carrying low beta. Measured on the full universe run: mean long
beta **1.50**, mean short beta **0.24**. A dollar-neutral 6v6 book at equal
weights therefore came out at beta **0.63** against a ±0.30 limit — net exposure
0.0 and still badly long the market.

`beta_net_limit` was declared as a limit but only ever *reported* after the
fact. Selection now respects it: the book is built on rank and the sector cap
first, and only if it breaches does it swap the worst offender for the
best-ranked eligible replacement that moves beta toward zero. Rank still leads —
no swaps happen when the book already complies — and every swap is reported:

```
beta rebalance: swapped long VICR (beta 3.28) -> GSHD (beta -0.33) to reduce portfolio beta
beta rebalance: swapped long MTRN (beta 2.01) -> CME (beta -0.32) to reduce portfolio beta
```

Two swaps took the live book from 0.63 to **+0.132**. Disable with
`[filters] beta_aware_selection = false` to get pure rank order and a reported
breach instead.

Note this is a *selection* lever, not a *sizing* one. Beta-neutralising by
weight instead would require roughly 14% long / 86% short gross given those
mean betas, which breaks dollar neutrality and the net-exposure limits.
`size_fraction` remains a stub returning 1.0.

---

## Configuration

```toml
[earnings_buckets]
edges = [30, 60, 90]       # CALENDAR-day cuts to next earnings

[filters]
catalyst_window_days = [30, 90]   # PTM's 20-60 trading days, in calendar days
max_screen_pe = 200.0             # above this the P/E reflects a near-zero EPS
require_eg_case = true            # a candidate must fit a process EG case
max_per_sector = 2                # per side
beta_aware_selection = true       # swap to respect beta_net_limit

[llm]
qualitative_bar = "consistent"    # "strict" demands quantified evidence (~55% vs ~80% pass)

[edgar]
fetch_guidance = false     # see §1: adjusted-vs-GAAP basis mismatch
max_extrapolated_growth = 0.5

[asof]
ism_months_available = 3   # calendar gate; the live probe is the real authority
ism_release_day = 4

[fred_asof]
publication_lag_days = 45  # keyless CSV fallback only
```

## Where the guarantees are tested

* `tests/test_asof.py` — PMI window, floor, rejection messages, cadence projection
* `tests/test_organize.py` — trading-day buckets, projection statements, recursive audit discovery
* `tests/test_group_review.py` — no price reaches the prompt, momentum module gone, verdicts not revisable
* `tests/test_timing_prm.py` — no SMA/EMA/MACD surface survives
* `tests/test_backdate_lookahead.py` — every leak above, no vendor fundamentals, EDGAR pricing off the run-date close
