"""Minimal Polymarket data client.

Talks to the public Polymarket APIs:

  * Gamma API   (https://gamma-api.polymarket.com)  — market metadata.
  * Data API    (https://data-api.polymarket.com)   — trades & positions.

The client is intentionally thin and dependency-light: it uses ``requests``
when available and otherwise falls back to ``urllib`` from the standard
library, so the package has *no hard third-party requirement*. Network access
is optional — the scoring/signal engines run entirely on the dataclasses in
:mod:`polymarket_copytrader.models`, which you can also populate from the synthetic
generator or your own data source.

Note: Polymarket's schema evolves. The parsing here targets the commonly
documented fields; adjust the ``_parse_*`` helpers if the upstream shape
changes. Mapping raw fills into :class:`ResolvedBet` (entry price + realized
outcome) depends on how you reconstruct each wallet's settled positions, so
that step is left to :meth:`build_wallet_history`, which you can override.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Market, OpenPosition, ResolvedBet, WalletHistory

GAMMA_BASE = "https://gamma-api.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"

try:  # optional, nicer HTTP if present
    import requests  # type: ignore

    _HAS_REQUESTS = True
except Exception:  # pragma: no cover - environment dependent
    _HAS_REQUESTS = False


class PolymarketClient:
    """Read-only client for fetching markets, trades and positions."""

    def __init__(
        self,
        gamma_base: str = GAMMA_BASE,
        data_base: str = DATA_BASE,
        timeout: float = 20.0,
        max_retries: int = 3,
        user_agent: str = "polymarket-copytrader/0.1",
    ) -> None:
        self.gamma_base = gamma_base.rstrip("/")
        self.data_base = data_base.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agent = user_agent

    # ------------------------------------------------------------------ HTTP
    def _get(self, url: str, params: Optional[dict[str, Any]] = None) -> Any:
        if params:
            url = f"{url}?{urlencode(params)}"
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                if _HAS_REQUESTS:
                    resp = requests.get(
                        url,
                        timeout=self.timeout,
                        headers={"User-Agent": self.user_agent},
                    )
                    resp.raise_for_status()
                    return resp.json()
                req = Request(url, headers={"User-Agent": self.user_agent})
                with urlopen(req, timeout=self.timeout) as fh:  # nosec - read-only
                    return json.loads(fh.read().decode("utf-8"))
            except Exception as err:  # pragma: no cover - network dependent
                last_err = err
                time.sleep(2.0 * (attempt + 1))
        raise RuntimeError(f"GET {url} failed after {self.max_retries} tries: {last_err}")

    # --------------------------------------------------------------- markets
    def fetch_markets(self, limit: int = 500, closed: Optional[bool] = None) -> list[Market]:
        """Fetch markets from the Gamma API."""
        params: dict[str, Any] = {"limit": limit}
        if closed is not None:
            params["closed"] = str(closed).lower()
        raw = self._get(f"{self.gamma_base}/markets", params)
        items = raw if isinstance(raw, list) else raw.get("data", [])
        return [m for m in (self._parse_market(it) for it in items) if m]

    @staticmethod
    def _parse_market(it: dict[str, Any]) -> Optional[Market]:
        try:
            outcomes = it.get("outcomes")
            if isinstance(outcomes, str):
                outcomes = json.loads(outcomes)
            if not outcomes or len(outcomes) < 2:
                outcomes = ["Yes", "No"]
            sides = (str(outcomes[0]), str(outcomes[1]))

            resolved_side = None
            if it.get("closed") and it.get("umaResolutionStatus") == "resolved":
                prices = it.get("outcomePrices")
                if isinstance(prices, str):
                    prices = json.loads(prices)
                if prices:
                    win_idx = max(range(len(prices)), key=lambda i: float(prices[i]))
                    resolved_side = sides[win_idx] if win_idx < len(sides) else None

            return Market(
                market_id=str(it.get("conditionId") or it.get("id")),
                question=str(it.get("question", "")),
                sides=sides,
                resolved_side=resolved_side,
                closed=bool(it.get("closed", False)),
            )
        except Exception:
            return None

    # ---------------------------------------------------------------- wallets
    def fetch_positions(self, address: str) -> list[dict[str, Any]]:
        """Raw current positions for a wallet (Data API)."""
        raw = self._get(f"{self.data_base}/positions", {"user": address})
        return raw if isinstance(raw, list) else raw.get("data", [])

    def fetch_trades(self, address: str, limit: int = 500) -> list[dict[str, Any]]:
        """Raw trade history for a wallet (Data API)."""
        raw = self._get(
            f"{self.data_base}/trades", {"user": address, "limit": limit}
        )
        return raw if isinstance(raw, list) else raw.get("data", [])

    # Known endpoints that have, at various times, exposed top traders. We try
    # them in order and keep the first that yields addresses, so "scan all the
    # top wallets" works without a manual address list.
    _LEADERBOARD_ENDPOINTS = (
        ("{data}/leaderboard", {"window": "all"}),
        ("{data}/leaderboard", {"by": "volume", "window": "all"}),
        ("{lb}/leaderboard", {"window": "all"}),
        ("{data}/activity/leaderboard", {}),
    )

    def fetch_leaderboard(self, limit: int = 100, window: str = "all") -> list[str]:
        """Return candidate wallet addresses from the leaderboard, if exposed.

        Tries several known endpoint shapes and de-duplicates the result. The
        Polymarket leaderboard API has moved around over time; adjust
        ``_LEADERBOARD_ENDPOINTS`` if none of them resolve.
        """
        lb_base = self.data_base.replace("data-api", "lb-api")
        seen: dict[str, None] = {}
        for tmpl, extra in self._LEADERBOARD_ENDPOINTS:
            url = tmpl.format(data=self.data_base, lb=lb_base)
            params = {"limit": limit, **extra}
            if "window" in params:
                params["window"] = window
            try:
                raw = self._get(url, params)
            except Exception:  # pragma: no cover - endpoint may differ
                continue
            items = raw if isinstance(raw, list) else raw.get("data", raw.get("leaderboard", []))
            for it in items or []:
                if not isinstance(it, dict):
                    continue
                addr = (
                    it.get("proxyWallet")
                    or it.get("user")
                    or it.get("address")
                    or it.get("wallet")
                )
                if addr:
                    seen.setdefault(str(addr), None)
            if seen:
                break
        return list(seen.keys())[:limit]

    def build_wallet_history(
        self,
        address: str,
        markets_by_id: dict[str, Market],
    ) -> WalletHistory:
        """Assemble a :class:`WalletHistory` from live positions.

        Open positions on still-open markets become :class:`OpenPosition`s.
        Positions on resolved markets become :class:`ResolvedBet`s, with the
        entry price used as the market-implied baseline and the realized side
        compared against the market's winning side.

        This is a pragmatic reconstruction from the positions endpoint; for
        rigorous accuracy scoring you may want to rebuild settled outcomes
        from full fill history instead. Override this method to do so.
        """
        resolved: list[ResolvedBet] = []
        open_pos: list[OpenPosition] = []

        for p in self.fetch_positions(address):
            market_id = str(p.get("conditionId") or p.get("market") or "")
            market = markets_by_id.get(market_id)
            if market is None:
                continue
            side = str(p.get("outcome") or p.get("side") or "")
            try:
                entry = float(p.get("avgPrice") or p.get("entryPrice") or 0.0)
            except (TypeError, ValueError):
                continue
            size = float(p.get("currentValue") or p.get("size") or 0.0)
            if not 0.0 < entry < 1.0:
                continue

            if market.is_resolved():
                resolved.append(
                    ResolvedBet(
                        market_id=market_id,
                        side=side,
                        entry_price=entry,
                        won=(side == market.resolved_side),
                        size_usd=size,
                    )
                )
            elif not market.closed:
                open_pos.append(
                    OpenPosition(
                        market_id=market_id,
                        side=side,
                        entry_price=entry,
                        size_usd=size,
                    )
                )

        return WalletHistory(
            address=address, resolved_bets=resolved, open_positions=open_pos
        )
