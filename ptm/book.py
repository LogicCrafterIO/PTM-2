from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from ptm.config import data_dir, toml_settings
from ptm.io import write_json
from ptm.models import Bias, BookProposal, IdeaState, Side, TradeIdea
from ptm.ranking import ordered_ideas



def _below_mcap_floor(idea: TradeIdea, floor: float | None) -> bool:
    """Under the side's size floor, or too small to tell.

    A missing market cap counts as under: we cannot confirm the name is large
    enough, and an unborrowable micro-cap short is the risk this guards against.
    """
    if floor is None:
        return False
    cap = idea.candidate.market_cap
    return cap is None or cap < floor


def _pick(
    pool: list[TradeIdea],
    limit: int,
    max_per_sector: int,
    mcap_floor: float | None = None,
    max_below_floor: int | None = None,
) -> list[TradeIdea]:
    """Best-ranked names, spread across sectors and skewed to size.

    `pool` arrives in screen-rank order, so this walks it top-down and takes the
    strongest names subject to two caps:

    * `max_per_sector` — six shorts from one sector is one bet, not six.
    * `max_below_floor` — how many may sit under `mcap_floor`. Small-cap shorts
      carry borrow, squeeze and liquidity risk that large caps do not, so a
      short book stuffed with them is a different strategy than intended.

    Neither cap is relaxed to fill the book. Quietly topping up from a full
    sector, or with another micro-cap, would make the setting meaningless and
    hide the risk; instead the side comes back short and assemble_book records
    why.
    """
    chosen: list[TradeIdea] = []
    per_sector: Counter[str] = Counter()
    below = 0
    for idea in pool:
        if len(chosen) >= limit:
            break
        sector = idea.candidate.sector or "Unclassified"
        if per_sector[sector] >= max_per_sector:
            continue
        small = _below_mcap_floor(idea, mcap_floor)
        if small and max_below_floor is not None and below >= max_below_floor:
            continue
        chosen.append(idea)
        per_sector[sector] += 1
        below += 1 if small else 0
    return chosen


def _beta_of(idea: TradeIdea) -> float:
    """Beta against the index, from ptm/risk.py.

    Worth being precise: this is the OLS slope of the name's daily returns
    regressed on the S&P's, which equals correlation times the ratio of
    volatilities - not correlation. A name that tracks the index closely but
    moves half as far has a beta near 0.5 despite a correlation near 1.
    Defaults to 1.0 when unmeasurable, so an unknown never looks like a hedge.
    """
    return idea.prm.beta if idea.prm and idea.prm.beta is not None else 1.0


def _pool_rank(idea: TradeIdea, long_pool: list[TradeIdea], short_pool: list[TradeIdea]) -> int:
    """Where a candidate sits in the ranked pool it came from.

    Both pools arrive in selection order, so position IS rank. Anything not
    found sorts last rather than first, so a lookup miss cannot silently
    promote a name.
    """
    for pool in (long_pool, short_pool):
        try:
            return pool.index(idea)
        except ValueError:
            continue
    return 10**6


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


def _mcap_ok(
    picked: list[TradeIdea],
    candidate: TradeIdea,
    dropped: TradeIdea,
    floor: float | None,
    max_below: int | None,
) -> bool:
    """A beta swap must not smuggle in an extra sub-floor name."""
    if floor is None or max_below is None:
        return True
    if not _below_mcap_floor(candidate, floor):
        return True
    current = sum(
        1 for i in picked if i is not dropped and _below_mcap_floor(i, floor)
    )
    return current < max_below


