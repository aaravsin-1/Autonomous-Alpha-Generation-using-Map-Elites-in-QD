"""
strategies/signal_generator.py
Turns a decoded genome into buy/sell/hold signals.
Signal = +1 (long), -1 (short / exit), 0 (flat).
This is PURE, parameterised logic — no LLM, no code generation.
"""

import numpy as np
import pandas as pd
from strategies.indicators import sma, ema, rsi, macd, bollinger_bands, atr


def generate_signals(df: pd.DataFrame, params: dict) -> pd.Series:
    """
    Combines four signal sources with evolved weights.
    Returns a Series of {-1, 0, 1} indexed like df.
    """
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]
    weights = params["weights"]  # [w_ma, w_rsi, w_macd, w_bb]

    # ── 1. MA Crossover ───────────────────────────────────────────────────────
    fast = ema(close, params["fast_ma"])
    slow = ema(close, params["slow_ma"])
    ma_raw = (fast - slow) / (slow + 1e-9)           # continuous score
    ma_sig = np.sign(ma_raw).fillna(0)                # +1 when fast > slow

    # ── 2. RSI Mean-Reversion ─────────────────────────────────────────────────
    rsi_val = rsi(close, params["rsi_period"])
    rsi_sig = pd.Series(0.0, index=close.index)
    rsi_sig[rsi_val < params["rsi_oversold"]]  =  1.0   # oversold → buy
    rsi_sig[rsi_val > params["rsi_overbought"]] = -1.0  # overbought → sell

    # ── 3. MACD Momentum ──────────────────────────────────────────────────────
    macd_line, signal_line, histogram = macd(
        close,
        fast=params["macd_fast"],
        slow=params["macd_slow"],
        signal=params["macd_signal"],
    )
    macd_sig = np.sign(histogram).fillna(0)

    # ── 4. Bollinger Band Reversion ────────────────────────────────────────────
    upper, mid, lower = bollinger_bands(close, params["bb_period"], params["bb_std"])
    bb_pct = (close - lower) / (upper - lower + 1e-9)
    bb_sig = pd.Series(0.0, index=close.index)
    bb_sig[bb_pct < 0.05]  =  1.0    # near lower band → buy
    bb_sig[bb_pct > 0.95]  = -1.0    # near upper band → sell

    # ── Weighted combination ───────────────────────────────────────────────────
    raw_score = (
        weights[0] * ma_sig  +
        weights[1] * rsi_sig +
        weights[2] * macd_sig +
        weights[3] * bb_sig
    )

    # Threshold: only act if combined signal is strong enough
    threshold = 0.3
    signals = pd.Series(0, index=close.index, dtype=float)
    signals[raw_score >  threshold] =  1.0
    signals[raw_score < -threshold] = -1.0

    # ── Trend filter ──────────────────────────────────────────────────────────
    # If trend_filter is high, only take trades aligned with the trend
    tf = params["trend_filter"]
    if tf > 0.3 and "adx_pct" in df.columns:
        adx_pct = df["adx_pct"].fillna(0.5)
        # In weak trend (low ADX), reduce position size signal
        signals[adx_pct < tf] *= 0.5

    # ── Volatility filter ─────────────────────────────────────────────────────
    vf = params["vol_filter"]
    if vf > 0.3 and "vol_pct" in df.columns:
        vol_pct = df["vol_pct"].fillna(0.5)
        # In very high vol, reduce / cut signals
        signals[vol_pct > (1 - vf)] *= 0

    return signals.fillna(0)
