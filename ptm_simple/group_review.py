"""Group review for the simple process: is each valuation flag justified?

The table's three columns are THREE INDEPENDENT LAYERS, derived from three
different inputs — none of them from each other:

- SIDE (long/short/neutral) comes from the name's OWN 90d estimate revisions:
  rev90 > +0.5% -> long, < -0.5% -> short, else neutral — the same hard
  eligibility rule as analyze-all's coverage reports and the book's selection.
  The flag is never consulted for the side.
- FLAG (premium/discount/mixed/fair) comes from the quant table: the name's
  P/E and PEG versus ITS THEME'S median (quant.py `_flag_rows`). It says where
  the name sits relative to peers, nothing about direction.
- VERDICT (justified / not justified / uncertain) is the LLM's judgment of the
  FLAG against the print-focused forward case. It evaluates the market's
  pricing, not the trade: "not justified" on a PREMIUM means the forward case
  does not support paying the multiple (bearish fact, textbook-short setup);
  "not justified" on a DISCOUNT means the market's cheapness looks wrong — the
  deterioration is transitory or the catalysts contradict it (bullish fact,
  textbook-long setup). So discount -> short is NOT the mapping: the typical
  long is long+discount with a "not justified" discount, and the typical short
  is short+premium with a "not justified" premium.

One LLM pass per non-COLD theme, run AFTER the coverage reports exist. The
packet per member is built from the PRINT-FOCUSED qual (print_qual.py) — the
fresh EDGAR research pack, the name's own estimate direction, consensus numbers,
the theme-relative flag — deliberately NOT the deep dive, which is a
backward-looking artifact that can lag the calendar. The model judges whether
each member's premium/discount is JUSTIFIED by what the next print and the
following quarter(s) will reveal.

This is the opposite of ptm/group_review.py on purpose: that layer reviews the
main process's ideas with valuation excluded (the P/E outlier was the screen's
own premise); here the flag is the THING UNDER REVIEW, built in quant.py as a
pointer and judged here against the print-focused qual. It is still commentary,
not a gate — nothing downstream reads a review to include or drop a name.

Without an LLM the pass degrades to the deterministic packet rendered as
markdown, marked unjudged. Output: per-theme markdown beside the coverage
reports (ideas/simple/<theme>/_GROUP_REVIEW_<date>.md, which also carries each
member's next-print brief) and one aggregate JSON
(data/simple/group_review_<date>.json) the viewer reads.
"""
from __future__ import annotations

import json
from datetime import date

from ptm.llm import JSON_HINT, chat_json, llm_available
from ptm.log import log
from ptm_simple import simple_dir

_SYSTEM = (
    "You are a long/short portfolio manager reviewing the covered members of ONE equity theme "
    "against each other, around their next earnings prints. Each member carries a theme-relative valuation "
    "FLAG (premium/discount/mixed/fair: its P/E and PEG versus the theme median) and a print-focused "
    "forward case (what the next print will reveal, which KPIs decide the trade, filed guidance and "
    "catalysts). Your one job: judge whether each member's flag is JUSTIFIED by that forward case — what "
    "the next 1-2 quarters and the 2-4 month trade horizon reveal: guidance, backlog/bookings, margins, "
    "volume or pricing, dated events, peer-print read-throughs. Rules: a premium is justified when the "
    "forward case grows into it and unjustified when the catalysts point the other way; a discount is "
    "justified when the deterioration is real and durable and unjustified when it is transitory or the "
    "catalysts contradict it. The SIDE and the FLAG are independent inputs — side from the name's own "
    "revisions, flag from valuation versus the theme — and the verdict judges the FLAG, not the side: an "
    "unjustified discount on a long is bullish (the market's cheapness is wrong), an unjustified premium "
    "on a short is bullish for that short. PERIOD DISCIPLINE: today's date is given; quarters that already ended are "
    "the factual base, never an open question. Never invent a number that is not given. No price targets, "
    "no technicals, no price action. The flag ratios are the input under test — do not justify a flag BY "
    "the multiple itself ('it's expensive because it trades high') but by the fundamentals and catalysts. "
    "Cross-read the members too: name when two of them rest on the same driver or contradict each other. "
    "Return exactly one entry per ticker. Keep every reason under 300 characters. " + JSON_HINT
)


