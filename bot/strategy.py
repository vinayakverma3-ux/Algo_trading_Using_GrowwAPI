"""Strategy plug-in interface. Drop your own signal logic in strategies/."""
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Signal:
    """One trading intent. quantity=None lets the risk manager size it."""
    symbol: str
    side: str                       # BUY or SELL
    reason: str = ""
    quantity: int | None = None
    stop_loss: float | None = None  # price; used for risk-based sizing
    limit_price: float | None = None


@dataclass
class Context:
    """What a strategy gets to look at each cycle."""
    data: "object"                  # bot.data.MarketData
    positions: dict                 # symbol -> Position
    equity: float
    universe: list[str]

    def ltp(self, symbol: str) -> float | None:
        return self.data.ltp(symbol)

    def closes(self, symbol: str, interval: str = "MIN_15", days: int = 5) -> list[float]:
        return self.data.closes(symbol, interval, days)

    def holding(self, symbol: str) -> int:
        pos = self.positions.get(symbol)
        return pos.quantity if pos else 0


class Strategy(Protocol):
    name: str

    def generate(self, ctx: Context) -> list[Signal]:
        """Return the signals to act on this cycle. Empty list = do nothing."""
        ...
