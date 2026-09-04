"""The group ranking: one pass per industry, then one pass across industries.

This is the whole qualitative half of ptm_setups, and it replaces four layers
of the simple process (the per-member deep dive, the per-member forward brief,
the per-member print qual, and the per-theme flag-justification review) with
two kinds of call:

    HEATS   one call per non-COLD industry, over ALL of its covered members at
            once. It orders them as long and short setups into the next print
            and the 0-3 months around it, on the forward fundamental case.
    FINAL   one call over the heats' winners, ranking them across industries
            into a single best-longs / best-shorts leaderboard.

Three things follow from ranking a group instead of reviewing a name.

THE SIDE IS THE PASS'S OWN CALL. The simple process pins the side by hard rule
(FY1 consensus up over 90d -> long, down -> short) and never revisits it. Here
that direction is a strong prior the ranking is shown and may override — the
point of the pass is to find the best short even inside an industry whose
estimates are rising. Every override is DETERMINISTICALLY detected here
(`against_revisions`, computed from the prior and the assigned side, never
taken from the model's own claim) and the prompt requires the reason in the
risk field.

VALUATION IS A HURDLE, NOT A SCORE. A premium multiple is usually the market
correctly paying for better growth, returns or durability, and a discount is
usually a correct mark-down — so the LEVEL of the multiple carries almost no
directional information on a 0-3 month horizon, and ranking a name up for
being cheap is the error this prompt is written to prevent. Valuation enters
in exactly two ways: it sets the bar the print has to clear, and it sizes the
asymmetry if the driver the multiple assumes breaks. The industry-relative
flag from ptm_simple.quant is an input to that reading, not a verdict on it.

NO PRICE, ANYWHERE. The ranking reasons about fundamentals and valuation only.
The packets carry no price, no price history and no post-print price
reactions (ptm_setups.inputs documents the omissions), and the prompt forbids
technical language outright, so the third column of the ranking table is the
print SETUP — revisions, analyst counts, the beat record, the calendar —
rather than a trend read.

Safeguards carried over from the simple process unchanged: period discipline
(quarters that ended are facts, never open questions), never invent a number
that is not in the packet, web snippets are undated leads and not dated facts,
and the whole output is commentary — nothing downstream reads a ranking to
include or drop a name.

Without an LLM the pass degrades to the deterministic packets rendered as an
unranked table, marked as such. Output: per-industry markdown
(ideas/setups/<industry>/_RANKING_<date>.md), the cross-industry leaderboard
(ideas/setups/_LEADERBOARD_<date>.md), and one aggregate JSON
(data/setups/setups_<date>.json) the viewer reads.
"""

from __future__ import annotations

import json
from datetime import date

from ptm.llm import JSON_HINT, chat_json, llm_available, setups_model, setups_reasoning_effort
from ptm.log import log
from ptm_setups import setups_dir, setups_ideas_dir
from ptm_setups.inputs import (
    clip_words,
    has_anything_to_rank,
    member_packet,
    revision_side,
    setup_cell,
    surprise_cell,
    valuation_cell,
)

_SIDES = ("long", "short", "avoid")
_CONVICTIONS = ("high", "medium", "low")

_SYSTEM = (
    "You are a long/short equity portfolio manager ranking the members of ONE industry group "
    "against each other for the NEXT EARNINGS PRINT and the 0-3 months around it. Your job: order "
    "them into the best long setups and the best short setups, and justify the order.\n"
    "WHAT YOU ARE GIVEN per member, all measured and all in the packet: the last reported quarter's "
    "EPS actual against consensus and the surprise percentage, the beat record over the last four "
    "quarters with the average surprise, the name's OWN FY1 consensus change over 90 and 30 days, the "
    "analyst up/down counts, consensus FY1/FY2 EPS and growth, forward P/E, PEG and P/S together with "
    "the name's position against its industry median (the valuation flag), the next print date and the "
    "fiscal quarter that print REPORTS (computed for you — trust it), the last filed earnings exhibit "
    "and forward guidance language from EDGAR, and undated web-search snippets.\n"
    "TWO DIFFERENT QUARTERS, NEVER INTERCHANGEABLE. eps_surprise.last.quarter_ended is the period "
    "ALREADY reported — its beat or miss is a settled fact. next_print.reports_quarter is the period the "
    "UPCOMING print will reveal, about which nothing is yet known. Never attribute the past beat to the "
    "coming quarter. Both carry CALENDAR labels derived from the period end date: a company whose fiscal "
    "year does not end in December numbers the same period differently in its own filings (a June "
    "quarter is fiscal Q3 for a September year-end). Refer to periods by their END DATE, and use a "
    "fiscal quarter number only where the filed exhibit itself uses it.\n"
    "HOW TO RANK. Rank on the forward fundamental case into the print: the direction and breadth of "
    "estimate revisions, the beat/miss record and whether it is improving or decaying, filed guidance "
    "and what it implies for the quarter being reported, order/backlog/margin/pricing/volume detail "
    "from the filings, and read-throughs between members of the group. The SIDE IS YOURS to assign — "
    "long, short or avoid — and it need not follow the name's own revision direction, which is given "
    "as a prior. When you assign a side against that prior, say why in the risk field.\n"
    "PERCENTAGES OFF A NEAR-ZERO BASE. Where a packet sets low_base true, the percentage beside it is "
    "an arithmetic artefact and not a magnitude: the denominator is near zero or the two figures "
    "straddle zero, so a two-cent move reads as several hundred percent. In those cases reason from "
    "the dollar EPS figures given alongside (fy1_eps_now against fy1_eps_90d_ago, actual against "
    "estimate) and describe what happened — a loss turning into a small profit, say — never citing the "
    "percentage. A low_base name must NEVER outrank a genuine beat on the size of its percentage.\n"
    "HOW TO USE VALUATION. Valuation is mostly a summary of fundamentals: a premium multiple is usually "
    "the market correctly paying for better growth, returns or durability, and a discount is usually a "
    "correct mark-down of a worse business. The LEVEL of the multiple is therefore NOT a score. Never "
    "rank a name up because it is cheap or down because it is expensive, and never treat cheapness as a "
    "catalyst — nothing re-rates a cheap name inside three months without an event. Valuation enters in "
    "exactly two ways: (1) the HURDLE — a high multiple needs a bigger beat and a raise to hold, and an "
    "in-line print de-rates it; (2) the ASYMMETRY — it sizes what is lost if the driver the multiple "
    "assumes breaks, and what is gained if a marked-down name's deterioration proves transitory. So a "
    "discount is interesting only when something dated forces the market to re-mark it, and a premium is "
    "a negative only when the coming print is likely to break the growth it assumes.\n"
    "PROVE THE RANK IS NOT A VALUATION RANK. Every entry must carry ranked_on: the single FUNDAMENTAL "
    "fact that decided its position — a revision move, a beat or miss and its trend, a filed guidance "
    "change, or an order/backlog/margin detail from the filings. A multiple, a PEG, or any form of "
    "'cheap', 'expensive', 'over-valued', 'under-valued' or 'the valuation supports/does not justify it' "
    "is NOT an acceptable ranked_on. You may NOT place a name above another whose revisions, beat and "
    "guidance are ALL stronger on the strength of a lower multiple. Where two names' fundamentals are "
    "genuinely level, say so in ranked_on and break the tie on whose print lands first.\n"
    "NAME A BEST LONG AND A BEST SHORT, SEPARATELY. Beyond the ordered list, pick the single best LONG "
    "setup and the single best SHORT setup in this industry and write each one its own case: its own "
    "thesis, its own catalyst, its own setup and its own risk. They are two different trades and must "
    "not share reasoning. THE SHORT IS THE HARDER AND MORE VALUABLE CALL — do not treat it as the "
    "leftover at the bottom of the long list. Ask specifically which member's expectations are most "
    "likely to be cut: decaying beat sizes, guidance the filings do not support, analyst counts turning "
    "down, a driver that the coming print exposes. In an industry whose estimate breadth is NEGATIVE or "
    "flat the short is the primary output and the long is secondary, and your tactical line must lead "
    "with the short. If the industry genuinely offers no credible short (or no credible long), set that "
    "pick's ticker to null and give the reason — an invented short is worse than an admitted absence.\n"
    "HARD RULES. (1) NO TECHNICALS AND NO PRICE ACTION of any kind: no price levels, no support or "
    "resistance, no moving averages, no RSI, no momentum, trend or drift reads, no chart language, no "
    "analyst price targets, no entry or exit prices. You are not given prices and must never imply one. "
    "Rank in fundamental language ('the largest beat with the only raised guide'), never technical "
    "('the cleanest breakout'). (2) NEVER invent a number: every figure you cite must appear in the "
    "packet — if the number you want is absent, describe the direction in words instead. (3) PERIOD "
    "DISCIPLINE: today's date is given; quarters that already ended are the factual base, never open "
    "questions — write about the quarter the next print reports and the quarters after it. (4) The web "
    "snippets carry no verified dates: treat them as leads, write 'reports suggest' for anything that "
    "appears only there, and never state one as a dated fact. (5) Return exactly one entry per ticker "
    "given, ranked 1..N with no ties. Keep catalyst and setup under 400 characters each. " + JSON_HINT
)

