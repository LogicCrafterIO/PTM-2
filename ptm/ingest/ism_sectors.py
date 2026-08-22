"""Map ISM industry ranks and comments onto GICS sector tilts."""

from __future__ import annotations

import re

from ptm.models import Candidate, Side
from ptm.ranking import long_key, short_key

ISM_TO_GICS: dict[str, str] = {
    "chemical products": "Materials",
    "computer & electronic products": "Information Technology",
    "computer and electronic products": "Information Technology",
    "transportation equipment": "Industrials",
    "apparel, leather & allied products": "Consumer Discretionary",
    "apparel, leather and allied products": "Consumer Discretionary",
    "electrical equipment, appliances & components": "Industrials",
    "electrical equipment, appliances and components": "Industrials",
    "primary metals": "Materials",
    "nonmetallic mineral products": "Materials",
    "machinery": "Industrials",
    "food, beverage & tobacco products": "Consumer Staples",
    "food, beverage and tobacco products": "Consumer Staples",
    "wood products": "Materials",
    "plastics & rubber products": "Materials",
    "plastics and rubber products": "Materials",
    "furniture & related products": "Consumer Discretionary",
    "furniture and related products": "Consumer Discretionary",
    "fabricated metal products": "Industrials",
    "printing & related support activities": "Industrials",
    "printing and related support activities": "Industrials",
    "textile mills": "Consumer Discretionary",
    "miscellaneous manufacturing": "Industrials",
    "paper products": "Materials",
    "petroleum & coal products": "Energy",
    "petroleum and coal products": "Energy",
    "retail trade": "Consumer Discretionary",
    "transportation & warehousing": "Industrials",
    "transportation and warehousing": "Industrials",
    "wholesale trade": "Industrials",
    "management of companies & support services": "Industrials",
    "management of companies and support services": "Industrials",
    "information": "Communication Services",
    "construction": "Industrials",
    "accommodation & food services": "Consumer Discretionary",
    "accommodation and food services": "Consumer Discretionary",
    "public administration": "Utilities",
    "utilities": "Utilities",
    "educational services": "Consumer Discretionary",
    "mining": "Energy",
    "professional, scientific & technical services": "Industrials",
    "professional, scientific and technical services": "Industrials",
    "finance & insurance": "Financials",
    "finance and insurance": "Financials",
    "agriculture, forestry, fishing & hunting": "Consumer Staples",
    "agriculture, forestry, fishing and hunting": "Consumer Staples",
    "other services": "Industrials",
    "health care & social assistance": "Health Care",
    "health care and social assistance": "Health Care",
    "real estate, rental & leasing": "Real Estate",
    "real estate, rental and leasing": "Real Estate",
}

CYCLICAL_SECTORS = {
    "Materials",
    "Industrials",
    "Consumer Discretionary",
    "Information Technology",
    "Energy",
    "Financials",
    "Real Estate",
    "Communication Services",
}
DEFENSIVE_SECTORS = {"Consumer Staples", "Health Care", "Utilities"}

_NEG_WORDS = (
    "downturn",
    "slowing",
    "decline",
    "contract",
    "weak",
    "caution",
    "cautious",
    "slide",
    "pressure",
    "concern",
    "uncertain",
    "not sustainable",
    "reducing inventory",
)
_POS_WORDS = (
    "strong",
    "growth",
    "booming",
    "solid",
    "favorable",
    "expand",
    "robust",
    "demand continues",
    "positive",
    "pick up",
)


def gics_for_ism(industry: str) -> str | None:
    key = industry.strip().lower()
    if key in ISM_TO_GICS:
        return ISM_TO_GICS[key]
    for name, sector in ISM_TO_GICS.items():
        if name in key or key in name:
            return sector
    return None


def _rank_scores(names: list[str], sign: float, weight: float) -> dict[str, float]:
    scores: dict[str, float] = {}
    total = max(len(names), 1)
    for idx, name in enumerate(names):
        sector = gics_for_ism(name)
        if not sector:
            continue
        # first listed = fastest grower / most contracting
        strength = 1.0 - 0.6 * (idx / total)
        scores[sector] = scores.get(sector, 0.0) + sign * weight * strength
    return scores