def _trade_tag(side: str | None, flag: str | None, verdict: str) -> str:
    """Deterministic side×flag×verdict consistency — pure logic, no LLM.

    aligned:      the verdict AGREES with the side's premise —
                  long + (premium justified | discount not justified), or
                  short + (premium not justified | discount justified).
    contradicted: the mirror combinations — the verdict argues against the side
                  (long + premium not justified, long + discount justified, ...).
    neutral:      fair/mixed flags, neutral sides, uncertain verdicts, no flag.

    The four aligned combinations are the trade candidates: "the market is
    wrong" (not justified on the side's flag) and "the market is right, ride
    it" (justified premium for a long, justified discount for a short)."""
    if not side or side == "neutral" or not flag or flag == "n/a" or verdict == "uncertain":
        return "neutral"
    if flag not in ("premium", "discount"):
        return "neutral"  # fair/mixed never picks a side
    premium = flag == "premium"
    if verdict == "justified":
        return "aligned" if (side == "long") == premium else "contradicted"
    if verdict == "not justified":
        return "aligned" if (side == "long") != premium else "contradicted"
    return "neutral"


def _member_packet(ticker: str, side: str | None, qrow: dict, pq: dict | None, member: dict) -> dict:
    """Compact print-focused packet for one member — fresh inputs only, no dive."""
    from ptm_simple.brief import _reported_quarter

    row = {
        "ticker": ticker,
        "side": side or "neutral",
        "rev90_pct": qrow.get("rev90") or member.get("rev90"),
        "analysts_up30_down30": [member.get("up30"), member.get("down30")],
        "next_print": qrow.get("earnings_date") or member.get("earnings_date"),
        "days_to_print": qrow.get("days_to_print") if qrow.get("days_to_print") is not None else member.get("days_to_print"),
        "reports_quarter": _reported_quarter(qrow.get("earnings_date") or member.get("earnings_date")),
        "flag": qrow.get("flag"),
        "flag_detail": qrow.get("flag_detail"),
        "consensus": {
            "eps1": qrow.get("eps1"), "eps2": qrow.get("eps2"),
            "eg1": qrow.get("eg1"), "eg2": qrow.get("eg2"),
            "pe1": qrow.get("pe1"), "peg1": qrow.get("peg1"), "ps": qrow.get("ps"),
        },
    }
    if pq:
        if pq.get("points"):
            row["next_print_case"] = [p[:220] for p in pq["points"][:5]]
        if pq.get("watch"):
            row["kpis_that_decide"] = [w[:120] for w in pq["watch"][:4]]
    return row


