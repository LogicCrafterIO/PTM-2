from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from ptm.config import data_dir, toml_settings
from ptm.io import write_json
from ptm.models import Bias, BookProposal, IdeaState, Side, TradeIdea



def _pick(pool: list[TradeIdea], limit: int, max_per_sector: int) -> list[TradeIdea]:
    """Best-ranked names, spread across sectors.

    `pool` arrives in screen-rank order, so this walks it top-down and takes the
    strongest names subject to a per-sector cap. Six shorts drawn from one
    sector is one bet, not six, and nothing upstream prevented that.

    The cap is NOT relaxed to fill the book. Quietly topping up from an already
    -full sector would make the setting meaningless and hide correlated risk;
    instead the side comes back short and assemble_book records why.
    """
    chosen: list[TradeIdea] = []
    per_sector: Counter[str] = Counter()
    for idea in pool:
        if len(chosen) >= limit:
            break
        sector = idea.candidate.sector or "Unclassified"
        if per_sector[sector] >= max_per_sector:
            continue
        chosen.append(idea)
        per_sector[sector] += 1
    return chosen



def _beta_of(idea: TradeIdea) -> float:
    return idea.prm.beta if idea.prm and idea.prm.beta is not None else 1.0


def _portfolio_beta(longs: list[TradeIdea], shorts: list[TradeIdea]) -> float | None:
    selected = longs + shorts
    if not selected:
        return None
    n = len(selected)
    return (sum(_beta_of(i) for i in longs) - sum(_beta_of(i) for i in shorts)) / n


def _sector_ok(picked: list[TradeIdea], candidate: TradeIdea, dropped: TradeIdea, cap: int) -> bool:
    counts: Counter[str] = Counter(
        (i.candidate.sector or "Unclassified") for i in picked if i is not dropped
    )
    return counts[candidate.candidate.sector or "Unclassified"] < cap


def _rebalance_beta(
    longs: list[TradeIdea],
    shorts: list[TradeIdea],
    long_pool: list[TradeIdea],
    short_pool: list[TradeIdea],
    limit: float,
    max_per_sector: int,
) -> tuple[list[TradeIdea], list[TradeIdea], list[str]]:
    """Swap the fewest names needed to bring portfolio beta inside the limit.

    A P/E-outlier screen is beta-long by construction: premium-multiple longs are
    growth names carrying high beta, discount-multiple shorts are value and
    defensive names carrying low beta. Equal-weighting a dollar-neutral 6v6 book
    therefore lands well outside the limit even though net exposure is zero.

    Rank still leads. The book is built on rank and the sector cap first, and
    only if it breaches does this swap the worst offender for the best-ranked
    eligible replacement that moves beta toward zero. Each swap is reported, so
    the cost in rank is visible rather than silent.
    """
    swaps: list[str] = []
    for _ in range(len(longs) + len(shorts)):
        beta = _portfolio_beta(longs, shorts)
        if beta is None or abs(beta) <= limit:
            break
        best = None
        for side, picked, pool in (("long", longs, long_pool), ("short", shorts, short_pool)):
            for out_idea in picked:
                for in_idea in pool:
                    if in_idea in picked:
                        continue
                    if not _sector_ok(picked, in_idea, out_idea, max_per_sector):
                        continue
                    trial = [i for i in picked if i is not out_idea] + [in_idea]
                    new_beta = (
                        _portfolio_beta(trial, shorts)
                        if side == "long"
                        else _portfolio_beta(longs, trial)
                    )
                    if new_beta is None or abs(new_beta) >= abs(beta):
                        continue
                    if best is None or abs(new_beta) < abs(best[0]):
                        best = (new_beta, side, out_idea, in_idea)
        if best is None:
            break
        _, side, out_idea, in_idea = best
        target = longs if side == "long" else shorts
        target[target.index(out_idea)] = in_idea
        swaps.append(
            f"{side} {out_idea.candidate.ticker} (beta {_beta_of(out_idea):.2f}) -> "
            f"{in_idea.candidate.ticker} (beta {_beta_of(in_idea):.2f}) to reduce portfolio beta"
        )
    return longs, shorts, swaps


