"""Global themes, discovered in the filings rather than in the news.

The obvious way to add a thematic layer is a news or search API: ask what is hot,
then guess which tickers express it. This does the opposite, for three reasons.

**The ticker mapping falls out for free.** A headline says "AI is hot" and leaves
you to guess who is exposed. Reading filings, the theme and the exposure ranking
arrive together - DOCN mentions AI 49 times in its own release, which is a fact
about DOCN rather than an inference about it.

**Filings are dated.** Undated vendor prose is the one input this repository has
consistently refused, because it destroys the ability to run a past month
honestly. An 8-K has a filing date; a news article's relevance does not.

**A headline is evidence a theme is LATE.** What is in the news is by
construction already being priced, and the question worth asking is which themes
are not yet.

What this cannot do yet, stated plainly: it holds one snapshot, so it can say
*who is exposed* to a theme but not that a theme is *accelerating*. Detecting
that needs mention counts over successive runs, which `theme_history` starts
accumulating from the first run onwards and which is useless until several exist.

Themes are configured, not inferred. Unsupervised discovery over 1,500 filings is
a bigger and much noisier problem; a curated list is honest about being a
judgement call and takes thirty seconds to edit.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from ptm.config import data_dir, toml_settings
from ptm.io import read_json, write_json
from ptm.log import log

# Fallback set, used when config carries none. Deliberately broad: a theme is a
# lens for reading exposure, not a prediction.
DEFAULT_THEMES: dict[str, str] = {
    "AI and data centre": (
        r"artificial intelligence|\bAI\b|machine learning|\bGPU\b|data cent(?:er|re)|"
        r"hyperscal\w+|inference|accelerated comput\w+|large language model|\bLLM\b"
    ),
    "power demand and grid": (
        r"electrification|\bgrid\b|transmission|substation|load growth|power demand|"
        r"electricity demand|megawatt|capacity market|utility[- ]scale"
    ),
    "energy transition": (
        r"renewable|solar|wind (?:farm|power|energy)|battery storage|hydrogen|"
        r"carbon capture|energy transition|decarboni[sz]\w+"
    ),
    "reshoring and supply chain": (
        r"reshor\w+|onshor\w+|nearshor\w+|domestic manufactur\w+|supply chain resilien\w+|"
        r"dual[- ]sourc\w+|regionali[sz]\w+"
    ),
    "tariffs and trade policy": (
        r"tariff\w*|trade polic\w+|section 232|section 301|de minimis|"
        r"import dut\w+|customs dut\w+|USMCA"
    ),
    "GLP-1 and obesity": (
        r"GLP-1|semaglutide|tirzepatide|obesity|weight[- ]loss (?:drug|therap\w+)|incretin"
    ),
    "defence and rearmament": (
        r"defen[cs]e (?:budget|spending|program)|munition\w*|rearm\w+|NATO|"
        r"missile|military (?:aircraft|vehicle)"
    ),
    "labour cost and automation": (
        r"labo(?:u)?r (?:cost|shortage|inflation)|wage inflation|automat\w+|robotic\w*|"
        r"headcount reduction|workforce reduction"
    ),
}


def _cfg() -> dict:
    return toml_settings().get("themes") or {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", True))


def _min_mentions() -> int:
    return int(_cfg().get("min_mentions") or 2)


def _max_per_name() -> int:
    return int(_cfg().get("max_per_name") or 3)


def theme_patterns() -> dict[str, re.Pattern]:
    """Configured themes, else the built-in set."""
    raw = _cfg().get("patterns")
    source = raw if isinstance(raw, dict) and raw else DEFAULT_THEMES
    out = {}
    for name, pattern in source.items():
        try:
            out[str(name)] = re.compile(str(pattern), re.I)
        except re.error as exc:
            log(f"themes: skipping {name!r}, bad pattern ({exc})")
    return out


def exposure(text: str) -> list[dict]:
    """Which themes this name's own filings talk about, and how much.

    Mentions are a crude proxy for exposure and are treated as one: the count
    orders names within a theme, it does not measure revenue exposure. A company
    naming a theme twice in passing is not a pure play, which is why
    `min_mentions` exists and why the count travels with the label.
    """
    if not enabled() or not text:
        return []
    found = []
    for name, pattern in theme_patterns().items():
        hits = pattern.findall(text)
        if len(hits) >= _min_mentions():
            found.append({"theme": name, "mentions": len(hits)})
    found.sort(key=lambda row: -row["mentions"])
    return found[: _max_per_name()]


def labels(text: str) -> list[str]:
    """Theme names only, for the verdict prompt and the idea's JSON."""
    return [f"{row['theme']} ({row['mentions']})" for row in exposure(text)]


def prompt_block(text: str) -> str:
    """Theme context appended to the verdict question."""
    rows = exposure(text)
    if not rows:
        return ""
    listed = ", ".join(f"{r['theme']} [{r['mentions']} mentions]" for r in rows)
    return (
        "\n\nGLOBAL THEMES THIS COMPANY'S OWN FILINGS DISCUSS: "
        + listed
        + "\nTreat these as context, not as evidence. A theme tells you what the company is "
        "exposed to; it does not tell you the exposure is profitable, material, or unpriced. "
        "If a theme genuinely drives the numbers you cited, say so in direction_basis."
    )


