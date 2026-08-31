"""Render a deep dive as a self-contained markdown report.

Also renders the pipeline's trade-idea markdown when the dive IS the
qualitative pass: the quant header, the verdict and its weighted evidence, the
catalyst block and the analyst-revision block, followed by the full dive, so
each idea file is self-contained.
"""

from __future__ import annotations

from ptm.deepsearch.models import DeepResult

_STANCE_COLOR = {
    "constructive": "🟢",
    "cautious": "🔴",
    "balanced": "🟡",
    "unclear": "⚪",
}

_MACRO_DIR_COLOR = {"helps": "🟢", "hurts": "🔴", "mixed": "🟡"}


def _src_line(source) -> str:
    if not source or not (getattr(source, "url", "") or getattr(source, "title", "")):
        return ""
    label = source.title or source.url
    if source.title and source.url:
        return f" — [source]({source.url})"
    return f" — {label}"


def _dated(dated: str) -> str:
    return f" *(dated {dated})*" if dated else ""


def render_macro_section(view) -> str:
    """Macro & ISM section: dashboard state, sector tilt, transmission map."""
    if not view or not getattr(view, "available", False):
        reason = getattr(view, "reason", "") or "curated macro/ISM files not found (run `ptm weekly` or `ptm ingest`)"
        return f"\n## Macro & ISM backdrop\n\n*Not available: {reason}.*\n"
    out: list[str] = ["\n## Macro & ISM backdrop (PTM dashboard)", ""]
    metrics = []
    if view.pmi is not None:
        metrics.append(("ISM PMI", f"{view.pmi:.1f}"))
    if view.nmi is not None:
        metrics.append(("ISM NMI", f"{view.nmi:.1f}"))
    if view.new_orders is not None:
        metrics.append(("Mfg new orders", f"{view.new_orders:.1f} (50 = flat)"))
    if view.tens_minus_twos is not None:
        metrics.append(("10y−2y", f"{view.tens_minus_twos:+.2f}"))
    if view.vix is not None:
        metrics.append(("VIX", f"{view.vix:.1f}"))
    if view.spx_in_bear is not None:
        metrics.append(("S&P regime", "below 20% bear level" if view.spx_in_bear else "above 20% bear level"))
    if metrics:
        out.append("| Print | Value |")
        out.append("|---|---|")
        for name, value in metrics:
            out.append(f"| {name} | {value} |")
        out.append("")
    if view.bias:
        out.append(f"**Dashboard bias:** {view.bias}")
    if view.sector_tilt:
        icon = "🟢" if view.sector_tilt == "long" else "🔴" if view.sector_tilt == "short" else "⚪"
        scope = f" — {view.sector}" if view.sector else ""
        out.append(f"**ISM sector tilt{scope}:** {icon} {view.sector_tilt} — {view.sector_why or 'no reason recorded'}")
    for flag in view.industry_flags[:3]:
        out.append(f"- **ISM industry flag:** {flag.get('why') or flag.get('industry') or ''}")
    for comment in view.respondent_comments[:3]:
        out.append(f"> ISM purchasing manager ({comment.get('industry') or 'n/a'}): {(comment.get('quote') or '')[:240]}")
    if view.implications:
        out.append("")
        out.append("### How the backdrop transmits into this company's fundamentals")
        out.append("")
        for imp in view.implications:
            icon = _MACRO_DIR_COLOR.get(imp.direction, "⚪")
            out.append(f"- **{icon} {imp.channel} — {imp.direction} fundamentals**: {imp.why}")
    if view.narrative:
        out.append("")
        out.append(view.narrative)
    return "\n".join(out) + "\n"