def assemble_book(ideas: list[TradeIdea], bias: Bias) -> BookProposal:
    cfg = toml_settings()
    ready = []
    for idea in ideas:
        if idea.state not in {IdeaState.TEMPLATED, IdeaState.SIZED}:
            continue
        if idea.extra.get("gates"):
            continue
        ready.append(idea)
    per_side = cfg["filters"]["max_positions"] // 2
    max_per_sector = int(cfg["filters"].get("max_per_sector") or 2)
    longs = _pick(
        [idea for idea in ready if idea.candidate.side == Side.LONG], per_side, max_per_sector
    )
    shorts = _pick(
        [idea for idea in ready if idea.candidate.side == Side.SHORT], per_side, max_per_sector
    )
    beta_limit = float(cfg["prm"]["beta_net_limit"])
    swaps: list[str] = []
    if bool(cfg["filters"].get("beta_aware_selection", True)):
        longs, shorts, swaps = _rebalance_beta(
            longs,
            shorts,
            [i for i in ready if i.candidate.side == Side.LONG],
            [i for i in ready if i.candidate.side == Side.SHORT],
            beta_limit,
            max_per_sector,
        )
    selected = longs + shorts
    for idea in selected:
        idea.state = IdeaState.SIZED
        if idea.prm:
            idea.prm.size_fraction = 1.0

    weights = []
    betas = []
    n = max(len(selected), 1)
    for idea in selected:
        sign = 1.0 if idea.candidate.side == Side.LONG else -1.0
        frac = idea.prm.size_fraction if idea.prm else 1.0
        weight = sign * frac / n
        weights.append(weight)
        betas.append(idea.prm.beta if idea.prm and idea.prm.beta is not None else 1.0)
    port_beta = sum(w * b for w, b in zip(weights, betas)) if selected else None
    gross = sum(abs(w) for w in weights) if selected else None
    net = sum(weights) if selected else None
    breaches = []
    for swap in swaps:
        breaches.append(f"beta rebalance: swapped {swap}")
    if port_beta is not None and abs(port_beta) > cfg["prm"]["beta_net_limit"]:
        breaches.append(f"portfolio beta {port_beta:.2f} exceeds ±{cfg['prm']['beta_net_limit']}")
    if bias == Bias.NET_LONG and port_beta is not None and port_beta < 0:
        breaches.append("book beta sign disagrees with NET_LONG bias")
    if bias == Bias.NET_SHORT and port_beta is not None and port_beta > 0:
        breaches.append("book beta sign disagrees with NET_SHORT bias")
    for side_name, picked, pool_all in (
        ("long", longs, [i for i in ready if i.candidate.side == Side.LONG]),
        ("short", shorts, [i for i in ready if i.candidate.side == Side.SHORT]),
    ):
        wanted = min(per_side, len(pool_all))
        if len(picked) < wanted:
            breaches.append(
                f"{side_name} side held to {len(picked)} of {wanted} available by the "
                f"{max_per_sector}-per-sector cap"
            )
    if len(selected) < cfg["filters"]["min_positions"]:
        breaches.append(f"only {len(selected)} names (target {cfg['filters']['min_positions']}-{cfg['filters']['max_positions']})")

    book = BookProposal(
        as_of=datetime.now(timezone.utc).isoformat(),
        bias=bias,
        ideas=selected,
        gross_exposure=gross,
        net_exposure=net,
        portfolio_beta=port_beta,
        limit_breaches=breaches,
        narrative=f"{len(longs)} longs / {len(shorts)} shorts; bias {bias.value}",
    )
    write_json(
        data_dir("curated", "book.json"),
        book.model_dump(),
    )
    return book
