"""Accuracy scoring: skill vs. the market-implied baseline.

The central idea (the "free throw" test):

  * Each settled bet has a market-implied win probability ``p_i`` — the price
    the wallet paid for its side. If you only ever bought 0.70 sides, an
    *average* bettor with no edge wins ~70% of those bets.
  * The wallet's *expected* wins are ``Σ p_i``. Its *actual* wins are the
    observed count.
  * If actual >> expected by more than luck can explain, the wallet has skill.

We model the bets as a Poisson-binomial (independent Bernoulli trials with
heterogeneous probabilities) and use the normal approximation to test the
null hypothesis "this wallet is merely average".

    z = (actual_wins - expected_wins) / sqrt(Σ p_i (1 - p_i))

A large positive z means the wallet beats the baseline far more often than
chance allows. The z-score is also what we rank by, so a wallet hitting
95/100 outranks one hitting 75/100 — exactly the desired weighting.

No third-party dependencies: the normal CDF is computed from ``math.erf``.
"""

from __future__ import annotations

import math
from typing import Iterable

from .config import DEFAULT_SCORING, ScoringConfig
from .models import ResolvedBet, WalletHistory, WalletScore


def _norm_cdf(z: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def poisson_binomial_z(
    bets: Iterable[ResolvedBet],
    *,
    continuity_correction: bool = True,
) -> tuple[float, float, float, float]:
    """Return ``(z, actual_wins, expected_wins, variance)`` for the bets.

    ``variance`` is the Poisson-binomial variance ``Σ p_i (1 - p_i)``. When it
    is zero (e.g. every entry price is degenerate) the z-score is defined as
    0.0 — we cannot distinguish skill from luck.
    """
    actual = 0.0
    expected = 0.0
    variance = 0.0
    for bet in bets:
        p = bet.entry_price
        actual += 1.0 if bet.won else 0.0
        expected += p
        variance += p * (1.0 - p)

    if variance <= 0.0:
        return 0.0, actual, expected, variance

    excess = actual - expected
    if continuity_correction and excess != 0.0:
        # Shrink the gap by half an event toward zero (conservative).
        excess -= math.copysign(0.5, excess)

    z = excess / math.sqrt(variance)
    return z, actual, expected, variance


def _confidence_from_z(z: float) -> float:
    """Map a z-score to a 0..100 confidence that the wallet is truly skilled.

    This is the one-sided probability the wallet sits above the average
    bettor, ``Φ(z)``, expressed as a percentage. Negative-edge wallets land
    below 50; a wallet several sigma clear of the baseline approaches 100.
    """
    return 100.0 * _norm_cdf(z)


def score_wallet(
    history: WalletHistory,
    config: ScoringConfig = DEFAULT_SCORING,
) -> WalletScore:
    """Grade a single wallet against the market-implied baseline.

    A wallet is flagged ``is_sharp`` only if it clears *all* of:
      * ``min_resolved_bets`` settled bets (enough sample to trust),
      * ``z_threshold`` standardized excess wins (statistically significant),
      * ``min_edge`` accuracy above its own baseline (economically real).
    """
    bets = history.resolved_bets
    n = len(bets)

    if n == 0:
        return WalletScore(
            address=history.address,
            n_bets=0,
            actual_wins=0.0,
            expected_wins=0.0,
            hit_rate=0.0,
            baseline_rate=0.0,
            edge=0.0,
            z_score=0.0,
            p_value=1.0,
            confidence=0.0,
            is_sharp=False,
            weight=0.0,
        )

    z, actual, expected, _variance = poisson_binomial_z(
        bets, continuity_correction=config.continuity_correction
    )

    hit_rate = actual / n
    baseline_rate = expected / n
    edge = hit_rate - baseline_rate
    p_value = 1.0 - _norm_cdf(z)
    confidence = _confidence_from_z(z)

    is_sharp = (
        n >= config.min_resolved_bets
        and z >= config.z_threshold
        and edge >= config.min_edge
    )

    # Voting weight for consensus: only sharp wallets carry weight, and it
    # scales with how far past the baseline they sit (z). A 95-hitter thus
    # outweighs a 75-hitter when we tally agreement on a market.
    weight = z if is_sharp else 0.0

    return WalletScore(
        address=history.address,
        n_bets=n,
        actual_wins=actual,
        expected_wins=expected,
        hit_rate=hit_rate,
        baseline_rate=baseline_rate,
        edge=edge,
        z_score=z,
        p_value=p_value,
        confidence=confidence,
        is_sharp=is_sharp,
        weight=weight,
    )