def render_markdown(result: DeepResult) -> str:
    ticker = result.ticker
    lines: list[str] = []
    title_name = result.name or ticker
    lines.append(f"# {ticker} — deep qualitative dive")
    lines.append("")
    lines.append(f"*{title_name} · {result.sector or 'n/a'} · {result.industry or 'n/a'} · run {result.as_of} · LLM: {'yes' if result.llm_used else 'no'}*")
    lines.append("")

    thesis = result.thesis
    if result.error and not thesis:
        lines.append(f"> **Dive incomplete:** {result.error}")
        lines.append("")
        if result.research and result.research.findings:
            lines.append("## What was found anyway")
            lines.append("")
            for f in result.research.findings[:15]:
                lines.append(f"- {f.claim}{_dated(f.dated)}{_src_line(f.source)}")
            lines.append("")
        return "\n".join(lines)

    if thesis:
        icon = _STANCE_COLOR.get(thesis.stance, "⚪")
        lines.append(f"## Verdict: {icon} {thesis.stance.upper()}")
        lines.append("")
        lines.append(f"**Confidence:** {thesis.confidence} — {thesis.confidence_why}")
        lines.append("")
        lines.append("## Thesis")
        lines.append("")
        lines.append(thesis.thesis)
        lines.append("")

    # Macro & ISM transmission sits right after the thesis so the reader sees
    # the dashboard state before the driver-by-driver debate.
    lines.append(render_macro_section(result.macro))

    if thesis and thesis.drivers:
        lines.append("## Drivers")
        lines.append("")
        lines.append("| Driver | Read | Evidence | Confidence |")
        lines.append("|---|---|---|---|")
        for d in thesis.drivers:
            ev = d.evidence[:160]
            src = f" [src]({d.source.url})" if d.source.url else ""
            lines.append(f"| {d.name} | {d.direction} | {ev}{src} | {d.confidence} |")
        lines.append("")

    if thesis and thesis.debate:
        lines.append("## Bull vs bear, driver by driver")
        lines.append("")
        for r in thesis.debate:
            lines.append(f"### {r.driver}")
            lines.append("")
            lines.append(f"- **Bull:** {r.bull}{_src_line(r.bull_source)}")
            lines.append(f"- **Bear:** {r.bear}{_src_line(r.bear_source)}")
            verdict = f"**Verdict: {r.verdict_side or 'unresolved'}**"
            if r.verdict:
                verdict += f" — {r.verdict}"
            lines.append(f"- {verdict}")
            lines.append("")

    # The scorecard belongs HERE, inside the dive and right after the debate it
    # scores — the synthesis scored each driver while choosing the stance, so
    # the numbers read as the debate's outcome, not a bolt-on report.
    from ptm.deepsearch.verdict import driver_rows as _rows_for_card

    card = _scorecard_md(_rows_for_card(thesis), scored_by_synthesis=bool(thesis and thesis.drivers and any(d.score is not None for d in thesis.drivers)))
    if card:
        lines += card

    if thesis and thesis.bull_case:
        lines.append("## Bull case")
        lines.append("")
        for b in thesis.bull_case:
            lines.append(f"- **({b.strength})** {b.point}{_src_line(b.source)}")
            if b.evidence:
                lines.append(f"  - {b.evidence}")
        lines.append("")

    if thesis and thesis.bear_case:
        lines.append("## Bear case")
        lines.append("")
        for b in thesis.bear_case:
            lines.append(f"- **({b.severity})** {b.point}{_src_line(b.source)}")
            if b.evidence:
                lines.append(f"  - {b.evidence}")
        lines.append("")

    if thesis and thesis.falsifiers:
        lines.append("## What would change this call")
        lines.append("")
        for f in thesis.falsifiers:
            lines.append(f"- {f}")
        lines.append("")

    if result.catalysts:
        lines.append("## Catalysts")
        lines.append("")
        for c in result.catalysts:
            window = f" — *{c.window}*" if c.window else ""
            lines.append(f"- **{c.event}**{window}{_src_line(c.source)}")
            if c.expected:
                lines.append(f"  - {c.expected}")
        lines.append("")

    research = result.research
    if research and research.findings:
        lines.append("## Research base")
        lines.append("")
        if research.queries_run:
            lines.append(f"*Queries run ({len(research.queries_run)}):* " + "; ".join(f"`{q}`" for q in research.queries_run))
            lines.append("")
        cats: dict[str, list] = {}
        for f in research.findings:
            cats.setdefault(f.category or "other", []).append(f)
        for cat in sorted(cats):
            lines.append(f"### {cat}")
            lines.append("")
            for f in cats[cat]:
                lines.append(f"- {f.claim}{_dated(f.dated)}{_src_line(f.source)}")
            lines.append("")

    lines.append("---")
    lines.append("*Generated by the PTM deep-dive engine. Web sources via Ollama web search; "
                 "filing context from SEC EDGAR. Claims are as reported by their sources — verify before trading.*")
    return "\n".join(lines)


