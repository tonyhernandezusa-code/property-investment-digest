#!/usr/bin/env python3
"""
Property Investment Digest — Authorized Development Stock Updater

Development / authorized-access use only.

Retrieves market data through yfinance/Yahoo Finance, then encrypts the entire
market-data payload before it is committed to the public GitHub Pages repository.
The password is supplied only through the GitHub Actions secret
STOCK_ACCESS_PASSWORD and is never written to the repository or logs.

This password restriction does NOT change Yahoo Finance/yfinance licensing terms.
Do not treat this as permission for commercial subscriber redistribution.
"""

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

OUTPUT = Path(__file__).with_name("authorized-stocks.enc.json")

WATCHLIST = [
    "AAPL", "GOOGL", "QCOM", "TSM", "META", "TSLA", "MSFT", "INTC", "NVDA",
    "AMD", "ORCL", "AVGO", "JNJ", "AMZN", "BMY", "MRK", "LLY", "CSCO", "WMT",
    "PEP", "KO", "V", "MA", "CAT", "UNP", "PLTR", "DELL", "MU", "LMT", "ABBV",
    "RTX", "HON"
]

INDEXES = [
    ("Dow Jones", "^DJI"),
    ("S&P 500", "^GSPC"),
    ("Nasdaq Composite", "^IXIC"),
    ("Nasdaq-100", "^NDX"),
    ("Russell 2000", "^RUT"),
    ("Russell 1000", "^RUI"),
    ("S&P MidCap 400", "^MID"),
    ("US Dollar (DXY)", "DX-Y.NYB"),
    ("VIX (Volatility)", "^VIX"),
    ("FTSE 100 (UK)", "^FTSE"),
    ("DAX (Germany)", "^GDAXI"),
    ("CAC 40 (France)", "^FCHI"),
    ("Nikkei 225 (Japan)", "^N225"),
    ("Hang Seng (Hong Kong)", "^HSI"),
    ("Shanghai Composite (China)", "000001.SS"),
    ("Sensex (India)", "^BSESN"),
    ("Nifty 50 (India)", "^NSEI"),
    ("KOSPI (South Korea)", "^KS11"),
    ("ASX 200 (Australia)", "^AXJO"),
    ("TSX Composite (Canada)", "^GSPTSE"),
    ("Bovespa (Brazil)", "^BVSP"),
    ("IPC (Mexico)", "^MXX"),
]

INDEX_FUTURES = [
    ("S&P 500 Futures (E-mini)", "ES=F"),
    ("Dow Futures (E-mini)", "YM=F"),
    ("Nasdaq-100 Futures (E-mini)", "NQ=F"),
    ("Russell 2000 Futures (E-mini)", "RTY=F"),
    ("Nikkei 225 Futures", "NIY=F"),
]

COMMODITIES = [
    ("Oil (WTI)", "CL=F"),
    ("Oil (Brent)", "BZ=F"),
    ("Natural Gas", "NG=F"),
    ("Gold", "GC=F"),
    ("Silver", "SI=F"),
    ("Copper", "HG=F"),
    ("Platinum", "PL=F"),
    ("Corn", "ZC=F"),
    ("Wheat", "ZW=F"),
    ("Soybeans", "ZS=F"),
    ("Coffee", "KC=F"),
    ("Sugar", "SB=F"),
]

def safe_float(value):
    try:
        if value is None:
            return None
        number = float(value)
        if number != number:
            return None
        return number
    except Exception:
        return None

def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    value = safe_float(rsi.iloc[-1]) if len(rsi) else None
    return round(value, 2) if value is not None else None

def downsample_history(close, max_points=60):
    series = close.dropna()
    if series.empty:
        return []
    if len(series) <= max_points:
        selected = series
    else:
        indexes = [round(i * (len(series) - 1) / (max_points - 1)) for i in range(max_points)]
        selected = series.iloc[indexes]
    return [
        {"date": idx.strftime("%Y-%m-%d"), "close": round(float(val), 2)}
        for idx, val in selected.items()
    ]

def fetch_history(symbol, period="1y"):
    try:
        data = yf.download(
            symbol,
            period=period,
            interval="1d",
            progress=False,
            auto_adjust=True,
            threads=False,
        )
        if data is None or data.empty:
            return None
        # yfinance may return either a Series-like column or a one-column DataFrame.
        close = data["Close"].squeeze().dropna()
        if len(close) < 2:
            return None
        return data, close
    except Exception as exc:
        print(f"{symbol}: price history error: {exc}", flush=True)
        return None

