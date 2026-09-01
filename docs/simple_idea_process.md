# PTM-simple — theme-first idea process (v2)

Reverse-engineered from `John pre mentoring starterpack.xlsx`, revised per
John: **no options structuring** (yfinance options data is not accurate),
**no price targets**, **no technicals or price action anywhere**, themes are
the unit of analysis, and the **qualitative deep dive is kept**.

Supersedes v1 (the calendar-spread variant). Changelog at the bottom.

---

## 1. What the starter pack contributes (and what we keep)

- **Master watchlist**: ~300 names clustered into ~88 *themes* — stories,
  not GICS ("Optical Networking", "AI Power and Grid Expansion", "Cloud
  data Infrastructure", "Semi testing/Packaging"). This becomes the theme
  map — the pipeline's primary axis.
- **GATEKEEPING**: five questions on a 2-4 month horizon. We keep them,
  reworded where they referenced price/technicals:
  1. **WHY NOW?** — what activated the theme? (graded GREAT / GOOD / NONE;
     price-only activation is TOURISM → rejected)
  2. **FULL POSITION OR SCALE** — an execution plan, not a vibe.
  3. **AM I EARLY OR LATE?** — measured without price (see §4).
  4. **AM I GETTING PAID IF I'M RIGHT?** — reframed as an estimate-impact
     test, NOT a price target (see §2, gate 3).
  5. **AM I LISTENING TO THE MARKET?** — estimate breadth and filings
     direction, not price action.
- **Actionable Watchlist**: names that fail a gate park per theme; they
  re-queue when the theme activates. Nothing dies.
- **Realised ledger**: win %, R, Kelly on closed ideas — the process's own
  scorecard.

## 2. The pipeline

```
theme map (static, maintained)
      │
      ▼
WEEKLY THEME RADAR — is any theme activating?        (deterministic + 1 LLM call)
      │  activated themes (usually 0-2 of 88)
      ▼
TICKER SELECTION inside the theme                    (deterministic ranking)
      │  shortlist: 2-5 names
      ▼
DEEP DIVE — kept, scoped to the shortlist            (the existing engine)
      │
      ▼
GATEKEEPING — why-now / early-late / getting-paid    (deterministic)
      │
      ├── pass → structured idea → capped book
      └── fail → parked on the theme watchlist
```

### Stage 0 — Theme map
A small static file: `theme → [tickers]`, seeded from the starter pack's
clusters (typo-normalised), each with a one-line thesis. Maintained by
hand, weekly — new tickers join when the news justifies it, dead themes
retire. ~88 themes × ~5-15 names. Everything downstream reads this file.

### Stage 1 — Weekly theme radar (the "when might it take off" problem)
One pass per theme per week, all deterministic except one call:
- **Revision breadth**: % of theme names with FY1 EPS estimates moving up
  over 30d (PTM's expectations data, aggregated). A theme move shows up as
  *breadth*, not as one name — that is the single best early signal, and
  PTM already computes it per name.
- **Activation count**: how many theme names had company-specific news in
  the last 2-3 weeks (guidance moves, contracts, product launches, M&A).
  One cheap LLM call per week scans headlines for the *whole theme* and
  grades events GREAT / GOOD / NONE.
- **Bellwether calendar**: which theme anchor prints in the next 2 weeks
  (TSM in foundry, AVGO in custom silicon…). A bellwether print is the
  theme's information event — the natural window for the whole cluster.
- **ISM / sector data direction** and **filings direction** across members
  (PTM has both per name).

Theme activation = breadth rising + clustered activations + a dated
catalyst ahead. Output per theme: `ACTIVE / WARM / COLD` + the why-now
grade + the activation events. Zero price input.

### Stage 2 — Ticker selection inside an activated theme
Deterministic ranking of theme members, no LLM:
1. **Revenue exposure** — does the name actually sell into the theme
   (industry/segment tags; refined over time from filings)?
2. **Revision momentum** — its own 30d/90d estimate direction (PTM has it).
3. **Cluster divergence** — peers revising up while the name lags = the
   "know more than the market" long candidate; revising down while the
   theme rises = the short candidate.
4. **Catalyst timing** — its next print inside the window; the bellwether
   already printed or printing this week.
5. **Durability basics** — net cash, margin trend (fundamentals only).

Deep dive the top **2-5** names — and only those. This is the big saving:
the dive engine runs on a shortlist, not on a 197-name screen.

### Stage 3 — Deep dive (kept as-is, scoped by the theme)
The existing engine runs unchanged — findings, debate, synthesis
scorecard, adapter — with one addition to the prompt: the theme activation
context ("theme X activated: <events>; your job is to test whether THIS
name expresses it — revenue exposure, position, capacity to deliver").
The dive verdict now answers two gatekeeping questions directly: does the
name's own case corroborate the theme, and is it quantified enough to
matter.

### Stage 4 — Gatekeeping (no technicals, no price action, no price targets)
1. **Why now** — the theme's graded activation + the dive's corroboration.
2. **Early or late, without price** — where the name sits in the theme's
   revision cycle: revisions just turning up and the bellwether not yet
   printed = EARLY (good); most peers already printed post-revision and
   the move in estimates is old = LATE → park.
3. **Getting paid, without price targets** — estimate-impact test: are the
   dive's quantified reasons large *relative to the consensus base*? A $2B
   contract is noise for a $30B-revenue company and a thesis for a $500M
   one. The verifier already demands real magnitudes; this gate only asks
   whether they are big enough to move estimates materially.
4. **Listening to the market** — cluster breadth + filings direction must
   not point against the idea (the existing revision-veto, applied at
   theme level).

### Stage 5 — Idea file, book, realised loop
One-page idea per survivor: theme + activation events, the dive scorecard
(unchanged), the divergence argument, the estimate-impact test. Book =
survivors ranked by theme strength, sector-capped (2/side). Closed ideas
log into the Realised sheet (win %, R, Kelly) shown next to the live book
in the viewer.

## 3. Why this is genuinely simpler

- **The entry filter is a story, not a screen.** No PE-outlier scan, no
  88-gate funnel; theme membership + activation decides who gets analysed.
- **The group review is replaced.** The theme radar IS the cross-sectional
  read — it runs weekly over clusters before any dive, not after.
- **LLM budget collapses**: 1-2 calls per week for the radar (per theme,
  not per name) + 2-5 full dives on shortlisted names. A typical week is
  ~10 LLM calls, not ~800.
- **Everything decision-relevant is measured, not forecast**: revision
  breadth, filings direction, ISM, print calendar. No technicals, no price
  targets, no options data.

## 4. Honest risks

- **Theme map staleness**: the xlsx taxonomy has typos and will age; themes
  evolve. Needs a light weekly maintenance touch, and a rule for renaming/
  retiring clusters.
- **No price anchor at all**: without price targets, discipline rests on
  the estimate-impact test and the realised ledger. That is a real loss of
  anchoring — the compensating control is that "getting paid" still demands
  a number (magnitude vs consensus), just not a price.
- **Revenue exposure is the weak data point**: yfinance industry tags are
  coarse; segment revenue needs filings parsing. Start with tags + manual
  curation per theme; refine only where the theme is live.
- **Breadth signals lag at inflections**: revision breadth is backward-
  looking; the bellwether calendar is what makes it forward-looking. When
  in doubt, park — the watchlist is free.

## 5. Build order

1. Theme map file + member normalisation (deterministic; reuses ingest).
2. Theme radar: breadth + print calendar + ISM (deterministic viewer tab).
3. Weekly why-now theme call (the one LLM stage) + parked watchlist.
4. Deep-dive scoping: theme context in the prompt; shortlist selection.
5. Gatekeeping pass (estimate-impact + early/late) + idea file + Realised
   ledger + viewer page.
6. Run both generators 2-3 weeks; compare against the audit trail.

---

*Changelog*: v1 (superseded) used the starter pack's calendar-spread
structuring with IV/payoff math; dropped because yfinance options data is
not accurate, and price-target computation was dropped with it. v2 keeps
the deep dive, replaces the group review with the theme radar, and trades
equity ideas around dated catalysts with no price or technical input.