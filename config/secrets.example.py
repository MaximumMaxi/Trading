"""
secrets.example.py — copy this to `secrets.py` and fill in your real MT5
credentials. `secrets.py` is git-ignored so your password never gets committed.

Alternatively, set environment variables MT5_LOGIN / MT5_PASSWORD / MT5_SERVER,
which take priority over this file.
"""

MT5_LOGIN    = 12345678            # your account number (int)
MT5_PASSWORD = "your_password"     # your account password
MT5_SERVER   = "ICMarkets-Demo"    # your broker server name
MT5_PATH     = None                # optional: r"C:\Program Files\MetaTrader 5\terminal64.exe"
