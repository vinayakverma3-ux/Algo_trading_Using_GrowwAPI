"""Adapter: run a rules.py strategy inside the live engine.

The backtester manages stops and targets internally. Live, nothing does —
so this tracks each open position's stop/target and emits the exit itself.
"""
import logging

from bot.depth import DepthTracker
from bot.strategy import Context, Signal
from strategies.rules import REGISTRY

log = logging.getLogger("bot.strategy")


class LiveRule:
    def __init__(self, rule_key: str, interval: str = "MIN_15",
                 days: int = 5, instance: str = "default", **params):
        self.rule = REGISTRY[rule_key](**params)
        self.interval, self.days = interval, days
        self.name = f"{self.rule.name}[live]"
        self.brackets: dict[str, dict] = {}   # symbol -> {stop, target, entry}
        self.wants_depth = (getattr(self.rule, "needs_depth", False)
                            or getattr(self.rule, "min_buy_sell_ratio", None) is not None)
        self.tracker = DepthTracker(instance=instance) if self.wants_depth else None
        self._warned = set()
        self.stream = None          # set by the engine when streaming is enabled

    def _depth(self, ctx: Context, symbol: str) -> dict | None:
        """Sample the book once per cycle and fold it into the tracker."""
        if not self.wants_depth:
            return None
        # Prefer the live stream: fold in every tick since the last cycle so
        # the baseline reflects continuous pressure, not one REST snapshot.
        if self.stream is not None:
            ticks = self.stream.drain(symbol)
            reading = None
            for _ts, buy, sell in ticks:
                reading = self.tracker.observe(symbol, buy, sell) if self.tracker else \
                          {"buy_qty": buy, "sell_qty": sell,
                           "ratio": buy / sell if sell else float("inf")}
            if reading is not None:
                return reading
            live = self.stream.latest(symbol)
            if live is not None:
                return (self.tracker.observe(symbol, live["buy_qty"], live["sell_qty"])
                        if self.tracker else live)
            # stream up but no data for this symbol yet: fall through to REST

        raw = ctx.data.depth(symbol)
        if raw is None:
            if symbol not in self._warned:
                log.warning("%s: no order-book depth available (market closed?)", symbol)
                self._warned.add(symbol)
            return None
        if self.tracker is None:
            return raw
        reading = self.tracker.observe(symbol, raw["buy_qty"], raw["sell_qty"])
        if reading and not reading["ready"]:
            log.debug("%s: warming up, %d/%d samples",
                      symbol, reading["samples"], self.tracker.min_samples)
        return reading

    def generate(self, ctx: Context) -> list[Signal]:
        signals: list[Signal] = []

        for symbol in ctx.universe:
            held = ctx.holding(symbol)
            price = ctx.ltp(symbol)
            if price is None:
                continue

            depth = self._depth(ctx, symbol)

            # --- manage an open position first ---
            if held:
                br = self.brackets.get(symbol)
                if not br:
                    continue          # position we did not open; leave it alone
                flip = (self.rule.should_exit(depth)
                        if hasattr(self.rule, "should_exit") else None)
                if flip:
                    signals.append(Signal(symbol, "SELL", quantity=held, reason=flip))
                    self.brackets.pop(symbol, None)
                    continue
                if price <= br["stop"]:
                    signals.append(Signal(symbol, "SELL", quantity=held,
                                          reason=f"stop hit {br['stop']:.2f}"))
                    self.brackets.pop(symbol, None)
                elif price >= br["target"]:
                    signals.append(Signal(symbol, "SELL", quantity=held,
                                          reason=f"target hit {br['target']:.2f}"))
                    self.brackets.pop(symbol, None)
                continue

            # --- flat: look for an entry ---
            self.brackets.pop(symbol, None)
            bars = ctx.data.history(symbol, self.interval, self.days)
            if len(bars) < 10:
                continue
            today = [b for b in bars if b.ts.date() == bars[-1].ts.date()]
            # order-book pressure, only fetched when the rule actually wants it
            entry = self.rule.decide(today or bars, depth)
            if entry:
                self.brackets[symbol] = {"stop": entry.stop, "target": entry.target,
                                         "entry": price}
                signals.append(Signal(symbol, entry.side, reason=entry.reason,
                                      stop_loss=entry.stop))
        if self.tracker:
            self.tracker.save()
        return signals
