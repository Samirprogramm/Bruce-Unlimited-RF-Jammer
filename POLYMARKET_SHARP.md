# Polymarket Sharp Wallets

Find the wallets on Polymarket that are *actually* sharp — ranked by
**accuracy**, not profit — and only surface a prediction when several of them
independently land on the same side of a market.

> Most "top trader" lists rank by P&L, which mostly rewards size and luck.
> A whale can dump millions into 50/50 markets, get lucky, and top the
> leaderboard while being no better than a coin flip. This project grades a
> wallet the way you'd grade a free-throw shooter: against the rate it was
> *expected* to hit.

## The idea, in one paragraph

Every bet a wallet makes has a market-implied probability built into the price
it paid. Buy the "Yes" side at **0.70** and the crowd is saying there's a 70%
chance — so an *average* bettor wins ~70% of bets like that. Sum those implied
probabilities across all of a wallet's settled bets and you get its
**baseline**: the number of wins you'd expect from someone with no edge. Compare
that to how many it *actually* won. If a wallet keeps winning far more often
than its prices imply, that's skill, not noise — and we can measure exactly how
unlikely the gap is by chance.

## How it works

```
scan  ->  score  ->  rank  ->  signal
```

1. **Scan** — pull markets and wallet positions from Polymarket
   (`polymarket_sharp/client.py`), or generate a synthetic universe for
   testing (`polymarket_sharp/synthetic.py`).

2. **Score** (`scoring.py`) — model each wallet's settled bets as a
   Poisson-binomial (independent Bernoulli trials with different probabilities)
   and compute a z-score for how far its real win count beats the baseline:

   ```
   expected_wins = Σ pᵢ                     # market-implied baseline
   actual_wins   = Σ outcomeᵢ
   z = (actual_wins − expected_wins) / sqrt(Σ pᵢ(1 − pᵢ))
   ```

   A wallet is flagged **sharp** only if it clears *all three* gates:
   - enough settled bets (default ≥ 30) — small samples prove nothing,
   - a high z-score (default ≥ 2.326, i.e. ~99% one-sided),
   - a real accuracy edge over its own baseline (default ≥ 3 points).

   In practice the large majority of wallets fail: they win at roughly their
   implied rate, which is exactly what luck predicts.

3. **Rank** (`ranking.py`) — survivors are sorted by z-score, so a wallet
   hitting 95/100 outranks one hitting 75/100 and carries more weight
   downstream. Each gets a 0–100 **confidence** score (`Φ(z)`).

4. **Signal** (`signals.py`) — a single sharp wallet can still be wrong, so we
   never surface a lone bet. We wait for **independent agreement**: several
   top-ranked wallets holding the *same* side of the same open market. Each
   votes with its skill weight; a signal only fires when the dominant side
   clears the wallet-count, agreement, and net-conviction thresholds.

## Quick start

No third-party packages are required to run the core or the demo.

```bash
# End-to-end on synthetic data (offline) — see the full flow:
python -m polymarket_sharp.cli demo

# Scale it up:
python -m polymarket_sharp.cli demo --wallets 20000 --seed 1

# Run the tests:
pip install pytest        # only needed for the test suite
pytest
```

### Scoring real wallets

```bash
# Provide your own newline-delimited wallet addresses:
python -m polymarket_sharp.cli live --wallets-file addresses.txt

# Optional, nicer HTTP:
pip install requests
```

The live client targets the public Gamma (`gamma-api.polymarket.com`) and
Data (`data-api.polymarket.com`) APIs. Polymarket's schema changes over time;
`client.py` keeps parsing isolated in small `_parse_*` / `build_wallet_history`
helpers you can adapt. For rigorous accuracy scoring you'll want to reconstruct
each wallet's *settled outcomes from full fill history* rather than the
snapshot positions endpoint — that reconstruction is the one piece left as a
deliberate extension point.

## Library use

```python
from polymarket_sharp import run_pipeline
from polymarket_sharp.synthetic import generate_universe

markets, histories = generate_universe(n_wallets=5000)
result = run_pipeline(markets, histories)
print(result.report())

for wallet in result.sharp[:10]:
    print(wallet.summary())

for signal in result.signals:
    print(signal.summary())
```

## Tuning

All thresholds live in `polymarket_sharp/config.py` (`ScoringConfig`,
`SignalConfig`) and can be passed into `run_pipeline`. Loosen them to explore,
tighten them to be conservative.

## Caveats

- **Accuracy ≠ guarantees.** Beating the baseline historically is evidence of
  skill, not a promise about the next market. Markets adapt and edges decay.
- **Garbage in, garbage out.** The scoring is only as good as the reconstructed
  entry prices and resolved outcomes. Validate the data layer before trusting
  the rankings.
- **Not financial advice.** This is a research tool for analyzing public
  on-chain trading behavior.

## Layout

```
polymarket_sharp/
  config.py      # tunable thresholds
  models.py      # dataclasses (Market, ResolvedBet, WalletScore, Signal, ...)
  scoring.py     # accuracy-vs-baseline statistics
  ranking.py     # rank & filter the sharp minority
  signals.py     # independent-consensus signal detection
  client.py      # Polymarket Gamma + Data API client (no hard deps)
  synthetic.py   # offline data generator for demo/tests
  pipeline.py    # scan -> score -> rank -> signal
  cli.py         # `demo` and `live` commands
tests/           # pytest suite
```
