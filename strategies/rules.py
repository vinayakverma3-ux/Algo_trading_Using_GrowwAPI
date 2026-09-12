"""Pure strategy rules operating on a list of bars.

Shared by the backtester and the live engine so what you test is what you trade.
Each rule returns an Entry (or None) evaluated at the LAST bar in `bars`.
"""
from dataclasses import dataclass


@dataclass
class Entry:
    side: str          # BUY only for cash intraday (no short selling in CNC)
    stop: float
    target: float
    reason: str


def _vwap(bars) -> float:
    tv = sum(((b.high + b.low + b.close) / 3) * b.volume for b in bars)
    vol = sum(b.volume for b in bars)
    return tv / vol if vol else bars[-1].close


def sma(vals, n):
    return sum(vals[-n:]) / n if len(vals) >= n else None


class OpeningRangeBreakout:
    """Buy when price breaks above the first N bars' high.

    The oldest intraday idea there is. Works in trending opens, chops badly
    in rangebound ones.
    """
    name = "opening-range-breakout"

    def __init__(self, opening_bars: int = 3, target_pct: float = 1.0, stop_pct: float = 0.5):
        self.n, self.target_pct, self.stop_pct = opening_bars, target_pct, stop_pct

    def decide(self, bars, depth: dict | None = None) -> Entry | None:
        if len(bars) <= self.n:
            return None
        opening_high = max(b.high for b in bars[:self.n])
        prev, cur = bars[-2], bars[-1]
        # break must happen on this bar, not already be in progress
        if prev.close <= opening_high < cur.close:
            p = cur.close
            return Entry("BUY", p * (1 - self.stop_pct / 100), p * (1 + self.target_pct / 100),
                         f"broke opening range high {opening_high:.2f}")
        return None


class VwapReversion:
    """Buy when price dips a set % below VWAP, betting on reversion to it."""
    name = "vwap-reversion"

    def __init__(self, dip_pct: float = 0.6, target_pct: float = 1.0, stop_pct: float = 0.5,
                 min_buy_sell_ratio: float | None = None):
        self.dip_pct, self.target_pct, self.stop_pct = dip_pct, target_pct, stop_pct
        # Require this much pending buy interest vs sell before buying a dip.
        # Live only: order-book depth does not exist in historical candles.
        self.min_buy_sell_ratio = min_buy_sell_ratio

    def decide(self, bars, depth: dict | None = None) -> Entry | None:
        if len(bars) < 6:
            return None
        v, p = _vwap(bars), bars[-1].close
        if p >= v * (1 - self.dip_pct / 100):
            return None

        note = ""
        if self.min_buy_sell_ratio is not None:
            if depth is None:
                return None          # filter requested but no book — do not trade blind
            if depth["ratio"] < self.min_buy_sell_ratio:
                return None
            note = f", buy/sell {depth['ratio']:.2f}"

        return Entry("BUY", p * (1 - self.stop_pct / 100), p * (1 + self.target_pct / 100),
                     f"{(v - p) / v * 100:.2f}% below VWAP {v:.2f}{note}")


class SmaCross:
    """Buy when a fast SMA crosses above a slow SMA."""
    name = "sma-cross"

    def __init__(self, fast: int = 5, slow: int = 20, target_pct: float = 1.0, stop_pct: float = 0.5):
        self.fast, self.slow = fast, slow
        self.target_pct, self.stop_pct = target_pct, stop_pct

    def decide(self, bars, depth: dict | None = None) -> Entry | None:
        c = [b.close for b in bars]
        if len(c) < self.slow + 1:
            return None
        f_now, s_now = sma(c, self.fast), sma(c, self.slow)
        f_prev, s_prev = sma(c[:-1], self.fast), sma(c[:-1], self.slow)
        if None in (f_now, s_now, f_prev, s_prev):
            return None
        if f_prev <= s_prev and f_now > s_now:
            p = c[-1]
            return Entry("BUY", p * (1 - self.stop_pct / 100), p * (1 + self.target_pct / 100),
                         f"SMA{self.fast} crossed above SMA{self.slow}")
        return None


class DeltaSpike:
    """Trade when order-book delta deviates sharply from its own baseline.

    Buys when buy-side pressure spikes (z >= entry_z). Exits early when the
    imbalance flips hard against the position (z <= exit_z), in addition to
    the usual stop and target.

    LIVE ONLY — historical candles carry no order book, so this rule cannot
    be backtested. It needs a warm-up period each session to learn a baseline.
    """
    name = "delta-spike"

    def __init__(self, entry_z: float = 2.0, exit_z: float = -2.0,
                 target_pct: float = 1.0, stop_pct: float = 0.5,
                 min_dip_pct: float | None = None):
        self.entry_z, self.exit_z = entry_z, exit_z
        self.target_pct, self.stop_pct = target_pct, stop_pct
        # optional: only act on a spike if price is also below VWAP
        self.min_dip_pct = min_dip_pct
        self.needs_depth = True

    def decide(self, bars, depth: dict | None = None) -> Entry | None:
        if not bars or not depth or not depth.get("ready"):
            return None
        z = depth.get("z")
        if z is None or z < self.entry_z:
            return None

        p = bars[-1].close
        if self.min_dip_pct is not None:
            v = _vwap(bars)
            if p >= v * (1 - self.min_dip_pct / 100):
                return None

        return Entry("BUY", p * (1 - self.stop_pct / 100), p * (1 + self.target_pct / 100),
                     f"delta spike z={z:+.2f} (imb {depth['imbalance']:+.3f} vs "
                     f"baseline {depth['baseline']:+.3f}, delta {depth['delta']:+,})")

    def should_exit(self, depth: dict | None) -> str | None:
        """Early exit when book pressure flips hard against us."""
        if not depth or not depth.get("ready") or depth.get("z") is None:
            return None
        if depth["z"] <= self.exit_z:
            return f"delta flipped z={depth['z']:+.2f}"
        return None


REGISTRY = {
    "orb": OpeningRangeBreakout,
    "vwap": VwapReversion,
    "sma": SmaCross,
    "delta": DeltaSpike,
}
