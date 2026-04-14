"""
evolution/evaluator.py  — vectorised backtester + behavioral descriptors

BD1 = momentum bias (0=mean-reversion, 1=momentum) — from genome directly
BD2 = risk tolerance / stop-loss width (0=tight, 1=wide) — from genome

Using genome-based BDs gives perfect spread across [0,1]² regardless of
market data, and characterises strategy TYPE not just performance.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional, Tuple
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import MIN_TRADES, FITNESS_METRIC
from strategies.signal_generator import generate_signals
from metrics.fitness import compute_fitness, max_drawdown, win_rate, profit_factor


@dataclass
class BacktestResult:
    fitness:        float
    bd1:            float   # momentum bias  [0,1]
    bd2:            float   # risk tolerance [0,1]
    sharpe:         float
    total_return:   float
    max_drawdown:   float
    n_trades:       int
    win_rate:       float
    profit_factor:  float
    equity_curve:   Optional[pd.Series] = None
    is_valid:       bool = True


INVALID_RESULT = BacktestResult(
    fitness=-10.0, bd1=0.5, bd2=0.5,
    sharpe=-10.0, total_return=-1.0,
    max_drawdown=-1.0, n_trades=0,
    win_rate=0.0, profit_factor=0.0,
    is_valid=False,
)


def _genome_bds(genome) -> Tuple[float, float]:
    """Fast genome-based BDs — no backtest required."""
    params = genome.decode()
    w      = params["weights"]

    # BD1: momentum fraction [MA+MACD vs RSI+BB]
    bd1 = (w[0] + w[2]) / (sum(w) + 1e-9)

    # BD2: stop-loss width normalised [0.5% → 8%]
    lo, hi = 0.005, 0.08
    bd2 = (params["stop_loss"] - lo) / (hi - lo)

    return float(np.clip(bd1, 0.0, 1.0)), float(np.clip(bd2, 0.0, 1.0))


class BacktestEngine:

    def __init__(self, df: pd.DataFrame,
                 transaction_cost: float = 0.001,
                 slippage: float = 0.0005):
        self.df               = df.copy()
        self.transaction_cost = transaction_cost
        self.slippage         = slippage

    def run(self, genome, generation: int = 0) -> BacktestResult:
        try:
            params  = genome.decode()
            bd1, bd2 = _genome_bds(genome)
            return self._backtest(params, bd1, bd2)
        except Exception:
            return INVALID_RESULT

    def _backtest(self, params, bd1, bd2) -> BacktestResult:
        df    = self.df
        close = df["Close"]

        signals  = generate_signals(df, params)
        signals  = signals.shift(1).fillna(0)
        signals  = self._apply_stops(df, signals, params)

        daily_ret    = close.pct_change().fillna(0)
        strategy_ret = signals * daily_ret
        cost         = signals.diff().abs().fillna(0) * (self.transaction_cost + self.slippage)
        net_ret      = strategy_ret - cost
        equity       = (1 + net_ret).cumprod()

        trade_rets = self._extract_trades(signals, net_ret)
        n_trades   = len(trade_rets)

        if n_trades < MIN_TRADES:
            return INVALID_RESULT

        fitness    = compute_fitness(net_ret, FITNESS_METRIC)
        sharpe_val = compute_fitness(net_ret, "sharpe")

        return BacktestResult(
            fitness       = fitness,
            bd1           = bd1,
            bd2           = bd2,
            sharpe        = sharpe_val,
            total_return  = float(equity.iloc[-1] - 1),
            max_drawdown  = float(max_drawdown(equity)),
            n_trades      = n_trades,
            win_rate      = win_rate(trade_rets),
            profit_factor = profit_factor(trade_rets),
            equity_curve  = equity,
            is_valid      = True,
        )

    def _apply_stops(self, df, signals, params):
        sl, tp = params["stop_loss"], params["take_profit"]
        close  = df["Close"].values
        sig    = signals.values.copy()
        entry  = None
        pos    = 0
        for i in range(1, len(sig)):
            if pos == 0 and sig[i] != 0:
                pos   = sig[i]; entry = close[i]
            elif pos != 0:
                ret = (close[i] - entry) / (entry + 1e-9) * pos
                if ret <= -sl or ret >= tp:
                    sig[i] = 0; pos = 0; entry = None
                elif sig[i] != pos:
                    pos = sig[i]; entry = close[i]
        return pd.Series(sig, index=signals.index)

    def _extract_trades(self, signals, returns):
        trades = []
        in_t, tr = False, []
        for i in range(len(signals)):
            s = signals.iloc[i]
            if not in_t and s != 0:
                in_t = True; tr = []
            if in_t:
                tr.append(returns.iloc[i])
                if s == 0 or i == len(signals) - 1:
                    trades.append(sum(tr)); in_t = False; tr = []
        return trades
