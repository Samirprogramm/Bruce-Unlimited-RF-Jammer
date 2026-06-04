"""Polymarket Sharp Wallets.

Score Polymarket wallets by *accuracy* (skill vs. the market-implied
baseline), not by raw profit, then surface consensus signals when several
independently-sharp wallets land on the same side of a market.

The public surface mirrors the pipeline described in the project README:

    scan -> score -> rank -> signal

Most callers only need a handful of names:

    from polymarket_sharp import (
        score_wallet,
        rank_wallets,
        find_signals,
        run_pipeline,
    )
"""

from .models import (
    Market,
    ResolvedBet,
    OpenPosition,
    WalletHistory,
    WalletScore,
    Signal,
)
from .scoring import score_wallet
from .ranking import rank_wallets
from .signals import find_signals
from .pipeline import run_pipeline, PipelineResult

__all__ = [
    "Market",
    "ResolvedBet",
    "OpenPosition",
    "WalletHistory",
    "WalletScore",
    "Signal",
    "score_wallet",
    "rank_wallets",
    "find_signals",
    "run_pipeline",
    "PipelineResult",
]

__version__ = "0.1.0"
