"""Turn pipeline objects into JSON-serializable dicts for the dashboard/API."""

from __future__ import annotations

from typing import Any

from .models import Signal, WalletScore
from .pipeline import PipelineResult


def wallet_to_dict(s: WalletScore, rank: int | None = None) -> dict[str, Any]:
    return {
        "rank": rank,
        "address": s.address,
        "short": s.address[:6] + "…" + s.address[-4:],
        "n_bets": s.n_bets,
        "hit_rate": round(s.hit_rate, 4),
        "baseline_rate": round(s.baseline_rate, 4),
        "edge": round(s.edge, 4),
        "z_score": round(s.z_score, 3),
        "confidence": round(s.confidence, 2),
        "is_sharp": s.is_sharp,
    }


def signal_to_dict(sig: Signal) -> dict[str, Any]:
    return {
        "market_id": sig.market_id,
        "question": sig.question,
        "side": sig.side,
        "n_wallets": sig.n_wallets,
        "agreement": round(sig.agreement, 4),
        "net_weight": round(sig.net_weight, 3),
        "confidence": round(sig.confidence, 2),
        "wallets": [
            {"address": a, "short": a[:6] + "…" + a[-4:]}
            for a in sig.contributing_wallets
        ],
    }


def result_to_dict(result: PipelineResult, max_sharp: int = 100) -> dict[str, Any]:
    sharp = result.sharp[:max_sharp]
    n_total = len(result.scores)
    n_sharp = len(result.sharp)
    return {
        "stats": {
            "wallets_scanned": n_total,
            "sharp_count": n_sharp,
            "failed_count": n_total - n_sharp,
            "pass_rate": round(result.pass_rate, 4),
            "fail_rate": round(1.0 - result.pass_rate, 4),
            "signal_count": len(result.signals),
        },
        "sharp_wallets": [
            wallet_to_dict(s, rank=i + 1) for i, s in enumerate(sharp)
        ],
        "signals": [signal_to_dict(s) for s in result.signals],
    }