def _printqual_md(theme_row: dict, packet: dict, pq: dict | None, ref: date):
    """One per-ticker print-qual markdown, beside the coverage reports.

    Every reviewed member gets one — including flat/no-side names, which have
    no dive-based coverage report but now have a print-focused qual artifact."""
    from ptm_simple import simple_ideas_dir

    ticker = packet["ticker"]
    side = packet["side"]
    lines = [
        f"# Print qual — {ticker} ({side})\n",
        f"*Theme-first simple process · {ref.isoformat()} · dive-free and print-focused: what the next "
        f"print reveals for the flag call — fresh EDGAR pack, bounded web search, consensus. Not the deep "
        f"dive, not a gate.*\n",
        f"**Theme**: {theme_row.get('theme')} — {theme_row.get('status')}, lean {theme_row.get('lean')}",
        f"**Valuation flag (vs theme)**: {packet.get('flag') or 'n/a'}"
        + (f" — {packet.get('flag_detail')}" if packet.get("flag_detail") else ""),
        f"**Next print**: {packet.get('next_print') or 'unknown'}"
        + (f" — reports {packet['reports_quarter']}" if packet.get("reports_quarter") else "")
        + (f" · in {packet['days_to_print']} days" if packet.get("days_to_print") is not None else ""),
    ]
    if isinstance(packet.get("rev90_pct"), (int, float)):
        lines.append(f"**Side**: {side} (own 90d revisions {packet['rev90_pct']:+.2f}%)")
    else:
        lines.append(f"**Side**: {side}")
    cons_bits = [f"{k} {v}" for k, v in (packet.get("consensus") or {}).items() if v is not None]
    if cons_bits:
        lines.append(f"**Consensus**: " + ", ".join(cons_bits))
    lines.append("")
    if pq:
        watch = pq.get("watch") or []
        if watch:
            lines.append("## Watch — the KPIs that decide the trade")
            lines += [f"- {w}" for w in watch]
            lines.append("")
        points = pq.get("points") or []
        if points:
            lines.append("## What the next print will reveal")
            lines += [f"- {p}" for p in points]
            lines.append("")
    else:
        lines.append("_(no print brief — no research pack or LLM unavailable)_")
        lines.append("")
    lines.append("*Sources: research pack (EDGAR), bounded web-search snippets, consensus cache — never the deep dive.*")
    theme_dir = simple_ideas_dir(str(theme_row["theme"]).replace("/", "-").replace(" ", "_"))
    path = theme_dir / f"printqual_{ticker}_{ref.isoformat()}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _review_prompt(theme_row: dict, packets: list[dict], ref: date) -> tuple[str, str]:
    theme = theme_row["theme"]
    user = (
        "Return JSON keys: summary (one line on what this theme's flags collectively look like when "
        "judged against the forward cases), reviews (array of {ticker, verdict, reason} — verdict is "
        "exactly one of: justified, not justified, uncertain).\n"
        f"Today: {ref.isoformat()}\n"
        f"Theme: {theme} — status {theme_row.get('status')}, lean {theme_row.get('lean')} "
        f"(breadth {theme_row.get('breadth', 0):+.2f}; share of covered members revising up minus down over 90d)\n"
        + (f"Theme thesis: {str(theme_row.get('thesis') or '')[:300]}\n" if theme_row.get("thesis") else "")
        + (f"Bellwether printing within 14 days: {theme_row.get('bellwether')}\n" if theme_row.get("bellwether") else "")
        + f"Members ({len(packets)}):\n{json.dumps(packets, default=str)[:12000]}"
    )
    return _SYSTEM, user