def _comment_scores(comments: list[dict], weight: float = 0.35) -> dict[str, float]:
    scores: dict[str, float] = {}
    for row in comments:
        sector = gics_for_ism(str(row.get("industry") or ""))
        if not sector:
            continue
        quote = str(row.get("quote") or "").lower()
        pos = sum(1 for word in _POS_WORDS if word in quote)
        neg = sum(1 for word in _NEG_WORDS if word in quote)
        if pos == neg:
            continue
        delta = weight if pos > neg else -weight
        scores[sector] = scores.get(sector, 0.0) + delta
    return scores


def _merge(target: dict[str, float], extra: dict[str, float]) -> None:
    for key, value in extra.items():
        target[key] = target.get(key, 0.0) + value


def _macro_overlay(pmi: float | None, peak: float = 60.0, expansion: float = 50.0) -> dict[str, float]:
    overlay: dict[str, float] = {}
    if pmi is None:
        return overlay
    if pmi >= peak:
        shift = 0.0
    elif pmi >= expansion:
        shift = 0.25
    elif 40 <= pmi <= 45:
        shift = 0.15
    else:
        shift = -0.25
    for sector in CYCLICAL_SECTORS:
        overlay[sector] = overlay.get(sector, 0.0) + shift
    for sector in DEFENSIVE_SECTORS:
        overlay[sector] = overlay.get(sector, 0.0) - shift
    return overlay


def industry_match(candidate_industry: str, ism_name: str) -> bool:
    hay = (candidate_industry or "").lower()
    if not hay:
        return False
    skip = {"products", "related", "support", "activities", "services", "equipment", "mills", "trade"}
    tokens = [t for t in re.split(r"[^a-z]+", ism_name.lower()) if len(t) >= 5 and t not in skip]
    if not tokens:
        tokens = [t for t in re.split(r"[^a-z]+", ism_name.lower()) if len(t) >= 4 and t not in skip]
    return any(token in hay for token in tokens)


def compute_industry_tilts(ism: dict) -> list[dict]:
    rows: list[dict] = []
    for report_key, label in (("manufacturing", "mfg"), ("services", "svc")):
        report = ism.get(report_key) or {}
        industries = report.get("industries") or {}
        orders = report.get("new_orders_industries") or {}
        contraction = list(industries.get("contraction") or [])
        growth = list(industries.get("growth") or [])
        only = len(contraction) == 1
        for name in contraction:
            score = -1.6 if only else -1.1
            if name in (orders.get("contraction") or []):
                score -= 0.5
            rows.append(
                {
                    "industry": name,
                    "sector": gics_for_ism(name),
                    "tilt": "short",
                    "score": score,
                    "why": f"{label} contraction{' (only industry)' if only else ''}: {name}",
                }
            )
        for idx, name in enumerate(growth[:3]):
            rows.append(
                {
                    "industry": name,
                    "sector": gics_for_ism(name),
                    "tilt": "long",
                    "score": 0.9 - 0.15 * idx,
                    "why": f"{label} top growth #{idx + 1}: {name}",
                }
            )
        for name in orders.get("contraction") or []:
            if name in contraction:
                continue
            rows.append(
                {
                    "industry": name,
                    "sector": gics_for_ism(name),
                    "tilt": "short",
                    "score": -1.2,
                    "why": f"{label} new orders contracting: {name}",
                }
            )
    return rows


def _why_matching_tilt(parts: list[str], tilt: str) -> str:
    if tilt == "long":
        kept = [p for p in parts if "contract" not in p.lower()]
    elif tilt == "short":
        kept = [p for p in parts if "growth" not in p.lower() or "contract" in p.lower()]
    else:
        kept = parts
    return "; ".join(kept[:3]) or "ISM composite score"


