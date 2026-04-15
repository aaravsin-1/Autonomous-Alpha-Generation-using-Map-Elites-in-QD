"""
data/csv_loader.py

Handles all Yahoo Finance CSV formats:

  OLD format (single header):
    Date,Open,High,Low,Close,Adj Close,Volume
    2010-01-04,113.33,...

  NEW format (3 header rows):
    Price,Close,High,Low,Open,Volume
    Ticker,SPY,SPY,SPY,SPY,SPY
    Date,,,,,
    2010-01-14,85.99,...
"""

import pandas as pd
import numpy as np
from pathlib import Path


def load_csv(path: str) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"\n\n  File not found: {path}\n"
            f"  Make sure SPY.csv is inside your data/ folder.\n"
        )

    # Peek at first 5 rows to detect format
    with open(path) as f:
        first_lines = [f.readline().strip() for _ in range(5)]

    first_cell = first_lines[0].split(",")[0].strip().lower()

    # -- New Yahoo Finance format (starts with "Price" or "Ticker") ------------
    if first_cell in ("price", "ticker"):
        # Row 0: Price, Close, High, Low, Open, Volume
        # Row 1: Ticker, SPY, SPY, ...
        # Row 2: Date, , , , ,
        # Row 3+: actual data
        df = pd.read_csv(path, skiprows=3, header=None)

        # Assign column names from row 0
        header_row = first_lines[0].split(",")
        # first element is "Price" -> becomes "Date"
        header_row[0] = "Date"
        cols = [c.strip().title() for c in header_row]

        # Pad or trim if needed
        if len(cols) > len(df.columns):
            cols = cols[:len(df.columns)]
        elif len(cols) < len(df.columns):
            cols += [f"extra_{i}" for i in range(len(df.columns) - len(cols))]

        df.columns = cols

    # -- Old Yahoo Finance format (starts with "Date") -------------------------
    else:
        df = pd.read_csv(path)
        df.columns = [c.strip().title() for c in df.columns]

    # -- Parse date ------------------------------------------------------------
    date_col = next((c for c in df.columns if "date" in c.lower()), None)
    if date_col is None:
        raise ValueError(
            f"No Date column found.\n"
            f"Columns detected: {list(df.columns)}\n"
            f"First rows:\n{df.head(3)}"
        )

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])
    df = df.set_index(date_col).sort_index()

    # -- Normalise column names ------------------------------------------------
    rename = {}
    for col in df.columns:
        cl = col.lower().replace(" ", "")
        if "adjclose" in cl or ("adj" in cl and "close" in cl):
            rename[col] = "Close"
        elif cl == "close" and "Close" not in rename.values():
            rename.setdefault(col, "Close")
        elif cl == "open":
            rename[col] = "Open"
        elif cl == "high":
            rename[col] = "High"
        elif cl == "low":
            rename[col] = "Low"
        elif "vol" in cl:
            rename[col] = "Volume"

    df = df.rename(columns=rename)

    # -- Keep only OHLCV -------------------------------------------------------
    needed = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing columns after parsing: {missing}\n"
            f"Found: {list(df.columns)}\n"
            f"First rows:\n{df.head(3)}"
        )

    df = df[needed].copy()

    # -- Clean -----------------------------------------------------------------
    df = df.apply(pd.to_numeric, errors="coerce")
    df = df.dropna()
    df = df[df["Close"] > 0]

    print(f"  [data] Loaded {len(df)} rows from {path.name}  "
          f"({df.index[0].date()} -> {df.index[-1].date()})")
    return df