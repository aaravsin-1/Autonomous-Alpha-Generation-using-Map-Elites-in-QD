"""
strategies/indicators.py
All technical indicators implemented from scratch.
Pure pandas/numpy — no external ta-lib dependency.
"""

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs  = avg_gain / (avg_loss + 1e-9)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series,
         fast: int = 12, slow: int = 26,
         signal: int = 9) -> tuple:
    """Returns (macd_line, signal_line, histogram)."""
    fast_ema   = ema(series, fast)
    slow_ema   = ema(series, slow)
    macd_line  = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram   = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(series: pd.Series,
                    period: int = 20,
                    std_dev: float = 2.0) -> tuple:
    """Returns (upper, middle, lower)."""
    middle = sma(series, period)
    std    = series.rolling(window=period, min_periods=period).std()
    upper  = middle + std_dev * std
    lower  = middle - std_dev * std
    return upper, middle, lower


def atr(high: pd.Series, low: pd.Series,
        close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()


def adx(high: pd.Series, low: pd.Series,
        close: pd.Series, period: int = 14) -> pd.Series:
    """Average Directional Index — trend strength 0-100."""
    plus_dm  = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    mask     = plus_dm < minus_dm
    plus_dm[mask] = 0
    mask2    = minus_dm <= plus_dm
    minus_dm[mask2] = 0

    tr_val   = atr(high, low, close, period)
    plus_di  = 100 * (plus_dm.ewm(com=period-1, adjust=False).mean() / (tr_val + 1e-9))
    minus_di = 100 * (minus_dm.ewm(com=period-1, adjust=False).mean() / (tr_val + 1e-9))
    dx       = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9))
    return dx.ewm(com=period-1, adjust=False).mean()


def rolling_volatility(returns: pd.Series, period: int = 20) -> pd.Series:
    """Annualised rolling volatility."""
    return returns.rolling(window=period).std() * np.sqrt(252)


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds a standard set of indicators to a price DataFrame.
    Returns the enriched DataFrame.
    """
    df = df.copy()
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]

    df["returns"]    = close.pct_change()
    df["log_ret"]    = np.log(close / close.shift(1))

    # Moving averages
    for p in [5, 10, 20, 50, 100, 200]:
        df[f"sma_{p}"] = sma(close, p)
        df[f"ema_{p}"] = ema(close, p)

    # RSI
    for p in [7, 14, 21]:
        df[f"rsi_{p}"] = rsi(close, p)

    # MACD
    df["macd"], df["macd_sig"], df["macd_hist"] = macd(close)

    # Bollinger Bands
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = bollinger_bands(close)
    df["bb_pct"] = (close - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"] + 1e-9)

    # ATR
    for p in [7, 14, 21]:
        df[f"atr_{p}"] = atr(high, low, close, p)

    # ADX
    df["adx"] = adx(high, low, close)

    # Volatility
    df["vol_20"]  = rolling_volatility(df["returns"], 20)
    df["vol_60"]  = rolling_volatility(df["returns"], 60)

    # Volatility percentile (rolling 252-day window)
    df["vol_pct"] = df["vol_20"].rolling(252).rank(pct=True)

    # Trend strength percentile
    df["adx_pct"] = df["adx"].rolling(252).rank(pct=True)

    return df.dropna()
