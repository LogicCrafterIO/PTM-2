"""PTM-setups: group-only fundamental ranking for the next earnings print.

A second qualitative layer over the SAME theme-first front half as ptm_simple.
The deterministic stages are shared, not copied — the theme map, the weekly
radar and the quant table are identical computations writing identical
artifacts under data/simple/, so both processes read one set of numbers and
there is only one place to fix them.

What differs is the whole qualitative half:

    ptm_simple   per-member deep dive -> per-member forward brief ->
                 per-member print qual -> one review per theme judging
                 whether each valuation flag is justified
    ptm_setups   NO per-member pass at all. One ranking pass per non-COLD
                 industry over ALL its members at once, ordering them as long
                 and short setups into the next print (0-3 months), then one
                 cross-industry final over the per-industry winners.

The ranking reasons about fundamentals and valuation only: the last print's
EPS surprise, the beat record, the name's own consensus revisions, filed
guidance from EDGAR, consensus growth, and forward P/E / PEG / P/S against the
industry median. No price, no price history, no technicals — see
ptm_setups.inputs for the full list of what is deliberately kept out of the
prompt and why.

Everything writes under data/setups/ and ideas/setups/. Nothing in ptm/ or
ptm_simple reads them.
"""

__version__ = "0.1.0"


def setups_dir(*parts: str):
    """Artifacts of the ranking process, kept out of the simple process's set."""
    from ptm.config import data_dir

    path = data_dir("setups", *parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def setups_ideas_dir(*parts: str):
    from ptm.config import ideas_dir

    path = ideas_dir("setups", *parts)
    path.mkdir(parents=True, exist_ok=True)
    return path
