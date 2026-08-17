from __future__ import annotations

import json

from pathlib import Path

import typer

from ptm.ingest.ism import scrape_ism
from ptm.llm import llm_available, model_name
from ptm.pipeline import generate_ideas, ingest, research_funnel, run, screen

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def status() -> None:
    """Show LLM backend and whether a key is loaded."""
    typer.echo(f"LLM available: {llm_available()}")
    if llm_available():
        typer.echo(f"Model: {model_name()}")


@app.command("ingest")
def ingest_cmd(
    max_tickers: int | None = typer.Option(None, help="Cap universe size for a smoke run"),
    force: bool = typer.Option(False, help="Refresh cached downloads"),
    pmi_html: Path | None = typer.Option(None, help="Saved Manufacturing PMI HTML/markdown"),
    services_html: Path | None = typer.Option(None, help="Saved Services PMI HTML/markdown"),
) -> None:
    universe = ingest(max_tickers=max_tickers, force=force, pmi_html=pmi_html, services_html=services_html)
    from ptm.config import data_dir
    from ptm.io import read_df

    fund_path = data_dir("curated", "yahoo_fundamentals.csv")
    fund_n = int(len(read_df(fund_path))) if fund_path.exists() else 0
    typer.echo(f"Universe rows: {len(universe)}; fundamentals: {fund_n}")


@app.command("ingest-ism")
def ingest_ism_cmd(
    pmi_html: Path | None = typer.Option(None, help="Saved Manufacturing PMI HTML/markdown"),
    services_html: Path | None = typer.Option(None, help="Saved Services PMI HTML/markdown"),
) -> None:
    """Parse ISM Manufacturing/Services reports from live pages or saved files."""
    payload = scrape_ism(pmi_html=pmi_html, services_html=services_html)
    typer.echo(
        json.dumps(
            {
                "pmi": payload.get("pmi"),
                "nmi": payload.get("nmi"),
                "new_orders": ((payload.get("manufacturing") or {}).get("components") or {}).get("new_orders"),
                "mfg_contraction": ((payload.get("manufacturing") or {}).get("industries") or {}).get("contraction"),
                "urls": payload.get("urls"),
                "errors": payload.get("errors"),
            },
            indent=2,
        )
    )


@app.command()
def dashboard() -> None:
    from ptm.config import data_dir
    from ptm.io import read_df

    snap, candidates = screen()
    uni_path = data_dir("curated", "universe.csv")
    fund_path = data_dir("curated", "yahoo_fundamentals.csv")
    universe_n = int(len(read_df(uni_path))) if uni_path.exists() else 0
    fundamentals_n = int(len(read_df(fund_path))) if fund_path.exists() else 0
    summary = research_funnel(universe_n, fundamentals_n, candidates, [], [])
    typer.echo(
        json.dumps(
            {
                "bias": snap.bias.value,
                "score": snap.score,
                "notes": snap.notes,
                "sector_tilts": snap.sector_tilts[:8],
                **summary,
            },
            indent=2,
        )
    )


@app.command()
def ideas(
    max_candidates: int | None = typer.Option(None),
    skip_llm: bool = typer.Option(False),
) -> None:
    out = generate_ideas(max_candidates=max_candidates, skip_llm=skip_llm)
    from ptm.book import assemble_book
    from ptm.config import data_dir
    from ptm.io import read_json
    from ptm.models import MacroSnapshot

    snap_path = data_dir("curated", "macro_snapshot.json")
    if snap_path.exists():
        snap = MacroSnapshot.model_validate(read_json(snap_path))
        assemble_book(out, snap.bias)
    typer.echo(f"Wrote {len(out)} ideas")


@app.command()
def weekly(
    max_tickers: int | None = typer.Option(None, help="Cap universe size for a smoke run"),
    max_candidates: int | None = typer.Option(None),
    skip_llm: bool = typer.Option(False),
    force: bool = typer.Option(False, help="Refresh cached downloads"),
    pmi_html: Path | None = typer.Option(None, help="Saved Manufacturing PMI HTML/markdown"),
    services_html: Path | None = typer.Option(None, help="Saved Services PMI HTML/markdown"),
) -> None:
    """Ingest, screen, write ideas and a book, then audit — one command."""
    result = run(
        max_tickers=max_tickers,
        max_candidates=max_candidates,
        skip_llm=skip_llm,
        force=force,
        pmi_html=pmi_html,
        services_html=services_html,
    )
    typer.echo(json.dumps(result, indent=2))


@app.command()
def audit(
    ideas_folder: Path | None = typer.Option(None, "--ideas-dir", help="ideas/YYYY-MM-DD folder to score"),
) -> None:
    """Score a completed research run against the PTM process rubric."""
    from ptm.eval import audit_run, write_audit

    result = audit_run(ideas_folder=ideas_folder)
    path = write_audit(result)
    typer.echo(
        json.dumps(
            {
                "findings": len(result.findings),
                "by_stage": result.by_stage,
                "by_severity": result.by_severity,
                "report": str(path),
            },
            indent=2,
        )
    )
