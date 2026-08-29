"""Macro / ISM / PTM-dashboard context for the deep dive.

The weekly pipeline already turns ISM reports and FRED/yahoo series into a
scored dashboard (`ptm/macro.py`) with per-sector tilts (`ptm/ingest/ism_sectors.py`).
This module projects that state onto ONE ticker:

  * which way the ISM sector tilt points for the company's GICS sector,
  * which ISM industries the company's industry string matches,
  * what purchasing managers in its sector actually said,
  * the headline macro prints (PMI, NMI, new orders, curve, VIX, permits).

The deterministic part builds the context; one LLM pass then works out how the
backdrop transmits into THIS company's fundamentals. Nothing here fetches
anything new — it reads what `ptm weekly` already wrote.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ptm.config import data_dir
from ptm.deepsearch.models import MacroImplication, MacroView
from ptm.ingest.ism_sectors import industry_match
from ptm.io import read_json
from ptm.llm import JSON_HINT
from ptm.log import log

IMPACT_SYSTEM = (
    "You are a macro-driven equity analyst. You receive the PTM macro dashboard state "
    "(ISM PMI/NMI, new orders, yield curve, building permits, consumer sentiment, VIX), the ISM "
    "sector tilt for THIS company, and matched respondent comments. Explain concretely how the "
    "CURRENT macro backdrop transmits into THIS company's fundamentals over the next 2-4 "
    "quarters: demand for its products, pricing power, input costs, margins, capex, or financing "
    "costs. Rules: one implication per channel; name the channel precisely; direction is "
    "'helps' or 'hurts' this company's fundamentals (not the stock price); if the ISM sector "
    "tilt contradicts the company-specific findings, say that in the narrative. " + JSON_HINT
)


def _load_state() -> dict:
    """Curated macro/ISM files as written by `ptm weekly`, or an empty state."""
    state: dict = {"snapshot": None, "ism": None, "as_of": ""}
    snap_path = data_dir("curated", "macro_snapshot.json")
    ism_path = data_dir("curated", "ism.json")
    if snap_path.exists():
        try:
            state["snapshot"] = read_json(snap_path)
            state["as_of"] = str(snap.get("as_of") or "") if (snap := state["snapshot"]) else ""
        except Exception:
            state["snapshot"] = None
    if ism_path.exists():
        try:
            state["ism"] = read_json(ism_path)
            if not state["as_of"]:
                state["as_of"] = str(state["ism"].get("run_date") or "")
        except Exception:
            state["ism"] = None
    return state


def build_macro_view(sector: str, industry: str) -> MacroView:
    """Deterministic projection of the dashboard onto one ticker."""
    state = _load_state()
    snap = state.get("snapshot") or {}
    ism = state.get("ism") or {}
    if not snap and not ism:
        return MacroView(available=False, reason="no macro_snapshot.json / ism.json; run `ptm ingest` or `ptm weekly` first")
    view = MacroView(available=bool(snap or ism))
    view.snapshot_notes = [str(n) for n in (snap.get("notes") or [])]

    if snap:
        view.bias = str(snap.get("bias") or "")
        view.pmi = snap.get("ism_pmi")
        view.nmi = snap.get("ism_nmi")
        view.new_orders = snap.get("ism_new_orders")
        view.tens_minus_twos = snap.get("tens_minus_twos")
        view.vix = snap.get("vix")
        view.spx_in_bear = snap.get("in_bear")
        view.ism_report_month = str(snap.get("ism_report_month") or "")

    # ISM sector tilt: from the saved snapshot when present, else recompute.
    tilts = list(snap.get("sector_tilts") or [])
    if not tilts and ism:
        try:
            from ptm.ingest.ism_sectors import compute_sector_tilts

            tilts = compute_sector_tilts(ism, pmi=view.pmi)
        except Exception:
            tilts = []
    if sector:
        for row in tilts:
            if row.get("sector") == sector and not row.get("industry"):
                view.sector_tilt = str(row.get("tilt") or "")
                view.sector_score = float(row.get("score") or 0.0)
                view.sector_why = str(row.get("why") or "")
                break
        if ism:
            # industries this company's industry string matches
            try:
                from ptm.ingest.ism_sectors import compute_industry_tilts

                for flag in compute_industry_tilts(ism):
                    if industry_match(industry, str(flag.get("industry") or "")):
                        view.industry_flags.append(flag)
            except Exception:
                pass
            # respondent comments mapped to the sector
            for report_key in ("manufacturing", "services"):
                for comment in (ism.get(report_key) or {}).get("comments") or []:
                    from ptm.ingest.ism_sectors import gics_for_ism

                    if gics_for_ism(str(comment.get("industry") or "")) == sector:
                        view.respondent_comments.append(comment)
    return view


def prompt_block(view: MacroView) -> str:
    """The macro backdrop as compact text for the analysis prompts."""
    lines: list[str] = []
    if view.bias:
        lines.append(f"Market regime bias (deterministic dashboard): {view.bias}")
    metrics = []
    if view.pmi is not None:
        metrics.append(f"ISM Manufacturing PMI {view.pmi:.1f}")
    if view.nmi is not None:
        metrics.append(f"ISM Services NMI {view.nmi:.1f}")
    if view.new_orders is not None:
        metrics.append(f"Manufacturing new orders {view.new_orders:.1f} (50 = flat)")
    if view.tens_minus_twos is not None:
        metrics.append(f"10y-2y curve {view.tens_minus_twos:+.2f}")
    if view.vix is not None:
        metrics.append(f"VIX {view.vix:.1f}")
    if metrics:
        lines.append("Latest prints: " + "; ".join(metrics) + ".")
    if view.spx_in_bear is not None:
        lines.append("S&P 500 below its 20% bear level." if view.spx_in_bear else "S&P 500 above its 20% bear level.")
    if view.sector_tilt:
        lines.append(f"ISM sector tilt for {view.sector or 'this sector'}: {view.sector_tilt} ({view.sector_why or 'no reason recorded'})")
    for flag in view.industry_flags[:3]:
        lines.append(f"ISM industry flag: {flag.get('why') or ''}")
    for comment in view.respondent_comments[:3]:
        lines.append(f"ISM purchasing manager ({comment.get('industry')}): {(comment.get('quote') or '')[:220]}")
    if view.snapshot_notes:
        lines.append("Dashboard notes: " + " | ".join(view.snapshot_notes[:6]))
    return "\n".join(f"- {ln}" for ln in lines)


def llm_impact(view: MacroView, findings: list[dict], filing_context: str, who: str, sector: str) -> MacroView:
    """One LLM pass: how the backdrop transmits into this company's fundamentals.

    Mutates and returns the view. Raises on LLM failure so the caller decides
    how to degrade.
    """
    from ptm.deepsearch.analysis import findings_block, _call_json

    payload = _call_json(
        IMPACT_SYSTEM,
        f"Company: {who} (GICS sector: {sector or 'unknown'})\n\n"
        f"Macro / ISM backdrop (from the PTM dashboard):\n{prompt_block(view)}\n\n"
        f"Company findings for context (numbered):\n{findings_block(findings)[:12000]}\n\n"
        f"SEC-filing context:\n{filing_context[:2000]}\n\n"
        'Write JSON: {"narrative": "2-4 sentences on how the macro backdrop affects THIS company\'s '
        'fundamentals, mentioning the strongest channel(s) by name", '
        '"implications": [{"channel": "e.g. end-market demand|pricing power|input costs|order backlog|'
        'working capital|capex|financing costs", "direction": "helps|hurts|mixed", '
        '"why": "one sentence, mechanical and specific"}]} with at most 6 implications.',
    )
    view.narrative = str(payload.get("narrative") or "").strip()[:1200]
    for imp in (payload.get("implications") or [])[:6]:
        if not str(imp.get("channel") or "").strip():
            continue
        view.implications.append(
            MacroImplication(
                channel=str(imp.get("channel")).strip()[:80],
                direction=str(imp.get("direction") or "mixed").strip().lower()[:8],
                why=str(imp.get("why") or "").strip()[:300],
            )
        )
    view.llm_used = True
    return view


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def manifest_note(view: MacroView) -> str:
    return json.dumps({"sector_tilt": view.sector_tilt, "bias": view.bias})