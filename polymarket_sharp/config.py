"""Tunable thresholds for the scoring and signal pipeline.

These defaults encode the editorial stance described in the README: be
strict about what counts as "sharp" so that the ~3% that survive are
genuinely beating the market, and only emit a signal when several of them
agree without coordinating.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringConfig:
    """Parameters controlling how a single wallet is graded."""

    # A wallet needs a minimum number of *resolved* bets before we trust any
    # accuracy number. With too few samples, beating the baseline is just
    # noise (the free-throw analogy: 4/4 tells you nothing).
    min_resolved_bets: int = 30

    # One-sided z threshold the wallet must clear to be considered skilled.
    # 1.645 ~ 95% one-sided, 2.326 ~ 99%. We default strict.
    z_threshold: float = 2.326

    # The wallet must also beat the market-implied baseline by at least this
    # many percentage points of accuracy, so that statistically-significant
    # but economically-trivial edges are filtered out.
    min_edge: float = 0.03

    # Continuity correction on the normal approximation to the Poisson-
    # binomial. Mildly conservative; keep on by default.
    continuity_correction: bool = True


@dataclass(frozen=True)
class SignalConfig:
    """Parameters controlling when a consensus signal is emitted."""

    # Minimum number of *distinct* sharp wallets that must independently hold
    # the same side before we surface anything.
    min_consensus_wallets: int = 3

    # The dominant side must own at least this share of the total weight on
    # the market. 0.70 => 70% of the conviction-weight points one way.
    min_agreement: float = 0.70

    # Minimum net conviction weight (sum of winning-side weights minus losing
    # side) required. Filters markets where sharps technically agree but
    # barely have skin / conviction in the game.
    min_net_weight: float = 4.0

    # Only wallets ranked within the top-N (by skill) are eligible to vote.
    # None => every passing wallet votes.
    top_n_voters: int | None = None


DEFAULT_SCORING = ScoringConfig()
DEFAULT_SIGNALS = SignalConfig()
