"""Broker implementations. PaperBroker simulates; LiveBroker sends real orders."""
import json
import logging
from dataclasses import dataclass, field, asdict
from bot import paths

log = logging.getLogger("bot.broker")


@dataclass
class Position:
    symbol: str
    quantity: int
    avg_price: float

    def pnl(self, ltp: float) -> float:
        return (ltp - self.avg_price) * self.quantity


@dataclass
class Fill:
    symbol: str
    side: str
    quantity: int
    price: float
    order_id: str


class PaperBroker:
    """Simulates fills at the last traded price. Persists across restarts."""

    live = False

    def __init__(self, starting_cash: float, instance: str = "default"):
        self.state_file = paths.state(instance)
        self.cash = starting_cash
        self.positions: dict[str, Position] = {}
        self._seq = 0
        self._load()

    def _load(self) -> None:
        if not self.state_file.exists():
            return
        data = json.loads(self.state_file.read_text())
        self.cash = data["cash"]
        self._seq = data.get("seq", 0)
        self.positions = {s: Position(**p) for s, p in data["positions"].items()}
        log.info("paper state restored: cash=%.2f positions=%d", self.cash, len(self.positions))

    def _save(self) -> None:
        self.state_file.write_text(json.dumps({
            "cash": self.cash,
            "seq": self._seq,
            "positions": {s: asdict(p) for s, p in self.positions.items()},
        }, indent=2))

    def get_positions(self) -> dict[str, Position]:
        return dict(self.positions)

    def equity(self, ltps: dict[str, float]) -> float:
        mtm = sum(p.quantity * ltps.get(s, p.avg_price) for s, p in self.positions.items())
        return self.cash + mtm

    def place(self, symbol: str, side: str, quantity: int, price: float, **_) -> Fill:
        self._seq += 1
        oid = f"PAPER-{self._seq:05d}"
        cost = quantity * price
        if side == "BUY":
            if cost > self.cash:
                raise ValueError(f"insufficient paper cash: need {cost:.2f}, have {self.cash:.2f}")
            self.cash -= cost
            pos = self.positions.get(symbol)
            if pos:
                total = pos.quantity + quantity
                pos.avg_price = (pos.avg_price * pos.quantity + cost) / total
                pos.quantity = total
            else:
                self.positions[symbol] = Position(symbol, quantity, price)
        else:
            pos = self.positions.get(symbol)
            if not pos or pos.quantity < quantity:
                raise ValueError(f"cannot sell {quantity} {symbol}: holding {pos.quantity if pos else 0}")
            self.cash += cost
            pos.quantity -= quantity
            if pos.quantity == 0:
                del self.positions[symbol]
        self._save()
        log.info("PAPER %s %d %s @ %.2f -> cash %.2f", side, quantity, symbol, price, self.cash)
        return Fill(symbol, side, quantity, price, oid)


class LiveBroker:
    """Sends real orders to Groww. Real money."""

    live = True

    def __init__(self, client, exchange: str, segment: str, product: str):
        self.g = client
        self.exchange, self.segment, self.product = exchange, segment, product

    def get_positions(self) -> dict[str, Position]:
        raw = self.g.get_positions_for_user(segment=self.segment)
        out = {}
        for p in raw.get("positions") or []:
            qty = int(p.get("quantity") or p.get("net_quantity") or 0)
            if qty:
                sym = p.get("trading_symbol")
                out[sym] = Position(sym, qty, float(p.get("net_price") or p.get("avg_price") or 0))
        return out

    def equity(self, ltps: dict[str, float]) -> float:
        m = self.g.get_available_margin_details()
        cash = float(m.get("clear_cash") or 0)
        mtm = sum(p.quantity * ltps.get(s, p.avg_price) for s, p in self.get_positions().items())
        return cash + mtm

    def place(self, symbol: str, side: str, quantity: int, price: float,
              order_type: str = "LIMIT") -> Fill:
        resp = self.g.place_order(
            trading_symbol=symbol,
            transaction_type=side,
            quantity=quantity,
            order_type=order_type,
            product=self.product,
            exchange=self.exchange,
            segment=self.segment,
            validity="DAY",
            price=price if order_type == "LIMIT" else 0.0,
        )
        oid = resp.get("groww_order_id", "?")
        log.warning("LIVE %s %d %s @ %.2f -> order %s", side, quantity, symbol, price, oid)
        return Fill(symbol, side, quantity, price, oid)