def render_idea_markdown(
    candidate,
    qual,
    cats,
    earnings,
    expectations: dict | None,
    deep_md: str,
    deepdive_extra: dict | None = None,
) -> str:
    """The pipeline idea file when the deep dive IS the qualitative pass.

    Deterministic — no template LLM call. The header carries what the book
    build was decided on (side, screen facts, verdict, weighted conviction,
    catalysts, revision momentum); the full deep dive follows, so the idea
    file and the dive the evidence came from never diverge.
    """
    from ptm.llm import _earnings_block, _evidence_block, _revisions_block, _relative_peg_line
    from ptm.models import Side
    from ptm.risk import catalyst_window

    window_low, window_high = catalyst_window()

    side = "LONG" if candidate.side == Side.LONG else "SHORT"
    stance = (deepdive_extra or {}).get("stance") or (result_stance(qual) if qual else "")
    confidence = (deepdive_extra or {}).get("confidence", "")
    stance_bit = f" · dive stance {stance}" + (f" ({confidence} confidence)" if confidence else "") if stance else ""
    s_long = (deepdive_extra or {}).get("score_long")
    s_short = (deepdive_extra or {}).get("score_short")
    s_bit = ""
    if s_long is not None:
        s_val = (deepdive_extra or {}).get("score_s") or 0.0
        s_bit = (
            f" · evidence score {s_val:+.2f} (long {s_long:.1f}/10, short {s_short:.1f}/10)"
            " — scorecard inside the dive"
        )
    if (deep_md or "").strip():
        basis = (
            f"Qualitative basis: **deep research dive**{stance_bit}{s_bit} — full report below; "
            "every claim is source-cited there."
        )
    else:
        basis = (
            "Qualitative basis: the deep research dive FAILED for this name, so no verdict "
            "evidence is shown here and the idea is not bookable; rerun to retry the dive."
        )
    header = [
        f"# {side} {candidate.ticker} — {candidate.name}",
        "",
        f"Sector: {candidate.sector}  ",
        f"EG case: {candidate.eg_case}  ",
        f"Price: {candidate.price}  Mcap: {candidate.market_cap}",
        f"PE1 {candidate.pe1} vs sector {candidate.sector_pe1}"
        + (
            f" vs industry {candidate.industry_pe1}"
            if candidate.industry_pe1 is not None
            else ""
        )
        + f"  EG1 {candidate.eg1}",
        _relative_peg_line(candidate),
        "",
        basis,
        "",
        "## Verdict",
        "",
        (qual.why or qual.summary or "n/a") if qual else "n/a",
        "",
        *_evidence_block(qual, candidate.side),
        *([f"- {q}" for q in (qual.evidence_quotes or [])[:3]]),
        "",
        "## Catalysts",
        "",
        *_earnings_block(earnings),
        f"Earnings inside the {window_low}-{window_high} day catalyst window: "
        f"{cats.earnings_in_window}",
        *(
            [f"- {item}" for item in (cats.non_earnings or [])]
            or ["- non-earnings events: see the dive's dated catalyst list below"]
        ),
        f"- Gate: {cats.reason}",
        "",
        *_revisions_block(expectations),
    ]
    lines = [ln for ln in header if ln is not None]
    if (deep_md or "").strip():
        lines += [
            "---",
            "",
            deep_md.strip(),
        ]
    return "\n".join(lines) + "\n"


