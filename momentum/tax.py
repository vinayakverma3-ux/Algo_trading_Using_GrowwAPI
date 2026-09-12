"""Indian capital gains tax on equity, as of FY2026-27.

STCG (held <= 12 months): 20% under Sec 111A
LTCG (held  > 12 months): 12.5% on gains above Rs 1.25 lakh per financial year
Both plus 4% health & education cess. Surcharge (income > Rs 50L) not modelled.
"""
STCG_RATE = 0.20
LTCG_RATE = 0.125
LTCG_EXEMPTION = 125_000.0
CESS = 0.04
LONG_TERM_DAYS = 365


def financial_year(ts) -> int:
    """Indian FY runs 1 April - 31 March; labelled by its starting year."""
    return ts.year if ts.month >= 4 else ts.year - 1


def tax_due(stcg: float, ltcg: float) -> float:
    """Tax on one financial year's realised gains. Losses are not carried."""
    st = max(0.0, stcg) * STCG_RATE
    lt = max(0.0, max(0.0, ltcg) - LTCG_EXEMPTION) * LTCG_RATE
    return (st + lt) * (1 + CESS)
