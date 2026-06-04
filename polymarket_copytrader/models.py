"""Core data structures shared across the pipeline.

Everything here is a plain dataclass so the modules stay dependency-free and
easy to test. The Polymarket client constructs these from API responses; the
scoring and signal engines only ever see these types, never raw JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Market:
    """A Polymarket binary market.

    For our purposes a market reduces to two named sides. ``resolved_side`` is
    the winning side once the market settles (``None`` while still open).
    """

    market_id: str
    question: str
    sides: tuple[str, str]
    resolved_side: Optional[str] = None
    closed: bool = False

    def is_resolved(self) -> bool:
        return self.resolved_side is not None


@dataclass(frozen=True)
class ResolvedBet:
    """A single settled position taken by a wallet.

    ``entry_price`` is the price paid for the chosen side at entry, i.e. the
    market-implied probability that this side would win. This is the baseline
    we grade the wallet against: paying 0.70 means the crowd thought there was
    a 70% chance, so an *average* bettor wins ~70% of such bets.
    """

    market_id: str
    side: str
    entry_price: float          # market-implied P(win) at entry, in (0, 1)
    won: bool                   # did the chosen side ultimately win?
    size_usd: float = 0.0       # notional; used for tie-breaking / reporting

    def __post_init__(self) -> None:
        if not 0.0 < self.entry_price < 1.0:
            raise ValueError(
                f"entry_price must be in (0,1), got {self.entry_price!r}"
            )


@dataclass(frozen=True)
class OpenPosition:
    """A live, unresolved position a wallet currently holds on a market."""

    market_id: str
    side: str
    entry_price: float
    size_usd: float = 0.0


@dataclass
class WalletHistory:
    """Everything we know about one wallet."""

    address: str
    resolved_bets: list[ResolvedBet] = field(default_factory=list)
    open_positions: list[OpenPosition] = field(default_factory=list)


@dataclass(frozen=True)
class WalletScore:
    """The graded result for a wallet."""

    address: str
    n_bets: int
    actual_wins: float          # observed wins (sum of outcomes)
    expected_wins: float        # baseline wins implied by entry prices
    hit_rate: float             # actual_wins / n_bets
    baseline_rate: float        # expected_wins / n_bets
    edge: float                 # hit_rate - baseline_rate
    z_score: float              # standardized excess wins
    p_value: float              # one-sided P(luck explains it)
    confidence: float           # 0..100, "how far past the baseline"
    is_sharp: bool              # passed the full test?
    weight: float               # voting weight for signal consensus

    def summary(self) -> str:
        flag = "SHARP" if self.is_sharp else "----"
        return (
            f"[{flag}] {self.address[:10]}  "
            f"n={self.n_bets:<4} hit={self.hit_rate:5.1%} "
            f"base={self.baseline_rate:5.1%} edge={self.edge:+5.1%} "
            f"z={self.z_score:5.2f} conf={self.confidence:5.1f}"
        )


@dataclass(frozen=True)
class Signal:
    """A surfaced prediction backed by independent sharp-wallet consensus."""

    market_id: str
    question: str
    side: str                   # the side the sharps favor
    n_wallets: int              # distinct sharp wallets on that side
    agreement: float            # weighted share favoring the side (0..1)
    net_weight: float           # net conviction weight toward the side
    confidence: float           # 0..100 overall signal confidence
    contributing_wallets: tuple[str, ...] = ()

    def summary(self) -> str:
        return (
            f"SIGNAL  {self.side!r}  conf={self.confidence:5.1f}  "
            f"wallets={self.n_wallets}  agree={self.agreement:4.0%}  "
            f"net_w={self.net_weight:5.2f}  | {self.question}"
        )