def review_theme(theme_row: dict, quant_by_ticker: dict[str, dict], ref: date) -> dict:
    """One theme's group review: print-focused packets -> one LLM call -> {theme, summary, reviews}.

    Every member with something to judge is included: directional names take the
    side their own revisions imply, flat/no-side names go in side-neutral (the
    print brief asks what would CREATE a side), and a member is skipped only
    when it has neither revision data nor a valuation flag to judge."""
    from ptm_simple import simple_ideas_dir
    from ptm_simple.print_qual import print_brief

    theme = theme_row["theme"]
    members = theme_row.get("members") or []
    peer_prints = [
        {"ticker": m["ticker"], "earnings_date": m.get("earnings_date"), "days_to_print": m.get("days_to_print")}
        for m in members
        if m.get("days_to_print") is not None and 0 <= m["days_to_print"] <= 120
    ]
    packets = []
    skipped = []
    print_focus: dict[str, dict] = {}
    pq_paths: dict[str, str] = {}
    for m in members:
        ticker = m["ticker"]
        qrow = quant_by_ticker.get(ticker) or {}
        rev = qrow.get("rev90") or m.get("rev90")
        # Side is derived from the name's OWN revisions only — never from the
        # flag (see the module docstring for how the three layers relate).
        side = "long" if (rev or 0) > 0.5 else "short" if (rev or 0) < -0.5 else None
        flagged = qrow.get("flag") not in (None, "n/a")
        if not m.get("covered") and rev is None and not flagged:
            skipped.append(ticker)  # nothing at all to judge: no data, no flag
            continue
        pq = print_brief(ticker, side, m, qrow, theme_row, peer_prints, ref)
        print_focus[ticker] = pq or {}
        packet = _member_packet(ticker, side, qrow, pq, m)
        packets.append(packet)
        try:
            pq_path = _printqual_md(theme_row, packet, pq, ref)
            pq_paths[ticker] = str(pq_path.relative_to(simple_ideas_dir()))
        except Exception as exc:
            log(f"group review {theme}: printqual md {ticker} failed: {str(exc)[:80]}")
    out = {
        "theme": theme,
        "status": theme_row.get("status"),
        "lean": theme_row.get("lean"),
        "breadth": theme_row.get("breadth"),
        "members_reviewed": len(packets),
        "members_skipped_flat": skipped,
        "reviews": [],
        "print_focus": print_focus,
        "summary": "",
        "llm_used": False,
    }
    if not packets:
        out["summary"] = "no members with data or a flag to review"
        return out

    def _row(p: dict, verdict: str, reason: str) -> dict:
        return {
            "ticker": p["ticker"], "side": p["side"], "flag": p["flag"], "verdict": verdict,
            "reason": reason, "trade": _trade_tag(p["side"], p["flag"], verdict),
            "watch": (print_focus.get(p["ticker"]) or {}).get("watch") or [],
            "printqual": pq_paths.get(p["ticker"], ""),
        }

    if not llm_available():
        out["summary"] = "LLM unavailable — flags rendered unjudged"
        out["reviews"] = [
            _row(p, "uncertain", "no LLM pass — see the member's print qual or coverage report")
            for p in packets
        ]
        return out
    try:
        payload = chat_json(*_review_prompt(theme_row, packets, ref))
    except Exception as exc:
        log(f"group review {theme}: FAIL {str(exc)[:120]}")
        out["summary"] = "LLM call failed — flags rendered unjudged"
        out["reviews"] = [
            _row(p, "uncertain", "review call failed — see the member's print qual or coverage report")
            for p in packets
        ]
        return out
    out["llm_used"] = True
    out["summary"] = str(payload.get("summary") or "").strip()[:300]
    by_ticker = {p["ticker"]: p for p in packets}
    seen = set()
    for item in payload.get("reviews") or []:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        if ticker not in by_ticker or ticker in seen:
            continue
        seen.add(ticker)
        verdict = str(item.get("verdict") or "uncertain").strip().lower()
        if verdict not in ("justified", "not justified", "uncertain"):
            verdict = "uncertain"
        out["reviews"].append(_row(by_ticker[ticker], verdict, str(item.get("reason") or "").strip()[:300]))
    for p in packets:  # coverage: a member the model skipped is recorded, not lost
        if p["ticker"] not in seen:
            out["reviews"].append(
                _row(p, "uncertain", "not covered by the review pass — see the member's print qual or coverage report"))
    log(f"group review {theme}: {len(out['reviews'])} member(s) judged")
    return out


