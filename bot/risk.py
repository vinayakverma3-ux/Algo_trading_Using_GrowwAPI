"""Pre-trade risk checks and position sizing. Every order passes through here."""
import logging

log = logging.getLogger("bot.risk")


class RiskHalt(Exception):
    """Raised when a limit is breached and trading must stop for the day."""


class RiskManager:
    def __init__(self, cfg):
        self.cfg = cfg
        self.orders_today = 0
        self.day_open_equity: float | None = None
        self.halted = False

    def start_day(self, equity: float) -> None:
        self.day_open_equity = equity
        self.orders_today = 0
        self.halted = False
        log.info("day start: equity=%.2f", equity)

    def check_portfolio(self, equity: float) -> None:
        """Account-level guards. Raises RiskHalt to stop the session."""
        if self.day_open_equity is None:
            self.start_day(equity)
            return
        drawdown = (self.day_open_equity - equity) / self.day_open_equity * 100
        if drawdown >= self.cfg.max_daily_loss_pct:
            self.halted = True
            raise RiskHalt(
                f"daily loss {drawdown:.2f}% >= limit {self.cfg.max_daily_loss_pct}%"
            )
        if self.orders_today >= self.cfg.max_orders_per_day:
            self.halted = True
            raise RiskHalt(f"order cap reached ({self.orders_today})")

    def size(self, signal, price: float, equity: float, positions: dict) -> int:
        """Return the share count to trade, or 0 to skip."""
        if signal.quantity is not None:
            qty = signal.quantity
        elif signal.stop_loss:
            risk_amt = equity * self.cfg.risk_per_trade_pct / 100
            per_share = abs(price - signal.stop_loss)
            if per_share <= 0:
                log.warning("%s: stop-loss equals price, skipping", signal.symbol)
                return 0
            qty = int(risk_amt / per_share)
        else:
            # No stop-loss: we cannot size by risk, so fall back to a plain
            # budget of risk_per_trade_pct of equity. Prefer supplying a stop.
            budget = equity * self.cfg.risk_per_trade_pct / 100
            qty = int(budget / price)
            if qty == 0:
                log.warning(
                    "%s: skipped — no stop-loss, and one share costs %.2f which "
                    "exceeds the %.1f%% budget of %.2f. Supply a stop_loss to size "
                    "by risk, or raise risk_per_trade_pct.",
                    signal.symbol, price, self.cfg.risk_per_trade_pct, budget,
                )

        cap = int(equity * self.cfg.max_position_pct / 100 / price)
        if qty > cap:
            log.info("%s: sized %d capped to %d by max_position_pct", signal.symbol, qty, cap)
            qty = cap
        return max(qty, 0)

    def approve(self, signal, qty: int, price: float, positions: dict) -> bool:
        """Per-order guards. False = drop this order, keep running."""
        if self.halted:
            return False
        if qty <= 0:
            return False
        if signal.side == "BUY":
            if signal.symbol not in positions and len(positions) >= self.cfg.max_open_positions:
                log.info("%s: rejected, max_open_positions=%d reached",
                         signal.symbol, self.cfg.max_open_positions)
                return False
        else:
            held = positions[signal.symbol].quantity if signal.symbol in positions else 0
            if held < qty:
                log.info("%s: rejected sell %d, holding %d", signal.symbol, qty, held)
                return False
        return True

    def record(self) -> None:
        self.orders_today += 1
