"""
data/synthetic.py
Generates realistic synthetic price data with embedded market regimes.
Used when live data is unavailable.
Produces a DataFrame identical in structure to yfinance output.
"""

import numpy as np
import pandas as pd


def generate_market_data(n_days: int = 3000,
                         seed: int = 42) -> pd.DataFrame:
    """
    Generates a realistic synthetic price series with alternating regimes:
    - Bull trending (low vol, upward drift)
    - Bear trending (medium vol, downward drift)
    - High volatility choppy (no clear trend)
    - Low volatility ranging (mean-reverting, calm)
    """
    np.random.seed(seed)
    dates = pd.bdate_range("2010-01-04", periods=n_days)

    # Define regime schedule
    regimes = []
    i = 0
    while i < n_days:
        regime_type = np.random.choice(
            ["bull", "bear", "choppy", "ranging"],
            p=[0.35, 0.20, 0.25, 0.20]
        )
        duration = np.random.randint(60, 300)
        duration = min(duration, n_days - i)
        regimes.extend([regime_type] * duration)
        i += duration
    regime_labels = regimes[:n_days]

    # Regime parameters
    params = {
        "bull":    {"drift": 0.0008,  "vol": 0.008, "mean_rev": 0.0},
        "bear":    {"drift": -0.0006, "vol": 0.013, "mean_rev": 0.0},
        "choppy":  {"drift": 0.0001,  "vol": 0.022, "mean_rev": 0.0},
        "ranging": {"drift": 0.0001,  "vol": 0.005, "mean_rev": 0.3},
    }

    # Generate log returns with regime-dependent noise
    log_returns = np.zeros(n_days)
    price_mean  = 0.0

    for t in range(1, n_days):
        r = regime_labels[t]
        p = params[r]
        noise = np.random.normal(0, p["vol"])
        # Mild mean reversion in ranging regime
        rev   = -p["mean_rev"] * (log_returns[t-1] - price_mean)
        log_returns[t] = p["drift"] + noise + rev

    # Build price series
    log_prices = np.cumsum(log_returns)
    close      = 200.0 * np.exp(log_prices)

    # Build OHLCV
    daily_vol   = pd.Series(log_returns).rolling(5).std().fillna(0.01).values
    high_factor = 1 + np.abs(np.random.normal(0, daily_vol))
    low_factor  = 1 - np.abs(np.random.normal(0, daily_vol))
    open_factor = 1 + np.random.normal(0, daily_vol * 0.3)

    df = pd.DataFrame({
        "Open":   close * open_factor,
        "High":   close * high_factor,
        "Low":    close * low_factor,
        "Close":  close,
        "Volume": np.random.randint(50_000_000, 150_000_000, n_days),
        "Regime": regime_labels,
    }, index=dates)

    df["High"]  = df[["Open", "Close", "High"]].max(axis=1)
    df["Low"]   = df[["Open", "Close", "Low"]].min(axis=1)

    return df


def split_data(df: pd.DataFrame,
               train_end: str = "2022-12-31") -> tuple:
    """Split into train and test sets."""
    train = df[df.index <= train_end].copy()
    test  = df[df.index >  train_end].copy()
    return train, test
