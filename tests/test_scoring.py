"""Tests for the accuracy-vs-baseline scoring engine."""

import math

from polymarket_copytrader.config import ScoringConfig
from polymarket_copytrader.models import ResolvedBet, WalletHistory
from polymarket_copytrader.scoring import poisson_binomial_z, score_wallet


def _bets(n, price, win_rate, seed=0):
    """Deterministic bets: ``win_rate`` fraction marked as wins."""
    import random

    rng = random.Random(seed)
    bets = []
    for _ in range(n):
        bets.append(
            ResolvedBet("m", "Yes", entry_price=price, won=rng.random() < win_rate)
        )
    return bets


def test_average_wallet_is_not_sharp():
    # Wins at exactly the implied rate -> no edge -> not sharp.
    bets = _bets(200, price=0.6, win_rate=0.6, seed=1)
    score = score_wallet(WalletHistory("0xavg", bets))
    assert not score.is_sharp
    assert abs(score.edge) < 0.1
    assert score.z_score < 2.0


def test_skilled_wallet_is_flagged_sharp():
    # Buys 0.5 sides but wins 80% of the time -> big edge.
    bets = _bets(200, price=0.5, win_rate=0.8, seed=2)
    score = score_wallet(WalletHistory("0xsharp", bets))
    assert score.is_sharp
    assert score.edge > 0.2
    assert score.z_score > 2.326
    assert score.confidence > 99.0


def test_small_sample_cannot_be_sharp():
    # Perfect record but far too few bets to clear min_resolved_bets.
    bets = [ResolvedBet("m", "Yes", 0.5, won=True) for _ in range(10)]
    score = score_wallet(WalletHistory("0xtiny", bets))
    assert score.n_bets == 10
    assert not score.is_sharp


def test_empty_history_is_safe():
    score = score_wallet(WalletHistory("0xnone", []))
    assert score.n_bets == 0
    assert not score.is_sharp
    assert score.confidence == 0.0


def test_poisson_binomial_z_matches_manual():
    bets = [
        ResolvedBet("m", "Yes", 0.5, won=True),
        ResolvedBet("m", "Yes", 0.5, won=True),
        ResolvedBet("m", "Yes", 0.5, won=False),
        ResolvedBet("m", "Yes", 0.5, won=True),
    ]
    z, actual, expected, var = poisson_binomial_z(bets, continuity_correction=False)
    assert actual == 3.0
    assert math.isclose(expected, 2.0)
    assert math.isclose(var, 1.0)            # 4 * 0.25
    assert math.isclose(z, 1.0)              # (3 - 2)/sqrt(1)


def test_negative_edge_low_confidence():
    bets = _bets(200, price=0.7, win_rate=0.4, seed=3)
    score = score_wallet(WalletHistory("0xbad", bets))
    assert score.edge < 0
    assert score.confidence < 50.0
    assert not score.is_sharp


def test_higher_zscore_for_more_decisive_wallet():
    sharp_95 = _bets(200, price=0.5, win_rate=0.95, seed=4)
    sharp_75 = _bets(200, price=0.5, win_rate=0.75, seed=5)
    s95 = score_wallet(WalletHistory("0x95", sharp_95))
    s75 = score_wallet(WalletHistory("0x75", sharp_75))
    # The decisive hitter must carry more weight.
    assert s95.z_score > s75.z_score
    assert s95.weight > s75.weight


def test_custom_config_thresholds():
    # Clearly skilled (70% at 0.5 baseline) but only 50 bets: passes a lenient
    # config, fails a strict one solely on the larger sample requirement.
    bets = _bets(50, price=0.5, win_rate=0.7, seed=6)
    strict = ScoringConfig(min_resolved_bets=100, z_threshold=2.0, min_edge=0.05)
    lenient = ScoringConfig(min_resolved_bets=20, z_threshold=1.0, min_edge=0.01)
    assert not score_wallet(WalletHistory("0xc", bets), strict).is_sharp
    assert score_wallet(WalletHistory("0xc", bets), lenient).is_sharp
