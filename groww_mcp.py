"""MCP server exposing the Groww trading API as tools."""
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from growwapi import GrowwAPI
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

load_dotenv(Path(__file__).parent / ".env")

mcp = MCPServer("groww", instructions="Access Groww trading account data and market quotes.")

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)

_client: Optional[GrowwAPI] = None


def client() -> GrowwAPI:
    """Authenticate lazily so the server starts even without credentials."""
    global _client
    if _client is None:
        api_key = os.getenv("GROWW_API_KEY")
        api_secret = os.getenv("GROWW_API_SECRET")
        if api_key and api_secret:
            _client = GrowwAPI(GrowwAPI.get_access_token(api_key=api_key, secret=api_secret))
        elif token := os.getenv("GROWW_ACCESS_TOKEN"):
            _client = GrowwAPI(token)
        else:
            raise ToolError(
                "No Groww credentials. Set GROWW_API_KEY + GROWW_API_SECRET "
                "(or GROWW_ACCESS_TOKEN) in the .env file at the project root."
            )
    return _client


def call(fn, *args, **kwargs):
    """Invoke a Groww client method, translating API errors into readable ones."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        if "forbidden" in str(exc).lower():
            raise ToolError(
                "Groww returned 'Access forbidden'. This account has no active Trading API "
                "subscription (Rs 499/month, which bundles live data, historical candles, "
                "orders and portfolio). Order and portfolio endpoints answer without it; "
                "market data does not. Subscribe at https://groww.in/trade-api"
            ) from exc
        raise ToolError(f"Groww API error: {exc}") from exc


# --- market data ---------------------------------------------------------

@mcp.tool(annotations=READ_ONLY)
def get_ltp(symbols: list[str], segment: str = "CASH") -> dict[str, Any]:
    """Last traded price for one or more symbols.

    Args:
        symbols: Exchange-prefixed symbols, e.g. ["NSE_RELIANCE", "NSE_TCS"].
        segment: CASH, FNO, COMMODITY or CURRENCY.
    """
    return call(client().get_ltp, exchange_trading_symbols=tuple(symbols), segment=segment)


@mcp.tool(annotations=READ_ONLY)
def get_quote(trading_symbol: str, exchange: str = "NSE", segment: str = "CASH") -> dict[str, Any]:
    """Full quote: depth, OHLC, volume, circuit limits.

    Args:
        trading_symbol: Bare symbol without exchange prefix, e.g. "RELIANCE".
        exchange: NSE or BSE.
        segment: CASH, FNO, COMMODITY or CURRENCY.
    """
    return call(client().get_quote, trading_symbol=trading_symbol, exchange=exchange, segment=segment)


@mcp.tool(annotations=READ_ONLY)
def get_ohlc(symbols: list[str], segment: str = "CASH") -> dict[str, Any]:
    """Open/high/low/close for one or more symbols.

    Args:
        symbols: Exchange-prefixed symbols, e.g. ["NSE_INFY"].
        segment: CASH, FNO, COMMODITY or CURRENCY.
    """
    return call(client().get_ohlc, exchange_trading_symbols=tuple(symbols), segment=segment)


@mcp.tool(annotations=READ_ONLY)
def get_historical_candles(
    groww_symbol: str,
    start_time: str,
    end_time: str,
    candle_interval: str = "DAY",
    exchange: str = "NSE",
    segment: str = "CASH",
) -> dict[str, Any]:
    """Historical OHLCV candles.

    Args:
        groww_symbol: Groww symbol, e.g. "NSE-RELIANCE".
        start_time: "YYYY-MM-DD HH:MM:SS".
        end_time: "YYYY-MM-DD HH:MM:SS".
        candle_interval: MIN_1, MIN_5, MIN_15, MIN_30, HOUR_1, DAY, WEEK or MONTH.
        exchange: NSE or BSE.
        segment: CASH, FNO, COMMODITY or CURRENCY.
    """
    return call(client().get_historical_candles, 
        exchange=exchange,
        segment=segment,
        groww_symbol=groww_symbol,
        start_time=start_time,
        end_time=end_time,
        candle_interval=candle_interval,
    )


@mcp.tool(annotations=READ_ONLY)
def lookup_instrument(trading_symbol: str, exchange: str = "NSE") -> dict[str, Any]:
    """Resolve a trading symbol to its instrument metadata and groww_symbol."""
    return call(client().get_instrument_by_exchange_and_trading_symbol, 
        exchange=exchange, trading_symbol=trading_symbol
    )


# --- portfolio -----------------------------------------------------------

@mcp.tool(annotations=READ_ONLY)
def get_holdings() -> dict[str, Any]:
    """Long-term demat holdings for the account."""
    return call(client().get_holdings_for_user)


@mcp.tool(annotations=READ_ONLY)
def get_positions(segment: Optional[str] = None) -> dict[str, Any]:
    """Open intraday and F&O positions. Optionally filter by segment."""
    return call(client().get_positions_for_user, segment=segment)


@mcp.tool(annotations=READ_ONLY)
def get_margin() -> dict[str, Any]:
    """Available margin and cash balance."""
    return call(client().get_available_margin_details)


@mcp.tool(annotations=READ_ONLY)
def get_order_list(page: int = 0, page_size: int = 25, segment: Optional[str] = None) -> dict[str, Any]:
    """Recent orders, most recent first."""
    return call(client().get_order_list, page=page, page_size=page_size, segment=segment)


@mcp.tool(annotations=READ_ONLY)
def get_order_status(groww_order_id: str, segment: str = "CASH") -> dict[str, Any]:
    """Current status of a single order."""
    return call(client().get_order_status, groww_order_id=groww_order_id, segment=segment)


# --- trading (opt-in) ----------------------------------------------------

if os.getenv("GROWW_ENABLE_TRADING", "").lower() == "true":

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True))
    def place_order(
        trading_symbol: str,
        transaction_type: str,
        quantity: int,
        order_type: str = "MARKET",
        product: str = "CNC",
        exchange: str = "NSE",
        segment: str = "CASH",
        validity: str = "DAY",
        price: float = 0.0,
        trigger_price: Optional[float] = None,
    ) -> dict[str, Any]:
        """Place a real order that spends real money. Confirm with the user first.

        Args:
            trading_symbol: Bare symbol, e.g. "RELIANCE".
            transaction_type: BUY or SELL.
            quantity: Number of shares/lots.
            order_type: MARKET, LIMIT, STOP_LOSS or STOP_LOSS_MARKET.
            product: CNC, MIS, NRML or MTF.
            exchange: NSE or BSE.
            segment: CASH, FNO, COMMODITY or CURRENCY.
            validity: DAY or IOC.
            price: Limit price. Required when order_type is LIMIT.
            trigger_price: Trigger for stop-loss orders.
        """
        return call(client().place_order, 
            trading_symbol=trading_symbol,
            transaction_type=transaction_type,
            quantity=quantity,
            order_type=order_type,
            product=product,
            exchange=exchange,
            segment=segment,
            validity=validity,
            price=price,
            trigger_price=trigger_price,
        )

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True))
    def cancel_order(groww_order_id: str, segment: str = "CASH") -> dict[str, Any]:
        """Cancel a pending order."""
        return call(client().cancel_order, groww_order_id=groww_order_id, segment=segment)


if __name__ == "__main__":
    mcp.run()
