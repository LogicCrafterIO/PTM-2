# Feature limitations and substitutions

What the features do, what they cannot do, and exactly what stands in for the
missing part. Read the **Forward EPS** section before trusting any P/E-based
screen output, live or backdated.

Last updated 2026-08-30.

---

## 0a. The qualitative pass is now the deep dive

`ptm ideas` / `ptm weekly` replaced the EDGAR-pack qualitative pass
(`research_pack` → extract → verdict, three LLM calls over ~12 KB of filing
text) with a **full deep research dive per candidate** — filings grounding,
planned web research, source-cited findings, drivers, a structured bull-vs-bear
debate, a synthesised stance — and one verdict-model call
(`ptm/deepsearch/verdict.py`) mapping that dossier onto the same structured
`QualResult` the gates and the ranking already consumed. The old pass survives
as `--legacy-qual`.

What this buys and what it costs:

* **The evidence base is web-grounded, not filing-only.** The old pack could
  never see competitor moves, end-market data or the bear case; the dive plans
  queries for exactly those angles and cites a source for every claim.
* **Slow, by design.** ~15 LLM calls and ~12 web searches per name. The idea
  thread pool (`[llm] idea_workers`, default 5) is what makes it minutes rather
  than hours; `DEEPSEARCH_CACHE_DAYS` (default 2) reuses a fresh dive across
  runs, and the per-query web caches are shared with the Deep-dives tab.
* **Backdated runs fall back to the legacy verdict automatically** — web search
  returns today's web, and serving that inside an "as of 2026-07-20" book is
  lookahead. The fallback is logged at run start and repeated as a warning in
  the run summary. This keeps the backdate guarantee in
  `tests/test_backdate_lookahead.py` intact.
* **Quantified evidence is verified, not trusted.** The adapter marks an
  evidence item `quantified` only when the percentage it claims appears
  verbatim in the dive text; anything else is stripped to an unquantified claim
  (and flagged `unverifiable_magnitude_stripped`) before it can reach the
  conviction score or gate on `min_quantified_for`.
* **A failed dive defers, it does not pass.** A dive that errors leaves the
  idea without a verdict (`extra.deepdive.error`), which keeps it out of the
  book rather than guessing.

_Stance mapping:_ constructive supports a long idea, cautious supports a short
(a cautious read on a discounted name is *confirming* evidence), balanced
supports neither, unclear defers. The verdict model is told — and the tests
pin — that this mapping is side-aware, so a strong-company report no longer
converts into an automatic long ticket.

---

## 0. Where data comes from

**All *reported* fundamentals come from SEC EDGAR. yfinance supplies price history
and analyst consensus estimates — and nothing else.**

The split is deliberate: EDGAR holds what companies *filed*, and can never hold
what analysts *expect*. Consensus is not a filing, so an EDGAR-only design cannot
express a forward-multiple screen at all. See §1.

| Field | Source |
|---|---|
| daily OHLC, index/macro prices | yfinance |
| forward EPS FY1/FY2, consensus growth | yfinance `earnings_estimate` — live runs only; no consensus = not screenable |
| shares outstanding | XBRL (`dei:EntityCommonStockSharesOutstanding`) |
| trailing EPS (TTM diluted) | XBRL (`us-gaap:EarningsPerShareDiluted`) |
| revenue, net income, EBIT, cash, debt | XBRL |
| market cap | EDGAR shares x run-date close |
| trailing P/E | run-date close / EDGAR TTM EPS — **exact** |
| next earnings date | projected from the company's own 10-K/10-Q cadence |
| sector / industry | index constituent tables, not a data vendor |
| macro series | FRED (ALFRED vintages when a key is set) |
| ISM PMI / Services | ismworld.org |

Still removed: Yahoo `info` (`forwardEps`, `trailingEps`, `forwardPE`,
`marketCap`, `earningsGrowth`, `revenueGrowth`, `beta`), Yahoo's earnings
calendar, `targetMeanPrice`, `recommendationMean`, and the Yahoo business
summary and news headlines that used to pad the research pack. Estimates are a
separate, explicit module — not a reopening of the `info` snapshot. All were a live
snapshot with no history: unusable in a backdated run, and opaque in a live one.
Beta is now computed from price history instead.

`tests/test_backdate_lookahead.py::test_no_vendor_fundamentals_anywhere` fails
the build if any of them come back.