def _rebalance_beta(
    longs: list[TradeIdea],
    shorts: list[TradeIdea],
    long_pool: list[TradeIdea],
    short_pool: list[TradeIdea],
    limit: float,
    max_per_sector: int,
    short_floor: float | None = None,
    max_small_shorts: int | None = None,
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
        # Every swap that improves beta is a candidate; the question is which to
        # take. Selecting on beta alone was a real bug - the docstring promised
        # the best-ranked eligible replacement and the code ignored rank
        # entirely, so one run swapped in AWR (revision momentum +0.0) when
        # BRK-B at +10.6 and CASY at +8.0 were both available with betas just as
        # useful. Beta is a constraint to satisfy, not a quantity to minimise.
        compliant, improving = [], []
        for side, picked, pool in (("long", longs, long_pool), ("short", shorts, short_pool)):
            for out_idea in picked:
                for in_idea in pool:
                    if in_idea in picked:
                        continue
                    if not _sector_ok(picked, in_idea, out_idea, max_per_sector):
                        continue
                    if side == "short" and not _mcap_ok(
                        picked, in_idea, out_idea, short_floor, max_small_shorts
                    ):
                        continue
                    trial = [i for i in picked if i is not out_idea] + [in_idea]
                    new_beta = (
                        _portfolio_beta(trial, shorts)
                        if side == "long"
                        else _portfolio_beta(longs, trial)
                    )
                    if new_beta is None or abs(new_beta) >= abs(beta):
                        continue
                    row = (new_beta, side, out_idea, in_idea)
                    improving.append(row)
                    if abs(new_beta) <= limit:
                        compliant.append(row)
        if not improving:
            break
        # Among swaps that bring the book INSIDE the limit, take the best-ranked
        # replacement - the pool arrives in rank order, so its index is its rank.
        if compliant:
            best = min(compliant, key=lambda r: _pool_rank(r[3], long_pool, short_pool))
        else:
            # Nothing gets inside the limit yet, so make the most progress and
            # let the loop try again.
            best = min(improving, key=lambda r: abs(r[0]))
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
    # Size band and ISM tilt still lead, but conviction outranks earnings growth
    # from here: every name has already cleared the outlier screen and the gate,
    # and eg1 is not comparable across EG cases (a turnaround's is negative by
    # definition). See ordered_ideas.
    ready = ordered_ideas(ready)
    per_side = cfg["filters"]["max_positions"] // 2
    max_per_sector = int(cfg["filters"].get("max_per_sector") or 2)
    # Small-cap shorts carry borrow, squeeze and liquidity risk a large cap does
    # not. The screen already flags names under short_mcap_min, but nothing
    # stopped the book filling up with them.
    short_floor = float(cfg["filters"].get("short_mcap_min") or 0) or None
    max_small_shorts = cfg["filters"].get("short_max_below_mcap")
    max_small_shorts = None if max_small_shorts is None else int(max_small_shorts)
    longs = _pick(
        [idea for idea in ready if idea.candidate.side == Side.LONG], per_side, max_per_sector
    )
    shorts = _pick(
        [idea for idea in ready if idea.candidate.side == Side.SHORT],
        per_side,
        max_per_sector,
        mcap_floor=short_floor,
        max_below_floor=max_small_shorts,
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
            short_floor,
            max_small_shorts,
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
            reason = f"{max_per_sector}-per-sector cap"
            if side_name == "short" and max_small_shorts is not None and short_floor:
                big = sum(1 for i in pool_all if not _below_mcap_floor(i, short_floor))
                reason += (
                    f" and the limit of {max_small_shorts} short(s) below "
                    f"${short_floor / 1e9:.0f}bn (only {big} of {len(pool_all)} ready shorts clear it)"
                )
            breaches.append(
                f"{side_name} side held to {len(picked)} of {wanted} available by the {reason}"
            )
    if max_small_shorts is not None and short_floor:
        small = sum(1 for i in shorts if _below_mcap_floor(i, short_floor))
        if small:
            names = ", ".join(
                i.candidate.ticker for i in shorts if _below_mcap_floor(i, short_floor)
            )
            breaches.append(
                f"short book carries {small} name(s) below ${short_floor / 1e9:.0f}bn "
                f"(limit {max_small_shorts}): {names}"
            )
    # Options liquidity, which replaced borrow and squeeze risk as the thing that
    # actually constrains this book. Removing the short size floor was right -
    # there is no borrow to locate on an options-expressed position - but it left
    # nothing watching whether a tradeable contract exists at a sensible price. A
    # $2bn name can carry a chain with single-digit open interest and a 30%
    # spread whatever its fundamentals say. Reported, never gated: thin is a
    # trading constraint, not a defect in the idea.
    thin: list[str] = []
    unknown: list[str] = []
    for idea in selected:
        implied = (idea.extra.get("expectations") or {}).get("implied") or {}
        if implied.get("available") and implied.get("open_interest_missing"):
            unknown.append(idea.candidate.ticker)
        elif implied.get("available") and implied.get("thin") is True:
            spread = implied.get("spread_pct")
            detail = f", spread {spread:.0f}%" if spread is not None else ""
            thin.append(
                f"{idea.candidate.ticker} (OI {implied.get('open_interest')} over "
                f"{implied.get('strikes')} strikes, {implied.get('two_sided_strikes')} quotable{detail})"
            )
        elif implied and not implied.get("available") and implied.get("reason"):
            thin.append(f"{idea.candidate.ticker} ({implied['reason']})")

    if unknown:
        breaches.append(
            f"options liquidity UNKNOWN on {len(unknown)} of {len(selected)} names - the feed "
            f"returned no open interest, which is missing data and not an empty market. Verify "
            f"in your broker before sizing: {', '.join(unknown)}"
        )
    if thin:
        breaches.append(
            f"thin or missing options chain on {len(thin)} of {len(selected)} names, "
            f"check these are tradeable before sizing: {', '.join(thin)}"
        )
    priced = [
        idea.candidate.ticker
        for idea in selected
        if idea.qual is not None and idea.qual.priced_in == "already_priced"
    ]
    if priced:
        breaches.append(
            f"{len(priced)} name(s) whose thesis the verdict judged already priced "
            f"(true, but not news): {', '.join(priced)}"
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
