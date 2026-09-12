"""Bot configuration and risk limits."""
from dataclasses import dataclass, field


@dataclass
class Config:
    # --- mode ---
    instance: str = "default"   # names this bot's state/log files
    paper: bool = True                  # True = simulate fills, never send real orders
    universe: list[str] = field(default_factory=lambda: ["TCS", "HCLTECH", "TECHM", "BAJFINANCE", "VEDL"])
    exchange: str = "NSE"
    segment: str = "CASH"
    product: str = "MIS"                # MIS intraday, CNC delivery

    # --- capital & sizing ---
    starting_cash: float = 200_000.0    # paper mode only; live reads real margin
    risk_per_trade_pct: float = 1.0     # % of equity risked per position
    max_position_pct: float = 20.0      # cap any single position at % of equity

    # --- risk limits (breach = halt for the day) ---
    max_open_positions: int = 3
    max_daily_loss_pct: float = 3.0     # halt if equity drops this % from day open
    max_orders_per_day: int = 20

    # --- loop ---
    stream_depth: bool = False   # use the WebSocket feed for order-book depth
    poll_seconds: int = 60
    square_off_minutes_before_close: int = 15   # MIS auto-exit buffer

    def validate(self) -> None:
        if self.risk_per_trade_pct <= 0 or self.risk_per_trade_pct > 100:
            raise ValueError("risk_per_trade_pct must be in (0, 100]")
        if self.max_position_pct <= 0 or self.max_position_pct > 100:
            raise ValueError("max_position_pct must be in (0, 100]")
        if self.product not in {"MIS", "CNC", "NRML"}:
            raise ValueError(f"unsupported product: {self.product}")