**Cost.** EDGAR is one companyfacts document plus one submissions call per
ticker, so a full-universe build is slow on first run (comparable to the Yahoo
backfill it replaced) and fast afterwards — small per-ticker extracts are
cached, and the multi-megabyte source payloads deliberately are not.

---

## 1. Forward EPS

**EDGAR does not contain analyst consensus, and never will.** It holds what
companies file; consensus is a proprietary product. The PTM screen runs on
forward multiples and forward growth, so this is the one input that has to come
from somewhere else.

**Live runs use analyst consensus** (`ptm/ingest/estimates.py`, yfinance
`earnings_estimate`): FY1 and FY2 EPS as two independent numbers, with growth
measured against the same table's prior-year EPS so the basis stays consistent.
Coverage on the live universe: **1416 of 1505 names (94%)**, fetched in about a
minute. Names below `[estimates] min_analysts` do not count — a two-analyst
"consensus" is one opinion with a rounding error.

This matters more than it sounds. With extrapolation, `eps2 = eps1 x (1 + g)`
reused the same `g`, so eg1 and eg2 were the same number and the EG taxonomy
collapsed from nine reachable cases to three. With consensus, **0 of 1405 names
have eg1 == eg2**. Full analysis: [EG-CASES.md](EG-CASES.md).

### A name without consensus is excluded, not estimated around

The 89 uncovered names are dropped from the screen (`[estimates]
require_consensus`), rather than falling back to extrapolation. Falling back
would mix two accounting bases in a single screen:

| Group | median forward EPS / trailing EPS |
|---|---|
| consensus (adjusted) | **1.184** |
| extrapolated (GAAP) | **1.000** |

Adjusted consensus runs ~18% above GAAP trailing, so a fallback name's forward
P/E is struck with a smaller denominator and looks expensive as an artefact —
VTR at 112.6 against a 29.6 sector median was mostly that. And because those rows
also sat inside `sector_pe1`, eighty-nine mismatched names were shifting the
benchmark for fourteen hundred good ones.

Cost of excluding them: 4 candidates out of 210. They remain in
`yahoo_fundamentals.csv` with `forward_source` recorded, so the exclusion is
auditable rather than invisible.

**Backdated runs refuse consensus** — today's estimates carry no history, so
using them to screen a past date is the lookahead the rest of the pipeline exists
to prevent. `consensus_eps` returns None when the run is pinned, the whole
universe falls to one consistent basis, and `require_consensus` is ignored
(enforcing it would empty the screen).

### The backdated fallback

1. **Realised TTM growth, extrapolated one year** — arithmetic, not a forecast.
2. **Held flat** at trailing when there is no usable growth signal.

Under it `eps2 = eps1 x (1 + g)` with the same `g`, so eg1 and eg2 are one
number and only the eg1-only EG cases are meaningful. See
[EG-CASES.md](EG-CASES.md) §4.

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

### Without it, the EG taxonomy breaks (backdated runs)

Where consensus is unavailable — that is, on backdated runs — `eps2` is derived
as `eps1 x (1 + g)` with the same `g` that produced `eps1`, so
**eg1 and eg2 are the same number** (equal to ~1e-16 across all 155 candidates).
Every EG case that compares them was therefore decided by floating-point noise —
19 names labelled `acceleration` and 8 `worsening` on the 16th decimal place.
With a tolerance applied, the taxonomy collapses from eleven cases to three.
This is the most concrete cost of the missing consensus data. Full analysis and
four routes to fixing it: [EG-CASES.md](EG-CASES.md).

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

**Asked and answered.** This section used to say the ATR stop, range target and
R-score were kept deliberately, and invited the call to remove them. That call
was made once the book moved to options, and they are now gone too:
`stop_pct`, `target_pct`, `r_score` and `atrp` are off `PRMResult`, the ATR
maths is out of `ptm/formulas.py`, the `timing.rscore_tautology` audit check is
deleted, and the dead `[timing]` block and five unread `[prm]` keys are out of
the config. `ptm/timing_prm.py` is renamed **`ptm/risk.py`**, which after the
cut is beta plus the earnings-window helpers.

The reasoning: a stop distance on the underlying is not how a defined-risk
options position is managed, and the three numbers gated nothing and ranked
nothing — the repository's own audit had been reporting *"R-score is currently a
constant; it cannot rank ideas"* the entire time. `atrp` was read nowhere at all.

