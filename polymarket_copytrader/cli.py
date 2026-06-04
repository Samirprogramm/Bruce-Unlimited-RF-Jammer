"""Command-line entry point.

Two modes:

  * ``demo``  — run the whole pipeline on synthetic data (no network). Great
    for seeing the scan -> score -> rank -> signal flow end to end.
  * ``live``  — pull markets and a set of wallets from Polymarket and score
    them. Requires network access and a list of wallet addresses (or a
    leaderboard that exposes them).

Usage:
    python -m polymarket_copytrader.cli demo
    python -m polymarket_copytrader.cli demo --wallets 20000 --seed 1
    python -m polymarket_copytrader.cli live --wallets-file addrs.txt
"""

from __future__ import annotations

import argparse
import sys

from .client import PolymarketClient
from .config import ScoringConfig, SignalConfig
from .pipeline import run_pipeline
from .synthetic import generate_universe


def _cmd_demo(args: argparse.Namespace) -> int:
    markets, histories = generate_universe(
        n_wallets=args.wallets,
        sharp_fraction=args.sharp_fraction,
        seed=args.seed,
    )
    result = run_pipeline(markets, histories)
    print(result.report(max_sharp=args.max_sharp))
    return 0


def _cmd_live(args: argparse.Namespace) -> int:
    client = PolymarketClient()

    addresses: list[str] = []
    if args.wallets_file:
        with open(args.wallets_file, "r", encoding="utf-8") as fh:
            addresses = [ln.strip() for ln in fh if ln.strip()]
    else:
        addresses = client.fetch_leaderboard(limit=args.wallets)

    if not addresses:
        print(
            "No wallet addresses to score. Pass --wallets-file or ensure the "
            "leaderboard endpoint is reachable.",
            file=sys.stderr,
        )
        return 2

    print(f"Fetching markets...", file=sys.stderr)
    markets = client.fetch_markets(limit=args.market_limit)
    markets_by_id = {m.market_id: m for m in markets}

    print(f"Building histories for {len(addresses)} wallets...", file=sys.stderr)
    histories = []
    for i, addr in enumerate(addresses, 1):
        try:
            histories.append(client.build_wallet_history(addr, markets_by_id))
        except Exception as err:  # pragma: no cover - network dependent
            print(f"  [{i}] {addr[:10]}: {err}", file=sys.stderr)
        if i % 25 == 0:
            print(f"  ...{i}/{len(addresses)}", file=sys.stderr)

    result = run_pipeline(markets, histories)
    print(result.report(max_sharp=args.max_sharp))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="polymarket-copytrader",
        description="Score Polymarket wallets by accuracy and surface consensus signals.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="run on synthetic data (offline)")
    demo.add_argument("--wallets", type=int, default=2000)
    demo.add_argument("--sharp-fraction", type=float, default=0.03)
    demo.add_argument("--seed", type=int, default=7)
    demo.add_argument("--max-sharp", type=int, default=20)
    demo.set_defaults(func=_cmd_demo)

    live = sub.add_parser("live", help="score real Polymarket wallets")
    live.add_argument("--wallets-file", type=str, default=None,
                      help="newline-delimited wallet addresses")
    live.add_argument("--wallets", type=int, default=100,
                      help="leaderboard size when no file is given")
    live.add_argument("--market-limit", type=int, default=1000)
    live.add_argument("--max-sharp", type=int, default=20)
    live.set_defaults(func=_cmd_live)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
