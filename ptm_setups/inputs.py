"""Deterministic packets for the group ranking — fundamentals only, no price action.

Every field here is measured and already cached; nothing in this module calls
an LLM. That is the rule the whole process rests on: the ranking pass may only
reason about numbers that appear in these packets, so there is no room for an
invented figure.

Sources, all shared with the simple process (same files, same computation):

1. the expectations cache (data/raw/expectations/<T>.json) — the name's own FY1
   consensus change over 90d and 30d, the analyst up/down counts, the next
   print date, and the EPS SURPRISE history (actual vs consensus per quarter,
   the beat record and the average surprise);
2. the quant table (data/simple/quant_<date>.json) — consensus FY1/FY2 EPS,
   growth EG1/EG2, forward P/E, PEG, P/S, and the name's position against its
   industry median as the theme-relative valuation flag (ptm_simple.quant);
3. the EDGAR research pack (data/raw/research/<T>.json) — the last earnings
   exhibit's actuals, forward MD&A/guidance language, and reported consensus
   changes. Read with the simple process's own pack reader, so both layers see
   identical filed text;
4. bounded web-search snippets, gathered per INDUSTRY rather than per name
   (ptm_setups.search) — developments since the filings, treated as undated
   leads.

DELIBERATELY ABSENT, and the reason the omission is load-bearing: price, price
history, moving averages, momentum or trend measures, the post-print price
reactions the expectations cache also stores, and analyst price targets. This
process ranks on fundamentals and valuation, so no price level ever reaches the
prompt. Valuation is the single channel through which price enters at all, and
it arrives already reduced to a ratio (P/E, PEG, P/S) and to that ratio's
position against the industry median.
"""

from __future__ import annotations

import json
from datetime import date

# The EDGAR pack reader and the print-quarter calendar are the simple process's
# own; reusing them keeps the filed facts and the reported quarter identical
# across the two qualitative layers instead of drifting apart.
from ptm_simple.brief import _reported_quarter
from ptm_simple.print_qual import _pack_inputs


