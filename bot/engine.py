"""The trading loop: fetch data, run strategy, risk-check, execute."""
import csv
import logging
import time
from pathlib import Path

from bot import clock
from bot.broker import LiveBroker, PaperBroker
from bot import heartbeat, paths
from bot.data import MarketData
from bot.notify import build as build_notifier
from bot.risk import RiskHalt, RiskManager
from bot.stream import DepthStream
from bot.strategy import Context, Signal

log = logging.getLogger("bot.engine")


class Engine:
    def __init__(self, cfg, client, strategy, notifier=None):
        cfg.validate()
        self.cfg = cfg
        self.strategy = strategy
        self.data = MarketData(client, cfg.exchange, cfg.segment)
        self.risk = RiskManager(cfg)
        self.trade_log = paths.trades(cfg.instance)
        self.notify = notifier or build_notifier()
        self._fail_streak = 0
        self._last_cycle = None
        self.broker = (
            PaperBroker(cfg.starting_cash, cfg.instance) if cfg.paper
            else LiveBroker(client, cfg.exchange, cfg.segment, cfg.product)
        )
        self.stream = None
        if getattr(cfg, "stream_depth", False) and getattr(strategy, "wants_depth", False):
            self.stream = DepthStream(client, cfg.universe, cfg.exchange, cfg.segment)
            if self.stream.start():
                strategy.stream = self.stream
            else:
                log.warning("depth stream unavailable, falling back to REST polling")
                self.stream = None

        self.mode = "PAPER" if cfg.paper else "LIVE"
        log.info("engine ready | mode=%s strategy=%s universe=%s",
                 self.mode, getattr(strategy, "name", "?"), cfg.universe)
        self.notify.send(
            f"\u25b6 <b>Bot started</b> [{cfg.instance} \u00b7 {self.mode}]\n"
            f"strategy: {getattr(strategy, 'name', '?')}\n"
            f"universe: {', '.join(cfg.universe)}"
        )

    # --- execution -------------------------------------------------------

    def _record_trade(self, fill, reason: str) -> None:
        new = not self.trade_log.exists()
        with self.trade_log.open("a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["timestamp", "instance", "mode", "symbol", "side", "qty", "price", "order_id", "reason"])
            w.writerow([clock.now().isoformat(), self.cfg.instance,
                        "PAPER" if self.cfg.paper else "LIVE",
                        fill.symbol, fill.side, fill.quantity, f"{fill.price:.2f}",
                        fill.order_id, reason])

    def _execute(self, signals: list[Signal], ltps: dict, equity: float) -> None:
        positions = self.broker.get_positions()
        for sig in signals:
            price = sig.limit_price or ltps.get(sig.symbol)
            if price is None:
                log.warning("%s: no price available, skipping", sig.symbol)
                continue
            qty = self.risk.size(sig, price, equity, positions)
            if not self.risk.approve(sig, qty, price, positions):
                continue
            try:
                fill = self.broker.place(sig.symbol, sig.side, qty, price)
            except Exception as exc:
                log.error("%s: order failed: %s", sig.symbol, exc)
                continue
            self.risk.record()
            self._record_trade(fill, sig.reason)
            icon = "\U0001f7e2" if fill.side == "BUY" else "\U0001f534"
            self.notify.send(
                f"{icon} <b>{fill.side} {fill.quantity} {fill.symbol}</b> @ \u20b9{fill.price:,.2f} "
                f"[{self.cfg.instance} \u00b7 {self.mode}]\n{sig.reason}\n<i>order {fill.order_id}</i>"
            )
            positions = self.broker.get_positions()

    def _square_off(self, ltps: dict) -> None:
        """Flatten intraday positions before the close."""
        for sym, pos in self.broker.get_positions().items():
            price = ltps.get(sym, pos.avg_price)
            try:
                fill = self.broker.place(sym, "SELL", pos.quantity, price)
                self._record_trade(fill, "square-off before close")
                self.notify.send(
                    f"\u23f0 <b>Square-off</b> SELL {fill.quantity} {sym} @ \u20b9{price:,.2f} "
                    f"[{self.mode}]\n P&L \u20b9{pos.pnl(price):,.2f}"
                )
            except Exception as exc:
                log.error("%s: square-off failed: %s", sym, exc)

    # --- main loop -------------------------------------------------------

    def cycle(self) -> None:
        ltps = self.data.refresh(self.cfg.universe)
        if not ltps:
            log.warning("no LTPs returned, skipping cycle")
            return
        equity = self.broker.equity(ltps)
        self.risk.check_portfolio(equity)
        heartbeat.write(self.cfg.instance, self.mode,
                        getattr(self.strategy, "name", "?"),
                        equity, len(self.broker.get_positions()))

        if self.cfg.product == "MIS" and clock.minutes_to_close() <= self.cfg.square_off_minutes_before_close:
            if self.broker.get_positions():
                log.info("approaching close, squaring off")
                self._square_off(ltps)
            return

        ctx = Context(self.data, self.broker.get_positions(), equity, self.cfg.universe)
        signals = self.strategy.generate(ctx)
        if signals:
            log.info("%d signal(s): %s", len(signals),
                     ", ".join(f"{s.side} {s.symbol}" for s in signals))
        self._execute(signals, ltps, equity)

    def run(self, once: bool = False) -> None:
        if once:
            self.cycle()
            return
        while True:
            if not clock.is_open():
                wait = clock.seconds_until_open()
                # Short naps, not one long one: if the machine suspends mid-sleep
                # the timer does not advance, so a long sleep can overshoot the
                # open by however long the machine was out.
                if wait > 300:
                    log.info("market closed, %.0f min to open", wait / 60)
                time.sleep(min(wait, 60))
                continue
            gap = time.time() - self._last_cycle if self._last_cycle else 0
            # our own error backoff also creates gaps; only warn when we were
            # not the cause
            if self._last_cycle and gap > self.cfg.poll_seconds * 5 and self._fail_streak == 0:
                log.warning("cycle gap of %.0fs — process was suspended?", gap)
                self.notify.send(
                    f"\u26a0\ufe0f <b>Gap of {gap / 60:.0f} min between cycles</b> [{self.mode}]\n"
                    "The bot was suspended (machine sleep?). Signals in that window were missed."
                )
            self._last_cycle = time.time()
            try:
                self.cycle()
            except RiskHalt as halt:
                log.error("RISK HALT: %s — no further orders today", halt)
                self.notify.send(f"\U0001f6d1 <b>RISK HALT</b> [{self.mode}]\n{halt}\n"
                                 "No further orders today.")
                time.sleep(clock.seconds_until_open() or 3600)
                self.risk.start_day(self.broker.equity(self.data.refresh(self.cfg.universe)))
            except Exception as exc:
                log.exception("cycle failed, continuing")
                self._fail_streak += 1
                if self._fail_streak in (3, 10):
                    self.notify.send(f"\u26a0\ufe0f <b>{self._fail_streak} consecutive cycle "
                                     f"failures</b> [{self.mode}]\n{type(exc).__name__}: {exc}")
                # back off harder the longer we keep failing, capped at 10 min
                time.sleep(min(self.cfg.poll_seconds * self._fail_streak, 600))
                continue
            self._fail_streak = 0
            time.sleep(self.cfg.poll_seconds)
