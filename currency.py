#!/usr/bin/env python3
"""
Currency conversion helper for Hermes subscription manager.
Fetches live rates from open.er-api.com (free, no key needed).
Falls back to hardcoded rates if API unavailable.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, date
from pathlib import Path
from typing import Optional

CACHE_FILE = Path.home() / ".hermes" / "fx-cache.json"
CACHE_TTL_HOURS = 6

FALLBACK_RATES_TO_USD = {
    "USD": 1.0,
    "NGN": 1 / 1580.0,   # ~1580 NGN = 1 USD
    "GBP": 1.27,
    "EUR": 1.08,
    "CAD": 0.74,
    "AUD": 0.65,
    "INR": 0.012,
    "BRL": 0.18,
    "MXN": 0.052,
    "JPY": 0.0067,
    "KES": 0.0077,
    "ZAR": 0.054,
    "GHS": 0.062,
}


def _load_cache() -> Optional[dict]:
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE) as f:
            data = json.load(f)
        cached_at = datetime.fromisoformat(data["cached_at"])
        age_hours = (datetime.now() - cached_at).total_seconds() / 3600
        if age_hours < CACHE_TTL_HOURS:
            return data["rates"]
    except Exception:
        pass
    return None


def _save_cache(rates: dict):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({"cached_at": datetime.now().isoformat(), "rates": rates}, f)
    except Exception:
        pass


def get_rates() -> dict:
    """Return dict of currency → USD rate. Cached for 6 hours."""
    cached = _load_cache()
    if cached:
        return cached

    try:
        url = "https://open.er-api.com/v6/latest/USD"
        req = urllib.request.Request(url, headers={"User-Agent": "hermes-subbot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        if data.get("result") == "success":
            raw = data["rates"]  # these are USD→X rates, need to invert
            rates = {cur: 1.0 / rate for cur, rate in raw.items() if rate > 0}
            rates["USD"] = 1.0
            _save_cache(rates)
            return rates
    except Exception:
        pass

    return FALLBACK_RATES_TO_USD


def to_usd(amount: float, currency: str) -> float:
    """Convert amount in given currency to USD."""
    if currency == "USD":
        return round(amount, 2)
    rates = get_rates()
    rate = rates.get(currency.upper())
    if not rate:
        return amount  # unknown currency, return as-is
    return round(amount * rate, 2)


def format_amount(amount: float, currency: str, show_usd: bool = True) -> str:
    """Format amount with currency symbol, optionally showing USD equivalent."""
    symbols = {"USD": "$", "NGN": "₦", "GBP": "£", "EUR": "€"}
    sym = symbols.get(currency, currency + " ")
    formatted = f"{sym}{amount:,.2f}"
    if show_usd and currency != "USD":
        usd = to_usd(amount, currency)
        formatted += f" (~${usd:.2f})"
    return formatted


if __name__ == "__main__":
    print("Testing currency module...")
    print(f"NGN 57,000 = {format_amount(57000, 'NGN')}")
    print(f"GBP 10 = {format_amount(10, 'GBP')}")
    print(f"USD 20 = {format_amount(20, 'USD')}")