def _exp_cache(ticker: str) -> dict | None:
    """The raw expectations cache for a ticker, or None.

    Read straight off disk rather than through ptm.ingest.expectations, which
    fetches on a miss and returns nothing on a backdated run. The radar and the
    group review read it the same way; the ranking's own backfill (rank.py)
    fills the gaps before a pass starts.
    """
    from ptm.config import data_dir

    path = data_dir("raw", "expectations", f"{ticker}.json")
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _num(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        out = float(value)
        return None if out != out else out  # NaN
    except (TypeError, ValueError):
        return None


# Below this absolute EPS, a percentage change stops describing a magnitude: a
# consensus of $0.01 turns a two-cent move into +200%. Real names hit it —
# HTLD printed $0.14 against a -$0.01 estimate, an arithmetically true
# "+2445% beat" that is a loss-to-profit swing and nothing more.
_LOW_BASE_EPS = 0.25
# A surprise past this magnitude is a near-zero-base artefact in every real
# case; one in the four-quarter window invalidates the average surprise.
_DISTORTED_SURPRISE_PCT = 200.0


def low_base(newer: float | None, older: float | None) -> bool:
    """True when a percentage between these two is an artefact, not a magnitude.

    Either the denominator is near zero, or the two straddle zero so the
    percentage has no meaningful sign. Flagged in the packet so the ranking
    prompt can be told to reason from the dollar figures instead — otherwise a
    loss-to-profit swing outranks every genuine beat in the group.
    """
    if newer is None or older is None:
        return False
    if abs(older) < _LOW_BASE_EPS:
        return True
    return (newer < 0) != (older < 0)


def quarter_label(quarter_end) -> str:
    """'Q2 2026' for a quarter-END date — the CALENDAR quarter, not a fiscal one.

    Two separate traps here. The first: the packet used to give the last print a
    bare date ("2026-06-30") while giving the next print a named quarter ("Q3
    2026"), and a live pass duly described the June beat as "Q3 2026 earnings".
    Both are now named.

    The second is why this label is explicitly CALENDAR. A company whose fiscal
    year does not end in December labels the same period differently in its own
    filings — Moog's year ends in September, so the quarter ending 2026-06-30 is
    its fiscal Q3, and a pass reading Moog's exhibit correctly called the same
    beat "Q3" while this function called it "Q2". Neither is wrong; they are
    different calendars. So the packet carries the period END DATE as the
    primary key, this label beside it marked as calendar, and the prompt is told
    to prefer the date and to take any fiscal label from the filing itself.
    """
    try:
        d = date.fromisoformat(str(quarter_end)[:10])
    except (ValueError, TypeError):
        return ""
    return f"Q{(d.month - 1) // 3 + 1} {d.year}"


def surprise_facts(exp: dict | None) -> dict:
    """The EPS surprise record: the latest print and the four-quarter tally.

    `last` is the most recently REPORTED quarter — the packet's single most
    concrete fact about how this business is executing against expectations,
    and the first column of the ranking table.
    """
    out: dict = {"available": False, "last": None, "beats": None, "of": None, "avg_pct": None}
    sur = (exp or {}).get("surprise") or {}
    if not sur.get("available"):
        return out
    prints = [p for p in (sur.get("prints") or []) if isinstance(p, dict) and p.get("quarter")]
    prints.sort(key=lambda p: str(p["quarter"]))
    out["available"] = True
    out["beats"], out["of"] = sur.get("beats"), sur.get("of")
    out["avg_pct"] = _num(sur.get("avg_surprise_pct"))
    if prints:
        last = prints[-1]
        actual, estimate = _num(last.get("actual")), _num(last.get("estimate"))
        out["last"] = {
            # the period END DATE is the unambiguous key; the calendar label is
            # a convenience that a non-December fiscal year will disagree with
            "quarter_ended": str(last.get("quarter") or ""),
            "calendar_quarter": quarter_label(last.get("quarter")),
            "quarter": str(last.get("quarter") or ""),
            "actual": actual,
            "estimate": estimate,
            "surprise_pct": _num(last.get("surprise_pct")),
            "low_base": low_base(actual, estimate),
        }
    out["history"] = [
        {"quarter": str(p["quarter"]), "surprise_pct": _num(p.get("surprise_pct"))}
        for p in prints
    ]
    # The four-quarter average is precomputed upstream, so one base-distorted
    # quarter silently poisons it (HTLD averages +633% across four prints on the
    # strength of a single two-cent swing). Only the actual/estimate pair of the
    # LATEST quarter is available to test, so the average is judged by its own
    # history instead: a surprise past this magnitude is a near-zero base every
    # time, and once one is in the window the average means nothing.
    out["avg_distorted"] = any(
        (h["surprise_pct"] is not None and abs(h["surprise_pct"]) > _DISTORTED_SURPRISE_PCT)
        for h in out["history"]
    )
    return out


def member_packet(ticker: str, member: dict, qrow: dict, ref: date) -> dict:
    """One member's deterministic packet for the ranking prompt.

    `member` is a radar member row (coverage, revisions, print date), `qrow` the
    quant table row (consensus, multiples, industry-relative flag). Missing
    inputs are simply absent — the prompt says so rather than guessing.
    """
    exp = _exp_cache(ticker)
    rev = (exp or {}).get("revisions") or {}
    print_date = qrow.get("earnings_date") or member.get("earnings_date") or (exp or {}).get("earnings_date")
    days = qrow.get("days_to_print")
    if days is None:
        days = member.get("days_to_print")
    rev90 = member.get("rev90")
    if rev90 is None:
        rev90 = qrow.get("rev90")
    if rev90 is None:
        rev90 = _num(rev.get("change_90d_pct"))
    packet: dict = {
        "ticker": ticker,
        "name": str(qrow.get("name") or ""),
        "industry": str(qrow.get("industry") or ""),
        "market_cap_usd": qrow.get("market_cap"),
        "revisions": {
            "fy1_change_90d_pct": rev90,
            "fy1_change_30d_pct": _num(rev.get("change_30d_pct")),
            # The EPS LEVELS behind those percentages. A 90d change of +1369%
            # is a two-cent move off a near-zero consensus; with the levels in
            # the packet the pass can read the dollar move instead of the ratio.
            "fy1_eps_now": _num(rev.get("eps_current")),
            "fy1_eps_30d_ago": _num(rev.get("eps_d30")),
            "fy1_eps_90d_ago": _num(rev.get("eps_d90")),
            "low_base": low_base(_num(rev.get("eps_current")), _num(rev.get("eps_d90"))),
            "analysts_up_30d": member.get("up30") if member.get("up30") is not None else rev.get("analysts_up_30d"),
            "analysts_down_30d": member.get("down30") if member.get("down30") is not None else rev.get("analysts_down_30d"),
        },
        "next_print": {
            "date": print_date,
            "days_away": days,
            "reports_quarter": _reported_quarter(print_date),
        },
        "eps_surprise": surprise_facts(exp),
        "consensus": {
            "eps_fy1": qrow.get("eps1"),
            "eps_fy2": qrow.get("eps2"),
            "growth_fy1": qrow.get("eg1"),
            "growth_fy2": qrow.get("eg2"),
        },
        "valuation": {
            "forward_pe_fy1": qrow.get("pe1"),
            "forward_pe_fy2": qrow.get("pe2"),
            "peg_fy1": qrow.get("peg1"),
            "peg_fy2": qrow.get("peg2"),
            "price_to_sales": qrow.get("ps"),
            "vs_industry_median_pe": qrow.get("pe_vs_theme"),
            "vs_industry_median_peg": qrow.get("peg_vs_theme"),
            "flag": qrow.get("flag"),
            "flag_detail": qrow.get("flag_detail"),
        },
        "revenue_latest_filing_usd": qrow.get("revenue"),
    }
    filed = _pack_inputs(ticker)
    if filed:
        packet["filed"] = {
            "edgar_pack_date": filed.get("run_date"),
            "last_earnings_exhibit": filed.get("last_earnings_exhibit"),
            "forward_guidance_lines": filed.get("filed_facts"),
            "reported_consensus_changes": filed.get("reported_consensus_changes"),
        }
    return packet


def revision_side(packet: dict) -> str:
    """The side the name's OWN revisions imply — the prior, not the verdict.

    The simple process treats this as a hard rule; here it is one input the
    ranking may override, and every override has to be declared (rank.py
    records `against_revisions` and the reason).
    """
    rev90 = (packet.get("revisions") or {}).get("fy1_change_90d_pct")
    if rev90 is None:
        return "none"
    if rev90 > 0.5:
        return "long"
    if rev90 < -0.5:
        return "short"
    return "flat"


def has_anything_to_rank(packet: dict) -> bool:
    """True when the packet carries at least one forward fundamental input.

    A name with no revisions, no surprise history, no consensus and no filed
    pack cannot be ranked on fundamentals — it is reported as skipped rather
    than ranked on nothing.
    """
    rev = packet.get("revisions") or {}
    cons = packet.get("consensus") or {}
    return bool(
        rev.get("fy1_change_90d_pct") is not None
        or (packet.get("eps_surprise") or {}).get("available")
        or cons.get("eps_fy1") is not None
        or packet.get("filed")
    )


# ------------------------------------------------------------------ table cells
# The ranking table's factual columns are rendered HERE, from the packet, and
# never from the model's prose — so every number the reader sees in them is the
# measured one. The model fills only the judgement column and the narrative.

def surprise_cell(packet: dict) -> str:
    """'**+41.98% EPS beat** ($3.72 vs $2.62 est, 2026-06-30) · beat 4 of 4, avg +21.5%'.

    An artefact percentage is never shown, not merely footnoted: a base-distorted
    cell leads with the dollar figures and names the swing, because the headline
    number is what a reader — and anything that quotes this cell downstream —
    takes away from it.
    """
    sur = packet.get("eps_surprise") or {}
    last = sur.get("last") or {}
    pct, actual, est = last.get("surprise_pct"), last.get("actual"), last.get("estimate")
    if pct is None and actual is None:
        return "—"
    ended = str(last.get("quarter_ended") or last.get("quarter") or "")[:10]
    quarter = f"quarter ended {ended}" if ended else ""
    pair = f"${actual:,.2f} vs ${est:,.2f} est" if (actual is not None and est is not None) else ""
    if pct is None:
        # dollars without a percentage — the estimate was missing, so the sign
        # test has nothing to compare against; report the fact, not a verdict
        bits = f"**${actual:,.2f} reported**" if actual is not None else "**no measurable surprise**"
        detail = ", ".join(x for x in (pair, quarter) if x)
        bits = bits + (f" ({detail})" if detail else "")
        tail = ""
    elif last.get("low_base"):
        if not pair:
            return "—"
        swing = ("loss to profit" if (est is not None and actual is not None and est < 0 <= actual)
                 else "profit to loss" if (est is not None and actual is not None and actual < 0 <= est)
                 else "near-zero base")
        detail = ", ".join(x for x in (swing, quarter) if x)
        bits = f"**{pair}**" + (f" ({detail})" if detail else "")
        tail = "*% withheld — artefact of a near-zero base*"
    else:
        word = "beat" if pct >= 0 else "miss"
        detail = ", ".join(x for x in (pair, quarter) if x)
        bits = f"**{pct:+.2f}% EPS {word}**" + (f" ({detail})" if detail else "")
        tail = ""
    if sur.get("beats") is not None and sur.get("of"):
        tally = f"beat {sub_int(sur['beats'])} of {sub_int(sur['of'])}"
        if sur.get("avg_distorted"):
            tally += ", avg n/a (a quarter's % is base-distorted)"
        elif sur.get("avg_pct") is not None:
            tally += f", avg {sur['avg_pct']:+.1f}%"
        bits += f" · {tally}"
    return f"{bits} · {tail}" if tail else bits


def clip_words(text: str, limit: int) -> str:
    """Trim to `limit` on a word boundary, with an ellipsis when anything went.

    These strings land in table cells, and a hard character slice cut them
    mid-word ("without a demanding hurdl"), which reads as corruption rather
    than as an abbreviation.
    """
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rstrip()
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space].rstrip()
    return cut.rstrip(",;:.") + "…"


