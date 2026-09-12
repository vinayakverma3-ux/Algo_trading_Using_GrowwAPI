"""Price-based quality screen — no paid data required.

Momentum ranks on returns alone, so it will happily surface a distressed
penny stock that has bounced hard (Vodafone Idea at Rs 14 with 120% momentum
was the case that prompted this). These filters use only price and volume,
which we already have, and cost nothing.
"""


def screen(px, date, min_price: float = 50.0, min_turnover_cr: float = 5.0,
           lookback_days: int = 60) -> set[str]:
    """Return symbols to EXCLUDE as of `date`.

    min_price       drops penny stocks, where a 1-tick move is a large %
    min_turnover_cr median daily traded value in Rs crore over the lookback
    """
    hist = px.loc[:date].tail(lookback_days)
    if hist.empty:
        return set()
    out = set()
    for sym in px.columns:
        col = hist[sym].dropna()
        if col.empty:
            continue
        if float(col.iloc[-1]) < min_price:
            out.add(sym)
    return out


def screen_with_volume(px, vol, date, min_price=50.0, min_turnover_cr=5.0,
                       lookback_days=60) -> set[str]:
    """As `screen`, plus a median-turnover test when volume data is available."""
    out = screen(px, date, min_price, min_turnover_cr, lookback_days)
    if vol is None:
        return out
    ph = px.loc[:date].tail(lookback_days)
    vh = vol.loc[:date].tail(lookback_days)
    for sym in px.columns:
        if sym in out or sym not in vh.columns:
            continue
        turnover = (ph[sym] * vh[sym]).dropna()
        if turnover.empty:
            continue
        if float(turnover.median()) / 1e7 < min_turnover_cr:
            out.add(sym)
    return out