# --- run-over-run accumulation ------------------------------------------------


def record(day: str, per_ticker: dict[str, list[dict]]) -> dict:
    """Append this run's theme counts so acceleration becomes visible later.

    A single snapshot cannot say a theme is emerging - only that a company
    mentions it. Storing each run builds the series that can, and there is no
    way to backfill it, so it starts now and is worthless until several runs
    exist. That limitation is the honest reason this is a separate file rather
    than a signal.
    """
    path = data_dir("curated", "theme_history.json")
    history = {}
    if path.exists():
        try:
            loaded = read_json(path)
            if isinstance(loaded, dict):
                history = loaded
        except Exception:
            history = {}
    totals: dict[str, dict] = {}
    for ticker, rows in per_ticker.items():
        for row in rows:
            bucket = totals.setdefault(row["theme"], {"tickers": 0, "mentions": 0, "names": []})
            bucket["tickers"] += 1
            bucket["mentions"] += int(row["mentions"])
            bucket["names"].append(ticker)
    for bucket in totals.values():
        bucket["names"] = sorted(bucket["names"], key=lambda t: t)[:25]
    history[day] = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "themes": totals,
    }
    write_json(path, history)
    runs = len(history)
    log(
        f"themes: {len(totals)} themes across {len(per_ticker)} names recorded for {day} "
        f"({runs} run{'s' if runs != 1 else ''} stored; acceleration needs at least 3)"
    )
    return totals


def trend(theme: str) -> dict:
    """Mention trend for one theme across stored runs, or an empty read."""
    path = data_dir("curated", "theme_history.json")
    if not path.exists():
        return {"available": False, "runs": 0}
    try:
        history = read_json(path)
    except Exception:
        return {"available": False, "runs": 0}
    days = sorted(history)
    series = [
        (day, (history[day].get("themes") or {}).get(theme, {}).get("tickers", 0))
        for day in days
    ]
    series = [(d, n) for d, n in series if n or d == days[-1]]
    if len(series) < 3:
        return {"available": False, "runs": len(days), "series": series}
    first, last = series[0][1], series[-1][1]
    return {
        "available": True,
        "runs": len(days),
        "series": series,
        "change": last - first,
        "direction": "spreading" if last > first else ("narrowing" if last < first else "flat"),
    }


# --- theme cohorts ------------------------------------------------------------
# A theme is a shared driver, which makes it a corroboration test for revision
# momentum. If a name's estimates are rising AND the other names exposed to the
# same theme are broadly being upgraded, the driver is theme-wide rather than
# idiosyncratic. A name whose estimates rise while its cohort is flat is more
# likely noise.
#
# This is deliberately NOT price momentum. Nothing here reads a return, a moving
# average or a chart; the inputs are analyst estimate revisions and the words
# companies use in their own filings.

# Below this a "cohort" is one or two names and its average says nothing.
MIN_COHORT = 4


