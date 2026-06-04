"""Tests for the consensus signal engine and the end-to-end pipeline."""

from polymarket_copytrader.config import SignalConfig
from polymarket_copytrader.models import (
    Market,
    OpenPosition,
    WalletHistory,
    WalletScore,
)
from polymarket_copytrader.pipeline import run_pipeline
from polymarket_copytrader.signals import find_signals
from polymarket_copytrader.synthetic import generate_universe


def _score(addr, weight, sharp=True):
    return WalletScore(
        address=addr, n_bets=100, actual_wins=80, expected_wins=50,
        hit_rate=0.8, baseline_rate=0.5, edge=0.3, z_score=weight,
        p_value=0.0, confidence=99.9, is_sharp=sharp, weight=weight,
    )


def _hist(addr, market_id, side):
    return WalletHistory(
        addr, resolved_bets=[],
        open_positions=[OpenPosition(market_id, side, 0.5, 1000)],
    )


def test_consensus_among_sharps_emits_signal():
    market = Market("m1", "Will X happen?", ("Yes", "No"))
    addrs = ["0xa", "0xb", "0xc", "0xd"]
    scores = [_score(a, 3.0) for a in addrs]
    histories = [_hist(a, "m1", "Yes") for a in addrs]

    signals = find_signals([market], histories, scores)
    assert len(signals) == 1
    assert signals[0].side == "Yes"
    assert signals[0].n_wallets == 4
    assert signals[0].agreement == 1.0


def test_lone_wallet_does_not_emit():
    market = Market("m1", "Q", ("Yes", "No"))
    scores = [_score("0xa", 5.0)]
    histories = [_hist("0xa", "m1", "Yes")]
    assert find_signals([market], histories, scores) == []


def test_split_sharps_below_agreement_no_signal():
    market = Market("m1", "Q", ("Yes", "No"))
    addrs = ["0xa", "0xb", "0xc", "0xd"]
    scores = [_score(a, 3.0) for a in addrs]
    # 2 vs 2 -> 50% agreement, below the 70% threshold.
    histories = [
        _hist("0xa", "m1", "Yes"),
        _hist("0xb", "m1", "Yes"),
        _hist("0xc", "m1", "No"),
        _hist("0xd", "m1", "No"),
    ]
    assert find_signals([market], histories, scores) == []


def test_non_sharp_wallets_excluded():
    market = Market("m1", "Q", ("Yes", "No"))
    addrs = ["0xa", "0xb", "0xc"]
    scores = [_score(a, 0.0, sharp=False) for a in addrs]
    histories = [_hist(a, "m1", "Yes") for a in addrs]
    assert find_signals([market], histories, scores) == []


def test_resolved_market_never_signals():
    market = Market("m1", "Q", ("Yes", "No"), resolved_side="Yes", closed=True)
    addrs = ["0xa", "0xb", "0xc"]
    scores = [_score(a, 3.0) for a in addrs]
    histories = [_hist(a, "m1", "Yes") for a in addrs]
    assert find_signals([market], histories, scores) == []


def test_pipeline_on_synthetic_universe():
    markets, histories = generate_universe(n_wallets=600, seed=11)
    result = run_pipeline(markets, histories)

    # ~3% sharp by construction; allow a generous band for sampling noise.
    assert 0.005 < result.pass_rate < 0.10
    assert len(result.sharp) >= 3
    # The planted consensus markets should produce at least one signal.
    assert len(result.signals) >= 1
    for sig in result.signals:
        assert sig.n_wallets >= 3
        assert sig.agreement >= 0.70
        assert 0 <= sig.confidence <= 100


def test_top_n_voters_limits_eligibility():
    market = Market("m1", "Q", ("Yes", "No"))
    addrs = [f"0x{i}" for i in range(5)]
    scores = [_score(a, float(i + 1)) for i, a in enumerate(addrs)]
    histories = [_hist(a, "m1", "Yes") for a in addrs]
    # Only top-2 voters eligible -> fewer than min_consensus_wallets -> none.
    cfg = SignalConfig(top_n_voters=2)
    assert find_signals([market], histories, scores, cfg) == []
