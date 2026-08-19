# EG cases: how a candidate is classified

The EG (earnings growth) case is the process's taxonomy of *what kind of trade
this is*. It is computed in `ptm/quant.py` and is now a hard filter: a name that
fits no case is not a candidate at all (`[filters] require_eg_case`).

**Live runs use analyst consensus and the full taxonomy works.** A name without
consensus is excluded from the screen entirely rather than estimated around —
see §4. Backdated runs cannot use consensus at all, and there the multi-year
cases are unreachable.

---

## 1. The inputs

| Symbol | Meaning | Where it comes from |
|---|---|---|
| `eps0` | trailing EPS | TTM diluted EPS from XBRL filings public on the run date |
| `eps1` | **year 1** forward EPS | analyst consensus FY1 (live; no consensus = not screenable). Backdated: `eps0 x (1 + g)` |
| `eps2` | **year 2** forward EPS | analyst consensus FY2 (live). Backdated: `eps1 x (1 + g)`, same `g` |
| `eg1` | year-1 growth | `earnings_growth(eps1, eps0)` |
| `eg2` | year-2 growth | `earnings_growth(eps2, eps1)` |
| `sector_eg1` | sector benchmark | **median** eg1 of screenable names in the sector |
| `pe1`, `pe2` | forward P/E | `price / eps1`, `price / eps2` |
| `peg1`, `peg2` | PEG | `pe / (eg x 100)`, only when `eg > 0` |

`earnings_growth(now, prev)` is `(now - prev) / abs(prev)`, with sign-flip cases
pinned to ±1.0 so a swing through zero cannot produce a nonsense ratio.

`sector_eg1` and `sector_pe1` are **medians**, taken only over names that are
themselves screenable: a positive, plausible P/E **and** analyst consensus. Using the mean put ~80% of the universe "below sector"
and skewed the book short; including loss-makers let a shrinking loss read as
+50% growth and lifted the bar for everyone else.

---

## 2. Long cases

Evaluated in order; the first match wins. `sector` below means `sector_eg1`.

| Case | Condition | What it means |
|---|---|---|
| `long_case_1_acceleration` | `eg1 > sector` and `eg2 > sector` and `eg2 > eg1 + tol` | Growing above sector **and speeding up**. The premium multiple is being grown into. |
| `long_case_2_stable_above` | `eg1 > sector` and `eg2 > sector` and `abs(eg2 - eg1) < 0.05` | Consistently above sector, flat trajectory. The classic quality compounder. |
| `long_case_3_decel_still_above` | `eg1 > sector` and `eg2 < eg1 - tol` and `eg2 > sector` | Still beating the sector but slowing. Premium is at risk if deceleration continues. |
| `long_case_4_6_opportunity_cost` | `eg1 > sector * 0.5` | Growing, but not enough to clearly beat the sector. Held only against what else the capital could do. |
| `long_case_7_10_turnaround` | `eg1 < 0 < eg2` | Currently shrinking, expected to inflect. The highest-variance long. |
| `long_non_ideal` | anything else | **Not a candidate.** Fits no pattern the process recognises. |
| `unknown` | `eg1 is None` | No usable growth figure. **Not a candidate.** |

## 3. Short cases

| Case | Condition | What it means |
|---|---|---|
| `short_case_1_worsening` | `eg1 < 0` and `eg2 < eg1 - tol` | Shrinking and **accelerating downward**. The cleanest short. |
| `short_case_2_decel_decline` | `eg1 < 0`, `eg2 < 0`, `eg2 > eg1 + tol` | Still shrinking but less badly. Decline is decelerating — a short with a shortening clock. |
| `short_case_3_4_xgrowth` | `eg1 >= 0` and `eg2 < 0` | Growth is expected to cross into decline. The market has not repriced it yet. |
| `short_case_5_turnaround_or_trap` | `eg1 < 0 < eg2` and `eg2 < sector` | Expected to inflect, but weakly. Either a value trap or an early turnaround — the riskiest short. |
| `short_below_sector` | `eg1 < sector` and `eg2 < sector` | Persistently growing slower than the sector. A relative short. |
| `short_non_ideal` | anything else | **Not a candidate.** |
| `unknown` | `eg1 is None` | **Not a candidate.** |

`tol` is `EG_TOLERANCE = 0.005` (0.5 percentage points) — see below.

---

## 4. Why eg2 must be an independent estimate

EDGAR contains no analyst consensus and never will — consensus is what analysts
*expect*, not what a company *filed*. Without it, `eps1` was extrapolated from
realised growth and `eps2` reused the same rate:

```
g    = TTM EPS / prior TTM EPS - 1        (clamped to +/-50%)
eps1 = eps0 * (1 + g)
eps2 = eps1 * (1 + g)                     <-- the SAME g
```

So `eg1 = g` and `eg2 = g`. Measured on the live universe at the time:
**eg1 == eg2 for all 155 candidates**, equal to within ~1e-16. Every case
comparing them compared a number with itself, decided by rounding:

```
eg1 = 0.21052631578947342
eg2 = 0.21052631578947376   ->  "eg2 > eg1"  ->  long_case_1_acceleration
```

That mislabelled 19 names as accelerating and 8 as worsening on the 16th decimal
place, while `long_case_3_decel_still_above` was unreachable. With
`EG_TOLERANCE = 0.005` guarding the comparisons, the taxonomy collapsed to three
reachable cases: `stable_above`, `below_sector`, `opportunity_cost`.

### Resolved for live runs

`ptm/ingest/estimates.py` supplies consensus FY1 and FY2 EPS, so eg1 and eg2 are
independent. On the live universe: **0 of 1405 names have eg1 == eg2**, and nine
cases populate rather than three.

| | Extrapolated | Consensus |
|---|---|---|
| eg1 == eg2 | 155 / 155 | **0 / 1405** |
| reachable cases | 3 | **9** |
| ROKU | one number | eg1 +3.94 -> eg2 +0.31 (real deceleration) |
| DASH | one number | eg1 +0.20 -> eg2 +0.74 (real acceleration) |
| ECHO | one number | eg1 +12.8 -> eg2 -0.60 (growth crossing into decline) |

Consensus covers **1416 of 1505 names (94%)**, fetched in about a minute.

### No consensus means not screenable, not estimated around

The 89 uncovered names are **excluded from the screen**, not fallen back on
(`[estimates] require_consensus`). Falling back would mix two accounting bases in
one screen:

| Group | median forward EPS / trailing EPS |
|---|---|
| consensus (adjusted) | **1.184** |
| extrapolated (GAAP) | **1.000** |

Consensus EPS is adjusted and sits ~18% above GAAP trailing, so a fallback name's
`pe1` is struck with a systematically smaller denominator. It looks expensive as
an artefact — VTR showed P/E 112.6 against a 29.6 sector median, most of it basis
mismatch, not valuation.

The second-order effect is worse: those names also sat **inside `sector_pe1`**,
the median every other name is judged against. Eighty-nine mismatched rows were
shifting the benchmark for fourteen hundred good ones.

Excluding them cost 4 candidates out of 210. They stay in
`yahoo_fundamentals.csv` with `forward_source` recorded, so you can see exactly
who was dropped and why; they are simply never candidates and never enter a
benchmark.

**Backdated runs are exempt.** Consensus is refused there, so the whole universe
is on one consistent extrapolated basis — internally comparable, even though eg2
collapses onto eg1 and only the three eg1-only cases carry information. Requiring
consensus would empty a backdated screen entirely.

### Basis discipline

Consensus EPS is normally adjusted/non-GAAP. Growth is therefore measured
against `yearAgoEps` from the *same* consensus table, never against EDGAR's GAAP
trailing EPS — mixing them produced AbbVie's fake 296% "growth". `trailing_pe`
stays EDGAR GAAP over the run-date close and is still exact.

