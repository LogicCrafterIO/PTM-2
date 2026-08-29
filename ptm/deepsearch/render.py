"""Render a deep dive as a self-contained markdown report."""

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