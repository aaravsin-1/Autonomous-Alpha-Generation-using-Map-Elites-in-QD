"""
testing/benchmark.py

Compare QD strategies against standard benchmarks.

Benchmarks:
  1. Buy & Hold         -- just own the asset
  2. 50/200 MA Cross    -- classic golden/death cross
  3. RSI 30/70          -- classic mean-reversion
  4. Random strategy    -- random signals (noise floor)
  5. Best QD strategy   -- what we evolved

If our strategy can't beat a simple moving average crossover,
something is wrong. If it does beat it -- consistently --
that's genuine value.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from strategies.indicators import sma, ema, rsi
from metrics.fitness import (
    sharpe_ratio, calmar_ratio, max_drawdown,
    win_rate, profit_factor
)


@dataclass
class BenchmarkResult:
    name:           str
    sharpe:         float
    calmar:         float
    total_return:   float
    max_drawdown:   float
    volatility:     float
    win_rate:       float
    n_trades:       int
    equity_curve:   pd.Series


def _run_signals(signals: pd.Series,
                 close:   pd.Series,
                 cost:    float = 0.001) -> BenchmarkResult:
    raise NotImplementedError   # helper below


def _compute(name, signals, close, cost=0.001) -> BenchmarkResult:
    sig      = signals.shift(1).fillna(0)
    ret      = sig * close.pct_change().fillna(0)
    c        = sig.diff().abs().fillna(0) * cost
    net      = ret - c
    equity   = (1 + net).cumprod()

    trades   = []
    in_t, tr = False, []
    for i in range(len(sig)):
        s = sig.iloc[i]
        if not in_t and s != 0:
            in_t = True; tr = []
        if in_t:
            tr.append(net.iloc[i])
            if s == 0 or i == len(sig)-1:
                trades.append(sum(tr)); in_t = False; tr = []

    return BenchmarkResult(
        name         = name,
        sharpe       = round(sharpe_ratio(net), 3),
        calmar       = round(calmar_ratio(net), 3),
        total_return = round(float(equity.iloc[-1] - 1), 4),
        max_drawdown = round(float(max_drawdown(equity)), 4),
        volatility   = round(float(net.std() * np.sqrt(252)), 4),
        win_rate     = round(win_rate(trades), 4),
        n_trades     = len(trades),
        equity_curve = equity,
    )


def buy_and_hold(df: pd.DataFrame) -> BenchmarkResult:
    signals = pd.Series(1.0, index=df.index)
    return _compute("Buy & Hold", signals, df["Close"], cost=0.0)


def ma_crossover(df: pd.DataFrame,
                 fast: int = 50, slow: int = 200) -> BenchmarkResult:
    close   = df["Close"]
    f       = ema(close, fast)
    s       = ema(close, slow)
    signals = (f > s).astype(float) * 2 - 1
    signals = signals.fillna(0)
    return _compute(f"MA {fast}/{slow}", signals, close)


def rsi_strategy(df: pd.DataFrame,
                 period: int = 14,
                 ob: float = 70, os: float = 30) -> BenchmarkResult:
    close   = df["Close"]
    r       = rsi(close, period)
    signals = pd.Series(0.0, index=close.index)
    signals[r < os]  =  1.0
    signals[r > ob]  = -1.0
    return _compute(f"RSI {os}/{ob}", signals, close)


def random_strategy(df: pd.DataFrame,
                    seed: int = 42) -> BenchmarkResult:
    np.random.seed(seed)
    signals = pd.Series(
        np.random.choice([-1.0, 0.0, 1.0], size=len(df)),
        index=df.index,
    )
    return _compute("Random", signals, df["Close"])


def qd_best(df: pd.DataFrame,
            archive,
            label: str = "QD Best") -> BenchmarkResult:
    from strategies.signal_generator import generate_signals
    from strategies.indicators import add_all_indicators

    df_ind  = add_all_indicators(df)
    best_cell = None
    best_fit  = -99
    for i in range(archive.grid_size):
        for j in range(archive.grid_size):
            c = archive.grid[i][j]
            if c and c.fitness > best_fit:
                best_fit  = c.fitness
                best_cell = c

    if best_cell is None:
        return None

    params  = best_cell.genome.decode()
    signals = generate_signals(df_ind, params)
    return _compute(label, signals, df["Close"])


def run_all_benchmarks(df: pd.DataFrame,
                       archive=None) -> List[BenchmarkResult]:
    benchmarks = [
        buy_and_hold(df),
        ma_crossover(df, 50, 200),
        ma_crossover(df, 20, 50),
        rsi_strategy(df),
        random_strategy(df),
    ]
    if archive is not None:
        qd = qd_best(df, archive)
        if qd:
            benchmarks.append(qd)

    benchmarks.sort(key=lambda x: -x.sharpe)
    return benchmarks


def print_benchmark_table(benchmarks: List[BenchmarkResult]):
    print(f"\n  {'Strategy':<20} {'Sharpe':>8} {'Calmar':>8} "
          f"{'Return%':>9} {'MaxDD%':>8} {'WinR%':>8} {'Trades':>7}")
    print("  " + "-" * 70)
    for b in benchmarks:
        marker = " <--" if "QD" in b.name else ""
        print(
            f"  {b.name:<20} {b.sharpe:+8.3f} {b.calmar:+8.3f} "
            f"{b.total_return*100:+9.1f} {b.max_drawdown*100:+8.1f} "
            f"{b.win_rate*100:+8.1f} {b.n_trades:7d}{marker}"
        )