**What is kept:** `beta`, because `_rebalance_beta` swaps names in and out of the
book on it; and `size_fraction`, which is a stub returning 1.0 but is real
arithmetic in the weight calculation. Both live on an independent code path
inside `prm_for` and were untouched by the cut.

### Coverage: large groups used to be silently unreviewed

Asked to comment on all 137 names in one earnings window, the model returned 8
and stopped. The other 129 fell back to `"not covered by the group LLM pass"` —
204 placeholders across the run, 66% of every view. Worse, `ranked_tickers` was
padded with the unranked remainder, so a partial ranking read as a complete one.

Per-name views are now requested in chunks of `VIEW_CHUNK = 12`, with the
narrative as a separate synthesis pass over compact lines. Coverage went from
**34% to 100%** (307/308). Both numbers are recorded on the review and printed
in the markdown header — `LLM: yes — 33/33 names individually reviewed` — and a
partial ranking now says so rather than being padded into a fake one.

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
book. A third, a size floor on shorts, was tried and removed; see below.

### Sector cap

`[filters] max_per_sector = 2`, per side. Six shorts drawn from one sector is
one bet, not six, and nothing previously prevented it.

The cap is **not** relaxed to fill the book. Quietly topping up from a full
sector would make the setting meaningless and hide correlated risk, so the side
comes back short and `limit_breaches` records why:
`"short side held to 4 of 6 available by the 2-per-sector cap"`.

### Short size floor — added, then removed

`short_mcap_min` was set to $20bn with `short_max_below_mcap = 1`, on the
reasoning that small-cap shorts carry borrow, squeeze and liquidity risk large
caps do not. It cost more than it saved and is now **off** (`short_mcap_min = 0`,
`short_max_below_mcap` unset).

The failure was where the floor acted. `mcap_ok` is the **first key** in every
ranking function, so a floor did not merely cap how many small shorts entered
the book — it sorted *every* sub-floor short beneath *every* large cap
regardless of idea quality. With only **3 of 23** ready shorts clearing $20bn on
the last full run, the short side came back at 4 of 6 on every run, and the two
names the process actually liked best were unreachable.

Longs keep their band (`long_mcap_min`/`long_mcap_max`, $3-10bn) because hunting
that size is the process, not a risk control.

The machinery survives and is re-enabled by setting both values together:
`_pick(mcap_floor=..., max_below_floor=...)` in `ptm/book.py` still honours a
floor when handed one, `_rebalance_beta` still refuses to smuggle a sub-floor
name in via a beta swap, and both paths stay under test. What is gone is the
default, not the option.

**What this gives up.** Nothing now stops a short book of small caps, and the
engine models none of what that implies. Borrow cost and squeeze risk are the
usual objections, and they do not bind here — the book is expressed in options,
where there is no borrow to locate and no position to squeeze.

What does still bind is **options liquidity**, which the repository does not
look at anywhere. The first rebuild under this change put five of six shorts
under $20bn, two of them near $2bn, and a $2bn name can carry a thin chain,
wide spreads and sparse expiries whatever its fundamentals. Nothing upstream
checks that a tradeable contract exists at a sensible price, so it stays a
manual check on the short side.

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

## 5b. Directional revision momentum, not mispricing

The pipeline does not claim to identify true mispricings or estimate the move
needed to exceed live implied volatility. Its ranked signal is narrower and
measurable: analyst estimate revisions travelling in the direction the trade
needs, supported by filing direction and momentum durability. Live IV and trade
structure are assessed manually downstream.

### The verdict model was never shown the research pack

`qualitative()` is two passes. Pass A reads the 12 KB pack; pass B — the verdict
that produces `evidence_for` and every `impact_pct` — received only
`extract_summary`, roughly 1.5 KB of business line, plan, ≤6 KPIs and ≤4 quotes.
Its own system prompt told it to *"search the pack for the number that sizes
it."* **The pack was not there.** The model was being asked to find figures in a
document it had never been given, which is why most evidence came back
unquantified regardless of prompt wording.

`_sized_facts()` in `ptm/llm.py` now hands the verdict the figures directly:
sentences from the pack carrying a number and a unit, ordered **changes before
levels** because `impact_pct` is defined as a change ("revenue grew 9%" can size
a claim, "revenue was $87 million" cannot), led by the pack's pre-computed
`REPORTED CHANGES` block. Median 11 sized facts per pack, none empty across 202.
OGN — which returned **zero** quantified evidence and was rejected by both human
reviewers for exactly that — had 11 available, including "trailing EPS −34.6%".