Very large consensus growth (ECHO's +1280%, off a near-zero base) is left
unclamped because it is real reported consensus, not an artefact.
`candidate_warnings` flags any `|eg1| > 200%` as "law of small numbers" instead.

## 5. Remaining gap: backdated runs

Live runs are solved. Backdating still is not, because the free sources carry
only *current* estimates:

| Source | Forward years | History | Cost |
|---|---|---|---|
| **yfinance `earnings_estimate`** — in use | FY1 + FY2 | none | free |
| Financial Modeling Prep | several | some | ~$20-80/mo |
| Finnhub | several | limited | free tier / paid |
| Nasdaq Data Link (Zacks) | several | **vintages** | paid |
| I/B/E/S, FactSet, Capital IQ | several | **vintages** | institutional |

Only a vintage product stores what consensus *was* on a past date, which is what
a backdated run would need. Swap point is one function: `ptm/fundamentals.py:
row_for`.

A second option needs no vendor at all: derive two independent **realised**
growth rates from three TTM windows in EDGAR (`TTM/TTM-1` and `TTM-1/TTM-2`).
`eps_windows` already assembles two; a third is a small change. That would make
the eg2-vs-eg1 comparison real for backdated runs too — but backward-looking,
so "acceleration" would mean *has been* accelerating rather than *is expected
to*. A different claim, and it would need saying in the output.

## 6. What to trust today

* **`trailing_pe` is exact** — run-date close over EPS from filings public that
  day. No estimate anywhere in it.
* **On a live run** eg1, eg2, peg1 and peg2 are all real: two independent
  consensus estimates on a consistent adjusted basis, and every candidate has
  them, because a name without consensus never becomes a candidate. Every case
  is reachable.
* **On a backdated run** eg2 collapses onto eg1 and only the eg1-only cases
  (`stable_above`, `below_sector`, `opportunity_cost`) carry information. The run
  warnings say so, and `forward_source` on each row reads `extrapolated`,
  `extrapolated_clamped` or `flat`.
* **Mind the mix of trades.** With the taxonomy working, `turnaround` and
  `xgrowth` names reach research for the first time — genuinely higher-variance
  cases than `stable_above`. The qualitative pass rate fell from ~92% to ~65%
  accordingly, which is the gate doing its job on a harder mix, not a regression.

See [FEATURE-LIMITATIONS.md](FEATURE-LIMITATIONS.md) §1 for the forward-EPS
substitution in full.

---

## 7. Conviction: how the qualitative work orders the book

The EG case says *what kind of trade* this is. Conviction says *how well
evidenced* it is, and it is what orders names inside the book.

### Why it ranks ahead of eg1

Book selection order is `(mcap_ok, -ism_score, -conviction, +/-eg1)`. Size band
and ISM tilt still lead - liquidity and sector direction are the screen's
structural filters. But conviction sits **ahead of earnings growth**, because by
selection time every name has already cleared the P/E outlier screen, fits an EG
case and passed the qualitative gate, so eg1 is no longer separating good ideas
from bad. Worse, it is **not comparable across cases**. Measured on one run's 98
ready longs:

| EG case | n | eg1 median | range |
|---|---|---|---|
| `decel_still_above` | 25 | **+0.60** | +0.19 .. +5.32 |
| `turnaround` | 22 | **-0.39** | -0.79 .. -0.01 |
| `opportunity_cost` | 21 | +0.16 | +0.07 .. +1.06 |
| `acceleration` | 18 | +0.19 | +0.08 .. +0.81 |

A turnaround long has negative eg1 *by definition*. Sorting on eg1 buried all 22
turnarounds beneath every decel-still-above name for reasons that say nothing
about idea quality. eg1 still orders *within* a conviction level, where names
share an EG profile and the comparison is meaningful.

Disable with `[filters] qual_rank = false` to fall back to eg1 ordering.

### Reasons are weighed, not counted

Counting reasons made "backlog up 22%" and "management sounds confident"
identical, so a name with four vague reasons outranked one with two quantified
ones. Each evidence item now carries a magnitude:

```json
{"claim": "EPS guidance raised 25%", "metric": "adjusted EPS",
 "impact_pct": 25.0, "impact_on": "earnings", "quantified": true}
```

Weight is `BASE_WEIGHT + MAX_BONUS x magnitude x scope`:

| Term | Value | Why |
|---|---|---|
| `BASE_WEIGHT` | 1.0 | an unquantified but genuine reason - the old count behaviour |
| `MAX_BONUS` | 3.0 | most a single quantified claim can add |
| `IMPACT_CAP_PCT` | 30% | above this, size stops adding: a 300% figure off a near-zero base scores the same as 30% |
| scope | earnings 1.0, revenue 0.75, margin 0.5, other 0.25 | earnings accretion is what the screen trades; revenue is a step removed |

So one reason ranges 1.0 to 4.0, and `conviction = sum(for) - sum(against)`,
minus 1.0 if the verdict carried a **process** failure (`verdict_model_downgraded`,
`json_failed`, `contradicts_evidence`). Business risks do not dock conviction -
a red flag about tariffs is the analysis working.

### Invented numbers are refused

The prompt states that a magnitude may be given **only** when the research pack
contains it, and that a precise number the model invented is worse than none.
`_evidence_items` enforces it at parse time: `quantified` must be true *and*
`impact_pct` present, or the magnitude is stripped entirely. A model that sets
`quantified=false` while supplying a number loses the number.

### What this looks like in practice

POWL, from a live run:

| | Reason | Magnitude | Weight |
|---|---|---|---|
| for | Strong Backlog Growth | not quantified | 1.00 |
| for | High Book-to-Bill Ratio | not quantified | 1.00 |
| for | Record New Orders | not quantified | 1.00 |
| for | Accelerating Commercial Momentum | not quantified | 1.00 |
| against | Decline in Petrochemical Market Revenue | **-49.0% revenue** | **3.25** |

Counted, that is +4 -1 = **+3**, a strong long. Weighed, it is 4.00 - 3.25 =
**+0.75**. One hard number nearly cancels four assertions - which is the right
reading, since the only figure in the filing pointed the other way.

Around 85% of evidence comes back unquantified, because most packs simply do not
state a percentage and the model is forbidden from inventing one. Those items
score exactly as they did under counting, so nothing is lost; the weighting bites
on the minority of claims that carry a number, and POWL shows that can flip a
name.

### Where to find it

Every idea's JSON carries `extra.conviction` and `extra.conviction_detail`, the
latter holding each reason with its magnitude, scope and earned weight, the
running totals, and the scale used - so the number that ordered the book can be
checked rather than trusted. The same table is rendered in each idea's markdown
under **Qualitative**.

### Two limits worth knowing

The magnitude is what the *filing* reported, not the impact on the *thesis*.
POWL's -49% is one segment, and nothing sizes it against total revenue.

And it cannot tell a 25% figure the market already expects from one it does not.
Both would need the model to reason about materiality against a base, which is
not something to trust without testing it first.