def sub_int(value) -> str:
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return "?"


def setup_cell(packet: dict) -> str:
    """The print-setup column: revisions, analyst counts and the print date.

    This is where the technical-trend column of a conventional setup table
    would sit. It carries estimate and calendar facts instead — the forward
    fundamental read on how expectations are moving into the print.
    """
    rev = packet.get("revisions") or {}
    nxt = packet.get("next_print") or {}
    bits = []
    d90, d30 = rev.get("fy1_change_90d_pct"), rev.get("fy1_change_30d_pct")
    if rev.get("low_base") and rev.get("fy1_eps_now") is not None and rev.get("fy1_eps_90d_ago") is not None:
        # The percentage would be an artefact here, so show the move itself.
        bits.append(f"FY1 est ${rev['fy1_eps_90d_ago']:,.2f} → ${rev['fy1_eps_now']:,.2f} over 90d "
                    f"(% meaningless off this base)")
    else:
        if d90 is not None:
            bits.append(f"FY1 est {d90:+.1f}% 90d")
        if d30 is not None:
            bits.append(f"{d30:+.1f}% 30d")
    up, down = rev.get("analysts_up_30d"), rev.get("analysts_down_30d")
    if up is not None or down is not None:
        bits.append(f"{sub_int(up)} up / {sub_int(down)} down 30d")
    if nxt.get("date"):
        when = str(nxt["date"])[:10]
        if nxt.get("days_away") is not None:
            when += f" ({sub_int(nxt['days_away'])}d)"
        bits.append(f"prints {when}")
    else:
        bits.append("print date unknown")
    return " · ".join(bits) if bits else "—"


def valuation_cell(packet: dict) -> str:
    """Deterministic valuation half of the guidance/valuation column.

    The model writes the guidance read; these are the measured multiples it is
    written against, so the column always shows real ratios even when the model
    says little.
    """
    val = packet.get("valuation") or {}
    bits = []
    if val.get("forward_pe_fy1") is not None:
        bits.append(f"PE1 {val['forward_pe_fy1']:.1f}x")
    if val.get("peg_fy1") is not None:
        bits.append(f"PEG1 {val['peg_fy1']:.2f}")
    if val.get("price_to_sales") is not None:
        bits.append(f"P/S {val['price_to_sales']:.1f}x")
    flag = val.get("flag")
    if flag and flag != "n/a":
        vs = []
        if val.get("vs_industry_median_pe") is not None:
            vs.append(f"P/E {val['vs_industry_median_pe']:.2f}x")
        if val.get("vs_industry_median_peg") is not None:
            vs.append(f"PEG {val['vs_industry_median_peg']:.2f}x")
        bits.append(f"{flag} vs industry" + (f" ({', '.join(vs)} median)" if vs else ""))
    return " · ".join(bits) if bits else "—"
