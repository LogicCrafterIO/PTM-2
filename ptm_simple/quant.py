"""Deterministic quant snapshot for the simple process.

No LLM, no network: every input comes from the cached fundamentals table the
main process already ingested (data/curated/yahoo_fundamentals.csv — EDGAR
XBRL levels + analyst consensus forward EPS) and from the radar's member rows.
The formulas are the main process's own (ptm.formulas), applied the same way
ptm.quant.build_candidates applies them — forward EPS expectations (FY1/FY2),
growth (EG1/EG2), PE1/PE2, PEG1/PEG2 — plus price-to-sales, which the PTM
screen does not compute.

The output is a reference table, NOT a ranking: it does not select, gate,
order or score anything in the process. It answers "what does the market
charge for this name's fundamentals" so the qual brief can be read against it.
"""

from __future__ import annotations

import json
from datetime import date

from ptm.formulas import earnings_growth, peg, pe
from ptm.log import log


def _num(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        out = float(value)
        if out != out or out in (float("inf"), float("-inf")):  # NaN / inf
            return None
        return out
    except (TypeError, ValueError):
        return None


def quant_path(ref: date):
    from ptm_simple import simple_dir

    return simple_dir(f"quant_{ref.isoformat()}.json")


def load_quant(ref) -> dict | None:
    path = quant_path(ref)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _quant_row(ticker: str, member: dict, fund: dict | None) -> dict:
    """One ticker's deterministic numbers, mirroring ptm.quant.build_candidates."""
    row = {
        "ticker": ticker,
        "rev90": member.get("rev90"),
        "days_to_print": member.get("days_to_print"),
        "earnings_date": member.get("earnings_date"),
        "covered": member.get("covered", False),
    }
    if not fund:
        row["note"] = "no cached fundamentals — run the main pipeline's ingest first"
        return row

    def _txt(v) -> str:
        # a blank CSV cell reads back as NaN, which is TRUTHY — guard it or the
        # row carries the literal string "nan" as its industry
        return "" if v is None or v != v else str(v)

    price = _num(fund.get("price"))
    market_cap = _num(fund.get("market_cap"))
    revenue = _num(fund.get("revenue"))
    eps0 = _num(fund.get("trailing_eps"))
    eps1 = _num(fund.get("forward_eps"))
    eps2 = _num(fund.get("forward_eps2"))
    est_eg1 = _num(fund.get("eg1"))
    est_eg2 = _num(fund.get("eg2"))
    # Same fallback chain as the PTM screen: consensus eg1/eg2 win; only
    # derive when the consensus column is absent.
    if eps2 is None and eps1 is not None and est_eg1 is not None:
        eps2 = eps1 * (1.0 + est_eg1)
    eg1 = est_eg1 if est_eg1 is not None else earnings_growth(eps1, eps0)
    eg2 = est_eg2 if est_eg2 is not None else (earnings_growth(eps2, eps1) if eps2 is not None else None)
    pe1 = pe(price, eps1)
    pe2 = pe(price, eps2)
    row.update(
        {
            "name": _txt(fund.get("name")),
            "sector": _txt(fund.get("sector")),
            "industry": _txt(fund.get("industry")),
            "price": price,
            "market_cap": market_cap,
            "revenue": revenue,
            "ps": (market_cap / revenue) if (market_cap and revenue and revenue > 0) else None,
            "eps0": eps0,
            "eps1": eps1,
            "eps2": eps2,
            "eg1": eg1,
            "eg2": eg2,
            "pe1": pe1,
            "pe2": pe2,
            "peg1": peg(pe1, eg1),
            "peg2": peg(pe2, eg2),
            "forward_source": str(fund.get("forward_source") or ""),
            "fundamentals_as_of": str(fund.get("as_of") or ""),
        }
    )
    return row


def _flag_rows(rows: list[dict]) -> None:
    """Attach a deterministic premium/discount flag to each row, THEME-relative.

    A name's P/E and PEG are compared with the median of its own theme (the
    unit of analysis here): >= 1.5x the theme median reads "premium", <= 0.67x
    "discount", both at once "mixed", otherwise "fair". No theme median (too
    few covered members with a multiple) leaves the flag "n/a". The flag is a
    pointer for the qual report — it never gates, ranks or selects anything;
    whether the premium/discount is justified is a judgement the brief and the
    dive support, not an automatic one."""
    by_theme: dict[str, list[dict]] = {}
    for r in rows:
        by_theme.setdefault(r.get("theme") or "", []).append(r)
    for theme_rows in by_theme.values():
        pes = sorted(r["pe1"] for r in theme_rows if r.get("pe1"))
        pegs = sorted(r["peg1"] for r in theme_rows if r.get("peg1") is not None)
        med_pe = pes[len(pes) // 2] if len(pes) >= 3 else None
        med_peg = pegs[len(pegs) // 2] if len(pegs) >= 3 else None
        for r in theme_rows:
            ratios = []
            bits = []
            if r.get("pe1") and med_pe:
                ratios.append(r["pe1"] / med_pe)
                bits.append(f"P/E {r['pe1'] / med_pe:.1f}x theme median")
            if r.get("peg1") is not None and med_peg:
                ratios.append(r["peg1"] / med_peg)
                bits.append(f"PEG {r['peg1'] / med_peg:.1f}x theme median")
            r["pe_vs_theme"] = round(r["pe1"] / med_pe, 2) if (r.get("pe1") and med_pe) else None
            r["peg_vs_theme"] = round(r["peg1"] / med_peg, 2) if (r.get("peg1") is not None and med_peg) else None
            if not ratios:
                if len(theme_rows) == 1:
                    r["flag"], r["flag_detail"] = (
                        "n/a",
                        "sole member of its theme — no peer median; read the absolute multiples",
                    )
                else:
                    r["flag"], r["flag_detail"] = "n/a", "no theme median (too few members with a multiple)"
                continue
            hi, lo = max(ratios), min(ratios)
            if lo <= 0.67 and hi >= 1.5:
                r["flag"] = "mixed"
            elif lo <= 0.67:
                r["flag"] = "discount"
            elif hi >= 1.5:
                r["flag"] = "premium"
            else:
                r["flag"] = "fair"
            r["flag_detail"] = " vs ".join(bits) if bits else "n/a"


def build_quant(ref: date, themes: list[dict], members_by_theme: dict | None = None) -> dict:
    """Compute and save the quant table for every member of every non-COLD theme.

    `themes` are radar rows (theme/status/lean/breadth [+ members]) — the live
    run passes theme_radar rows, a regen passes the saved radar's theme rows
    together with the saved radar's members dict. Pure computation: one CSV
    read, dict lookups, no LLM, no network.
    """
    from ptm_simple.run import _fundamentals

    fund = _fundamentals()
    members_by_theme = members_by_theme or {}
    rows: list[dict] = []
    kept_themes: list[str] = []
    for row in themes:
        if row.get("status") == "COLD":
            continue
        theme = row["theme"]
        kept_themes.append(theme)
        members = row.get("members") or members_by_theme.get(theme) or []
        for m in members:
            q = _quant_row(m["ticker"], m, fund.get(m["ticker"]))
            q.update(
                {
                    "theme": theme,
                    "status": row.get("status"),
                    "lean": row.get("lean"),
                    "breadth": row.get("breadth"),
                }
            )
            rows.append(q)
    payload = {
        "as_of": ref.isoformat(),
        "themes": kept_themes,
        "rows": rows,
        "note": "Deterministic reference numbers from the cached fundamentals table "
        "(EDGAR XBRL + analyst consensus) — not a ranking, not a gate. The flag is "
        "theme-relative (P/E and PEG vs the theme median); read the qual report to judge it.",
    }
    _flag_rows(rows)
    path = quant_path(ref)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    flagged = sum(1 for r in rows if r.get("flag") in ("premium", "discount", "mixed"))
    log(f"quant: {len(rows)} rows across {len(kept_themes)} non-COLD theme(s) "
        f"({flagged} flagged premium/discount/mixed) -> {path.name}")
    return payload