def fetch_stock(symbol):
    history = fetch_history(symbol, "1y")
    if not history:
        return None
    data, close = history
    price = safe_float(close.iloc[-1])
    previous = safe_float(close.iloc[-2])
    if price is None or previous in (None, 0):
        return None

    six_index = -127 if len(close) > 126 else 0
    six_price = safe_float(close.iloc[six_index])
    change_1d = (price / previous - 1) * 100
    change_6m = (price / six_price - 1) * 100 if six_price not in (None, 0) else None

    high_col = data["High"].squeeze().dropna()
    low_col = data["Low"].squeeze().dropna()
    vol_col = data["Volume"].squeeze().dropna()

    market_cap = None
    pe = None
    dividend_yield = None
    company_name = symbol
    sector = None

    try:
        ticker = yf.Ticker(symbol)
        try:
            fast = ticker.fast_info
            market_cap = safe_float(fast.get("market_cap"))
        except Exception:
            pass

        try:
            info = ticker.info or {}
            company_name = info.get("shortName") or info.get("longName") or symbol
            sector = info.get("sector")
            market_cap = market_cap or safe_float(info.get("marketCap"))
            pe = safe_float(info.get("trailingPE"))
            dy = safe_float(info.get("dividendYield"))
            # Recent yfinance versions generally expose dividendYield as a decimal.
            dividend_yield = dy * 100 if dy is not None and abs(dy) <= 1 else dy
        except Exception as exc:
            print(f"{symbol}: company-info warning: {exc}", flush=True)
    except Exception:
        pass

    return {
        "ticker": symbol,
        "name": company_name,
        "sector": sector,
        "price": round(price, 2),
        "change_1d_pct": round(change_1d, 2),
        "change_6m_pct": round(change_6m, 2) if change_6m is not None else None,
        "rsi_14": compute_rsi(close),
        "market_cap": round(market_cap, 2) if market_cap is not None else None,
        "pe_trailing": round(pe, 2) if pe is not None else None,
        "dividend_yield_pct": round(dividend_yield, 2) if dividend_yield is not None else None,
        "high_52w": round(float(high_col.max()), 2) if not high_col.empty else None,
        "low_52w": round(float(low_col.min()), 2) if not low_col.empty else None,
        "volume": int(vol_col.iloc[-1]) if not vol_col.empty else None,
        "avg_volume_3m": int(vol_col.tail(63).mean()) if not vol_col.empty else None,
        "history": downsample_history(close, 60),
    }

def fetch_market_item(name, symbol):
    history = fetch_history(symbol, "6mo")
    if not history:
        return {"name": name, "symbol": symbol, "error": "No data"}
    _, close = history
    price = safe_float(close.iloc[-1])
    previous = safe_float(close.iloc[-2])
    one_month = safe_float(close.iloc[-22]) if len(close) > 21 else safe_float(close.iloc[0])
    return {
        "name": name,
        "symbol": symbol,
        "price": round(price, 4) if price is not None else None,
        "change_1d_pct": round((price / previous - 1) * 100, 2) if price is not None and previous not in (None, 0) else None,
        "change_1m_pct": round((price / one_month - 1) * 100, 2) if price is not None and one_month not in (None, 0) else None,
        "history": downsample_history(close, 30),
    }

def encrypt_payload(payload, password):
    salt = os.urandom(16)
    nonce = os.urandom(12)
    iterations = 250_000
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=32,
    )
    plaintext = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return {
        "version": 1,
        "cipher": "AES-256-GCM",
        "kdf": "PBKDF2-HMAC-SHA256",
        "iterations": iterations,
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "updated_at_utc": payload["updated_at_utc"],
        "source_label": "Yahoo Finance via yfinance — Authorized Development Access",
    }

def main():
    password = os.environ.get("STOCK_ACCESS_PASSWORD", "")
    if not password:
        raise SystemExit(
            "STOCK_ACCESS_PASSWORD is missing. Add it as a GitHub Actions repository secret."
        )

    stocks = []
    stock_errors = []
    for symbol in WATCHLIST:
        print(f"Updating stock {symbol}...", flush=True)
        item = fetch_stock(symbol)
        if item:
            stocks.append(item)
        else:
            stock_errors.append(symbol)

    indexes = []
    for name, symbol in INDEXES:
        print(f"Updating index {name}...", flush=True)
        indexes.append(fetch_market_item(name, symbol))

    futures = []
    for name, symbol in INDEX_FUTURES:
        print(f"Updating future {name}...", flush=True)
        futures.append(fetch_market_item(name, symbol))

    commodities = []
    for name, symbol in COMMODITIES:
        print(f"Updating commodity {name}...", flush=True)
        commodities.append(fetch_market_item(name, symbol))

    payload = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo Finance via yfinance",
        "access_classification": "Authorized development access",
        "commercial_rights_confirmed": False,
        "stocks": stocks,
        "stock_errors": stock_errors,
        "indexes": indexes,
        "futures": futures,
        "commodities": commodities,
        "notes": [
            "Development/testing use only.",
            "Password protection does not grant commercial redistribution rights.",
            "Replace or license Yahoo-derived market data before a paid subscriber launch unless written rights permit that use.",
        ],
    }

    encrypted = encrypt_payload(payload, password)
    OUTPUT.write_text(json.dumps(encrypted, indent=2), encoding="utf-8")
    print(
        f"Wrote encrypted stock data: {len(stocks)} stocks, "
        f"{len(indexes)} indexes, {len(futures)} futures, "
        f"{len(commodities)} commodities.",
        flush=True,
    )

if __name__ == "__main__":
    main()
