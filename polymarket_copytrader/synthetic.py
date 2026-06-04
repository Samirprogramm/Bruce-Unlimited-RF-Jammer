"""Synthetic data generator.

Produces a realistic-shaped universe of markets and wallets so the pipeline
can be demonstrated and tested entirely offline. It deliberately bakes in the
README's premise: a large majority of wallets have *no edge* (they win at the
market-implied rate), while a small minority are genuinely skilled and beat
the baseline. A handful of those sharps are then nudged onto the same side of
a few open markets to produce consensus signals.
"""

from __future__ import annotations

import hashlib
import random

from .models import Market, OpenPosition, ResolvedBet, WalletHistory


def _fake_address(seed: int, i: int) -> str:
    """A deterministic, realistic-looking 40-hex wallet address."""
    return "0x" + hashlib.sha1(f"{seed}:{i}".encode()).hexdigest()[:40]


def _make_markets(n_resolved: int, n_open: int, rng: random.Random) -> list[Market]:
    markets: list[Market] = []
    for i in range(n_resolved):
        sides = ("Yes", "No")
        winner = rng.choice(sides)
        markets.append(
            Market(
                market_id=f"res-{i:04d}",
                question=f"Resolved market #{i}",
                sides=sides,
                resolved_side=winner,
                closed=True,
            )
        )
    for j in range(n_open):
        markets.append(
            Market(
                market_id=f"open-{j:04d}",
                question=f"Open market #{j}",
                sides=("Yes", "No"),
                resolved_side=None,
                closed=False,
            )
        )
    return markets


def _draw_price(rng: random.Random) -> float:
    """A plausible entry price away from the degenerate 0/1 ends."""
    return min(0.95, max(0.05, rng.betavariate(2.0, 2.0)))


def _make_resolved_bets(
    resolved_markets: list[Market],
    skill: float,
    n_bets: int,
    rng: random.Random,
) -> list[ResolvedBet]:
    """Generate ``n_bets`` settled bets for a wallet of a given ``skill``.

    ``skill`` is the extra probability of being right *beyond* the market
    baseline. skill=0 => average (wins at the implied price). skill=0.2 =>
    meaningfully sharp. The realized outcome is sampled so the chosen side
    wins with probability ``min(0.99, price + skill)``.
    """
    bets: list[ResolvedBet] = []
    for _ in range(n_bets):
        market = rng.choice(resolved_markets)
        side = rng.choice(market.sides)
        price = _draw_price(rng)
        win_prob = min(0.99, max(0.01, price + skill))
        won = rng.random() < win_prob
        bets.append(
            ResolvedBet(
                market_id=market.market_id,
                side=side,
                entry_price=price,
                won=won,
                size_usd=rng.uniform(50, 5000),
            )
        )
    return bets


def generate_universe(
    n_wallets: int = 2000,
    sharp_fraction: float = 0.03,
    n_resolved_markets: int = 300,
    n_open_markets: int = 40,
    n_consensus_markets: int = 3,
    seed: int = 7,
) -> tuple[list[Market], list[WalletHistory]]:
    """Build a synthetic ``(markets, histories)`` universe.

    A ``sharp_fraction`` of wallets are skilled; the rest are average. A few
    open markets ("consensus markets") get several sharps placed on the same
    side so the signal engine has something true to find.
    """
    rng = random.Random(seed)
    markets = _make_markets(n_resolved_markets, n_open_markets, rng)
    resolved_markets = [m for m in markets if m.is_resolved()]
    open_markets = [m for m in markets if not m.closed]
    consensus_markets = open_markets[:n_consensus_markets]

    n_sharp = max(1, int(round(n_wallets * sharp_fraction)))
    histories: list[WalletHistory] = []
    sharp_addrs: list[str] = []

    for i in range(n_wallets):
        is_sharp = i < n_sharp
        addr = _fake_address(seed, i)
        if is_sharp:
            sharp_addrs.append(addr)
            skill = rng.uniform(0.12, 0.30)        # genuinely beats baseline
            n_bets = rng.randint(60, 250)
        else:
            skill = rng.uniform(-0.02, 0.02)       # noise around average
            n_bets = rng.randint(30, 250)

        resolved_bets = _make_resolved_bets(resolved_markets, skill, n_bets, rng)

        # Average wallets hold random open positions; sharps too, but the
        # consensus markets get a deliberate skilled-side lean below.
        open_pos: list[OpenPosition] = []
        for m in rng.sample(open_markets, k=min(5, len(open_markets))):
            open_pos.append(
                OpenPosition(
                    market_id=m.market_id,
                    side=rng.choice(m.sides),
                    entry_price=_draw_price(rng),
                    size_usd=rng.uniform(50, 5000),
                )
            )

        histories.append(
            WalletHistory(
                address=addr, resolved_bets=resolved_bets, open_positions=open_pos
            )
        )

    # Plant independent consensus: put most sharps on the same (true) side of
    # each consensus market, with a little dissent so it isn't unanimous.
    hist_by_addr = {h.address: h for h in histories}
    for m in consensus_markets:
        true_side = rng.choice(m.sides)
        other = m.sides[0] if true_side == m.sides[1] else m.sides[1]
        for k, addr in enumerate(sharp_addrs):
            h = hist_by_addr[addr]
            # drop any random position already on this market
            h.open_positions = [p for p in h.open_positions if p.market_id != m.market_id]
            side = true_side if rng.random() < 0.85 else other
            h.open_positions.append(
                OpenPosition(
                    market_id=m.market_id,
                    side=side,
                    entry_price=_draw_price(rng),
                    size_usd=rng.uniform(500, 8000),
                )
            )

    return markets, histories
