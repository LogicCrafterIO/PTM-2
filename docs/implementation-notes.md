# Implementation notes — PTM research fixes

> **Superseded in places.** This file records the original v1 substitutions. Several
> have since changed: fundamentals now come from EDGAR rather than Yahoo, forward EPS
> from analyst consensus, technical analysis has been deleted outright, and the
> catalyst window is 30-90 calendar days. Where the two disagree,
> [FEATURE-LIMITATIONS.md](FEATURE-LIMITATIONS.md) and [EG-CASES.md](EG-CASES.md) are
> current.



What shipped vs what the plan asked for, plus how to run the suite.

## How to run

One command for the full weekly pipeline (ingest, ideas, book, audit):

```powershell
.\.venv\Scripts\python.exe -m ptm weekly
```

See [README.md](../README.md) for flags (`--skip-llm`, `--pmi-html`, `--force`, …). Weekly output includes a `funnel` string (`universe → fundamentals → candidates L/S → researched L/S → book L/S`). Fundamentals come from EDGAR and are backfilled on the next run; a short cache is not reused as an A-only PE screen. Default weekly researches **every PE-outlier candidate** and writes `ideas/<today>/RANKING.md`. Technical analysis is gone entirely — the SMA/MACD machinery was deleted, not merely bypassed (see [FEATURE-LIMITATIONS.md](FEATURE-LIMITATIONS.md) §3).

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ptm audit --ideas-dir ideas/2026-08-16
```

`pytest` writes into a temp `data/` and `ideas/` tree. It does not touch live research files.

## Feasible substitutes

These are the places the original plan was not practical as written. The product still does the job; the method is different.

### 1. R-score, the ATR stop and the range target are removed

This section used to explain how R-score was reconstructed (stop = 20-day ATRP, target = 63-day high/low range) because the literal ATRP(63)/ATRP(20) ratio sat near 1.0 and would have blocked every name.

That workaround is moot: all three are deleted. The book is traded as options, where a stop distance on the underlying does not manage a defined-risk position, and none of the three ever gated or ranked anything. `min_r_score` was dead config. See `docs/FEATURE-LIMITATIONS.md` §3 and `ptm/risk.py`.

### 2. `min_sector_names = 2`, not 8

A floor of 8 would empty the offline pipeline fixture (6 Industrials, 2 Materials) and the 3-name unit screen. The live AEE bug was a **one-name** sector PE mean. Blocking `n < 2` fixes that. A full S&P GICS group already has far more than 8 names.

### 3. Yield curve uses `^IRX`, not a 2-year note

Yahoo does not ship a clean 2-year yield in this project’s symbol list. The short leg is the 13-week bill (`^IRX`), with `^FVX` only if IRX is missing. `MacroSnapshot.curve_second_leg` is `"irx"` so `worldview.curve_label_10s5s` does not fire on new dashboards. Old eval fixtures without that field still flag the historical 10s-5s bug.

### 4. Catalyst window is calendar days, not trading days

No NYSE holiday calendar is in the repo. Dated catalysts must fall 20–60 calendar days out. Same window as the existing earnings helper.

### 5. ISM live fetch is still best-effort

Latest *released* print is last calendar month (mid-August tries `/july/`, not `/august/`). Fetch is curl-only (no Playwright): Chrome impersonation over HTTP/1.1 after a homepage cookie warmup. Cloudflare empty-replies HTTP/2 (curl 52). If that still fails, scrape falls back to saved `--pmi-html` / `--services-html` files, then the bundled July fixture. The audit still warns when the print is stale. We did not add an ISM login/cookie path.

### 6. Not built (still later)

| Item | Why not now |
|---|---|
| IR-site crawler | 10-K Item 1 / MD&A / EX-99.1 only. The Yahoo `longBusinessSummary` fallback was removed with the rest of the vendor fundamentals, so an empty Item 1 now stays empty (~7% of names) rather than being backfilled from undated vendor prose |
| Full DoR spreadsheet stops | Independent 63-day range is the retail stand-in |
| Streamlit dashboard | CLI + `AUDIT.md` is the operator surface |
| Reactive risk / live positions | Idea engine only |

## Macro dashboard signals

`build_dashboard()` averages an equally-weighted signal set into one score,
which sets the book's `bias`. A series that is missing contributes **no**
signal rather than a zero, so an unavailable input cannot quietly drag the score
toward neutral.

| Signal | Source | Reads |
|---|---|---|
| `regime` | ^GSPC vs 20% drawdown | bear level |
| `curve` | ^TNX minus ^IRX | inversion |
| `ism_pmi` | ISM report, FRED fallback | expansion / peak / trough / contraction |
| `ism_new_orders` | ISM manufacturing components | leads PMI |
| `ism_nmi` | ISM services | expansion |
| `umcsi` | FRED `UMCSENT` | consumer sentiment |
| `permits` | FRED `PERMIT` | housing, leads the cycle |
| `real_rate` | ^TNX minus CPI yoy | cost of capital |
| `vix` | ^VIX | stress |

### Building permits

`PERMIT` was already being fetched by `ptm/ingest/fred.py` and written to
`macro_fred.json`, but nothing read it — the dashboard scored eight signals and
ignored the ninth sitting in the file. It is now scored.

Permits lead the cycle by roughly six to twelve months, which is why the
Conference Board carries them in the LEI: housing turns before employment and
capex do. Scored on year-over-year change against `[macro] permits_strong`
(+5%), `permits_weak` (−5%) and `permits_recession` (−15%).

The one subtlety is the trough. A decline past `permits_recession` is the size
that has preceded past US recessions — *unless* the series is already bottoming,
which the annual comparison hides for up to a year. So a deep year-over-year
decline whose **3m/3m** reading has turned positive scores **+0.3** (trough)
rather than −1.0 (contraction), mirroring the ISM trough-zone treatment already
in the dashboard. The 3m/3m smoothing matters on its own terms: monthly permits
swing several percent on weather and pull-forward, so a single print says little.

Both `permits_yoy` and `permits_3m3m` land on `MacroSnapshot`, so the LLM macro
narrative sees them without further plumbing.

On the last full run: **+3.1% yoy, −2.3% 3m/3m → flat, signal 0.0**. Adding a
ninth signal at 0.0 moved the score from +0.463 to +0.411; bias stayed
`NET_LONG`.

## Where the expectations data comes from

`ptm/ingest/expectations.py` is the second module to break the EDGAR-only rule,
after `estimates.py`, and for the same structural reason: filings state what a
company **reported**, and expectations are by definition what it has **not
reported yet**.

| Field | yfinance surface | Notes |
|---|---|---|
| implied move | `Ticker.option_chain(expiry)` | ATM straddle ÷ spot, first expiry ≥ the projected earnings date |
| open interest, spread | same call | the options-liquidity check; free once the chain is fetched |
| consensus 30d/90d | `Ticker.eps_trend` | `current` vs `30daysAgo` / `90daysAgo`, period `0y` |
| revision counts | `Ticker.eps_revisions` | `upLast30days` / `downLast30days` |
| surprise history | `Ticker.earnings_history` | `surprisePercent` is a **fraction** (0.0923 = +9.23%) |
| past-print reaction | `prices.csv` + `<T>_reportdates.json` | offline; no network call |

All were already reachable from a vendor the repo uses and none was touched
before. Cached per ticker under `data/raw/expectations/`, `max_age_days = 2`,
fetched on 8 workers.

### The three things that will break first

1. **yfinance schema drift.** Each accessor is wrapped and returns
   `{"available": False}` on any exception, so a renamed column degrades the read
   rather than failing the run. It also means a silent schema change looks
   identical to "no data" — check `available` counts across a run before
   concluding a name has no coverage.
2. **Chain fetch cost.** Two network calls per name, ~200 names. It is the second
   slowest stage after EDGAR.
3. **`surprisePercent` units.** If yfinance ever switches to whole percent, every
   surprise figure silently becomes 100× too small. There is no way to detect that
   from one value.

## What did get fixed in code

- EDGAR Item 1 prefers 10-K, skips TOC hits; no Yahoo summary fallback
- MD&A skips TOC lines; empty sections are not cached
- 8-K cover pages are rejected; EX-99.1 names are scanned across 8-Ks
- `skip_llm` / no API key → `supports_outlier=None` (deferred), markdown still written, book excludes those ideas
- Sole-contraction industry (e.g. Chemical Products) cannot leave the parent sector long; long `why` text cannot say “contraction”
- Earnings dates stored as ISO; headline/table catalysts dropped
- Statement-line KPIs stripped
- Markdown files never dump JSON
- `generate_ideas` always writes `book.json` from the same in-memory list
- Book excludes zero size and hard `extra.gates`
- SMA/MACD timing lights are **removed from the codebase**, not just omitted; ATR/R-score remain as post-selection risk footnotes that gate nothing
- Every PE candidate is ranked into `RANKING.md`; qualitative is two-pass extract then EG-case verdict
