"""Real-time market depth over Groww's WebSocket feed.

REST polling gives one book snapshot per cycle. This keeps a live book and
accumulates depth samples continuously, so the delta tracker sees the shape
of order-book pressure between cycles instead of a single arbitrary instant.

What this does NOT provide: trade aggressor side. Groww streams resting
orders (buyBook/sellBook), not signed executions, so true order-flow delta
remains out of reach. See the notes in bot/depth.py.
"""
import logging
import threading
import time

from growwapi import GrowwFeed

log = logging.getLogger("bot.stream")


def _book_qty(book) -> int:
    """Total resting quantity in one side of the book.

    Groww's proto declares buyBook/sellBook as maps keyed by level index, so
    MessageToDict yields {"0": {...}, "1": {...}}, not a list. The quantity
    field is `qty`, not `quantity`.
    """
    if not book:
        return 0
    levels = book.values() if isinstance(book, dict) else book
    return sum(int(lvl.get("qty") or 0) for lvl in levels if isinstance(lvl, dict))


class DepthStream:
    """Background thread holding a live order book for a set of symbols."""

    def __init__(self, client, symbols: list[str], exchange: str = "NSE",
                 segment: str = "CASH"):
        self.g = client
        self.exchange, self.segment = exchange, segment
        self.symbols = symbols
        self.feed: GrowwFeed | None = None
        self._token_to_symbol: dict[str, str] = {}
        self._lock = threading.Lock()
        self._latest: dict[str, dict] = {}
        self._samples: dict[str, list] = {s: [] for s in symbols}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.connected = False
        self.updates = 0

    # --- setup ---------------------------------------------------------

    def _resolve(self) -> list[dict]:
        instruments = []
        for s in self.symbols:
            try:
                inst = self.g.get_instrument_by_exchange_and_trading_symbol(
                    exchange=self.exchange, trading_symbol=s)
            except Exception as exc:
                log.error("%s: cannot resolve instrument: %s", s, exc)
                continue
            token = str(inst.get("exchange_token") or "")
            if not token:
                log.error("%s: no exchange_token", s)
                continue
            self._token_to_symbol[token] = s
            instruments.append({"exchange": self.exchange,
                                "segment": self.segment,
                                "exchange_token": token})
        return instruments

    # --- ingest --------------------------------------------------------

    def _on_data(self) -> None:
        """Called by the feed on each update; snapshot every subscribed book."""
        try:
            depth = self.feed.get_market_depth() or {}
        except Exception as exc:
            log.debug("depth read failed: %s", exc)
            return
        now = time.time()
        with self._lock:
            for key, book in depth.items():
                if not book:
                    continue
                sym = self._symbol_for(key)
                if not sym:
                    continue
                buy = _book_qty(book.get("buyBook"))
                sell = _book_qty(book.get("sellBook"))
                if buy + sell <= 0:
                    continue
                self._latest[sym] = {"buy_qty": buy, "sell_qty": sell, "ts": now}
                self._samples[sym].append((now, buy, sell))
                # bound memory: keep the last ~10 minutes of ticks
                if len(self._samples[sym]) > 2000:
                    del self._samples[sym][:1000]
                self.updates += 1

    def _symbol_for(self, key) -> str | None:
        k = str(key)
        for token, sym in self._token_to_symbol.items():
            if token in k:
                return sym
        return self._token_to_symbol.get(k)

    # --- lifecycle -----------------------------------------------------

    def start(self) -> bool:
        instruments = self._resolve()
        if not instruments:
            log.error("no instruments resolved; stream not started")
            return False
        try:
            self.feed = GrowwFeed(self.g)
            self.feed.subscribe_market_depth(instruments, on_data_received=self._on_data)
        except Exception as exc:
            log.error("stream subscribe failed: %s", exc)
            return False

        def loop():
            self.connected = True
            try:
                while not self._stop.is_set():
                    try:
                        self.feed.consume()
                    except Exception as exc:
                        log.warning("feed consume error: %s", exc)
                        time.sleep(2)
            finally:
                self.connected = False

        self._thread = threading.Thread(target=loop, daemon=True, name="depth-stream")
        self._thread.start()
        log.info("depth stream started for %s", ", ".join(self.symbols))
        return True

    def stop(self) -> None:
        self._stop.set()
        try:
            if self.feed:
                self.feed.unsubscribe_market_depth(
                    [{"exchange": self.exchange, "segment": self.segment,
                      "exchange_token": t} for t in self._token_to_symbol]
                )
        except Exception:
            pass

    # --- read ----------------------------------------------------------

    def latest(self, symbol: str, max_age: float = 30.0) -> dict | None:
        """Most recent book for a symbol, or None if stale/absent."""
        with self._lock:
            d = self._latest.get(symbol)
            if not d or time.time() - d["ts"] > max_age:
                return None
            return {"buy_qty": d["buy_qty"], "sell_qty": d["sell_qty"],
                    "ratio": d["buy_qty"] / d["sell_qty"] if d["sell_qty"] else float("inf")}

    def drain(self, symbol: str) -> list[tuple]:
        """Return and clear ticks accumulated since the last call."""
        with self._lock:
            out = self._samples.get(symbol, [])
            self._samples[symbol] = []
            return out