def compute_sector_tilts(ism: dict, pmi: float | None = None) -> list[dict]:
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    def note(sector: str, text: str) -> None:
        reasons.setdefault(sector, []).append(text)

    for report_key, label, headline_weight, orders_weight in (
        ("manufacturing", "mfg", 0.7, 1.1),
        ("services", "svc", 0.5, 0.9),
    ):
        report = ism.get(report_key) or {}
        industries = report.get("industries") or {}
        orders = report.get("new_orders_industries") or {}
        growth = list(industries.get("growth") or [])
        contraction = list(industries.get("contraction") or [])
        _merge(scores, _rank_scores(growth, 1.0, headline_weight))
        _merge(scores, _rank_scores(contraction, -1.0, headline_weight + 0.2))
        if growth:
            note(gics_for_ism(growth[0]) or "", f"{label} fastest growth: {growth[0]}")
        if contraction:
            note(gics_for_ism(contraction[0]) or "", f"{label} contraction: {contraction[0]}")
        _merge(scores, _rank_scores(list(orders.get("growth") or []), 1.0, orders_weight))
        _merge(scores, _rank_scores(list(orders.get("contraction") or []), -1.0, orders_weight + 0.2))
        for name in orders.get("contraction") or []:
            sector = gics_for_ism(name)
            if sector:
                note(sector, f"{label} new orders contracting: {name}")
        _merge(scores, _comment_scores(report.get("comments") or []))

    _merge(scores, _macro_overlay(pmi if pmi is not None else ism.get("pmi")))
    scores.pop("", None)
    reasons.pop("", None)

    industry_rows = compute_industry_tilts(ism)
    any_short = {
        row["sector"]
        for row in industry_rows
        if row.get("sector") and row.get("tilt") == "short"
    }
    by_sector: dict[str, list[dict]] = {}
    for row in industry_rows:
        sector = row.get("sector")
        if sector:
            by_sector.setdefault(sector, []).append(row)
    for sector, raw in list(scores.items()):
        flags = by_sector.get(sector) or []
        net = sum(float(f.get("score") or 0.0) for f in flags)
        all_short = bool(flags) and all(f.get("tilt") == "short" for f in flags)
        if sector in any_short or (all_short and net < 0):
            if raw > 0.15:
                scores[sector] = 0.15

    tilts = []
    for sector, raw in sorted(scores.items(), key=lambda item: abs(item[1]), reverse=True):
        if raw > 0.15:
            tilt = "long"
        elif raw < -0.15:
            tilt = "short"
        else:
            tilt = "neutral"
        tilts.append(
            {
                "sector": sector,
                "tilt": tilt,
                "score": round(raw, 4),
                "why": _why_matching_tilt(reasons.get(sector, []), tilt),
            }
        )
    tilts.extend(industry_rows)
    return tilts


def tilt_map(tilts: list[dict]) -> dict[str, dict]:
    return {row["sector"]: row for row in tilts if row.get("sector") and not row.get("industry")}


def apply_ism_tilts(candidates: list[Candidate], tilts: list[dict]) -> list[Candidate]:
    lookup = tilt_map(tilts)
    industry_rows = [row for row in tilts if row.get("industry")]
    for cand in candidates:
        row = lookup.get(cand.sector) or {}
        sector_score = float(row.get("score") or 0.0)
        why = [str(row.get("why") or "")]
        for flag in industry_rows:
            if industry_match(cand.industry, str(flag.get("industry") or "")):
                sector_score += float(flag.get("score") or 0.0)
                why.append(str(flag.get("why") or flag["industry"]))
        aligned = sector_score if cand.side == Side.LONG else -sector_score
        cand.ism_score = round(aligned, 4)
        if sector_score > 0.15:
            cand.ism_tilt = "long"
        elif sector_score < -0.15:
            cand.ism_tilt = "short"
        else:
            cand.ism_tilt = str(row.get("tilt") or "neutral")
        cand.ism_why = "; ".join(part for part in why if part)[:400]
    return candidates


def split_quota(candidates: list[Candidate], limit: int) -> list[Candidate]:
    n_short = limit // 2
    n_long = limit - n_short
    longs = [c for c in candidates if c.side == Side.LONG]
    shorts = [c for c in candidates if c.side == Side.SHORT]

    longs.sort(key=long_key)
    shorts.sort(key=short_key)
    chosen = longs[:n_long] + shorts[:n_short]
    if len(chosen) < limit:
        leftover = [c for c in longs[n_long:] + shorts[n_short:] if c not in chosen]
        leftover.sort(key=lambda c: (0 if c.mcap_ok else 1, -(c.ism_score or 0.0)))
        chosen.extend(leftover[: limit - len(chosen)])
    return chosen
