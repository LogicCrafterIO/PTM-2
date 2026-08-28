"""Score a completed PTM research run against process-quality checks."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ptm.asof import coverage, day_slug, is_backdated
from ptm.config import ROOT, data_dir, ideas_dir, toml_settings
from ptm.organize import find_idea_files, find_idea_markdown
from ptm.io import read_json, write_json
from ptm.models import Bias, IdeaState


@dataclass
class Finding:
    ticker: str
    stage: str
    severity: str
    check_id: str
    evidence: str
    suggestion: str


@dataclass
class AuditResult:
    as_of: str
    ideas_folder: str
    findings: list[Finding] = field(default_factory=list)
    by_stage: dict[str, int] = field(default_factory=dict)
    by_severity: dict[str, int] = field(default_factory=dict)
    summary: str = ""

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def finalize(self) -> None:
        self.by_stage = dict(Counter(f.stage for f in self.findings))
        self.by_severity = dict(Counter(f.severity for f in self.findings))
        top = Counter(f.check_id for f in self.findings).most_common(8)
        lines = [f"{len(self.findings)} findings"]
        if top:
            lines.append("Top checks: " + ", ".join(f"{cid} ({n})" for cid, n in top))
        self.summary = "; ".join(lines)


def _isnan(value: Any) -> bool:
    try:
        return isinstance(value, float) and math.isnan(value)
    except TypeError:
        return False


def _latest_ideas_folder() -> Path | None:
    """The run date's folder if it exists, else the newest one.

    A backdated run must score its own output, not whichever day sorts highest.
    """
    root = ideas_dir()
    if not root.exists():
        return None
    pinned = root / day_slug()
    if pinned.is_dir():
        return pinned
    days = sorted((p for p in root.iterdir() if p.is_dir()), reverse=True)
    return days[0] if days else None


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return read_json(path)
    except Exception:
        return None


def _idea_rows(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def _md_is_json(text: str) -> bool:
    stripped = (text or "").lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


HEADLINE_RE = re.compile(r"\?$|outpaced|do options traders|what to expect", re.I)
GENERIC_KPIS = {"revenue", "net_income", "ebit", "cash", "debt", "assets", "equity", "interest"}
COVER_MARKERS = ("iso4217:usd", "xbrli:shares", "form 8-k current report", "item 9.01")


def check_worldview(ism: dict | None, snap: dict | None, cfg: dict) -> list[Finding]:
    findings: list[Finding] = []
    if ism:
        errors = ism.get("errors") or []
        urls = ism.get("urls") or {}
        url_blob = " ".join(str(v) for v in urls.values())
        if any("fixture" in str(err).lower() for err in errors) or "tests" in url_blob.replace("\\", "/"):
            findings.append(
                Finding(
                    ticker="MACRO",
                    stage="worldview",
                    severity="warning",
                    check_id="worldview.ism_fixture_fallback",
                    evidence="; ".join(str(e) for e in errors) or url_blob,
                    suggestion="Treat this ISM print as stale; re-run ptm ingest-ism after a live fetch.",
                )
            )
        as_of = str(ism.get("as_of") or (snap.get("as_of") if snap else "") or "")
        target = str(ism.get("target_report_month") or "")
        wanted = target.split(" ")[0].lower() if target else ""
        if wanted:
            mismatched = [
                str(v)
                for v in urls.values()
                if str(v).startswith("http") and f"/{wanted}/" not in str(v)
            ]
            if mismatched:
                findings.append(
                    Finding(
                        ticker="MACRO",
                        stage="worldview",
                        severity="warn",
                        check_id="worldview.ism_month_mismatch",
                        evidence=f"run date wanted {target}; used {mismatched}",
                        suggestion="ISM fell back to an older print than the run date allows; note the staleness.",
                    )
                )
        if ism.get("backdated"):
            findings.append(
                Finding(
                    ticker="MACRO",
                    stage="worldview",
                    severity="info",
                    check_id="worldview.backdated_run",
                    evidence=str(coverage()),
                    suggestion="Backdated run: read docs/FEATURE-LIMITATIONS.md before trusting the funnel.",
                )
            )
    if snap:
        tens = snap.get("tens_minus_twos")
        second = str(snap.get("curve_second_leg") or "")
        if tens is not None and second not in {"irx", "2y", "ust2y", "dgs2"}:
            findings.append(
                Finding(
                    ticker="MACRO",
                    stage="worldview",
                    severity="info",
                    check_id="worldview.curve_label_10s5s",
                    evidence=f"tens_minus_twos={tens} is ^TNX minus ^FVX (10s-5s), not 10s-2s",
                    suggestion="Rename the field or switch the second leg to a 2-year yield.",
                )
            )
        score = float(snap.get("score") or 0)
        bias = snap.get("bias")
        lo = cfg["macro"]["bias_long_threshold"]
        hi = cfg["macro"]["bias_short_threshold"]
        expected = Bias.NET_LONG.value if score > lo else Bias.NET_SHORT.value if score < hi else Bias.NEUTRAL.value
        if bias and bias != expected:
            findings.append(
                Finding(
                    ticker="MACRO",
                    stage="worldview",
                    severity="error",
                    check_id="worldview.bias_vs_score",
                    evidence=f"bias={bias} score={score} expected={expected}",
                    suggestion="Recompute bias from the configured score thresholds.",
                )
            )
        narrative = str(snap.get("llm_narrative") or "")
        for row in snap.get("sector_tilts") or []:
            if row.get("industry"):
                continue
            sector = row.get("sector") or ""
            why = str(row.get("why") or "").lower()
            tilt = row.get("tilt")
            if "contraction" in why and tilt == "long":
                findings.append(
                    Finding(
                        ticker=sector or "MACRO",
                        stage="sector",
                        severity="error",
                        check_id="sector.why_sign_mismatch",
                        evidence=f"{sector} tilt={tilt} why={row.get('why')}",
                        suggestion="Industry contraction should not produce a long sector tilt.",
                    )
                )
            if "growth" in why and "contraction" not in why and tilt == "short":
                findings.append(
                    Finding(
                        ticker=sector or "MACRO",
                        stage="sector",
                        severity="warning",
                        check_id="sector.why_sign_mismatch",
                        evidence=f"{sector} tilt={tilt} why={row.get('why')}",
                        suggestion="Growth language should not produce a short sector tilt.",
                    )
                )
            if sector and narrative and tilt:
                # LLM repeating a contradiction, e.g. long due to contraction
                pattern = re.compile(rf"{re.escape(sector)}.*{re.escape(str(tilt))}", re.I)
                if "contraction" in why and tilt == "long" and pattern.search(narrative):
                    findings.append(
                        Finding(
                            ticker=sector,
                            stage="worldview",
                            severity="warning",
                            check_id="worldview.narrative_contradicts_tilt",
                            evidence=narrative[:400],
                            suggestion="Keep the LLM narrative from restating contradictory sector tilts.",
                        )
                    )
        industry_rows = [r for r in (snap.get("sector_tilts") or []) if r.get("industry")]
        sector_rows = {r.get("sector"): r for r in (snap.get("sector_tilts") or []) if r.get("sector") and not r.get("industry")}
        for flag in industry_rows:
            sector = flag.get("sector")
            parent = sector_rows.get(sector) if sector else None
            if parent and flag.get("tilt") == "short" and parent.get("tilt") == "long":
                findings.append(
                    Finding(
                        ticker=str(sector),
                        stage="sector",
                        severity="error",
                        check_id="sector.industry_vs_sector_disagree",
                        evidence=f"industry {flag.get('industry')} short vs sector {sector} long",
                        suggestion="Do not let the cyclical PMI overlay overpower a sole contracting industry.",
                    )
                )
    return findings


def check_idea(idea: dict, pack: dict | None, cfg: dict) -> list[Finding]:
    findings: list[Finding] = []
    cand = idea.get("candidate") or {}
    ticker = str(cand.get("ticker") or "?")
    extra = idea.get("extra") or {}
    qual = idea.get("qual") or {}
    cats = idea.get("catalysts") or {}

    pe1, sector_pe1 = cand.get("pe1"), cand.get("sector_pe1")
    if pe1 is not None and sector_pe1 is not None and abs(float(pe1) - float(sector_pe1)) < 1e-9:
        findings.append(
            Finding(
                ticker=ticker,
                stage="quant",
                severity="warning",
                check_id="quant.pe_equals_sector",
                evidence=f"pe1={pe1} equals sector_pe1 (single-name sector?)",
                suggestion="Require more than one name before treating PE as a sector outlier.",
            )
        )
    eg_case = str(cand.get("eg_case") or "")
    if eg_case.endswith("non_ideal") or eg_case == "unknown":
        findings.append(
            Finding(
                ticker=ticker,
                stage="quant",
                severity="info",
                check_id="quant.non_ideal",
                evidence=eg_case,
                suggestion="Review whether this name should have been screened out.",
            )
        )
    if _isnan(cand.get("peg1")) or _isnan(cand.get("peg2")):
        findings.append(
            Finding(
                ticker=ticker,
                stage="quant",
                severity="warning",
                check_id="quant.peg_nan",
                evidence="peg1/peg2 is NaN",
                suggestion="Serialize undefined PEG as null, not NaN.",
            )
        )

    if pack:
        if pack.get("thin"):
            findings.append(
                Finding(
                    ticker=ticker,
                    stage="pack",
                    severity="warning",
                    check_id="pack.thin",
                    evidence="research pack marked thin",
                    suggestion="Refresh EDGAR/Yahoo sources before qualitative.",
                )
            )
        if len(str(pack.get("business") or "").strip()) < 40:
            findings.append(
                Finding(
                    ticker=ticker,
                    stage="pack",
                    severity="warning",
                    check_id="pack.item1_empty",
                    evidence=(pack.get("business") or "")[:120],
                    suggestion="Item 1 Business extraction missed the filing section.",
                )
            )
        mda = str(pack.get("mda") or "")
        if len(mda.strip()) < 200:
            findings.append(
                Finding(
                    ticker=ticker,
                    stage="pack",
                    severity="warning",
                    check_id="pack.mda_short",
                    evidence=mda[:160],
                    suggestion="MD&A looks like a TOC line; parse the full Item 2/7 section.",
                )
            )
        exhibit = str(pack.get("earnings_exhibit") or "").lower()
        if exhibit and any(marker in exhibit for marker in COVER_MARKERS) and "ex-99" not in exhibit[:200]:
            findings.append(
                Finding(
                    ticker=ticker,
                    stage="pack",
                    severity="warning",
                    check_id="pack.exhibit_cover_page",
                    evidence=exhibit[:180],
                    suggestion="Prefer 8-K EX-99.1 earnings text over the cover page.",
                )
            )

    supports = qual.get("supports_outlier")
    red_flags = [str(x) for x in (qual.get("red_flags") or [])]
    if supports is None and pack and not pack.get("thin") and (pack.get("summary") or pack.get("business")):
        findings.append(
            Finding(
                ticker=ticker,
                stage="qual",
                severity="error",
                check_id="qual.null_despite_pack",
                evidence="supports_outlier is null with a non-thin pack",
                suggestion="Only set null when there is no business description and no headlines.",
            )
        )
    kpis = [str(k).lower() for k in (qual.get("kpis") or [])]
    if kpis and all(k in GENERIC_KPIS for k in kpis):
        findings.append(
            Finding(
                ticker=ticker,
                stage="qual",
                severity="warning",
                check_id="qual.generic_kpis",
                evidence=", ".join(kpis),
                suggestion="KPIs should be operating drivers, not statement line items.",
            )
        )
    if "llm_skipped" in red_flags and supports is True:
        findings.append(
            Finding(
                ticker=ticker,
                stage="qual",
                severity="warning",
                check_id="qual.skip_llm_auto_pass",
                evidence="llm_skipped but supports_outlier=true",
                suggestion="Treat skip_llm as deferred evidence, not a qualitative pass.",
            )
        )

    earnings = str(cats.get("earnings_date") or "")
    if earnings and not re.match(r"20\d{2}-\d{2}-\d{2}", earnings):
        findings.append(
            Finding(
                ticker=ticker,
                stage="catalysts",
                severity="error",
                check_id="cat.earnings_not_iso",
                evidence=earnings,
                suggestion="Store earnings_date as YYYY-MM-DD.",
            )
        )
    non = [str(x) for x in (cats.get("non_earnings") or [])]
    if any(HEADLINE_RE.search(item) or "|" in item or "%" in item for item in non):
        findings.append(
            Finding(
                ticker=ticker,
                stage="catalysts",
                severity="warning",
                check_id="cat.headline_like",
                evidence="; ".join(non)[:400],
                suggestion="Catalysts must be dated events inside the window, not news headlines or table dumps.",
            )
        )
    if cats.get("tradeable") and not cats.get("earnings_in_window") and non:
        findings.append(
            Finding(
                ticker=ticker,
                stage="catalysts",
                severity="info",
                check_id="cat.tradeable_without_window",
                evidence=str(cats.get("reason") or non)[:300],
                suggestion="Confirm non-earnings catalysts actually fall inside the 30-90 calendar-day window.",
            )
        )

    md = idea.get("template_markdown") or ""
    if extra.get("template_error"):
        findings.append(
            Finding(
                ticker=ticker,
                stage="template",
                severity="error",
                check_id="template.error",
                evidence=str(extra["template_error"]),
                suggestion="Harden LLM JSON extraction and keep the deterministic markdown fallback.",
            )
        )
    if not str(md).strip():
        findings.append(
            Finding(
                ticker=ticker,
                stage="template",
                severity="error",
                check_id="template.empty_md",
                evidence="template_markdown is empty",
                suggestion="Never write an empty template; fall back to the deterministic markdown.",
            )
        )
    state = idea.get("state")
    if (
        state == IdeaState.INVESTMENT_ONLY.value
        and cats.get("tradeable") is True
        and qual.get("supports_outlier") is True
    ):
        findings.append(
            Finding(
                ticker=ticker,
                stage="catalysts",
                severity="error",
                check_id="cat.tradeable_marked_investment_only",
                evidence=f"state={state}; gates={extra.get('gates') or []}",
                suggestion="A supported, tradeable idea must advance to templated unless a process gate blocks it.",
            )
        )
    if state == IdeaState.IDENTIFIED.value:
        findings.append(
            Finding(
                ticker=ticker,
                stage="template",
                severity="info",
                check_id="template.state_identified",
                evidence=str(extra),
                suggestion="Investigate why this idea never left identified.",
            )
        )
    return findings


def check_book(
    book: dict | None,
    ideas: list[dict],
    cfg: dict,
    label: str = "BOOK",
) -> list[Finding]:
    findings: list[Finding] = []
    ready = [
        i
        for i in ideas
        if i.get("state") in {IdeaState.TEMPLATED.value, IdeaState.SIZED.value}
        and not ((i.get("prm") or {}).get("blocked"))
    ]
    selected = (book or {}).get("ideas") or []
    n = len(selected)
    lo, hi = cfg["filters"]["min_positions"], cfg["filters"]["max_positions"]
    if n < lo or n > hi:
        findings.append(
            Finding(
                ticker=label,
                stage="book",
                severity="error",
                check_id="book.out_of_range",
                evidence=f"{n} names (target {lo}-{hi}); breaches={(book or {}).get('limit_breaches')}",
                suggestion="ptm ideas must assemble the book from the same in-memory idea list as weekly.",
            )
        )
    selected_tickers = {((row.get("candidate") or {}).get("ticker")) for row in selected}
    ready_tickers = {((row.get("candidate") or {}).get("ticker")) for row in ready}
    if selected_tickers - ready_tickers:
        findings.append(
            Finding(
                ticker=label,
                stage="book",
                severity="error",
                check_id="book.not_subset",
                evidence=str(selected_tickers - ready_tickers),
                suggestion="Book names must be a subset of templated, unblocked ideas.",
            )
        )
    if ready_tickers and not selected_tickers:
        findings.append(
            Finding(
                ticker=label,
                stage="book",
                severity="error",
                check_id="book.stale_vs_ideas",
                evidence=f"{len(ready_tickers)} templated ideas on disk but book is empty",
                suggestion="Re-run book assembly after generate_ideas (ptm ideas now does this).",
            )
        )
    exclude = set(cfg["filters"].get("exclude_sectors") or [])
    for row in selected:
        sector = (row.get("candidate") or {}).get("sector")
        if sector in exclude:
            findings.append(
                Finding(
                    ticker=(row.get("candidate") or {}).get("ticker") or "BOOK",
                    stage="sector",
                    severity="warning",
                    check_id="sector.excluded_still_selected",
                    evidence=f"{sector} is in exclude_sectors",
                    suggestion="Honor exclude_sectors / skip_healthcare_v1 at book time.",
                )
            )
        gates = (row.get("extra") or {}).get("gates") or []
        if gates:
            findings.append(
                Finding(
                    ticker=(row.get("candidate") or {}).get("ticker") or "BOOK",
                    stage="book",
                    severity="warning",
                    check_id="book.gated_but_selected",
                    evidence=str(gates),
                    suggestion="Book assembly ignores extra.gates; decide whether gates are advisory or hard.",
                )
            )
    return findings


def check_markdown_files(folder: Path | None, ideas: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    if folder is None or not folder.exists():
        return findings
    for idea in ideas:
        cand = idea.get("candidate") or {}
        ticker = cand.get("ticker")
        side = cand.get("side")
        if not ticker or not side:
            continue
        path = find_idea_markdown(folder, str(side), str(ticker))
        if path is None or not path.exists():
            path = folder / f"{side}_{ticker}.md"
            findings.append(
                Finding(
                    ticker=str(ticker),
                    stage="template",
                    severity="error",
                    check_id="template.missing_md",
                    evidence=str(path),
                    suggestion="Write a markdown file per idea.",
                )
            )
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _md_is_json(text):
            findings.append(
                Finding(
                    ticker=str(ticker),
                    stage="template",
                    severity="error",
                    check_id="template.md_is_json",
                    evidence=text[:120],
                    suggestion="On template failure, write deterministic markdown instead of dumping JSON.",
                )
            )
    return findings


def check_window_books(ideas: list[dict], cfg: dict) -> list[Finding]:
    """Validate window artifacts without treating an honestly thin window as an error."""
    from ptm.organize import BEYOND, bucket_for_days, bucket_names

    findings: list[Finding] = []
    by_ticker = {
        str((idea.get("candidate") or {}).get("ticker") or ""): idea
        for idea in ideas
    }
    exclude = set(cfg["filters"].get("exclude_sectors") or [])
    minimum = int(cfg["filters"]["min_positions"])
    for label in bucket_names():
        path = data_dir("curated", f"book_{label}.json")
        payload = _load_json(path)
        if not isinstance(payload, dict):
            findings.append(
                Finding(
                    ticker=f"BOOK_{label}",
                    stage="book",
                    severity="warning",
                    check_id="book.window.missing_file",
                    evidence=str(path),
                    suggestion="Run window-book assembly after generating ideas.",
                )
            )
            continue
        selected = payload.get("ideas") or []
        if 0 < len(selected) < minimum:
            findings.append(
                Finding(
                    ticker=f"BOOK_{label}",
                    stage="book",
                    severity="info",
                    check_id="book.window.thin",
                    evidence=f"{len(selected)} names; aggregate target starts at {minimum}",
                    suggestion="Keep the window thin rather than relaxing signal or concentration limits.",
                )
            )
        for row in selected:
            ticker = str((row.get("candidate") or {}).get("ticker") or "")
            source = by_ticker.get(ticker)
            if source is None:
                findings.append(
                    Finding(
                        ticker=ticker or f"BOOK_{label}",
                        stage="book",
                        severity="error",
                        check_id="book.window.not_subset",
                        evidence=f"selected in {label} but absent from ideas.json",
                        suggestion="Window books must contain only generated ideas.",
                    )
                )
                continue
            days = (source.get("earnings") or {}).get("days_to_earnings")
            actual = bucket_for_days(days)
            if actual == BEYOND or actual != label:
                findings.append(
                    Finding(
                        ticker=ticker,
                        stage="book",
                        severity="error",
                        check_id="book.window.wrong_bucket",
                        evidence=f"stored days={days}; expected {actual}; selected in {label}",
                        suggestion="Use the stored run-date distance for window assignment.",
                    )
                )
            gates = (source.get("extra") or {}).get("gates") or []
            if gates:
                findings.append(
                    Finding(
                        ticker=ticker,
                        stage="book",
                        severity="warning",
                        check_id="book.window.gated_but_selected",
                        evidence=str(gates),
                        suggestion="Window selection must honor the same process gates as the aggregate book.",
                    )
                )
            sector = (source.get("candidate") or {}).get("sector")
            if sector in exclude:
                findings.append(
                    Finding(
                        ticker=ticker,
                        stage="sector",
                        severity="warning",
                        check_id="book.window.excluded_sector",
                        evidence=f"{sector} is in exclude_sectors",
                        suggestion="Honor excluded sectors in window selection.",
                    )
                )
    return findings


def audit_run(ideas_folder: Path | None = None) -> AuditResult:
    cfg = toml_settings()
    folder = Path(ideas_folder) if ideas_folder else _latest_ideas_folder()
    ideas = _idea_rows(_load_json(data_dir("curated", "ideas.json")))
    if folder and not ideas:
        ideas = []
        for path in find_idea_files(folder):
            payload = _load_json(path)
            if isinstance(payload, dict) and payload.get("candidate"):
                ideas.append(payload)
    book = _load_json(data_dir("curated", "book.json"))
    snap = _load_json(data_dir("curated", "macro_snapshot.json"))
    ism = _load_json(data_dir("curated", "ism.json"))
    result = AuditResult(
        as_of=datetime.now(timezone.utc).isoformat(),
        ideas_folder=str(folder) if folder else "",
    )
    result.findings.extend(check_worldview(ism if isinstance(ism, dict) else None, snap if isinstance(snap, dict) else None, cfg))
    packs: dict[str, dict] = {}
    research_root = data_dir("raw", "research")
    if research_root.exists():
        for path in research_root.glob("*.json"):
            payload = _load_json(path)
            if isinstance(payload, dict):
                packs[path.stem] = payload
    for idea in ideas:
        ticker = str((idea.get("candidate") or {}).get("ticker") or "")
        result.findings.extend(check_idea(idea, packs.get(ticker), cfg))
    result.findings.extend(check_book(book if isinstance(book, dict) else None, ideas, cfg))
    result.findings.extend(check_window_books(ideas, cfg))
    result.findings.extend(check_markdown_files(folder, ideas))
    result.finalize()
    return result


def render_markdown(result: AuditResult) -> str:
    lines = [
        "# PTM process audit",
        "",
        f"As of: {result.as_of}",
        f"Ideas folder: {result.ideas_folder or 'n/a'}",
        f"Summary: {result.summary}",
        "",
    ]
    if not result.findings:
        lines.append("No findings.")
        return "\n".join(lines) + "\n"
    by_stage: dict[str, list[Finding]] = {}
    for finding in result.findings:
        by_stage.setdefault(finding.stage, []).append(finding)
    for stage, rows in by_stage.items():
        lines.append(f"## {stage} ({len(rows)})")
        lines.append("")
        for finding in rows:
            lines.append(f"- **{finding.severity}** `{finding.check_id}` `{finding.ticker}`: {finding.evidence}")
            lines.append(f"  - {finding.suggestion}")
        lines.append("")
    return "\n".join(lines)


def write_audit(result: AuditResult) -> Path:
    payload = {
        "as_of": result.as_of,
        "ideas_folder": result.ideas_folder,
        "summary": result.summary,
        "by_stage": result.by_stage,
        "by_severity": result.by_severity,
        "findings": [finding.__dict__ for finding in result.findings],
    }
    json_path = data_dir("curated", "audit.json")
    write_json(json_path, payload)
    folder = Path(result.ideas_folder) if result.ideas_folder else _latest_ideas_folder()
    if folder is None:
        folder = ideas_dir(day_slug())
        folder.mkdir(parents=True, exist_ok=True)
    md_path = folder / "AUDIT.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return md_path


# Silence unused ROOT import if a test wants the repo root for fixture detection.
_ = ROOT
