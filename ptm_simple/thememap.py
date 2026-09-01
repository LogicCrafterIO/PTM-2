"""Parse the starter pack's Master watchlist into a machine theme map.

The sheet's layout: theme labels sit in columns I/J; member tickers are the
1-5 character upper-case tokens scattered left and right of the label in the
same row, and rows below until the next label. Section headers ('Tech',
'SOFTWARE', 'AI HARDWARE') sit in columns C/D and are ignored. Tickers may
appear under several themes; the reverse index is built for them.
"""

from __future__ import annotations

import re
from pathlib import Path

from ptm.log import log

# Typos and near-duplicate labels in the sheet collapse into these keys.
_LABEL_ALIASES = {
    "storgae hardware/memory": "Storage Hardware/Memory",
    "building prdoucts": "Building Products & Materials",
    "restaurants % food service": "Restaurants & Food service",
    "industrial conglomorates": "Industrial conglomerates",
    "packaging and contaimers": "Packaging and Containers",
    "speciality chemicals": "Specialty chemicals",
    "metal and glass": "Metal and Glass",
    "windows and doors": "Building Products & Materials",
    "wood products and timebr": "Wood Products and Timber",
    "diversfified telecomms": "Diversified telecomms",
    "apparel . footwear & luxury": "Apparel, Footwear & Luxury",
    "consumer platforms and experiences": "Internet Platforms/Consumer Software",
    "ai semiconductor   chips": "AI Semiconductor chips",
    "enterprise applications(erp/hcm/finance)": "Enterprise Applications (ERP/HCM/Finance)",
}
_TICKER_RE = re.compile(r"^[A-Z][A-Z.\-]{0,5}$")
_SKIP = {"XX", "O", "N/A", "TICKER", "NAME"}
_THEME_COL = {"I", "J"}


def _norm_label(raw: str) -> str | None:
    label = re.sub(r"\s+", " ", str(raw)).strip()
    if not label:
        return None
    key = _LABEL_ALIASES.get(label.lower())
    return label if key is None else key


def _tickerish(raw) -> str | None:
    text = str(raw).strip()
    if not text or not _TICKER_RE.match(text) or text in _SKIP:
        return None
    return text


def parse_watchlist(xlsx_path: str | Path, min_members: int = 2) -> list[dict]:
    """[{theme, members: [tickers]}] from the Master watchlist sheet.

    A strict ticker-shaped token (all caps, <=6 chars) is a member even when
    it sits in the label columns — the sheet puts names there too (IRM sits
    in the same column as 'Data centre REIT'). Mixed-case or longer strings
    in the label columns are labels.
    """
    import openpyxl

    valid: set[str] | None = None
    try:
        from ptm.config import data_dir
        from ptm.io import read_json

        sec = read_json(data_dir("curated", "sec_tickers.json"))
        if isinstance(sec, dict):
            valid = {str(k).upper() for k in sec} | {str(v).upper() for v in sec.values()}
    except Exception:  # the map still builds without validation, just noisier
        valid = None

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb["Master watchlist"]
    themes: list[dict] = []
    current: dict | None = None
    for row in ws.iter_rows():
        label = None
        members: list[str] = []
        for cell in row:
            if cell.value is None:
                continue
            text = str(cell.value).strip()
            if not text:
                continue
            if _TICKER_RE.match(text) and text.upper() not in _SKIP:
                members.append(text.upper())
            elif cell.column_letter in _THEME_COL and 3 <= len(text) <= 55 and any(ch.isalpha() for ch in text):
                label = _norm_label(text) or text
        if label is None:
            if current is not None and members:
                current["members"].extend(members)
            continue
        current = next((t for t in themes if t["theme"] == label), None)
        if current is None:
            current = {"theme": label, "members": []}
            themes.append(current)
        current["members"].extend(members)
    wb.close()
    for t in themes:
        seen: set[str] = set()
        t["members"] = [m for m in t["members"] if not (m in seen or seen.add(m))]
    if valid is not None:
        for t in themes:
            unknown = [m for m in t["members"] if m not in valid]
            if unknown:
                t["unknown_members"] = unknown
                t["members"] = [m for m in t["members"] if m in valid]
    return [t for t in themes if len(t["members"]) >= min_members]


def build_theme_map(xlsx_path: str | Path) -> dict:
    """Theme map artifact: themes, members, and the reverse ticker index."""
    from ptm.io import write_json
    from ptm_simple import simple_dir

    raw = parse_watchlist(xlsx_path)
    reverse: dict[str, list[str]] = {}
    for t in raw:
        for m in t["members"]:
            reverse.setdefault(m, []).append(t["theme"])
    out = {
        "source": str(xlsx_path),
        "theme_count": len(raw),
        "ticker_count": len(reverse),
        "themes": [
            {
                "theme": t["theme"],
                "members": sorted(set(t["members"])),
                "thesis": "",
                "unknown_members": sorted(t.get("unknown_members", [])),
            }
            for t in sorted(raw, key=lambda t: t["theme"].lower())
        ],
        "ticker_themes": {k: sorted(set(v)) for k, v in sorted(reverse.items())},
    }
    path = simple_dir("theme_map.json")
    from ptm.io import write_json

    write_json(path, out)
    log(f"theme map: {out['theme_count']} themes, {out['ticker_count']} tickers -> {path}")
    return out