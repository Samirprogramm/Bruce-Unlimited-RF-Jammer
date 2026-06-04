"""Consensus signal detection.

A single sharp wallet can still be wrong, so we never surface a lone bet.
Instead we wait for *independent agreement*: several top-ranked wallets, who
have no reason to be coordinating, holding the same side of the same open
market. Each wallet votes with the weight earned from its skill score, and we
only emit a signal when the dominant side clears the agreement, wallet-count
and net-weight thresholds in :class:`SignalConfig`.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

from .config import DEFAULT_SIGNALS, SignalConfig
from .models import Market, OpenPosition, Signal, WalletHistory, WalletScore


def _tally_market(
    positions: list[tuple[str, OpenPosition, float]],
) -> dict[str, dict]:
    """Aggregate weighted votes per side for one market.

    ``positions`` is a list of ``(address, OpenPosition, weight)``. Returns a
    mapping ``side -> {weight, wallets}``.
    """
    sides: dict[str, dict] = defaultdict(lambda: {"weight": 0.0, "wallets": set()})
    for address, pos, weight in positions:
        bucket = sides[pos.side]
        bucket["weight"] += weight
        bucket["wallets"].add(address)
    return sides


def _signal_confidence(agreement: float, net_weight: float, n_wallets: int) -> float:
    """Blend the three consensus dimensions into a 0..100 confidence.

    Agreement sets the ceiling (how lopsided the sharps are); net weight and
    wallet count temper it (a lopsided-but-thin consensus is worth less than a
    lopsided-and-deep one). The net-weight term saturates so a few extra
    sigmas don't push a marginal signal to certainty.
    """
    # Saturating contribution from conviction depth.
    depth = net_weight / (net_weight + 6.0)          # 0..1, ->1 as weight grows
    breadth = min(1.0, n_wallets / 6.0)              # 0..1, full at 6 wallets
    raw = agreement * (0.5 + 0.3 * depth + 0.2 * breadth)
    return round(100.0 * min(1.0, raw), 1)


def find_signals(
    markets: Iterable[Market],
    histories: Iterable[WalletHistory],
    scores: Iterable[WalletScore],
    config: SignalConfig = DEFAULT_SIGNALS,
) -> list[Signal]:
    """Surface consensus signals across open markets.

    Only wallets flagged sharp contribute. If ``config.top_n_voters`` is set,
    only that many of the highest-ranked sharps are eligible to vote.
    """
    score_by_addr: Mapping[str, WalletScore] = {s.address: s for s in scores}

    # Determine the eligible voter set (sharp, optionally top-N by weight).
    sharp = [s for s in score_by_addr.values() if s.is_sharp]
    sharp.sort(key=lambda s: s.weight, reverse=True)
    if config.top_n_voters is not None:
        sharp = sharp[: config.top_n_voters]
    eligible = {s.address for s in sharp}

    market_by_id = {m.market_id: m for m in markets}

    # Collect weighted open positions per market from eligible wallets only.
    by_market: dict[str, list[tuple[str, OpenPosition, float]]] = defaultdict(list)
    for hist in histories:
        if hist.address not in eligible:
            continue
        weight = score_by_addr[hist.address].weight
        for pos in hist.open_positions:
            if pos.market_id in market_by_id:
                by_market[pos.market_id].append((hist.address, pos, weight))

    signals: list[Signal] = []
    for market_id, positions in by_market.items():
        market = market_by_id[market_id]
        if market.is_resolved() or market.closed:
            continue

        sides = _tally_market(positions)
        total_weight = sum(b["weight"] for b in sides.values())
        if total_weight <= 0.0:
            continue

        # Dominant side by weight.
        top_side, top_bucket = max(sides.items(), key=lambda kv: kv[1]["weight"])
        n_wallets = len(top_bucket["wallets"])
        side_weight = top_bucket["weight"]
        agreement = side_weight / total_weight
        net_weight = 2.0 * side_weight - total_weight  # side - everyone else

        if (
            n_wallets >= config.min_consensus_wallets
            and agreement >= config.min_agreement
            and net_weight >= config.min_net_weight
        ):
            signals.append(
                Signal(
                    market_id=market_id,
                    question=market.question,
                    side=top_side,
                    n_wallets=n_wallets,
                    agreement=agreement,
                    net_weight=net_weight,
                    confidence=_signal_confidence(agreement, net_weight, n_wallets),
                    contributing_wallets=tuple(sorted(top_bucket["wallets"])),
                )
            )

    signals.sort(key=lambda s: s.confidence, reverse=True)
    return signals
