"""
metrics/fitness.py
Portfolio performance metrics.
All functions take a pd.Series of daily returns.
"""

import numpy as np
import pandas as pd
from config import RISK_FREE_RATE, MIN_TRADES


def sharpe_ratio(returns: pd.Series,
                 risk_free: float = RISK_FREE_RATE) -> float:
    """Annualised Sharpe ratio."""
    if len(returns) < 10 or returns.std() < 1e-10:
        return -10.0
    excess = returns - risk_free / 252
    return float(excess.mean() / (excess.std() + 1e-9) * np.sqrt(252))


def sortino_ratio(returns: pd.Series,
                  risk_free: float = RISK_FREE_RATE) -> float:
    """Sortino ratio — penalises only downside volatility."""
    if len(returns) < 10:
        return -10.0
    excess    = returns - risk_free / 252
    downside  = excess[excess < 0].std()
    if downside < 1e-10:
        return 5.0
    return float(excess.mean() / downside * np.sqrt(252))


def max_drawdown(equity_curve: pd.Series) -> float:
    """Maximum peak-to-trough drawdown as a positive fraction."""
    rolling_max = equity_curve.cummax()
    drawdowns   = (equity_curve - rolling_max) / (rolling_max + 1e-9)
    return float(drawdowns.min())   # negative number; e.g. -0.20


def calmar_ratio(returns: pd.Series) -> float:
    """Calmar ratio: annualised return / max drawdown."""
    if len(returns) < 20:
        return -10.0
    equity  = (1 + returns).cumprod()
    mdd     = abs(max_drawdown(equity))
    if mdd < 1e-6:
        return 5.0
    ann_ret = float((1 + returns.mean()) ** 252 - 1)
    return ann_ret / mdd


def win_rate(trade_returns: list) -> float:
    if not trade_returns:
        return 0.0
    wins = sum(1 for r in trade_returns if r > 0)
    return wins / len(trade_returns)


def profit_factor(trade_returns: list) -> float:
    if not trade_returns:
        return 0.0
    gross_profit = sum(r for r in trade_returns if r > 0)
    gross_loss   = abs(sum(r for r in trade_returns if r < 0))
    return gross_profit / (gross_loss + 1e-9)


def compute_fitness(returns: pd.Series, metric: str = "sharpe") -> float:
    """Single entry-point used by the evaluator."""
    if returns is None or len(returns) < MIN_TRADES:
        return -10.0
    if metric == "sharpe":
        return sharpe_ratio(returns)
    elif metric == "calmar":
        return calmar_ratio(returns)
    elif metric == "sortino":
        return sortino_ratio(returns)
    return sharpe_ratio(returns)
