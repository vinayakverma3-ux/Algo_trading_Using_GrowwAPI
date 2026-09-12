"""Market data access, normalised from the Groww API."""
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from bot.clock import CLOSE, IST, OPEN


def _interval_seconds(interval: str) -> int:
    """How long a bar of this interval stays current."""
    if interval.startswith("MIN_"):
        return int(interval.split("_")[1]) * 60
    if interval.startswith("HOUR_"):
        return int(interval.split("_")[1]) * 3600
    return 3600


@dataclass
class Candle:
    ts: datetime
    open: float | None      # None on DAY candles — Groww does not populate it
    high: float
    low: float
    close: float
    volume: int


class MarketData:
    """Thin wrapper over the Groww client with per-cycle LTP caching."""

    def __init__(self, client, exchange: str = "NSE", segment: str = "CASH"):
        self.g = client
        self.exchange = exchange
        self.segment = segment
        self._ltp_cache: dict[str, float] = {}
        # Candle history changes only once per bar, but the loop runs every
        # poll. Without this cache each cycle refetched every symbol and we
        # tripped Groww's rate limit.
        self._hist_cache: dict[tuple, tuple[float, list]] = {}

    def refresh(self, symbols: list[str]) -> dict[str, float]:
        """Fetch LTPs for the universe in one call. Call once per cycle."""
        keys = tuple(f"{self.exchange}_{s}" for s in symbols)
        raw = self.g.get_ltp(exchange_trading_symbols=keys, segment=self.segment)
        self._ltp_cache = {k.split("_", 1)[1]: v for k, v in raw.items() if v is not None}
        return self._ltp_cache

    def ltp(self, symbol: str) -> float | None:
        return self._ltp_cache.get(symbol)

    def history(self, symbol: str, interval: str = "MIN_15", days: int = 5,
                regular_session_only: bool = True) -> list[Candle]:
        """Recent candles, oldest first.

        Groww also returns pre-open (09:00) and post-close (15:30, 15:45) bars
        with near-zero volume and flat prices. They are dropped by default —
        trading on them is not possible and they corrupt indicators.
        """
        key = (symbol, interval, days)
        ttl = _interval_seconds(interval)
        hit = self._hist_cache.get(key)
        if hit and (time.time() - hit[0]) < ttl:
            return hit[1]

        end = datetime.now(IST)
        start = end - timedelta(days=days)
        fmt = "%Y-%m-%d %H:%M:%S"
        raw = self.g.get_historical_candles(
            exchange=self.exchange,
            segment=self.segment,
            groww_symbol=f"{self.exchange}-{symbol}",
            start_time=start.strftime(fmt),
            end_time=end.strftime(fmt),
            candle_interval=interval,
        )
        # DAY/WEEK/MONTH bars are stamped 00:00, so the session filter would
        # discard every one of them. It only makes sense for intraday bars.
        intraday = interval.startswith("MIN") or interval.startswith("HOUR")
        out = []
        for row in raw.get("candles") or []:
            ts, o, h, l, c, v = row[0], row[1], row[2], row[3], row[4], row[5]
            if c is None:
                continue
            bar_ts = datetime.fromisoformat(ts)
            if regular_session_only and intraday and not (OPEN <= bar_ts.time() < CLOSE):
                continue
            out.append(Candle(bar_ts, o, h, l, c, int(v or 0)))
        self._hist_cache[key] = (time.time(), out)
        return out

    def depth(self, symbol: str) -> dict | None:
        """Order-book pressure. Live only — never available historically.

        Returns total pending buy/sell quantity and their ratio, or None if
        the book is empty (market closed, or an illiquid name).
        """
        try:
            q = self.g.get_quote(trading_symbol=symbol, exchange=self.exchange,
                                 segment=self.segment)
        except Exception:
            return None
        buy = q.get("total_buy_quantity") or 0
        sell = q.get("total_sell_quantity") or 0
        if not buy and not sell:
            return None
        return {
            "buy_qty": buy,
            "sell_qty": sell,
            # >1 means more pending buy interest than sell
            "ratio": (buy / sell) if sell else float("inf"),
        }

    def closes(self, symbol: str, interval: str = "MIN_15", days: int = 5) -> list[float]:
        return [c.close for c in self.history(symbol, interval, days)]
