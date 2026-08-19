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

### 1. R-score is not ATRP(63) / ATRP(20)

Daily ATRP over 63 days is almost the same number as ATRP over 20 days, so that ratio sits near 1.0 and `min_r_score = 3.0` would block every name.

**What we did:** stop = 20-day ATRP (unchanged). Target = 63-day high/low range (`high/low - 1`), which moves with the stock’s actual swing and is independent of the stop. If there is not enough history, we still fall back to `stop * atrp_target_multiple`.

True weekly vs quarterly ATRP bars (the course spreadsheet) need a resample we do not store. That remains a later enhancement.

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
