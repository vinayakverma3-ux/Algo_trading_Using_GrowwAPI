"""Tracks order-book delta per symbol and flags statistical spikes.

delta      = total_buy_quantity - total_sell_quantity
imbalance  = delta / (buy + sell)   -> [-1, +1], comparable across stocks
z          = (imbalance - mean) / stdev   over a rolling window

A large positive z means buy-side pressure is unusually high *for this stock
right now* — which is what a fixed ratio threshold cannot express, because
every stock has its own resting imbalance.
"""
import json
import statistics as st
from collections import deque

from bot import paths


class DepthTracker:
    def __init__(self, window: int = 40, min_samples: int = 15, instance: str = "default"):
        self.window = window
        self.min_samples = min_samples
        self.hist: dict[str, deque] = {}
        self._file = paths.LOGS / f"{instance}_depth.json"
        self._load()

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            for sym, vals in json.loads(self._file.read_text()).items():
                self.hist[sym] = deque(vals, maxlen=self.window)
        except Exception:
            pass

    def save(self) -> None:
        paths.LOGS.mkdir(exist_ok=True)
        self._file.write_text(json.dumps({s: list(d) for s, d in self.hist.items()}))

    def reset(self) -> None:
        """Clear history — call at the start of each session."""
        self.hist.clear()
        self._file.unlink(missing_ok=True)

    def observe(self, symbol: str, buy: int, sell: int) -> dict | None:
        """Record one sample and return the current reading.

        Returns None while still warming up.
        """
        total = buy + sell
        if total <= 0:
            return None
        imbalance = (buy - sell) / total
        self.hist.setdefault(symbol, deque(maxlen=self.window)).append(imbalance)
        vals = self.hist[symbol]

        reading = {
            "buy_qty": buy,
            "sell_qty": sell,
            "delta": buy - sell,
            "imbalance": imbalance,
            "samples": len(vals),
            "ready": len(vals) >= self.min_samples,
            "z": None,
            "baseline": None,
        }
        if reading["ready"]:
            prior = list(vals)[:-1]           # exclude the current sample
            mean = st.mean(prior)
            sd = st.pstdev(prior)
            reading["baseline"] = mean
            # a flat book has no dispersion; treat that as "no signal"
            reading["z"] = (imbalance - mean) / sd if sd > 1e-9 else 0.0
        return reading