def _scorecard_md(rows, scored_by_synthesis: bool = False) -> list[str]:
    """The scorecard for a list of DriverScore rows: S, the mirrored
    long/short pair and the per-driver table, so a reader can SEE the verdict
    as numbers — derived from the dive's own reasoned driver scores, with the
    weights applied mechanically and visibly."""
    from ptm.deepsearch.verdict import (
        _score_threshold,
        aggregate_scores,
        category_weights,
        score_supports,
    )
    from ptm.models import Side

    rows = list(rows or [])
    if not rows:
        return []
    agg = aggregate_scores(rows)
    s = agg["s"]
    long_score, short_score = agg["long"], agg["short"]
    threshold = _score_threshold()
    is_long = score_supports(s, Side.LONG, threshold)
    is_short = score_supports(s, Side.SHORT, threshold)
    verdict_word = (
        "constructive — supports a LONG"
        if is_long
        else ("cautious — supports a SHORT" if is_short else "balanced — no edge either way")
    )
    source_note = (
        "Scores were written by the synthesis pass together with the stance — sign = which side won "
        "the driver's debate (bull +, bear −), magnitude = how decisively, per the analyst's own "
        "reasoning; the FIXED category weights apply mechanically. "
        if scored_by_synthesis
        else "Scores derive mechanically from the dive's own debate verdicts (this dive predates "
        "synthesis-side scoring); rerun the dive for analyst-scored drivers. "
    )
    covered = float(agg.get("weight_covered") or 1.0)
    absent = [c for c in ("valuation", "fundamentals", "catalysts", "competitive", "risk") if agg[c] is None]
    renorm_note = (
        f"This dive scored no {', '.join(absent)} driver(s), so S is renormalized over the categories it "
        f"did score ({covered * 100:.0f}% of the fixed mix scaled to 100%) — the decision bar means the "
        "same thing for every dive. "
        if covered < 0.995
        else ""
    )
    weights_txt = ", ".join(
        f"{c} {w * 100:.0f}%" for c, w in category_weights().items()
    )
    lines = [
        "## Qualitative scorecard",
        "",
        f"**Evidence score S = {s:+.2f}** on a −2..+2 scale → "
        f"**long thesis {long_score:.1f}/10 · short thesis {short_score:.1f}/10** → {verdict_word}.",
        "",
        source_note
        + renorm_note
        + f"Category weights: {weights_txt}, scaled by the dive's own driver confidence. Sub-scores are the same 0-10 view "
        "restricted to a category (short view = 10 minus the long view); n/a = no driver there.",
        "",
        "| Driver | Category | Verdict | Score | Conf | Weight | Contribution |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.driver} | {r.category or 'n/a'} | {r.verdict_side or 'tie'} | {r.score:+.2f} | {r.confidence or 'n/a'} "
            f"| {r.weight * 100:.0f}% | {r.contribution:+.2f} |{_why_cell(r.why)}"
        )
    subs = []
    for label in ("valuation", "fundamentals", "catalysts", "competitive", "risk"):
        value = agg[label]
        subs.append(f"{label} {'n/a' if value is None else f'{value:.1f}/10'}")
    lines.append("")
    lines.append("Sub-scores: " + " · ".join(subs))
    lines.append("")
    return lines


def _why_cell(why: str) -> str:
    return f" {why}" if why else ""


def result_stance(qual) -> str:
    """The dive stance carried on a QualResult's why prefix, when present.

    The prefix also carries the numeric score ('[dive: cautious | S=-1.35]');
    the label alone is what callers want.
    """
    why = (getattr(qual, "why", "") or "") or (getattr(qual, "summary", "") or "")
    if why.startswith("[dive: "):
        return why.split("]", 1)[0].removeprefix("[dive: ").split(" | ")[0]
    return ""