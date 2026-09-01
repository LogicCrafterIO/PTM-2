# PTM Simple — earnings-catalyst idea process (from the John pre-mentoring starterpack)

A deliberately simpler idea-generation process, reverse-engineered from
`John pre mentoring starterpack.xlsx`. It replaces the current
screen → macro → deep-dive → gates → group-review → book chain for a
specific job: **trading the next earnings**, the way the 4Pillar starter
pack teaches it. The existing PTM process stays untouched; this is a plan
for a second, lighter generator.

---

## 1. What the starter pack actually does (evidence from the sheets)

**Master watchlist** — ~300 names clustered into *themes, not GICS*: "AI
Semiconductor chips", "Optical Networking", "Cloud data Infrastructure",
"Cybersecurity", "AI advertising"… Each cluster is a story with its member
tickers. Themes carry the thesis; names are just the tradable expressions.

**Portfolio overview** — a sector × CORE/BIAS long-short tilt grid, a
"forward looking" market-observation habit ("look at a handful of
competitors to see what the subsector is doing"), and a *weekly refresh*
of the names worth watching (week-2 list: MU, CRS, CAVA, QTWO, PDFS, MELI,
PEN, SPOT…). The watchlist is alive, not an annual artifact.

**pre session / Structuring** — every trade is an **options calendar
spread around a dated earnings catalyst**:
- `NEXT EARNINGS` is a first-class column on every row (CLS 2026-10-26,
  AMD 2026-11-03, NOW 2026-10-28…).
- Long leg: CALL/PUT expiring *after* the print (NOW: Oct-16 $125 call vs
  the Oct-28 print), strike written toward the **price target** (NOW $145
  vs last $117.35; WING $90 vs $117.20).
- Short leg: the *near-dated same-strike* option, whose premium finances
  the long leg — you're selling the front-month premium to own the
  catalyst month. IV and time value are tracked per leg.
- P/L and RETURN computed per structure (the sheet's worked example shows
  +100% return on the NOW spread).

**GATEKEEPING** — the whole philosophy in five questions on a 2–4 month
horizon:
1. **WHY NOW?** — GRADED: GREAT (stock-specific news activating the
   watchlist name), GOOD (strong sector-specific catalyst), GREAT (genuine
   macro event), TOURISM (short-term price moves — rejected).
2. **FULL POSITION OR SCALE** — follow an execution plan.
3. **AM I EARLY OR LATE?** — "don't be late; better to be patient — back
   on the ACTIONABLE WATCHLIST."
4. **AM I GETTING PAID IF I'M RIGHT?** — "need a probable pathway to 200%
   return with quant-based sensible price target."
5. **AM I LISTENING TO THE MARKET PROPERLY?** — real signs away from the
   noise.

And the anti-patterns it names explicitly: years-long 50-page reports
nobody reads, screen jockeys "pretending they have a clue about 2028 EPS
growth", retail day-horizon momentum. The analyst's edge is *depth*, the
trader's edge is *timing* — this process buys timing with a checklist and
spends the research budget only where a catalyst justifies it.

**Actionable Watchlist** — "your next best trades — kept live once the
book is running": long and short candidate columns per sector. Failed
names don't die; they park here until a catalyst activates them.

**Realised** — closed-trade ledger with win %, R, Kelly: the process eats
its own cooking and measures the feed-back loop.

---

## 2. The PTM-simple pipeline (5 steps, one LLM call per candidate)

```
themed watchlist  →  catalyst queue  →  WHY-NOW check  →  payoff gate  →  structured idea
   (reuse screen)      (earnings date)     (1 LLM call)     (deterministic)    (spread + file)
                                                        ↘ rejected → Actionable Watchlist
```

### Stage 0 — Theme-clustered watchlist
Keep the existing screened universe and its fundamentals/consensus
ingestion, but tag every name with a **theme cluster** (the starter pack's
~30 stories: optical networking, cloud data, cyber, AI advertising, power
& grid, nuclear…). Themes are a small static mapping file — not analysis.
PTM's ISM tilt and sector data stay available as backdrop; nothing here
needs the macro dashboard to gate anything.

### Stage 1 — Catalyst queue (replaces the P/E-outlier screen as the organizer)
Every name enters the queue anchored on its **next earnings date**
(PTM already computes dated + estimated prints and buckets them
0-30/31-60/61-90d). Optional cheap quant pre-filters, all deterministic:
- dated print inside the window;
- measurable estimate-revision direction (PTM's expectations data);
- a reaction history (avg |move| per print) so the payoff math has inputs.

A name that fails only the *data* checks parks on the Actionable Watchlist
as "data-thin" rather than being rejected.

### Stage 2 — WHY-NOW check (replaces the deep dive — ONE small LLM call)
For each queued candidate, one structured call with the last ~3 weeks of
stock-specific headlines (PTM's web search, capped), the sector move, and
the macro event list. Output:
- `why_now`: GREAT (company-specific activation — guidance move, contract,
  product, M&A, filing) / GOOD (sector-wide catalyst) / NONE (price action
  only = TOURISM);
- up to **three** quantified, headline-cited reasons (magnitude required —
  the existing quantified-honesty verifier applies verbatim);
- one-line thesis.

No debate rounds, no driver scores, no scorecard. The qual bar is the
checklist, not a dossier. `NONE` never becomes an idea — it parks.

### Stage 3 — Payoff gate (deterministic, the 200% rule)
- **Sensible price target**: consensus target + the revision-implied move;
  sanity-banded against the name's own reaction history (avg |move| per
  print ±σ). "Quant-based" = it must reconcile with measured data.
- **Probable pathway to ~200%** on the *structure* (not the stock): using
  the front/back IV from the options data, does the average historical
  earnings move move the spread's long leg ≥ ~2× net debit? If the math
  can't get there, reject — the market is not paying you.
- **Early-or-late**: print < 5 trading days away and the activation news
  is > 10 days old → late → Actionable Watchlist (re-check next catalyst).

### Stage 4 — Idea file + book (the Structuring sheet, mechanical)
Each survivor writes a one-page idea: ticker, print date, direction,
**calendar-spread structure** (long option past the print, short front
same-strike, target strikes from the price target), the why-now grade with
its three quantified reasons, the payoff math, and the execution note
(full/scale). The book is the Actionable Watchlist sorted by payoff ratio
with a per-sector cap — no beta swaps, no conviction arithmetic, no
per-window books. Sector caps (2/side) and a light gross cap are the only
portfolio constraints, mirroring the starter pack's CORE/BIAS grid.

### Stage 5 — Realised loop
Log every closed structure (entry/exit, days, P/L, R); the viewer shows
win %, average R and Kelly on the same page as the live book. The
feedback loop is the process's scorecard.

---

## 3. What this changes vs the current PTM process

| | PTM current | PTM simple |
|---|---|---|
| Organizer | P/E-outlier screen | Next-earnings catalyst queue |
| Qualitative | 4-6 web-search dives/debates + synthesis + adapter (~4-6 LLM calls/name) | One why-now checklist call (~1/name) |
| Verdict | Evidence score S, weighted pillars, stance | Graded WHY-NOW + 3 quantified reasons |
| Decision layer | Gates + group reviews + books | Three gates: why-now / payoff / early-or-late |
| Instrument | Long/short equity book | Calendar spreads around the print |
| Rejections | qual_fail (88 last run) | → Actionable Watchlist (parked, not dead) |
| Feedback | Audit | Realised ledger (win%, R, Kelly) |

**LLM budget:** ~1 small call per queued candidate + zero per parked name,
vs a dive's full ladder — roughly an 80% cut on a typical week, and the
weekly-usage ceiling stops being the binding constraint it was.

## 4. Honest risks (what the complexity was buying)

- **No evidence dossier**: the why-now call cites headlines, not a
  source-cited dive. The 3-quantified-reasons rule plus the verbatim-number
  verifier is the honesty floor; it is weaker than the dive's audit trail.
- **No bull/bear debate**: single-side conviction by design — the payoff
  gate and the parked-watchlist are the safety nets, not debate.
- **Options carry risks equity ideas don't**: IV crush, pin risk, spread
  slippage. The Structuring sheet prices IV explicitly; the plan must
  ingest IV per leg or the 200% math is fiction.
- **The why-now grade is one LLM judgment**: keep the same
  quantified-verification discipline (magnitude must appear in the cited
  headline) so the checklist can't invent activation.

## 5. Suggested build order

1. Theme map + catalyst queue over the existing universe (deterministic;
   reuses ingest + earnings data). *Viewer: a "Queue" tab.*
2. Why-now checklist call + Actionable Watchlist writer (the one LLM
   stage). *Viewer: parked names visible per sector.*
3. Payoff gate with reaction history + IV (deterministic; needs an IV
   source for the two legs).
4. Structured idea file + Realised ledger + viewer page.
5. Run BOTH generators for 2-3 weeks; compare realized P/L and the audit
   trail before deciding which one earns the compute budget.