_FINAL_SYSTEM = (
    "You are a long/short equity portfolio manager choosing between the best setups your analysts "
    "ranked inside several separate industry groups. Each candidate arrives with the side its own "
    "industry pass assigned, that pass's reasoning, and the same measured fundamentals: last quarter's "
    "EPS surprise, the four-quarter beat record, the FY1 consensus change over 90 and 30 days, analyst "
    "up/down counts, consensus growth, forward P/E and PEG against the candidate's own industry median, "
    "and the next print date. Rank the LONGS against each other and the SHORTS against each other for "
    "the next print and the 0-3 months around it, best first.\n"
    "Judge on the strength and freshness of the forward fundamental case: how much the estimate "
    "direction has moved and how broadly, how decisively the last print beat or missed, whether filed "
    "guidance corroborates it, and how soon the print lands. Valuation is a hurdle and an asymmetry, "
    "never a score — do not promote a candidate for being cheap or demote one for being expensive; note "
    "the multiple only where it changes the bar the print must clear or the size of the move if the "
    "case breaks. A candidate whose case rests on the same industry driver as another is not two "
    "independent ideas — say so.\n"
    "HARD RULES, identical to the industry passes: no technicals, no price action, no price levels, no "
    "price targets, no momentum or trend language; never invent a number that is not given; quarters "
    "that already ended are facts, not open questions; keep every reason under 300 characters. Rank "
    "every candidate given, longs and shorts separately, with no ties. " + JSON_HINT
)


def _slug(theme: str) -> str:
    return str(theme).replace("/", "-").replace(" ", "_")