def _review_md(rev: dict, ref: date) -> str:
    """The per-theme markdown, written beside the coverage reports."""
    from ptm_simple import simple_ideas_dir

    lines = [
        f"# Group review — {rev['theme']}\n",
        f"*Theme-first simple process · {ref.isoformat()} · one pass over the covered members: is each "
        f"theme-relative valuation flag justified by the PRINT-FOCUSED forward case (fresh EDGAR filings, "
        f"guidance, consensus revisions, dated catalysts)? Commentary, not a gate.*\n",
        f"**Theme**: {rev.get('status', 'n/a')}, lean {rev.get('lean', '?')} "
        f"(breadth {rev.get('breadth', 0):+.2f}) · reviewed {rev.get('members_reviewed', 0)} member(s)"
        + (f" · no data, skipped: {', '.join(rev['members_skipped_flat'])}" if rev.get("members_skipped_flat") else ""),
        "",
        f"**Summary**: {rev.get('summary') or '(none)'}",
        "",
        "| Ticker | Side | Flag (vs theme) | Verdict | Idea | Why |",
        "|---|---|---|---|---|---|",
    ]
    idea_mark = {"aligned": "✅", "contradicted": "⛔", "neutral": "—"}
    for r in rev.get("reviews", []):
        mark = {"justified": "✅", "not justified": "❌", "uncertain": "❔"}.get(r["verdict"], "❔")
        lines.append(
            f"| **{r['ticker']}** | {r.get('side', '')} | {r.get('flag', 'n/a')} | {mark} {r['verdict']} | "
            f"{idea_mark.get(r.get('trade', 'neutral'), '—')} | "
            f"{str(r.get('reason', '')).replace('|', '/')} |"
        )
    focus = rev.get("print_focus") or {}
    if focus:
        lines += ["", "## Next-print focus (per member)", ""]
        for ticker, pq in focus.items():
            if not pq:
                lines.append(f"- **{ticker}** — (no print brief — no research pack or LLM unavailable)")
                continue
            watch = " · ".join(pq.get("watch") or [])
            lines.append(f"- **{ticker}** — watch: {watch}" if watch else f"- **{ticker}**")
            for p in (pq.get("points") or [])[:4]:
                lines.append(f"  - {p}")
    trade_rows = [r for r in rev.get("reviews", []) if r.get("trade") == "aligned"]
    if trade_rows:
        lines += [
            "",
            "## Trade ideas (deterministic: side × flag × verdict)",
            "*No LLM, no gate — pure logic on the verdict. `not justified` on the side's own flag = the "
            "market's pricing is wrong (a mispricing trade); `justified` = the market is right, ride it.*",
            "",
        ]
        wrong = [r for r in trade_rows if r["verdict"] == "not justified"]
        right = [r for r in trade_rows if r["verdict"] == "justified"]
        if wrong:
            lines.append("**The market is wrong (mispriced):**")
            for r in wrong:
                lines.append(f"- **{r['ticker']}** — {r['side']} · {r['flag']} · {r['verdict']}: {r.get('reason', '')}")
        if right:
            if wrong:
                lines.append("")
            lines.append("**The market is right, ride it:**")
            for r in right:
                lines.append(f"- **{r['ticker']}** — {r['side']} · {r['flag']} · {r['verdict']}: {r.get('reason', '')}")
        pq_links = [f"`{r['printqual']}`" for r in trade_rows if r.get("printqual")]
        if pq_links:
            lines.append("")
            lines.append("Per-ticker print quals: " + " · ".join(pq_links))
    lines += [
        "",
        "## How to read this",
        "- The three columns are independent layers: **Side** follows the name's own 90d estimate revisions "
        "(rev90 > +0.5% long, < -0.5% short), **Flag** compares its P/E and PEG with the theme median (see "
        "the quant table), and the **Verdict** judges the flag against the print-focused case — never the "
        "dive, which can lag the calendar.",
        "- The verdict evaluates the market's PRICING, not the trade. `not justified` on a premium = the "
        "forward case does not support paying the multiple (supports a short, warns a long); `not justified` "
        "on a discount = the cheapness looks transitory or contradicted (supports a long, warns a short); "
        "`justified` says the market's pricing matches the fundamentals either way.",
        "- So the textbook setups are: short + premium + `not justified` (expensive and deteriorating), "
        "long + discount + `not justified` (cheap and improving); the cautionary ones are long + premium "
        "(paying up against the theme) and short + discount + `justified` (cheap for a real reason).",
        "- `not justified` never ranks or gates anything — read the member's print qual and coverage report "
        "before acting.",
    ]
    theme_dir = simple_ideas_dir(str(rev["theme"]).replace("/", "-").replace(" ", "_"))
    path = theme_dir / f"_GROUP_REVIEW_{ref.isoformat()}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _ensure_expectations(tickers: list[str]) -> None:
    """Backfill the per-member data the weekly refresh gives its own names.

    Two gaps matter: a member the pipeline never covered has no expectations
    cache at all, and a freshly fetched one may still lack an earnings date —
    the date the rest of the process gets from the refresh's calendar pass.
    Both are fixed here: one ingest call each, then the print date projected
    from the company's own EDGAR filing cadence (the main pipeline's own
    deterministic method). Failures are logged, not fatal."""
    from ptm.config import data_dir
    from ptm.earnings import resolve as resolve_earnings
    from ptm.ingest.expectations import expectations

    for t in sorted(set(tickers)):
        try:
            exp = expectations(t, force=True)
            if not exp:
                log(f"expectations {t}: no revision data available")
                continue
            path = data_dir("raw", "expectations", f"{t}.json")
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("earnings_date"):
                log(f"expectations {t}: fetched")
                continue
            est = resolve_earnings(t, None)
            if est and getattr(est, "date", None):
                saved["earnings_date"] = est.date
                path.write_text(json.dumps(saved, indent=2), encoding="utf-8")
                log(f"expectations {t}: fetched, print date projected {est.date} ({getattr(est, 'basis', '')[:60]})")
            else:
                log(f"expectations {t}: fetched, print date unresolved")
        except Exception as exc:
            log(f"expectations {t}: FAIL {str(exc)[:80]}")


