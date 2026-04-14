"""
data/fetcher.py
Downloads and caches OHLCV market data via yfinance.
"""

import os
import json
import pandas as pd
import yfinance as yf
from pathlib import Path


CACHE_DIR = Path("data/cache")


def _cache_path(ticker: str, start: str, end: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tag = f"{ticker}_{start}_{end}".replace("-", "")
    return CACHE_DIR / f"{tag}.parquet"


def fetch_ohlcv(ticker: str, start: str, end: str,
                force_download: bool = False) -> pd.DataFrame:
    """
    Returns a clean OHLCV DataFrame indexed by date.
    Caches to disk so we don't hammer Yahoo Finance.
    """
    path = _cache_path(ticker, start, end)

    if path.exists() and not force_download:
        df = pd.read_parquet(path)
        return df

    print(f"  [data] Downloading {ticker} {start} → {end} ...")
    raw = yf.download(ticker, start=start, end=end,
                      auto_adjust=True, progress=False)

    if raw.empty:
        raise ValueError(f"No data returned for {ticker}")

    # Flatten MultiIndex columns if present
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = pd.to_datetime(df.index)
    df = df.dropna()

    df.to_parquet(path)
    print(f"  [data] {len(df)} rows cached → {path}")
    return df


def fetch_multiple(tickers: list, start: str, end: str) -> dict:
    """Returns {ticker: DataFrame} for multiple instruments."""
    return {t: fetch_ohlcv(t, start, end) for t in tickers}
