"""
testing/monte_carlo.py

Monte Carlo permutation test.

The question: is the strategy's Sharpe ratio genuinely good,
or could you get the same result by chance?

Method:
  1. Take the strategy's actual trade returns
  2. Randomly shuffle them 1000 times (destroy any temporal pattern)
  3. Compute Sharpe for each shuffle
  4. See where the real Sharpe sits in that distribution

If the real Sharpe beats 95% of random shuffles → p < 0.05 → statistically significant.
If not → the result might be luck.

This is one of the strongest tests for overfitting.
"""

import numpy as np
import pandas as pd
from typing import List, Tuple
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from metrics.fitness import sharpe_ratio


def permutation_test(
    strategy_returns: pd.Series,
    n_permutations:   int   = 1000,
    confidence:       float = 0.95,
) -> dict:
    """
    Permutation test on a single strategy's daily returns.

    Returns dict with p-value, percentile, and verdict.
    """
    real_sharpe = sharpe_ratio(strategy_returns)

    # Generate null distribution
    ret_array    = strategy_returns.values
    null_sharpes = []

    for _ in range(n_permutations):
        shuffled = np.random.permutation(ret_array)
        null_sharpes.append(
            sharpe_ratio(pd.Series(shuffled))
        )

    null_array  = np.array(null_sharpes)
    p_value     = float(np.mean(null_array >= real_sharpe))
    percentile  = float(np.mean(null_array < real_sharpe) * 100)
    significant = p_value < (1 - confidence)

    return {
        "real_sharpe":   round(real_sharpe, 3),
        "null_mean":     round(float(np.mean(null_array)), 3),
        "null_std":      round(float(np.std(null_array)), 3),
        "null_95pct":    round(float(np.percentile(null_array, 95)), 3),
        "p_value":       round(p_value, 4),
        "percentile":    round(percentile, 1),
        "significant":   significant,
        "verdict":       "SIGNIFICANT" if significant else "NOT SIGNIFICANT",
        "n_permutations": n_permutations,
    }


def bootstrap_confidence_interval(
    strategy_returns: pd.Series,
    n_bootstrap:      int   = 1000,
    ci:               float = 0.95,
) -> dict:
    """
    Bootstrap confidence interval for the Sharpe ratio.
    Tells you how stable the Sharpe estimate is.
    Wide interval = unreliable estimate.
    Narrow interval = robust estimate.
    """
    ret_array  = strategy_returns.values
    n          = len(ret_array)
    bootstrap_sharpes = []

    for _ in range(n_bootstrap):
        sample = np.random.choice(ret_array, size=n, replace=True)
        bootstrap_sharpes.append(
            sharpe_ratio(pd.Series(sample))
        )

    bs        = np.array(bootstrap_sharpes)
    alpha     = (1 - ci) / 2
    lo        = float(np.percentile(bs, alpha * 100))
    hi        = float(np.percentile(bs, (1 - alpha) * 100))
    real      = sharpe_ratio(strategy_returns)

    return {
        "sharpe":    round(real, 3),
        "ci_low":    round(lo, 3),
        "ci_high":   round(hi, 3),
        "ci_width":  round(hi - lo, 3),
        "stable":    (hi - lo) < 1.5,   # wide CI = unreliable
        "ci_level":  f"{int(ci*100)}%",
    }


def test_multiple_strategies(
    archive,
    df:              pd.DataFrame,
    n_permutations:  int = 500,
    top_n:           int = 10,
) -> List[dict]:
    """
    Run permutation test on the top N strategies in the archive.
    Returns list of results sorted by p-value.
    """
    from strategies.signal_generator import generate_signals

    # Collect top N strategies
    cells = []
    for i in range(archive.grid_size):
        for j in range(archive.grid_size):
            c = archive.grid[i][j]
            if c:
                cells.append((c.fitness, i, j, c))
    cells.sort(key=lambda x: -x[0])
    cells = cells[:top_n]

    results = []
    close   = df["Close"]

    for fit, i, j, cell in cells:
        params   = cell.genome.decode()
        signals  = generate_signals(df, params).shift(1).fillna(0)
        ret      = (signals * close.pct_change().fillna(0))
        cost     = signals.diff().abs().fillna(0) * 0.001
        net_ret  = ret - cost

        perm = permutation_test(net_ret, n_permutations=n_permutations)
        boot = bootstrap_confidence_interval(net_ret)

        results.append({
            "cell":          f"V{i}/T{j}",
            "train_fitness": round(fit, 3),
            **perm,
            "ci_low":        boot["ci_low"],
            "ci_high":       boot["ci_high"],
            "ci_width":      boot["ci_width"],
        })

    results.sort(key=lambda x: x["p_value"])
    return results