def run_group_review(source: str = "wiki", ref: date | None = None, theme: str | None = None) -> dict:
    """Review every non-COLD theme (or one) after the coverage reports exist.

    Members without an expectations cache get one fetched first, so the review
    covers every member with data or a flag — not just the directional ones."""
    from ptm.asof import as_of_date
    from ptm.config import data_dir
    from ptm_simple.run import load_theme_map
    from ptm_simple.radar import theme_radar, _fundamentals

    ref = ref or as_of_date()
    theme_map = load_theme_map(source)
    quant_path = simple_dir(f"quant_{ref.isoformat()}.json")
    if not quant_path.exists():
        raise SystemExit(f"no quant table for {ref.isoformat()} — run a pass or analyze-all first")
    quant_doc = json.loads(quant_path.read_text(encoding="utf-8"))
    quant_by_ticker = {row["ticker"]: row for row in quant_doc.get("rows") or []}
    # The review universe is the SWEEP's theme set — the themes the quant table
    # was built over — not today's recomputed radar status: the backfill below
    # adds covered members, and a theme that was WARM/ACTIVE at sweep time can
    # read COLD after its newly covered names dilute its breadth. The flags and
    # coverage reports already exist for the sweep's themes; review them all.
    theme_names = set(quant_doc.get("themes") or [])
    fund = _fundamentals()
    entries = [
        (entry, theme_radar(entry, fund, ref))
        for entry in theme_map["themes"]
    ]

    def _cache_needs_date(ticker: str) -> bool:
        path = data_dir("raw", "expectations", f"{ticker}.json")
        if not path.exists():
            return True
        try:
            return not (json.loads(path.read_text(encoding="utf-8")) or {}).get("earnings_date")
        except Exception:
            return True

    def _in_universe(row: dict) -> bool:
        if theme:
            return row["theme"] == theme
        if theme_names:
            return row["theme"] in theme_names
        return row["status"] != "COLD"

    to_fix = sorted({
        m["ticker"]
        for _, row in entries
        if _in_universe(row)
        for m in row["members"]
        if not m.get("covered") or _cache_needs_date(m["ticker"])
    })
    if to_fix:
        log(f"group review: {len(to_fix)} member(s) missing expectations or a print date — backfilling first")
        _ensure_expectations(to_fix)
        entries = [(entry, theme_radar(entry, fund, ref)) for entry, _ in entries]  # reread with the new caches
    reviews = []
    for _, row in entries:
        if not _in_universe(row):
            continue
        reviews.append(review_theme(row, quant_by_ticker, ref))
    payload = {
        "as_of": ref.isoformat(),
        "map_source": theme_map.get("source", ""),
        "note": "Per-theme group review: is each theme-relative valuation flag justified by the "
        "print-focused forward case (fresh EDGAR filings, guidance, consensus revisions, catalysts)? "
        "Commentary, not a gate.",
        "themes": reviews,
    }
    out = simple_dir(f"group_review_{ref.isoformat()}.json")
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    judged = sum(1 for t in reviews for r in t["reviews"] if r["verdict"] != "uncertain")
    log(f"group review: {len(reviews)} theme(s), {judged} member(s) judged -> {out.name}")
    paths = []
    for rev in reviews:
        if rev.get("members_reviewed"):
            paths.append(_review_md(rev, ref))
    log(f"group review: {len(paths)} markdown file(s) written")
    return {"themes": len(reviews), "judged": judged, "markdown": len(paths), "file": out.name}