### What is measured

`ptm/ingest/expectations.py` adds three non-option measures:

| Measure | Source | Answers |
|---|---|---|
| Estimate revisions | yfinance `eps_trend` / `eps_revisions` | which way consensus is moving |
| Past-print reaction | `prices.csv` + cached EDGAR report dates | how the stock reacted to recent reports |
| Surprise history | yfinance `earnings_history` | whether this name habitually beats |

Option-chain fields are not fetched into the directional payload and do not
gate, rank or create book breaches. Yahoo's chain is not reliable enough for
that job.

One caveat remains: filing dates are not release dates. Past-print reactions key off 10-K/10-Q
  filing dates, usually the same day as the 8-K for US issuers but not
  guaranteed. Only ~4 prints fall inside the one-year price window.

### Backdated runs get none of it

No revisions table or surprise history has a point-in-time archive. These
measures are refused when `is_backdated()`, exactly as `consensus_eps` already
is. **Live and backdated runs therefore see different evidence.** That asymmetry
is the cost of measuring revision momentum and is accepted deliberately:
`tests/test_backdate_lookahead.py` fails the build if the guard ever moves below
the fetch.

### Where it surfaces

Revision data appears under `extra.expectations.revisions`, in the deterministic
momentum payload, and in each idea's **Analyst revision momentum** section.
The qualitative schema deliberately has no `market_expectation`, `deviation`,
`priced_in` or model-estimated surprise fields.

---

## 6. Run time and concurrency

A full 1505-ticker run went from ~75 minutes to ~40. Where the time goes now:

| Stage | Before | After | How |
|---|---|---|---|
| EDGAR fundamentals (1505) | 40.6 min | **11 min** | 8 threads against one shared 8 req/s SEC budget |
| Idea generation (154) | ~33 min | **~26 min** | 4 concurrent ideas; capped by the LLM provider, not by us |
| Group cross-read | ~1 min | ~2 min | more calls, because coverage went from 34% to 100% |

### The SEC limiter

SEC publishes a ceiling of 10 requests/second for a declared User-Agent. Rather
than sleep between calls on a single thread, every SEC request now passes
through one process-wide token bucket (`ptm/ingest/edgar.py: sec_get`,
`SEC_MAX_RPS = 8`). Workers can be raised via `[edgar] workers` without changing
the request rate — the limiter, not the pool size, is the throttle.

### The LLM is the remaining bottleneck, and throttling is real

Running 5 ideas at once returned `429 Too Many Requests` on 4 of 12 ideas, and
each of those **silently lost its catalyst analysis** — which in the output is
indistinguishable from "no catalysts found". Concurrency without backoff is a
correctness bug, not a speedup.

`chat_json` now retries throttled calls with exponential backoff and jitter
(`RATE_LIMIT_RETRIES = 5`). The same benchmark then lost nothing, at 10.2s per
idea rather than 5.7s: the honest cost of staying inside the provider's budget.
`[llm] idea_workers` (default 4) tunes it; 1 restores fully sequential
behaviour.

### Run-to-run variability

`[llm] temperature` is **0.2** by choice. Be aware of the consequence: the same
inputs can produce different verdicts between runs, and it lands almost entirely
on the short side. Longs pass the qualitative gate ~92% of the time so noise
rarely flips one; shorts pass ~20%, so sampling noise moves names in and out of
a 6-slot book. Two runs of the same repo produced visibly different shorts and
near-identical longs for exactly this reason.

Set `temperature = 0.0` when you need two runs to be comparable — for example
when checking whether a code change moved the book, rather than the sampler.

### Where a backdated run spends its time

Caches are keyed by run date, so `--as-of` starts cold: ~11 min of EDGAR plus
~26 min of ideas. Re-running the *same* date afterwards is much faster, because
research packs and per-ticker extracts are already on disk.

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
temperature = 0.2                 # 0.0 if you need run-to-run comparability
idea_workers = 4                  # concurrent ideas; 1 = sequential

[edgar]
workers = 8                       # concurrent SEC fetchers, one shared 8 req/s budget
extract_max_age_days = 2          # cached XBRL extracts expire on live runs

[estimates]
enabled = true                    # analyst consensus EPS (yfinance), live runs only
min_analysts = 2                  # below this it is one opinion, not a consensus
max_age_days = 2
require_consensus = true          # no consensus -> excluded from screen and benchmark

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
