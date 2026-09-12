"""Promoter-group mapping. Sector caps miss this: four Adani names sit in
four different sectors but share one balance sheet and one set of risks.
"""
GROUPS = {
    "ADANIENT": "Adani", "ADANIPORTS": "Adani", "ADANIGREEN": "Adani",
    "ADANIPOWER": "Adani", "AMBUJACEM": "Adani",
    "TCS": "Tata", "TATASTEEL": "Tata", "TATAMOTORS": "Tata",
    "TATAPOWER": "Tata", "TATACONSUM": "Tata", "TITAN": "Tata",
    "TRENT": "Tata", "INDHOTEL": "Tata", "LTIM": "Tata", "VOLTAS": "Tata",
    "RELIANCE": "Reliance",
    "BAJFINANCE": "Bajaj", "BAJAJFINSV": "Bajaj", "BAJAJ-AUTO": "Bajaj",
    "GRASIM": "Birla", "ULTRACEMCO": "Birla", "HINDALCO": "Birla",
    "M&M": "Mahindra", "TECHM": "Mahindra",
    "HDFCBANK": "HDFC", "HDFCLIFE": "HDFC",
    "ICICIBANK": "ICICI", "ICICIGI": "ICICI", "ICICIPRULI": "ICICI",
    "SBIN": "SBI", "SBILIFE": "SBI", "SBICARD": "SBI",
    "JSWSTEEL": "JSW", "JSWENERGY": "JSW",
    # midcap-universe additions
    "ATGL": "Adani", "TATACOMM": "Tata", "TATAELXSI": "Tata",
    "TATAINVEST": "Tata", "TIINDIA": "Murugappa", "COROMANDEL": "Murugappa",
    "M&MFIN": "Mahindra", "ABCAPITAL": "Birla",
    "GODREJPROP": "Godrej", "LTF": "LT", "MFSL": "MaxGroup",
}


def group_of(symbol: str) -> str:
    return GROUPS.get(symbol, f"_{symbol}")   # ungrouped names are their own group
