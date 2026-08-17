from __future__ import annotations

from datetime import datetime, timezone

from ptm.config import data_dir, toml_settings
from ptm.io import write_json
from ptm.models import Bias, BookProposal, IdeaState, Side, TradeIdea


def assemble_book(ideas: list[TradeIdea], bias: Bias) -> BookProposal:
    cfg = toml_settings()
    ready = []
    for idea in ideas:
        if idea.state not in {IdeaState.TEMPLATED, IdeaState.SIZED}:
            continue
        if not idea.prm or idea.prm.blocked:
            continue
        if (idea.prm.size_fraction or 0) <= 0:
            continue
        if idea.extra.get("gates"):
            continue
        ready.append(idea)
    longs = [idea for idea in ready if idea.candidate.side == Side.LONG][: cfg["filters"]["max_positions"] // 2]
    shorts = [idea for idea in ready if idea.candidate.side == Side.SHORT][: cfg["filters"]["max_positions"] // 2]
    selected = longs + shorts
    for idea in selected:
        idea.state = IdeaState.SIZED
        if idea.prm:
            idea.prm.size_fraction = 0.5 if idea.timing and idea.timing.light.value == "amber" else idea.prm.size_fraction

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
    if port_beta is not None and abs(port_beta) > cfg["prm"]["beta_net_limit"]:
        breaches.append(f"portfolio beta {port_beta:.2f} exceeds ±{cfg['prm']['beta_net_limit']}")
    if bias == Bias.NET_LONG and port_beta is not None and port_beta < 0:
        breaches.append("book beta sign disagrees with NET_LONG bias")
    if bias == Bias.NET_SHORT and port_beta is not None and port_beta > 0:
        breaches.append("book beta sign disagrees with NET_SHORT bias")
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
