"""The forward-looking qual brief: 5-10 points on what could happen and why now.

One small LLM call per idea. The cached deep dive is the INPUT (its
backward-looking evidence — fundamentals, drivers, bull/bear cases, dated
catalysts, falsifiers) and the OUTPUT must be forward-looking: what could
happen next, the mechanism (why), and the timing or trigger (why now) — for
this side of the trade. No price targets, no technicals, no invented numbers.

Briefs cache under data/simple/qual_briefs/ keyed by run date + the dive
file's mtime, so regenerating reports never re-rolls the brief unless the
underlying dive changed.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

from ptm.log import log
from ptm_simple import simple_dir

_SYSTEM = (
    "You write the forward-looking brief for one idea in a theme-first equity process. "
    "You get the candidate (side: long or short), its theme state, its next earnings print, "
    "peer prints from the same theme, and its cached deep-dive content (what the company "
    "does, current fundamentals, drivers, bull/bear cases, dated catalysts, falsifiers). "
    "Write 5-10 FORWARD-LOOKING points on what could happen NEXT and why it matters for "
    "this side — each point must answer 'why this trade' and 'why now'. Rules: lead with "
    "what could happen; use the given numbers as the base for the projection (e.g. 'the "
    "Avis contract ends Sep 2026, so a revenue hole opens into Q4'); never invent a number "
    "that is not given; no price targets, no technicals; one or two short sentences per "
    "point, plain language, no jargon. PERIOD DISCIPLINE: today's date and the earnings "
    "calendar are given — quarters that already ENDED must only appear as the factual base "
    "('after the Q2 margin collapse to 1.8%'), never as an open possibility. The dive text may "
    "itself be stale: trust the dates in the context over the dive's tense — a print whose "
    "report date is before today has ALREADY happened, so its numbers are public facts and "
    "must never be the subject of 'the print will reveal'. A point about the next print must "
    "say what that print will REVEAL about the quarter it reports (named in the context) and "
    "how it guides the following quarter(s); most points should project the quarters AFTER "
    "the next print and the 12-18 month setup. Answer ONLY with JSON: "
    '{"points": ["<point 1>", "<point 2>"]}'
)

_VALIDATOR_SYSTEM = (
    "You validate forward-looking brief points for an equity idea. You get today's date, "
    "the earnings-calendar context, and draft points. Return ONLY the points that are "
    "genuinely about what could happen AFTER today: fix points that hedge about a quarter "
    "or period that has already ended (turn them into what the next print will reveal or "
    "what should follow), drop points that merely restate already-reported history as if "
    "it were uncertain, keep the original wording and numbering otherwise, target 5-10 "
    "points. Answer ONLY with JSON: "
    '{"points": ["<point 1>", "<point 2>"]}'
)

# A point hedging about quarters that ENDED before the run date is backward-looking —
# the deterministic first filter drops it; the validator call catches subtler cases.
_HEDGE_RE = re.compile(r"\b(could|may|might|would|should|whether)\b", re.I)
# Future-expectation language: 'the Q2 print will reveal...' hedges with 'will'.
_EXPECT_RE = re.compile(r"\b(could|may|might|would|should|whether|will)\b", re.I)
# Dated and bare quarter references: 'Q2 2026' vs 'the Q2 print'.
_QTR_RE = re.compile(r"\bQ([1-4])\s*(\d{4})\b", re.I)
# '<Qn> print|report|results|call|release' — a point written about a past print
# as if it were still ahead ('the Q2 print will reveal...').
_PAST_PRINT_RE = re.compile(r"\bQ([1-4])\s*(\d{4})?\s*'?s?\s*(print|report|results|earnings|release|call)\b", re.I)
# Typical lag from quarter end to the print that reports it.
_PRINT_LAG = timedelta(days=40)


def _strip_numbering(points: list[str]) -> list[str]:
    """The validator may echo its own 'N. ' prefixes — reports renumber, so strip them."""
    return [re.sub(r"^\s*\d+\s*[.)]\s+", "", p) for p in points]


def _drop_backward_hedges(points: list[str], ref: date) -> list[str]:
    """Drop points hedging about quarters whose PRINT already happened.

    'Q2 2026 could show...' is backward once Q2's report is behind us; a bare
    'Q2 print will reveal...' is the same trap without the year — the quarter
    resolves to the run-date year and the ~40-day reporting lag decides whether
    that print has already happened. Facts about completed quarters are kept —
    they are the base a forward point builds on."""

    def _quarter_end(q: int, year: int) -> date:
        import calendar

        return date(year, q * 3, calendar.monthrange(year, q * 3)[1])

    def _report_date(q: int, year: int | None) -> date:
        # Bare 'Q2' means the current year's Q2; the print lands ~40d after
        # quarter end, so 'the Q2 print' is only still ahead when that date is.
        return _quarter_end(q, year if year is not None else ref.year) + _PRINT_LAG

    kept = []
    for p in points:
        if _EXPECT_RE.search(p):
            # A past print discussed as if upcoming: 'the Q2 print will reveal'.
            past_print = any(
                _report_date(int(q), int(y) if y else None) < ref
                for q, y, _ in _PAST_PRINT_RE.findall(p)
            )
            if past_print:
                log(f"brief validate: dropped point about an already-made print: {p[:70]}")
                continue
        dated = [(int(q), int(y)) for q, y in _QTR_RE.findall(p)]
        bare = [int(q) for q in re.findall(r"\bQ([1-4])\b(?!\s*\d{4})", p, re.I)]
        refs = dated + [("bare", q) for q in bare]
        if refs and _HEDGE_RE.search(p):

            def _backward(entry) -> bool:
                if entry[0] == "bare":
                    # no year given: assume this year, and only call it past
                    # once its print (~40d after quarter end) has also happened
                    return _report_date(entry[1], None) < ref
                return _quarter_end(*entry) < ref

            if all(_backward(r) for r in refs):
                log(f"brief validate: dropped backward-looking point: {p[:70]}")
                continue
        kept.append(p)
    return kept


_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _month_end(year: int, month: int) -> date:
    import calendar

    return date(year, month, calendar.monthrange(year, month)[1])


def _parse_window_date(text: str) -> date | None:
    """The date the text's most SPECIFIC period reference points to, or None.

    Specificity tiers (highest present wins, max within a tier): ISO date,
    YYYY-MM, 'September 2026', 'Q3 2026', 'H1 2027', bare year. So
    'Q2 2026 (likely 2026-08)' resolves to 2026-08-31 — not inflated by the
    bare '2026' — while '2025 recapitalization, decision H1 2027' resolves to
    2027-06-30 (no more specific reference exists)."""
    if not text:
        return None

    def _max(dates: list[date]) -> date | None:
        return max(dates) if dates else None

    iso = []
    for y, m, d in re.findall(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text):
        try:
            iso.append(date(int(y), int(m), int(d)))
        except ValueError:
            pass
    if iso:
        return max(iso)
    ym = [_month_end(int(y), int(m)) for y, m in re.findall(r"\b(20\d{2})-(\d{2})\b", text) if 1 <= int(m) <= 12]
    if ym:
        return max(ym)
    months = [
        _month_end(int(y), mo)
        for name, y in re.findall(r"\b([A-Za-z]+)\s+(20\d{2})\b", text)
        if (mo := _MONTHS.get(name.lower()))
    ]
    if months:
        return max(months)
    quarters = [_month_end(int(y), int(q) * 3) for q, y in re.findall(r"\bQ([1-4])\s*(20\d{2})\b", text, re.I)]
    if quarters:
        return max(quarters)
    halves = [_month_end(int(y), int(h) * 6) for h, y in re.findall(r"\bH([12])\s*(20\d{2})\b", text, re.I)]
    if halves:
        return max(halves)
    years = [date(int(y), 12, 31) for y in re.findall(r"\b(20\d{2})\b", text)]
    return max(years) if years else None


def _future_only(catalysts: list[dict], ref: date) -> list[dict]:
    """Drop dive catalysts whose timing is provably in the past relative to the
    run date (the window field decides; the event text is the fallback). An
    unparsable window keeps the catalyst — it cannot be proven stale."""
    out = []
    for c in catalysts:
        wd = _parse_window_date(c.get("window") or "")
        if wd is not None:
            if wd < ref:
                log(f"catalyst dropped (past): {c.get('event', '')[:60]}")
                continue
        else:
            ed = _parse_window_date(c.get("event") or "")
            if ed is not None and ed < ref:
                log(f"catalyst dropped (past event date): {c.get('event', '')[:60]}")
                continue
        out.append(c)
    return out


def dive_content(ticker: str, ref: date | None = None) -> dict | None:
    """Structured backward-looking content from the cached deep dive."""
    from ptm.config import data_dir

    path = data_dir("raw", "deepsearch", "runs", f"{ticker}.json")
    if not path.exists():
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    thesis = result.get("thesis") or {}

    def _points(items: list | None, tag_key: str) -> list[dict]:
        out = []
        for p in (items or [])[:6]:
            point = str(p.get("point") or "").strip()
            if not point:
                continue
            out.append({
                "point": point[:200],
                "evidence": str(p.get("evidence") or "").strip()[:160],
                "tag": str(p.get(tag_key) or "").strip(),
            })
        return out

    catalysts = []
    for c in (result.get("catalysts") or [])[:5]:
        event = str(c.get("event") or "").strip()
        if not event:
            continue
        catalysts.append({
            "event": event[:120],
            "window": str(c.get("window") or "").strip()[:60],
            "expected": str(c.get("expected") or "").strip()[:140],
        })
    drivers = []
    for d in (thesis.get("drivers") or [])[:6]:
        name = str(d.get("name") or "").strip()
        if not name:
            continue
        drivers.append({
            "name": name[:100],
            "direction": str(d.get("direction") or "").strip(),
            "confidence": str(d.get("confidence") or "").strip(),
            "evidence": str(d.get("evidence") or "").strip()[:160],
        })
    return {
        "stance": str(thesis.get("stance") or "").strip(),
        "thesis_text": str(thesis.get("thesis") or "").strip()[:400],
        "bull": _points(thesis.get("bull_case"), "strength"),
        "bear": _points(thesis.get("bear_case"), "severity"),
        "drivers": drivers,
        "falsifiers": [str(f).strip()[:160] for f in (thesis.get("falsifiers") or []) if str(f).strip()][:4],
        "catalysts": _future_only(catalysts, ref) if ref is not None else catalysts,
    }


def _reported_quarter(print_date) -> str:
    """'Q3 2026 (quarter ending 2026-09-30)' for an upcoming print date, or ''.

    The print reports the last calendar quarter that ended at least ~20 days
    before the print: a Nov 5 print reports Q3 (ended Sep 30), an Aug 6 print
    reports Q2. This is what the brief must reason about — not 'the most
    recently completed quarter' as of TODAY, which is usually a quarter whose
    print already happened."""
    if not print_date:
        return ""
    try:
        d = date.fromisoformat(str(print_date)[:10])
    except ValueError:
        return ""
    for back in range(3):
        m, y = d.month - back, d.year
        while m <= 0:
            m += 12
            y -= 1
        q_end = date(y, ((m - 1) // 3) * 3 + 3, 1)
        import calendar

        q_end = q_end.replace(day=calendar.monthrange(y, q_end.month)[1])
        if (d - q_end).days >= 20:
            return f"Q{q_end.month // 3} {q_end.year} (quarter ending {q_end.isoformat()})"
    return ""


def forward_brief(ticker: str, side: str, ctx: dict, ref) -> dict | None:
    """{points: [...], catalysts: [...]} for one idea, or None when unavailable.

    `ctx` carries theme name/status/lean/breadth, the idea's print fields and
    the theme's peer prints. Cached per ticker for this run date and dive
    version; one small LLM call when the cache misses.
    """
    from ptm.config import data_dir
    from ptm.llm import chat_json, llm_available

    content = dive_content(ticker, ref)
    if content is None:
        return None
    dive_path = data_dir("raw", "deepsearch", "runs", f"{ticker}.json")
    # v2: calendar context + validation stages — bump forces cached briefs to regenerate
    key = f"v2|{ref.isoformat()}|{int(dive_path.stat().st_mtime)}" if dive_path.exists() else f"v2|{ref.isoformat()}"

    cache = simple_dir("qual_briefs", f"{ticker}.json")
    if cache.exists():
        try:
            saved = json.loads(cache.read_text(encoding="utf-8"))
            if saved.get("key") == key and saved.get("points"):
                pts = _strip_numbering(saved["points"])
                filtered = _drop_backward_hedges(pts, ref)
                if len(filtered) == len(pts) and filtered == pts:
                    return {"points": filtered, "catalysts": content["catalysts"]}
                # the strengthened filter caught cached points — regenerate below
                log(f"brief {ticker}: cached brief has backward-looking point(s) — regenerating")
        except Exception:
            pass
    if not llm_available():
        # No LLM: fall back to the cached points with the deterministic filter
        # applied, so a stale brief can at least lose its backward points.
        cached = locals().get("saved") or {}
        filtered = _drop_backward_hedges(_strip_numbering(cached.get("points") or []), ref)
        return {"points": filtered, "catalysts": content["catalysts"]} if len(filtered) >= 3 else None

    side_up = "LONG" if side == "long" else "SHORT"
    print_date = ctx.get("earnings_date") or "unknown"
    reported_q = _reported_quarter(print_date)
    print_line = f"Next print: {print_date} ({ctx.get('days_to_print') or '?'}d from today)"
    if reported_q:
        print_line += f" — this print REPORTS {reported_q}, a quarter still in progress today"
    print_line += " — the trade's dated catalyst"
    lines = [
        f"Today: {ref.isoformat()}",
        f"Candidate: {ticker} ({side_up})",
        f"Theme: {ctx.get('theme', '')} — status {ctx.get('status', '?')}, lean {ctx.get('lean', '?')} "
        f"(breadth {ctx.get('breadth', 0):+.2f})",
        print_line,
    ]
    if reported_q:
        lines.append(
            "PERIODS: every quarter that ended before today was ALREADY reported to the market "
            "(e.g. the quarter before the one above) — its numbers are public facts you may build "
            "on, never an open question; write about the quarter this next print reports and the "
            "quarters after it."
        )
    peers = [p for p in (ctx.get("peer_prints") or []) if p.get("ticker") != ticker and p.get("earnings_date")]
    if peers:
        lines.append("Peer prints in the same theme: " + "; ".join(
            f"{p['ticker']} {p['earnings_date']} ({p.get('days_to_print')}d)" for p in peers[:5]
        ))
    lines.append(f"Dive stance (on the company): {content['stance'] or 'n/a'}")
    if content["thesis_text"]:
        lines.append(f"What it does / where it stands: {content['thesis_text']}")
    if content["drivers"]:
        lines.append("Drivers: " + " | ".join(
            f"{d['name']} ({d['direction']}, {d['confidence']})" for d in content["drivers"][:4]
        ))
    for label, pts in (("Bull points", content["bull"]), ("Bear points", content["bear"])):
        if pts:
            lines.append(label + ":")
            lines += [f"- {p['point']}" + (f" [{p['evidence']}]" if p["evidence"] else "") for p in pts[:3]]
    if content["catalysts"]:
        lines.append("Dated catalysts: " + " | ".join(
            f"{c['event']} ({c['window']})" for c in content["catalysts"][:3]
        ))
    if content["falsifiers"]:
        lines.append("Falsifiers: " + " | ".join(content["falsifiers"]))
    user = "\n".join(lines)
    try:
        out = chat_json(_SYSTEM, user)
    except Exception as exc:
        log(f"brief {ticker}: FAIL {str(exc)[:100]}")
        return None
    points = [str(p).strip()[:320] for p in (out.get("points") or []) if str(p).strip()]
    points = _strip_numbering(_drop_backward_hedges(points, ref))
    # Second stage: an explicit validator pass over the draft — re-frames or
    # drops anything still not forward-looking relative to today's date.
    if points:
        # The validator sees the same period context the writer did, including
        # the PERIODS line, so it can tell a past print from the next one.
        val_ctx = "\n".join(lines[:4] + ([lines[4]] if reported_q else []))
        val_user = (
            f"{val_ctx}\n\nDraft points:\n" + "\n".join(f"{i}. {p}" for i, p in enumerate(points, 1))
            + "\n\nReturn the validated, forward-looking points."
        )
        try:
            validated = chat_json(_VALIDATOR_SYSTEM, val_user)
            v_points = [str(p).strip()[:320] for p in (validated.get("points") or []) if str(p).strip()]
            if len(v_points) >= 3:
                points = _strip_numbering(_drop_backward_hedges(v_points, ref))
                log(f"brief {ticker}: validator kept {len(points)} point(s)")
        except Exception as exc:
            log(f"brief {ticker}: validator FAIL {str(exc)[:80]} — keeping draft")
    if len(points) < 3:
        log(f"brief {ticker}: too few usable points — skipping")
        return None
    cache.write_text(
        json.dumps({"key": key, "ticker": ticker, "points": points}, indent=2), encoding="utf-8"
    )
    log(f"brief {ticker}: {len(points)} forward-looking points")
    return {"points": points, "catalysts": content["catalysts"]}