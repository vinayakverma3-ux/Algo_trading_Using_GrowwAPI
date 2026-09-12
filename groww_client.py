"""Groww Trading API client bootstrap."""
import os
from pathlib import Path

from dotenv import load_dotenv
from bot import force_ipv4
from growwapi import GrowwAPI

# Orders must originate from the whitelisted IPv4; a dual-stack host would
# otherwise prefer a rotating IPv6 address that can never stay registered.
force_ipv4.apply()

load_dotenv(Path(__file__).parent / ".env")


def connect() -> GrowwAPI:
    """Return an authenticated GrowwAPI client.

    Prefers the TOTP flow (api key + secret), falls back to a static token.
    """
    api_key = os.getenv("GROWW_API_KEY")
    api_secret = os.getenv("GROWW_API_SECRET")

    if api_key and api_secret:
        return GrowwAPI(GrowwAPI.get_access_token(api_key=api_key, secret=api_secret))

    token = os.getenv("GROWW_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Set GROWW_API_KEY + GROWW_API_SECRET, or GROWW_ACCESS_TOKEN in .env")
    return GrowwAPI(token)


if __name__ == "__main__":
    groww = connect()
    print("profile:", groww.get_user_profile())
    print("margin:", groww.get_available_margin_details())
    print(
        "RELIANCE LTP:",
        groww.get_ltp(
            segment=GrowwAPI.SEGMENT_CASH,
            exchange_trading_symbols="NSE_RELIANCE",
        ),
    )
