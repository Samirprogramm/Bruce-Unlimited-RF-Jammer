"""End-to-end orchestration: scan -> score -> rank -> signal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .config import (
    DEFAULT_SCORING,
    DEFAULT_SIGNALS,
    ScoringConfig,
    SignalConfig,
)
from .models import Market, Signal, WalletHistory, WalletScore
from .ranking import pass_rate, rank_wallets, sharp_wallets
from .signals import find_signals


@dataclass
class PipelineResult:
    """Everything the pipeline produces in one pass."""

    scores: list[WalletScore]
    sharp: list[WalletScore]
    signals: list[Signal]
    pass_rate: float

    def report(self, max_sharp: int = 20) -> str:
        lines = [
            "=" * 72,
            f"Scored {len(self.scores)} wallets | "
            f"sharp: {len(self.sharp)} ({self.pass_rate:.1%} pass rate)",
            "=" * 72,
            "",
            f"Top sharp wallets (of {len(self.sharp)}):",
        ]
        for s in self.sharp[:max_sharp]:
            lines.append("  " + s.summary())
        lines.append("")
        lines.append(f"Signals surfaced: {len(self.signals)}")
        for sig in self.signals:
            lines.append("  " + sig.summary())
            lines.append(
                "      backed by: "
                + ", ".join(w[:10] for w in sig.contributing_wallets)
            )
        return "\n".join(lines)


def run_pipeline(
    markets: Iterable[Market],
    histories: Iterable[WalletHistory],
    scoring: ScoringConfig = DEFAULT_SCORING,
    signal_cfg: SignalConfig = DEFAULT_SIGNALS,
) -> PipelineResult:
    """Run the full pipeline over a market universe and wallet set."""
    markets = list(markets)
    histories = list(histories)

    scores = rank_wallets(histories, scoring)
    sharp = sharp_wallets(scores)
    signals = find_signals(markets, histories, scores, signal_cfg)

    return PipelineResult(
        scores=scores,
        sharp=sharp,
        signals=signals,
        pass_rate=pass_rate(scores),
    )
