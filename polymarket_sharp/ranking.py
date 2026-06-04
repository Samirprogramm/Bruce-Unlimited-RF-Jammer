"""Rank scored wallets and isolate the sharp minority.

The README's framing: ~97% of wallets fail the accuracy test; the surviving
~3% get ranked by how decisively they beat the baseline (their z-score), so
the sharpest carry the most weight downstream.
"""

from __future__ import annotations

from typing import Iterable

from .config import DEFAULT_SCORING, ScoringConfig
from .models import WalletHistory, WalletScore
from .scoring import score_wallet


def rank_wallets(
    histories: Iterable[WalletHistory],
    config: ScoringConfig = DEFAULT_SCORING,
) -> list[WalletScore]:
    """Score every wallet and return them ranked by skill (z) descending.

    Both passing and failing wallets are returned so callers can report the
    full distribution; use :func:`sharp_wallets` to keep only the survivors.
    """
    scores = [score_wallet(h, config) for h in histories]
    scores.sort(key=lambda s: (s.is_sharp, s.z_score, s.edge), reverse=True)
    return scores


def sharp_wallets(scores: Iterable[WalletScore]) -> list[WalletScore]:
    """Filter to the wallets that passed the accuracy test, best first."""
    sharp = [s for s in scores if s.is_sharp]
    sharp.sort(key=lambda s: (s.z_score, s.edge), reverse=True)
    return sharp


def pass_rate(scores: list[WalletScore]) -> float:
    """Fraction of scored wallets that qualified as sharp (0..1)."""
    if not scores:
        return 0.0
    return sum(1 for s in scores if s.is_sharp) / len(scores)