def _clip(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _prose(value: object, limit: int) -> str:
    """Clip a rendered-as-prose field, collapsing the whitespace first.

    Every caller emits its result as a single markdown line behind a bold
    lead-in ("**Why this group is not COLD (upside):** ..."), so a blank line
    inside a multi-sentence answer would end the paragraph and leave the rest
    of the argument dangling as unlabelled body text.
    """
    return clip_words(" ".join(str(value or "").split()), limit)


# Character budget for the serialised packets inside one industry prompt. Real
# industries already exceed it: eight members with four EDGAR packs between
# them ran to 26k, and every additional cached pack pushes another group over.
_PACKET_CHARS = 48000

# Output budget for one ranking call. The provider-wide default (8192) is sized
# for the pipeline's per-name calls; one call about a whole industry has to
# write five prose fields per member, and a reasoning model spends part of the
# budget thinking before it emits any JSON. glm-5.3-flash hit finish_reason
# "length" on a THREE-name group at the default, and the salvage path then
# returned a well-formed object with an empty ranking — a silent, total loss of
# the pass's output. Scale with the group and leave reasoning headroom.
# Deliberately generous. The whole point of this process is that it spends 14
# calls instead of ~140, so the budget that would be reckless per-name is cheap
# here, and ranking quality is the only thing it buys. Reasoning tokens come
# out of the same allowance, so the headroom has to cover thinking AND five
# prose fields per member.
# Guards on the model's prose fields, in characters. They are NOT display
# widths: everything measured against them renders as a paragraph or a bullet,
# never inside a table cell, so the only job here is to stop a runaway model
# from writing a page. The values that suit a cell (see _row's guidance and
# label) were being applied to the analysis too, and cut the why-not-COLD
# judgement mid-argument.
_PROSE_CHARS = 2600   # why_not_cold, headline, tactical, summary, a pick's thesis
_CASE_CHARS = 1200    # catalyst / setup / risk, per name and per pick

_TOKENS_PER_MEMBER = 2400
_TOKENS_OVERHEAD = 18000  # +2k for the fuller why-not-COLD judgement
_TOKENS_CEILING = 64000


def _token_budget(members: int) -> int:
    return min(_TOKENS_CEILING, _TOKENS_OVERHEAD + _TOKENS_PER_MEMBER * max(members, 1))


# Per-request deadline. The shared client is built at 120s, which is right for a
# per-name call and far too short here: an eight-member group at medium
# reasoning ran past it, and the retry ladder then spent its one timeout retry
# re-running a call that could never fit, stalling four minutes before failing.
# 14 calls a run makes a generous deadline free.
_TIMEOUT_BASE_S = 180.0
_TIMEOUT_PER_MEMBER_S = 45.0
_TIMEOUT_CEILING_S = 900.0


def _timeout(members: int) -> float:
    return min(_TIMEOUT_CEILING_S, _TIMEOUT_BASE_S + _TIMEOUT_PER_MEMBER_S * max(members, 1))


def _fit_packets(packets: list[dict], limit: int = _PACKET_CHARS) -> tuple[str, str]:
    """Serialise the packets whole, shrinking only the filed TEXT until they fit.

    Slicing the JSON string would cut mid-structure and hand the model a
    malformed object — the failure mode is silent, because a truncated packet
    still looks like data. So the budget is met by trimming the filed EDGAR
    prose instead: it is the largest field, the most compressible, and the only
    one the ranking can afford to lose. The measured numbers always survive,
    since they are the only figures the pass is allowed to cite.

    Returns (json, note). The note goes into the prompt so the model is told its
    filed text is abridged rather than left to guess, and it is logged. The JSON
    is always valid, even if a very large group ends up over budget anyway —
    valid and long beats short and broken.
    """
    blob = json.dumps(packets, default=str)
    if len(blob) <= limit:
        return blob, ""
    work = json.loads(json.dumps(packets, default=str))  # deep copy, already JSON-safe
    for exhibit, facts in ((900, 6), (500, 4), (250, 3), (0, 2)):
        for p in work:
            filed = p.get("filed")
            if not filed:
                continue
            if exhibit:
                if filed.get("last_earnings_exhibit"):
                    filed["last_earnings_exhibit"] = str(filed["last_earnings_exhibit"])[:exhibit]
            else:
                filed.pop("last_earnings_exhibit", None)
            if filed.get("forward_guidance_lines"):
                filed["forward_guidance_lines"] = filed["forward_guidance_lines"][:facts]
        blob = json.dumps(work, default=str)
        if len(blob) <= limit:
            note = (
                f"NOTE: the filed EDGAR text below is abridged to fit the prompt "
                f"(exhibits cut to {exhibit} characters, {facts} guidance lines per member); "
                f"the numbers are complete."
                if exhibit else
                "NOTE: the filed earnings exhibits below were dropped to fit the prompt and only two "
                "guidance lines per member remain; the numbers are complete."
            )
            return blob, note
    for p in work:  # last resort: the numbers alone must reach the model intact
        p.pop("filed", None)
    blob = json.dumps(work, default=str)
    return blob, (
        "NOTE: the filed EDGAR text was dropped entirely to fit the prompt — rank from the "
        "consensus, revision and surprise data, and do not claim to have read any filing."
    )


def _macro_demand_line() -> str:
    """The ISM demand snapshot, for the group's forward-looking why-not-COLD call.

    Deterministic, from data/curated/ism.json — the same artifact the PMI tab
    reads. Purchasing managers' new orders and the industries they name as
    expanding or contracting are the survey evidence for where demand goes NEXT,
    which is exactly what a not-COLD reason has to argue from. Absent file or
    parse trouble yields an empty string: the pass then argues from its search
    snippets alone.
    """
    from ptm.config import data_dir
    from ptm.io import read_json

    try:
        ism = read_json(data_dir("curated", "ism.json"))
    except Exception:
        return ""
    if not ism or not (ism.get("pmi") or ism.get("nmi")):
        return ""
    mfg, svc = ism.get("manufacturing") or {}, ism.get("services") or {}

    def _no(report: dict) -> str:
        val = ((report.get("components") or {}).get("new_orders") or {}).get("value")
        return f" (new orders {val:.1f})" if isinstance(val, (int, float)) else ""

    bits = [f"Manufacturing PMI {ism.get('pmi'):.1f}{_no(mfg)}" if ism.get("pmi") else "",
            f"Services {ism.get('nmi'):.1f}{_no(svc)}" if ism.get("nmi") else ""]
    growth = [i for i in ((mfg.get("industries") or {}).get("growth") or [])[:8] if isinstance(i, str)]
    contraction = [i for i in ((mfg.get("industries") or {}).get("contraction") or [])[:8] if isinstance(i, str)]
    if growth:
        bits.append("expanding: " + ", ".join(growth))
    if contraction:
        bits.append("contracting: " + ", ".join(contraction))
    month = ism.get("target_report_month") or ""
    return f"Macro demand check (latest ISM report{', ' + month if month else ''}): " + " · ".join(bits) + "."


def _why_not_cold(payload: dict) -> dict | None:
    """Validate the pass's why-not-COLD field: direction + a forward reason."""
    raw = payload.get("why_not_cold") or {}
    if not isinstance(raw, dict):
        return None
    direction = _clip(raw.get("direction"), 12).lower()
    if direction not in ("upside", "downside"):
        return None
    # This renders as its own paragraph in the markdown and in the viewer, not
    # as a table cell, so the 460 that suits a cell was cutting the pass's most
    # analytical field mid-argument ("...not group demand…"). The limit here is
    # only a guard against a runaway model, not a display width.
    reason = _prose(raw.get("reason"), _PROSE_CHARS)
    if not reason:
        return None
    return {"direction": direction, "reason": reason}


def _heat_prompt(theme_row: dict, packets: list[dict], web: dict | None, ref: date) -> tuple[str, str]:
    """The per-industry user message: theme context, the packets, the snippets."""
    theme = theme_row.get("theme") or ""
    priors = {p["ticker"]: revision_side(p) for p in packets}
    lines = [
        "Return JSON keys: headline (2-4 sentences naming the strongest long setup, the best "
        "secondary setup and the weakest member, in the style of a PM's verdict), ranking (array of "
        "{ticker, rank, side, label, conviction, ranked_on, guidance_valuation, catalyst, setup, risk}), "
        "best_long and best_short (each an object {ticker, thesis, catalyst, setup, risk, conviction} "
        "carrying that trade's OWN case, not a copy of its row above; ticker null with a reason in "
        "thesis when the industry offers no credible one), "
        "tactical (one or two sentences on how to sequence these trades around the prints) and "
        "why_not_cold (an object {direction, reason}: the qualitative reason this group is NOT COLD, "
        "and it must be FORWARD-LOOKING — what happens next from here, never a description of what "
        "already happened. direction is exactly one of upside, downside and names which side that "
        "reason favours. reason is the fullest judgement you write in this pass — four to seven "
        "sentences, and it must work through, in this order: (a) the dated forward evidence, citing "
        "the specific figure and where it came from (a backlog, order book, delivery rate, capacity "
        "or price datapoint from the searched developments, the filed guidance language, or the ISM "
        "demand data); (b) what that means the NEXT prints should report — the line items and the "
        "guidance action it implies, not a direction word; (c) which named members it reaches and "
        "which one diverges from it, saying whether the divergence is idiosyncratic or the first "
        "sign the group read is wrong; (d) the observable that would flip this group to COLD — the "
        "datapoint, print or guidance change you would have to see, and roughly when. Ground every "
        "step in the searched developments, the filed text or the ISM data, never in a restatement "
        "of the 90-day revision table you were given, and cite no figure that is not in front of "
        "you. When the forward evidence genuinely points against the breadth, say so and let "
        "direction disagree with it). "
        "side is exactly one of: long, short, avoid. conviction is exactly one of: high, medium, low. "
        "rank is 1..N, 1 = best risk/reward, no ties. label is a short tag like 'Strongest long' or "
        "'Lagger — wait for evidence'. guidance_valuation is at most 200 characters on what filed "
        "guidance says and what the multiple demands of it — this becomes one cell of a table, so it "
        "must be dense and carry no price. ranked_on is at most 120 characters naming the single "
        "fundamental fact that put this name at this rank — a revision move, a beat and its trend, a "
        "guidance change or a filed operating detail; never a multiple, and never the words cheap, "
        "expensive, over-valued or under-valued. catalyst is what the next print reveals and why it "
        "matters for the side. setup is how the following quarter(s) line up. risk is what would break "
        "the call, and must state the reason whenever your side opposes the name's own revision prior.",
        f"Today: {ref.isoformat()}",
        f"Industry group: {theme} — radar status {theme_row.get('status')}, lean "
        f"{theme_row.get('lean')} (breadth {theme_row.get('breadth', 0):+.2f}; share of covered "
        f"members whose FY1 consensus rose minus fell over 90 days)",
    ]
    macro = _macro_demand_line()
    if macro:
        lines.append(macro)
        lines.append(
            "This is the survey evidence for where demand goes next — one basis for the forward-looking "
            "why_not_cold judgement, never the only one; the searched developments carry the rest."
        )
    if theme_row.get("thesis"):
        lines.append(f"Industry thesis on file: {_clip(theme_row.get('thesis'), 300)}")
    if theme_row.get("bellwether"):
        lines.append(f"Largest member printing within 14 days: {theme_row['bellwether']}")
    prints = [
        f"{p['ticker']} {(p.get('next_print') or {}).get('date')}"
        f" ({(p.get('next_print') or {}).get('days_away')}d)"
        for p in packets
        if (p.get("next_print") or {}).get("date")
    ]
    if prints:
        lines.append("Print calendar for the group (read-throughs run between these): " + "; ".join(prints))
    lines.append(
        "Revision priors (the side each name's OWN FY1 revisions imply — a prior you may override, "
        "not a rule): " + ", ".join(f"{t}={s}" for t, s in priors.items())
    )
    breadth = theme_row.get("breadth") or 0.0
    if breadth <= 0.2:
        lines.append(
            f"THIS INDUSTRY'S ESTIMATE BREADTH IS {breadth:+.2f} — not a rising group. The SHORT is the "
            "primary output here: lead the tactical line with it, and treat the long as the secondary "
            "idea. Name the long only if it stands on its own fundamentals."
        )
    else:
        lines.append(
            f"This industry's estimate breadth is {breadth:+.2f} — a rising group, so the long is the "
            "primary output. Still work the short properly: inside a rising industry the short is the "
            "member being left behind, and it is the more valuable half of the pair."
        )
    blob, budget_note = _fit_packets(packets)
    if budget_note:
        log(f"setups rank {theme}: {budget_note}")
        lines.append(budget_note)
    if len(packets) <= 2:
        lines.append(
            f"ISOLATED GROUP: this industry has only {len(packets)} member(s) on Wikipedia — there "
            "are no peers to read through to and no industry median, so the valuation flag is n/a. "
            "Judge each member in isolation: its own revisions, beat record and filed guidance, and "
            "the absolute level of its multiples measured only against the growth they assume (the "
            "hurdle and asymmetry framing still applies). Rank 1..N as given — with one member that "
            "member is rank 1 — and name a best_long or best_short only where the case genuinely "
            "stands on its own; null it with a reason otherwise."
        )
    lines.append(f"Members to rank ({len(packets)}):")
    lines.append(blob)
    if web and web.get("searches"):
        lines.append(
            "Web-search snippets for this industry and its members (developments since the filings; "
            "recency UNVERIFIED — leads, not dated facts):"
        )
        for s in web["searches"]:
            lines.append(f"- {s['title']}: {s['snippet']}" if s.get("title") else f"- {s['snippet']}")
    else:
        lines.append(
            "No web snippets available for this group — rank from the filed pack, the consensus and "
            "the revision data only, and do not speculate about news you were not given."
        )
    return _SYSTEM, "\n".join(lines)


def _row(packet: dict, item: dict | None, rank: int, note: str = "") -> dict:
    """One ranking row: deterministic cells + the model's judgement, reconciled.

    `against_revisions` is computed here from the revision prior and the
    assigned side — never read from the model, which has an obvious incentive
    to under-report going against the data.
    """
    prior = revision_side(packet)
    side = _clip((item or {}).get("side"), 12).lower()
    if side not in _SIDES:
        side = "avoid"
    conviction = _clip((item or {}).get("conviction"), 12).lower()
    if conviction not in _CONVICTIONS:
        conviction = "low" if item is None else "medium"
    # a table cell, so bounded — but cut on a word boundary, and wide enough
    # that a model overshooting the 200-character instruction still reads as
    # prose rather than as corruption ("without a demanding hurdl")
    guidance = clip_words((item or {}).get("guidance_valuation"), 320)
    val = valuation_cell(packet)
    return {
        "ticker": packet["ticker"],
        "name": packet.get("name") or "",
        "rank": rank,
        "side": side,
        "label": _clip((item or {}).get("label"), 48) or ("unranked" if item is None else ""),
        "conviction": conviction,
        "revision_prior": prior,
        "against_revisions": side in ("long", "short") and prior in ("long", "short") and side != prior,
        # factual columns, rendered from the packet — never from the model's prose
        "surprise_cell": surprise_cell(packet),
        "setup_cell": setup_cell(packet),
        "valuation_cell": val,
        # the fundamental fact the model had to name as the reason for this rank,
        # so a valuation-driven ordering cannot hide behind the narrative
        "ranked_on": clip_words((item or {}).get("ranked_on"), 180),
        "guidance_valuation": guidance,
        "guidance_valuation_cell": f"{guidance} · {val}" if guidance else val,
        "catalyst": _prose((item or {}).get("catalyst"), _CASE_CHARS),
        "setup": _prose((item or {}).get("setup"), _CASE_CHARS),
        "risk": _prose((item or {}).get("risk"), _CASE_CHARS) or note,
        "flag": (packet.get("valuation") or {}).get("flag"),
        "flag_detail": (packet.get("valuation") or {}).get("flag_detail"),
        "pe1": (packet.get("valuation") or {}).get("forward_pe_fy1"),
        "peg1": (packet.get("valuation") or {}).get("peg_fy1"),
        "eg1": (packet.get("consensus") or {}).get("growth_fy1"),
        "rev90": (packet.get("revisions") or {}).get("fy1_change_90d_pct"),
        "next_print": (packet.get("next_print") or {}).get("date"),
        "days_to_print": (packet.get("next_print") or {}).get("days_away"),
        "reports_quarter": (packet.get("next_print") or {}).get("reports_quarter"),
        "surprise_pct": ((packet.get("eps_surprise") or {}).get("last") or {}).get("surprise_pct"),
    }


def _best_pick(raw: object, side: str, by_ticker: dict[str, dict]) -> dict | None:
    """One side's headline pick with its own case, validated against the group.

    A pick naming a ticker that is not in this industry is dropped rather than
    displayed: the whole value of the pair is that each side gets its own
    reasoning about a real member. A pick with no ticker but a reason is kept —
    "no credible short here" is a legitimate and useful answer, and far better
    than an invented one.
    """
    if not isinstance(raw, dict):
        return None
    ticker = _clip(raw.get("ticker"), 12).upper()
    case = {
        "side": side,
        "thesis": _prose(raw.get("thesis"), _PROSE_CHARS),
        "catalyst": _prose(raw.get("catalyst"), _CASE_CHARS),
        "setup": _prose(raw.get("setup"), _CASE_CHARS),
        "risk": _prose(raw.get("risk"), _CASE_CHARS),
        "conviction": (_clip(raw.get("conviction"), 12).lower()
                       if _clip(raw.get("conviction"), 12).lower() in _CONVICTIONS else "medium"),
    }
    if ticker in ("", "NULL", "NONE"):
        if not case["thesis"]:
            return None
        return {**case, "ticker": "", "name": "", "none_reason": case["thesis"], "conviction": ""}
    if ticker not in by_ticker:
        log(f"setups rank: best {side} named {ticker!r}, which is not in this industry — dropped")
        return None
    packet = by_ticker[ticker]
    return {
        **case,
        "ticker": ticker,
        "name": packet.get("name") or "",
        "surprise_cell": surprise_cell(packet),
        "setup_cell": setup_cell(packet),
        "valuation_cell": valuation_cell(packet),
        "reports_quarter": (packet.get("next_print") or {}).get("reports_quarter"),
        "revision_prior": revision_side(packet),
        "against_revisions": revision_side(packet) in ("long", "short") and revision_side(packet) != side,
    }


def rank_group(theme_row: dict, quant_by_ticker: dict[str, dict], ref: date,
               model: str | None = None) -> dict:
    """One industry's ranking: deterministic packets -> one LLM call -> ordered rows.

    Every member with at least one forward fundamental input is included, with
    no side eligibility rule — a flat name is ranked too, because 'avoid' and
    'weakest of the group' are answers the pass is meant to give. A member is
    skipped only when it carries no revisions, no surprise history, no
    consensus and no filed pack: there is nothing to rank it on.
    """
    theme = theme_row.get("theme") or ""
    packets: list[dict] = []
    skipped: list[str] = []
    for m in theme_row.get("members") or []:
        ticker = m["ticker"]
        packet = member_packet(ticker, m, quant_by_ticker.get(ticker) or {}, ref)
        if not has_anything_to_rank(packet):
            skipped.append(ticker)
            continue
        packets.append(packet)
    out = {
        "theme": theme,
        "status": theme_row.get("status"),
        "lean": theme_row.get("lean"),
        "breadth": theme_row.get("breadth"),
        "thesis": theme_row.get("thesis", ""),
        "members_ranked": len(packets),
        "members_skipped": skipped,
        "headline": "",
        "tactical": "",
        "why_not_cold": None,
        # the short leads the write-up wherever the industry is not rising: a
        # falling or flat group's useful output is which member gets cut, not
        # which one is least bad
        "short_first": (theme_row.get("breadth") or 0.0) <= 0.2,
        "best_long": None,
        "best_short": None,
        "ranking": [],
        "llm_used": False,
        "model": "",
        "reasoning_effort": setups_reasoning_effort(),
        "web_queries": 0,
    }
    if not packets:
        out["headline"] = "no members with fundamental data to rank"
        return out

    def _unranked(reason: str) -> list[dict]:
        # Deterministic fallback keeps the measured table and drops only the
        # judgement, in packet order — never a made-up ranking.
        return [_row(p, None, i, note=reason) for i, p in enumerate(packets, 1)]

    if not llm_available():
        out["headline"] = "LLM unavailable — members listed with their measured fundamentals, unranked"
        out["ranking"] = _unranked("no LLM pass — the measured columns stand, the ranking does not")
        return out

    from ptm_setups.search import group_snippets

    web = group_snippets(theme, packets, ref)
    out["web_queries"] = (web or {}).get("queries", 0)
    system, user = _heat_prompt(theme_row, packets, web, ref)
    used: list[str] = []
    want = model or setups_model()
    budget = _token_budget(len(packets))
    payload = None
    # A thinking model can spend the whole allowance deliberating and answer
    # with nothing — measured on a five-name group at medium effort with a
    # 28k budget. So an empty result is retried ONCE at the ceiling budget with
    # thinking turned down to "low", which is the setting that demonstrably
    # returns content. Costs a second call only where the first produced
    # nothing, and beats shipping an industry with no ranking in it.
    for attempt, (effort, tokens) in enumerate((
        (setups_reasoning_effort(), budget),
        ("low", _TOKENS_CEILING),
    )):
        if attempt and payload is not None and (payload.get("ranking") or payload.get("best_short")):
            break
        if attempt:
            log(f"setups rank {theme}: retrying at reasoning effort 'low' with a "
                f"{tokens}-token budget — the first pass returned nothing usable")
        try:
            payload = chat_json(system, user, model=want, used_out=used, max_tokens=tokens,
                                reasoning_effort=effort, timeout=_timeout(len(packets)))
        except Exception as exc:
            log(f"setups rank {theme}: FAIL {str(exc)[:120]}")
            if attempt:
                out["headline"] = ("ranking call failed — members listed with their measured "
                                   "fundamentals, unranked")
                out["ranking"] = _unranked(
                    "ranking call failed — the measured columns stand, the ranking does not")
                return out
            payload = None
    if payload is None:
        out["headline"] = "ranking call failed — members listed with their measured fundamentals, unranked"
        out["ranking"] = _unranked("ranking call failed — the measured columns stand, the ranking does not")
        return out
    out["llm_used"] = True
    # used_out reports who actually answered: chat_json may silently fall back
    # to a smaller model, and a ranking produced by the 8B is not the ranking
    # that was asked for, so the artifact records what really ran.
    out["model"] = used[0] if used else want
    if used and used[0] != want:
        log(f"setups rank {theme}: asked for {want}, answered by {used[0]}")
    out["headline"] = _prose(payload.get("headline"), _PROSE_CHARS)
    out["tactical"] = _prose(payload.get("tactical"), _PROSE_CHARS)
    out["why_not_cold"] = _why_not_cold(payload)
    by_ticker = {p["ticker"]: p for p in packets}
    out["best_long"] = _best_pick(payload.get("best_long"), "long", by_ticker)
    out["best_short"] = _best_pick(payload.get("best_short"), "short", by_ticker)
    items: list[tuple[int, dict]] = []
    seen: set[str] = set()
    for item in payload.get("ranking") or []:
        if not isinstance(item, dict):
            continue
        ticker = _clip(item.get("ticker"), 12).upper()
        if ticker not in by_ticker or ticker in seen:
            continue
        seen.add(ticker)
        try:
            rank = int(item.get("rank"))
        except (TypeError, ValueError):
            rank = len(items) + 1
        items.append((rank, item))
    # Trust the model's ORDER, not its integers: ties and gaps get renumbered
    # 1..N so the table and the leaderboard always read cleanly.
    items.sort(key=lambda pair: pair[0])
    rows = [_row(by_ticker[_clip(item.get("ticker"), 12).upper()], item, i) for i, (_, item) in enumerate(items, 1)]
    for p in packets:  # coverage: a member the model dropped is recorded, not lost
        if p["ticker"] not in seen:
            rows.append(_row(p, None, len(rows) + 1, note="not covered by the ranking pass — measured columns only"))
    out["ranking"] = rows
    if not seen:
        # Every row fell through to the coverage fallback, so the call produced
        # nothing usable. The overwhelmingly likely cause is a truncated reply
        # (the budget above), and the failure is otherwise indistinguishable
        # from a genuine ranking of "avoid" — so name it here and in the file.
        out["headline"] = out["headline"] or (
            "the ranking pass returned no usable entries — likely a truncated reply; "
            "the measured columns stand, the ranking does not"
        )
        log(f"setups rank {theme}: WARNING the pass returned no usable ranking entries "
            f"(model {out['model']}, budget {budget} tokens) — the measured table stands, "
            f"the ordering does not; retry with a larger budget or a different model")
    against = sum(1 for r in rows if r["against_revisions"])
    log(f"setups rank {theme}: {len(rows)} member(s) ranked"
        + (f", {against} against their own revisions" if against else "")
        + (f", {len(skipped)} skipped (no data)" if skipped else ""))
    return out


# ------------------------------------------------------------------- the final

def _final_candidates(groups: list[dict]) -> list[dict]:
    """The best long and the best short from each industry — the heats' winners.

    Ranking every name across every industry would drown the final in the tail;
    each industry sends its top-ranked long and its top-ranked short, which is
    also the only comparison the leaderboard has to make.
    """
    out = []
    for g in groups:
        if not g.get("llm_used"):
            continue  # an unranked group has no winner to send
        rows = g.get("ranking") or []
        for side in ("long", "short"):
            # Prefer the pick the industry pass explicitly DECLARED for this
            # side over the top row that happens to carry it: the declared pick
            # is the considered choice and comes with its own thesis. The row is
            # still what travels, because it carries the numeric fields the
            # final compares — so the two are matched by ticker and merged.
            declared = (g.get(f"best_{side}") or {}).get("ticker") or ""
            best = next((r for r in rows if r["ticker"] == declared and declared), None)
            if best is None:
                best = next((r for r in rows if r["side"] == side), None)
            if best is None:
                continue
            pick = g.get(f"best_{side}") or {}
            out.append({
                **best,
                "theme": g["theme"],
                "theme_status": g.get("status"),
                "theme_breadth": g.get("breadth"),
                # the declared pick's own thesis, where it named one
                "thesis": pick.get("thesis") or "",
                "declared": bool(declared) and best["ticker"] == declared,
                # a side the industry pass called primary carries more weight
                "primary_side": "short" if g.get("short_first") else "long",
            })
    return out


def _fit_final(candidates: list[dict], plain) -> str:
    """The final round's candidate JSON, kept valid by shortening the prose.

    Same rule as the industry prompts: never slice the JSON. Here the only
    compressible part is each candidate's inherited reasoning, so that is what
    gives way — the measured fields the ranking compares are never touched.
    """
    rows = [plain(c) for c in candidates]
    blob = json.dumps(rows, default=str)
    if len(blob) <= _PACKET_CHARS:
        return blob
    for limit in (200, 100, 0):
        for r in rows:
            case = r.get("industry_case") or {}
            for key in list(case):
                case[key] = str(case[key] or "")[:limit] if limit else None
            if not limit:
                r.pop("industry_case", None)
        blob = json.dumps(rows, default=str)
        if len(blob) <= _PACKET_CHARS:
            break
    log(f"setups final: candidate reasoning shortened to fit the prompt budget")
    return blob


def _final_round(candidates: list[dict], ref: date, model: str | None = None) -> dict:
    """One cross-industry pass over the heats' winners -> ranked longs and shorts."""
    out: dict = {"summary": "", "longs": [], "shorts": [], "llm_used": False, "model": "",
                 "candidates": len(candidates)}
    if not candidates:
        out["summary"] = "no ranked industry winners to compare"
        return out

    def _plain(c: dict) -> dict:
        return {
            "ticker": c["ticker"], "name": c["name"], "industry": c["theme"], "side": c["side"],
            "industry_rank": c["rank"], "industry_label": c["label"], "conviction": c["conviction"],
            "last_eps_surprise_pct": c.get("surprise_pct"),
            "fy1_consensus_change_90d_pct": c.get("rev90"),
            "consensus_growth_fy1": c.get("eg1"),
            "forward_pe_fy1": c.get("pe1"), "peg_fy1": c.get("peg1"),
            "valuation_vs_industry": c.get("flag"),
            "next_print": c.get("next_print"), "days_to_print": c.get("days_to_print"),
            "reports_quarter": c.get("reports_quarter"),
            "against_own_revisions": c.get("against_revisions"),
            # whether its own industry pass named this side its primary call,
            # so the final can weigh a declared short in a falling group above
            # an incidental one in a rising group
            "its_industry_called_this_side_primary": c.get("primary_side") == c.get("side"),
            "industry_case": {"ranked_on": c.get("ranked_on"),
                              "thesis": c.get("thesis"),
                              "guidance_valuation": c.get("guidance_valuation"),
                              "catalyst": c.get("catalyst"), "risk": c.get("risk")},
        }

    if not llm_available():
        out["summary"] = "LLM unavailable — industry winners listed unranked"
        out["longs"] = [{"ticker": c["ticker"], "theme": c["theme"], "rank": i, "why": ""}
                        for i, c in enumerate([c for c in candidates if c["side"] == "long"], 1)]
        out["shorts"] = [{"ticker": c["ticker"], "theme": c["theme"], "rank": i, "why": ""}
                         for i, c in enumerate([c for c in candidates if c["side"] == "short"], 1)]
        return out
    user = "\n".join([
        "Return JSON keys: summary (2-4 sentences on where the best risk/reward sits across these "
        "industries and which cases overlap), longs (array of {ticker, rank, why}) and shorts (array "
        "of {ticker, rank, why}). Rank each side 1..N, 1 = best, no ties, every candidate placed.",
        f"Today: {ref.isoformat()}",
        f"Candidates ({len(candidates)}), each already the best of its side inside its own industry:",
        _fit_final(candidates, _plain),
    ])
    used: list[str] = []
    want = model or setups_model()
    try:
        payload = chat_json(_FINAL_SYSTEM, user, model=want, used_out=used,
                            max_tokens=_token_budget(len(candidates)),
                            reasoning_effort=setups_reasoning_effort(),
                            timeout=_timeout(len(candidates)))
    except Exception as exc:
        log(f"setups final: FAIL {str(exc)[:120]}")
        out["summary"] = "cross-industry pass failed — industry winners listed unranked"
        out["longs"] = [{"ticker": c["ticker"], "theme": c["theme"], "rank": i, "why": ""}
                        for i, c in enumerate([c for c in candidates if c["side"] == "long"], 1)]
        out["shorts"] = [{"ticker": c["ticker"], "theme": c["theme"], "rank": i, "why": ""}
                         for i, c in enumerate([c for c in candidates if c["side"] == "short"], 1)]
        return out
    out["llm_used"] = True
    out["model"] = used[0] if used else want
    if used and used[0] != want:
        log(f"setups final: asked for {want}, answered by {used[0]}")
    out["summary"] = _prose(payload.get("summary"), _PROSE_CHARS)
    by_side = {"long": {}, "short": {}}
    for c in candidates:
        by_side.setdefault(c["side"], {})[c["ticker"]] = c
    for key, side in (("longs", "long"), ("shorts", "short")):
        pool = by_side.get(side) or {}
        picked: list[tuple[int, dict]] = []
        seen: set[str] = set()
        for item in payload.get(key) or []:
            if not isinstance(item, dict):
                continue
            ticker = _clip(item.get("ticker"), 12).upper()
            if ticker not in pool or ticker in seen:
                continue
            seen.add(ticker)
            try:
                rank = int(item.get("rank"))
            except (TypeError, ValueError):
                rank = len(picked) + 1
            picked.append((rank, {"ticker": ticker, "theme": pool[ticker]["theme"],
                                  "why": clip_words(item.get("why"), 300)}))
        picked.sort(key=lambda pair: pair[0])
        rows = [{**row, "rank": i} for i, (_, row) in enumerate(picked, 1)]
        for ticker, c in pool.items():  # a candidate the model dropped still appears
            if ticker not in seen:
                rows.append({"ticker": ticker, "theme": c["theme"], "rank": len(rows) + 1,
                             "why": "not placed by the cross-industry pass"})
        out[key] = rows
    log(f"setups final: {len(out['longs'])} long(s) and {len(out['shorts'])} short(s) ranked "
        f"across {len({c['theme'] for c in candidates})} industry group(s)")
    return out


# ------------------------------------------------------------------- markdown

_HOW_TO_READ = [
    "",
    "## How to read this",
    "- **One pass, not one per name.** Every member of the industry was ranked against the others in a "
    "single call, from the same measured inputs — the last print's EPS surprise and the four-quarter "
    "beat record, the name's own FY1 consensus change over 90 and 30 days with the analyst up/down "
    "counts, consensus growth, filed guidance from the latest EDGAR pack, and forward P/E, PEG and P/S "
    "against the industry median. There is no per-name deep dive behind these rows.",
    "- **The factual columns are computed, not written.** Latest earnings surprise, print setup and the "
    "multiples in the guidance/valuation cell are rendered from the cached data; the model supplies only "
    "the guidance read, the ordering and the narrative. A number in those columns is measured.",
    "- **Fundamentals only, no price action.** No technicals, no moving averages, no momentum or trend "
    "reads, no support or resistance, no price targets — the pass is never shown a price. The third "
    "column is the print SETUP (how expectations are moving into the print), which is where a trend "
    "column would otherwise sit.",
    "- **Valuation is a hurdle and an asymmetry, never a score.** A premium multiple is usually the "
    "market correctly paying for better growth or durability, and a discount is usually a correct "
    "mark-down, so the level of the multiple is not itself bullish or bearish. It counts in two ways: a "
    "high multiple needs a bigger beat and a raise to hold, and the multiple sizes the damage if the "
    "driver it assumes breaks. Cheapness is not a catalyst inside three months.",
    "- **The best long and the best short are separate calls.** Each gets its own thesis, catalyst, "
    "setup and risk rather than a share of one ranking narrative, because they are two different "
    "trades. The short leads wherever the industry's estimate breadth is flat or negative: in a group "
    "that is not rising, the useful answer is which member's expectations get cut, and the tactical "
    "line leads with it. \"None in this industry\" is a real answer — an admitted absence beats an "
    "invented short.",
    "- **The side is the pass's call, not the revision rule's.** A ⚠ marks a name whose assigned side "
    "opposes the direction of its own FY1 revisions — the pass thinks it knows something the estimate "
    "trend has not caught up with, and the risk column has to say what.",
    "- Commentary, not a gate: nothing downstream reads this ranking to include or drop a name.",
]


def _rank_table(rows: list[dict]) -> list[str]:
    lines = [
        "| # | Ticker | Latest earnings surprise | Guidance / valuation | Print setup | Side | Risk/reward ranking |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        flagged = " ⚠" if r["against_revisions"] else ""
        label = r["label"] or ("unranked" if r["side"] == "avoid" else "")
        lines.append(
            f"| **#{r['rank']}** | **{r['ticker']}** | {r['surprise_cell']} | "
            f"{str(r['guidance_valuation_cell']).replace('|', '/')} | {r['setup_cell']} | "
            f"{r['side']}{flagged} | **{str(label).replace('|', '/')}** |"
        )
    return lines


def _one_pick_md(pick: dict | None, side: str, primary: bool) -> list[str]:
    """The best long or best short as its own section, with its own case."""
    label = "Best short" if side == "short" else "Best long"
    rank_note = " — the primary call for this industry" if primary else " — the secondary call"
    if not pick:
        return [f"## {label}", "", f"*(the pass named none)*", ""]
    if not pick.get("ticker"):
        return [f"## {label}", "", f"**None in this industry.** {pick.get('none_reason', '')}", ""]
    who = pick["ticker"] + (f" ({pick['name']})" if pick.get("name") else "")
    head = f"## {label}{rank_note}: {who}"
    lines = [head, ""]
    meta = [f"conviction {pick['conviction']}"] if pick.get("conviction") else []
    if pick.get("against_revisions"):
        meta.append(f"⚠ against its own revisions ({pick.get('revision_prior')} prior)")
    if meta:
        lines += [" · ".join(meta), ""]
    if pick.get("thesis"):
        lines.append(f"* **Thesis:** {pick['thesis']}")
    if pick.get("catalyst"):
        lines.append(f"* **The catalyst:** {pick['catalyst']}")
    if pick.get("setup"):
        lines.append(f"* **Setup:** {pick['setup']}")
    if pick.get("risk"):
        lines.append(f"* **Risk:** {pick['risk']}")
    facts = [x for x in (pick.get("surprise_cell"), pick.get("setup_cell"), pick.get("valuation_cell")) if x]
    if facts:
        lines += ["", "| measured | |", "|---|---|"]
        for name, value in (("Latest earnings surprise", pick.get("surprise_cell")),
                            ("Print setup", pick.get("setup_cell")),
                            ("Valuation vs industry", pick.get("valuation_cell"))):
            if value:
                lines.append(f"| {name} | {str(value).replace('|', '/')} |")
    lines.append("")
    return lines


def _best_pick_md(group: dict) -> list[str]:
    """Both headline picks, the more important side first.

    Order is not cosmetic: in an industry whose estimate breadth is flat or
    negative the useful answer is which member gets cut, so the short leads and
    the long follows. In a rising industry the reverse.
    """
    if not group.get("llm_used"):
        return []
    short_first = bool(group.get("short_first"))
    blocks: list[str] = []
    order = (("short", group.get("best_short")), ("long", group.get("best_long"))) if short_first else \
            (("long", group.get("best_long")), ("short", group.get("best_short")))
    for i, (side, pick) in enumerate(order):
        blocks += _one_pick_md(pick, side, primary=(i == 0))
    if group.get("tactical"):
        blocks += [f"**Tactical trade idea:** {group['tactical']}", ""]
    return blocks


def _group_md(group: dict, ref: date):
    """One industry's ranking markdown, written under ideas/setups/<industry>/."""
    rows = group.get("ranking") or []
    lines = [
        f"# Ranked setups — {group['theme']}\n",
        f"*Group-only fundamental ranking · {ref.isoformat()} · ONE pass over all "
        f"{group.get('members_ranked', 0)} member(s) of this non-COLD industry, ordered as long and "
        f"short setups into the next print and the 0-3 months around it. Fundamentals, filed guidance, "
        f"consensus revisions and valuation only — no technicals, no price action, no per-name deep "
        f"dive. Commentary, not a gate.*\n",
        f"**Industry**: {group.get('status', 'n/a')}, lean {group.get('lean', '?')} "
        f"(breadth {group.get('breadth', 0):+.2f}) · {group.get('members_ranked', 0)} ranked"
        + (f" · no fundamental data, skipped: {', '.join(group['members_skipped'])}"
           if group.get("members_skipped") else "")
        + (f" · {group['web_queries']} web query(ies)" if group.get("web_queries") else "")
        + (f" · model {group['model']}" if group.get("model") else ""),
    ]
    if group.get("thesis"):
        lines.append(f"**Industry thesis on file**: {group['thesis']}")
    lines += ["", group.get("headline") or "*(no headline — the ranking pass did not run)*", ""]
    wnc = group.get("why_not_cold") or {}
    if wnc.get("reason"):
        lines.append(f"**Why this group is not COLD ({wnc.get('direction', '?')}):** {wnc['reason']}")
        lines.append("")
    lines += _best_pick_md(group)
    if rows:
        lines += ["## The full ranking", ""] + _rank_table(rows) + ["", "---", ""]
        for r in rows:
            who = f"{r['ticker']}" + (f" ({r['name']})" if r["name"] else "")
            head = f"**{r['rank']}. {who}"
            if r["label"]:
                head += f" — {r['label']}"
            head += f"** · {r['side']}"
            if r["conviction"]:
                head += f" · conviction {r['conviction']}"
            if r["against_revisions"]:
                head += f" · ⚠ against its own revisions ({r['revision_prior']} prior)"
            lines.append(head)
            lines.append("")
            if r.get("catalyst"):
                lines.append(f"* **The catalyst:** {r['catalyst']}")
            if r.get("setup"):
                lines.append(f"* **Setup:** {r['setup']}")
            if r.get("risk"):
                lines.append(f"* **Risk:** {r['risk']}")
            if r.get("ranked_on"):
                lines.append(f"* **Ranked on:** {r['ranked_on']}")
            detail = []
            if r.get("reports_quarter"):
                detail.append(f"next print reports {r['reports_quarter']}")
            if r.get("flag_detail"):
                detail.append(f"valuation: {r['flag_detail']}")
            if detail:
                lines.append(f"* *{' · '.join(detail)}*")
            lines.append("")
    if group.get("tactical") and not group.get("llm_used"):
        # normally the tactical line sits with the two picks above; this covers
        # the degraded path, where there are no picks to sit with
        lines += [f"**Tactical trade idea:** {group['tactical']}", ""]
    lines += _HOW_TO_READ
    theme_dir = setups_ideas_dir(_slug(group["theme"]))
    path = theme_dir / f"_RANKING_{ref.isoformat()}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _leaderboard_md(payload: dict, ref: date):
    """The cross-industry leaderboard: best longs and best shorts, one file."""
    final = payload.get("leaderboard") or {}
    by_ticker = {
        r["ticker"]: {**r, "theme": g["theme"]}
        for g in payload.get("groups") or []
        for r in g.get("ranking") or []
    }
    lines = [
        f"# Best setups into the next print — {ref.isoformat()}\n",
        f"*Cross-industry final over the winners of {len(payload.get('groups') or [])} industry "
        f"ranking(s): each non-COLD industry's best long and best short, ranked against each other for "
        f"the next print and the 0-3 months around it. Fundamentals, filed guidance, consensus "
        f"revisions and valuation only — no technicals, no price action. Commentary, not a gate.*\n",
        final.get("summary") or "*(no cross-industry summary — the final pass did not run)*",
        "",
    ]
    for title, key in (("Best longs", "longs"), ("Best shorts", "shorts")):
        rows = final.get(key) or []
        lines += [f"## {title}", ""]
        if not rows:
            lines += ["*(none)*", ""]
            continue
        lines += [
            "| # | Ticker | Industry | Latest earnings surprise | Guidance / valuation | Print setup | Why it ranks here |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in rows:
            src = by_ticker.get(row["ticker"]) or {}
            flagged = " ⚠" if src.get("against_revisions") else ""
            lines.append(
                f"| **#{row['rank']}** | **{row['ticker']}**{flagged} | {row.get('theme', '')} | "
                f"{src.get('surprise_cell', '—')} | "
                f"{str(src.get('guidance_valuation_cell', '—')).replace('|', '/')} | "
                f"{src.get('setup_cell', '—')} | {str(row.get('why', '')).replace('|', '/')} |"
            )
        lines.append("")
    lines += [
        "## Per-industry rankings",
        "",
    ]
    for g in payload.get("groups") or []:
        lines.append(
            f"- **{g['theme']}** — {g.get('members_ranked', 0)} ranked · "
            f"`{_slug(g['theme'])}/_RANKING_{ref.isoformat()}.md`"
        )
    lines += _HOW_TO_READ
    path = setups_ideas_dir() / f"_LEADERBOARD_{ref.isoformat()}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ------------------------------------------------------------------- the pass

def run_setups(source: str = "manual", ref: date | None = None, theme: str | None = None,
               with_final: bool = True, model: str | None = None) -> dict:
    """Rank every non-COLD industry (or one), then rank the winners across them.

    Reads the quant table the deterministic front half wrote — the same
    artifact the simple process reads, so both layers judge identical numbers.
    Members lacking an expectations cache or a print date are backfilled first
    (the simple process's own helper), so the ranking sees the whole industry
    rather than only the names an earlier run happened to cover.
    """
    from ptm.asof import as_of_date
    from ptm.config import data_dir
    from ptm_simple import simple_dir
    from ptm_simple.group_review import _ensure_expectations
    from ptm_simple.radar import _fundamentals, theme_radar
    from ptm_simple.run import load_theme_map

    ref = ref or as_of_date()
    theme_map = load_theme_map(source)
    quant_path = simple_dir(f"quant_{ref.isoformat()}.json")
    if not quant_path.exists():
        # Name the dates that DO have one. The viewer's button always asks for
        # today, so this is the first thing a new user hits, and "run the radar"
        # alone does not tell them that an earlier run date is right there.
        have = sorted(p.stem.replace("quant_", "") for p in simple_dir().glob("quant_*.json"))
        hint = (f" Tables exist for: {', '.join(have[-5:])} — rerun with --day <date> to use one."
                if have else " No quant table exists for any date yet.")
        raise SystemExit(
            f"no quant table for {ref.isoformat()}: run '1 - Run radar' then "
            f"'2 - Refresh fundamentals' for this date first.{hint}"
        )
    quant_doc = json.loads(quant_path.read_text(encoding="utf-8"))
    quant_by_ticker = {row["ticker"]: row for row in quant_doc.get("rows") or []}
    # Same universe rule as the group review: the themes the quant table was
    # built over, not today's recomputed status — the backfill below adds
    # covered members, and a theme that was WARM at sweep time can read COLD
    # once its newly covered names dilute its breadth.
    theme_names = set(quant_doc.get("themes") or [])
    fund = _fundamentals()
    entries = [theme_radar(entry, fund, ref) for entry in theme_map["themes"]]

    def _needs_date(ticker: str) -> bool:
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
        for row in entries if _in_universe(row)
        for m in row["members"]
        if not m.get("covered") or _needs_date(m["ticker"])
    })
    if to_fix:
        log(f"setups: {len(to_fix)} member(s) missing expectations or a print date — backfilling first")
        _ensure_expectations(to_fix)
        entries = [theme_radar(entry, fund, ref) for entry in theme_map["themes"]]

    rows = [row for row in entries if _in_universe(row)]
    log(f"setups: ranking {len(rows)} industry group(s) at {ref.isoformat()} on "
        f"{model or setups_model()} — one pass each, no per-name dives")
    out = setups_dir(f"setups_{ref.isoformat()}.json")
    payload = {
        "as_of": ref.isoformat(),
        "map_source": theme_map.get("source", ""),
        "note": "Group-only fundamental ranking: one pass per non-COLD industry ordering its members "
        "as long/short setups into the next print (0-3 months), then one cross-industry final over the "
        "winners. Fundamentals, filed guidance, consensus revisions and valuation only — no technicals, "
        "no price action, no per-name deep dive. Commentary, not a gate.",
        "groups": [],
        "leaderboard": {},
    }
    # Persist per industry rather than at the end. At medium reasoning a full
    # sweep is ~20 minutes of LLM work, and writing only after the last group
    # meant a failure at industry 11 threw away all eleven. Each finished group
    # writes its own markdown and rewrites the aggregate, so an interrupted run
    # leaves everything it actually completed — and the viewer, which reads the
    # aggregate, fills in as the sweep progresses instead of staying empty.
    groups: list[dict] = payload["groups"]
    paths = []
    for row in rows:
        group = rank_group(row, quant_by_ticker, ref, model=model)
        groups.append(group)
        if group.get("members_ranked"):
            paths.append(_group_md(group, ref))
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if with_final:
        payload["leaderboard"] = _final_round(_final_candidates(groups), ref, model=model)
    else:
        payload["leaderboard"] = {"summary": "cross-industry final skipped", "longs": [], "shorts": [],
                                  "llm_used": False, "candidates": 0}
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _leaderboard_md(payload, ref)
    ranked = sum(len(g.get("ranking") or []) for g in groups)
    judged = sum(1 for g in groups if g.get("llm_used"))
    log(f"setups: {len(groups)} group(s), {ranked} member(s) ranked, {judged} group(s) judged by LLM "
        f"-> {out.name}, {len(paths)} ranking markdown + leaderboard")
    return {
        "groups": len(groups),
        "ranked": ranked,
        "llm_groups": judged,
        "longs": len((payload["leaderboard"] or {}).get("longs") or []),
        "shorts": len((payload["leaderboard"] or {}).get("shorts") or []),
        "markdown": len(paths) + 1,
        "file": out.name,
    }
