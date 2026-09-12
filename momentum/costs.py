"""Realistic Groww delivery (CNC) transaction costs."""

BROKERAGE_CAP = 20.0
BROKERAGE_PCT = 0.001
BROKERAGE_MIN = 5.0
DP_CHARGE = 3.5 + 16.5      # depository + Groww, per sell transaction per scrip


def _brokerage(value: float) -> float:
    return max(BROKERAGE_MIN, min(BROKERAGE_CAP, BROKERAGE_PCT * value))


def buy_cost(value: float) -> float:
    brok = _brokerage(value)
    stamp = 0.00015 * value
    exch = 0.0000297 * value
    sebi = 0.000001 * value
    gst = 0.18 * (brok + exch + sebi)
    return brok + stamp + exch + sebi + gst


def sell_cost(value: float) -> float:
    brok = _brokerage(value)
    stt = 0.001 * value          # delivery STT, sell side only
    exch = 0.0000297 * value
    sebi = 0.000001 * value
    gst = 0.18 * (brok + exch + sebi + DP_CHARGE)
    return brok + stt + exch + sebi + gst + DP_CHARGE


def round_trip(buy_value: float, sell_value: float) -> float:
    return buy_cost(buy_value) + sell_cost(sell_value)