def cohort_momentum(rows: list[dict]) -> dict[str, dict]:
    """Per theme, how the exposed names' estimates are moving in aggregate.

    `rows` is one dict per idea: {ticker, themes: [labels], direction, magnitude}
    where direction/magnitude come from ptm/drift.py. Returns a reading per
    theme, and only for themes with enough names to average.
    """
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        for label in row.get("themes") or []:
            name = str(label).rsplit(" (", 1)[0]
            buckets.setdefault(name, []).append(row)
    out: dict[str, dict] = {}
    for theme, members in buckets.items():
        sized = [m for m in members if m.get("direction")]
        if len(sized) < MIN_COHORT:
            out[theme] = {
                "available": False,
                "names": len(members),
                "why": f"only {len(sized)} of {len(members)} exposed names carry a revision",
            }
            continue
        up = sum(1 for m in sized if m["direction"] > 0)
        down = len(sized) - up
        net = up - down
        avg = sum(abs(float(m.get("magnitude") or 0)) for m in sized) / len(sized)
        direction = 0
        if abs(net) >= max(2, len(sized) // 4):
            direction = 1 if net > 0 else -1
        out[theme] = {
            "available": True,
            "names": len(sized),
            "up": up,
            "down": down,
            "direction": direction,
            "avg_magnitude_pct": round(avg, 2),
            "why": (
                f"{up} of {len(sized)} names exposed to this theme are seeing upgrades, "
                f"average revision {avg:.1f}%"
            ),
        }
    return out


def corroboration(themes: list[str], drift_direction: int, cohorts: dict[str, dict]) -> dict:
    """Do this name's themes point the same way its own estimates are moving?

    Returns a modest multiplier. Modest on purpose: this is momentum layered on
    momentum, and stacking two correlated signals hard would let one driver
    count twice.
    """
    out = {"multiplier": 1.0, "themes": [], "why": ""}
    if not themes or not drift_direction:
        return out
    agree = disagree = 0
    detail = []
    for label in themes:
        name = str(label).rsplit(" (", 1)[0]
        cohort = cohorts.get(name) or {}
        if not cohort.get("available") or not cohort.get("direction"):
            continue
        if cohort["direction"] == drift_direction:
            agree += 1
            detail.append(f"{name} cohort agrees ({cohort['up']}/{cohort['names']} upgraded)")
        else:
            disagree += 1
            detail.append(f"{name} cohort points the other way")
    if not detail:
        return out
    out["themes"] = detail
    if agree and not disagree:
        out["multiplier"] = 1.25
        out["why"] = "theme cohort corroborates: " + "; ".join(detail)
    elif disagree and not agree:
        out["multiplier"] = 0.85
        out["why"] = "theme cohort does not corroborate: " + "; ".join(detail)
    else:
        out["why"] = "theme cohorts are split: " + "; ".join(detail)
    return out


# --- ISM alignment ------------------------------------------------------------
# Themes come from what companies say; ISM comes from what purchasing managers
# say and what their order books are doing. Running the same theme vocabulary
# over both gives a macro cross-check on a bottom-up signal, from two
# independent sets of respondents.
#
# The two are genuinely different evidence. A theme detected only in filings may
# be a story management likes telling. A theme that also appears in ISM comments,
# in industries whose NEW ORDERS are growing, has an order book behind it.


def _ism_sections(ism: dict | None) -> list[dict]:
    return [s for s in ((ism or {}).get("manufacturing"), (ism or {}).get("services")) if s]


def ism_alignment(ism: dict | None) -> dict[str, dict]:
    """Per theme: is ISM talking about it, and are those orders growing?

    Comment text lives under `quote` (not `comment`) in the parsed report - a
    detail worth naming, because reading the wrong key returns None for every
    row and looks exactly like a report with no commentary.
    """
    from ptm.ingest.ism_sectors import gics_for_ism

    patterns = theme_patterns()
    out: dict[str, dict] = {}
    sections = _ism_sections(ism)
    if not sections:
        return {name: {"available": False, "why": "no ISM report"} for name in patterns}

    growing, contracting = set(), set()
    for section in sections:
        orders = section.get("new_orders_industries") or {}
        growing.update(orders.get("growth") or [])
        contracting.update(orders.get("contraction") or [])

    for name, pattern in patterns.items():
        industries, quotes = [], []
        for section in sections:
            for comment in section.get("comments") or []:
                text = str(comment.get("quote") or "")
                if text and pattern.search(text):
                    industries.append(str(comment.get("industry") or "unknown"))
                    quotes.append(text[:180])
        in_growth = sorted({i for i in industries if i in growing})
        in_contraction = sorted({i for i in industries if i in contracting})
        # A theme can also be aligned through the sectors of its industries even
        # when no purchasing manager mentioned it by name.
        sectors = sorted({gics_for_ism(i) for i in industries if gics_for_ism(i)})
        direction = 0
        if in_growth and not in_contraction:
            direction = 1
        elif in_contraction and not in_growth:
            direction = -1
        out[name] = {
            "available": bool(industries),
            "ism_mentions": len(industries),
            "industries": sorted(set(industries)),
            "sectors": sectors,
            "new_orders_growing": in_growth,
            "new_orders_contracting": in_contraction,
            "direction": direction,
            "quotes": quotes[:2],
            "why": (
                f"ISM respondents in {', '.join(sorted(set(industries))[:3])} raised it"
                + (
                    f"; new orders growing in {', '.join(in_growth[:2])}"
                    if in_growth
                    else (
                        f"; new orders CONTRACTING in {', '.join(in_contraction[:2])}"
                        if in_contraction
                        else ""
                    )
                )
                if industries
                else "no ISM respondent raised this theme"
            ),
        }
    return out


def ism_support(themes: list[str], alignment: dict[str, dict]) -> dict:
    """Does ISM back the themes this name is exposed to?

    Reported, and used only as a small modifier. ISM is a survey of a different
    population about a different question, so agreement is corroboration rather
    than confirmation - and a theme in a contracting order book is a warning
    worth surfacing even when the company sounds confident.
    """
    out = {"multiplier": 1.0, "notes": [], "why": ""}
    if not themes:
        return out
    supportive = adverse = 0
    for label in themes:
        name = str(label).rsplit(" (", 1)[0]
        read = alignment.get(name) or {}
        if not read.get("available"):
            continue
        if read.get("direction") > 0:
            supportive += 1
            out["notes"].append(f"ISM backs {name}: {read['why']}")
        elif read.get("direction") < 0:
            adverse += 1
            out["notes"].append(f"ISM warns on {name}: {read['why']}")
        else:
            out["notes"].append(f"ISM raises {name} without a clear order-book direction")
    if supportive and not adverse:
        out["multiplier"] = 1.1
    elif adverse and not supportive:
        out["multiplier"] = 0.9
    out["why"] = "; ".join(out["notes"])
    return out
