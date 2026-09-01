"""PTM-simple: theme-first earnings idea generation, separate from ptm/.

Built from docs/simple_idea_process.md (v2). The unit of analysis is the
THEME (the starter pack's watchlist clusters), not the single name: a weekly
radar detects which themes are activating (revision breadth + cluster news +
the bellwether print calendar), a deterministic ranking picks the 2-5 names
that best express an activated theme, the existing PTM deep-dive engine runs
on that shortlist, and a gatekeeping pass (no technicals, no price targets)
decides idea / parked.

Everything writes under data/simple/ and ideas/simple/ — nothing in the
main PTM pipeline reads or changes. Reused PTM pieces are read-only:
the LLM client, the drift/filings helpers, the dive engine, the curated
fundamentals table and the data_dir conventions.
"""

__version__ = "0.1.0"

from pathlib import Path


def simple_dir(*parts: str):
    """Artifacts of the simple process, kept out of the PTM curated set."""
    from ptm.config import data_dir

    path = data_dir("simple", *parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def simple_ideas_dir(*parts: str):
    from ptm.config import ideas_dir

    path = ideas_dir("simple", *parts)
    path.mkdir(parents=True, exist_ok=True)
    return path