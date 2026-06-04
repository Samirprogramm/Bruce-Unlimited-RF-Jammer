"""A self-contained web dashboard for the copytrader (stdlib only).

Launch it with::

    python -m polymarket_copytrader.cli serve

then open http://127.0.0.1:8000 in a browser. The page lets you scan a
universe of wallets (synthetic *demo* data by default, or *live* Polymarket
data where the network allows), grades them by accuracy, and surfaces the
consensus signals — all without any third-party web framework.
"""

from __future__ import annotations

import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import DEFAULT_SCORING, DEFAULT_SIGNALS
from .pipeline import run_pipeline
from .serialize import result_to_dict
from .synthetic import generate_universe

_STATIC = os.path.join(os.path.dirname(__file__), "static")


def _load_dashboard() -> bytes:
    with open(os.path.join(_STATIC, "dashboard.html"), "rb") as fh:
        return fh.read()


def _scan_demo(n_wallets: int, seed: int) -> dict:
    markets, histories = generate_universe(n_wallets=n_wallets, seed=seed)
    result = run_pipeline(markets, histories, DEFAULT_SCORING, DEFAULT_SIGNALS)
    return result_to_dict(result)


def _scan_live(n_wallets: int) -> dict:
    """Scan real Polymarket wallets. Requires network access to Polymarket."""
    from .client import PolymarketClient  # local import; optional dependency path

    client = PolymarketClient()
    addresses = client.fetch_leaderboard(limit=n_wallets)
    if not addresses:
        raise RuntimeError(
            "Could not fetch wallets from Polymarket (network blocked or "
            "leaderboard endpoint changed). Run locally where Polymarket is "
            "reachable, or use the Demo source."
        )
    markets = client.fetch_markets(limit=1000)
    markets_by_id = {m.market_id: m for m in markets}
    histories = []
    for addr in addresses:
        try:
            histories.append(client.build_wallet_history(addr, markets_by_id))
        except Exception:
            continue
    result = run_pipeline(markets, histories, DEFAULT_SCORING, DEFAULT_SIGNALS)
    return result_to_dict(result)


class _Handler(BaseHTTPRequestHandler):
    server_version = "polymarket-copytrader/0.1"

    def log_message(self, fmt, *args):  # quieter console
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict):
        self._send(code, json.dumps(payload).encode("utf-8"), "application/json")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            try:
                self._send(200, _load_dashboard(), "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(500, b"dashboard.html missing", "text/plain")
            return

        if parsed.path == "/api/scan":
            q = parse_qs(parsed.query)
            source = (q.get("source", ["demo"])[0]).lower()
            try:
                n = max(1, min(200_000, int(q.get("wallets", ["20000"])[0])))
                seed = int(q.get("seed", ["7"])[0])
            except ValueError:
                self._json(400, {"error": "bad parameters"})
                return
            try:
                data = _scan_live(n) if source == "live" else _scan_demo(n, seed)
                data["source"] = source
                self._json(200, data)
            except Exception as err:
                self._send(502, str(err).encode("utf-8"), "text/plain; charset=utf-8")
            return

        self._send(404, b"not found", "text/plain")


def serve(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True) -> None:
    httpd = ThreadingHTTPServer((host, port), _Handler)
    url = f"http://{host}:{port}"
    print(f"Polymarket Copytrader dashboard running at {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.6, lambda: _try_open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        httpd.server_close()


def _try_open(url: str) -> None:  # pragma: no cover - environment dependent
    try:
        webbrowser.open(url)
    except Exception:
        pass
