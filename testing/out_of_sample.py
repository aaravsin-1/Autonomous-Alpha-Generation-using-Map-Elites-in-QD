"""
testing/out_of_sample.py

Out-of-sample test.

The most important test of all.

The system evolved on data from 2010-2022.
It has NEVER seen data from 2023 onwards.

We now run the EXACT archive produced by evolution
on the unseen 2023+ data without touching it.

If it works -> the strategies have real predictive power.
If it fails -> the strategies overfit to training data.

We also test the ROUTING mechanism specifically:
does routing to the right regime actually help?
"""

import numpy as np
import pandas as pd
from typing import List
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from strategies.indicators import add_all_indicators
from strategies.signal_generator import generate_signals
from metrics.fitness import sharpe_ratio, max_drawdown
from testing.benchmark import run_all_benchmarks, print_benchmark_table


def out_of_sample_test(
    archive,
    df_test:   pd.DataFrame,
    df_train:  pd.DataFrame = None,
    verbose:   bool = True,
) -> dict:
    """
    Test every strategy in the archive on unseen data.
    Also tests the routing strategy (picks per-regime best).
    """
    df_ind  = add_all_indicators(df_test)
    close   = df_ind["Close"]
    results = {}

    # --- Test each strategy individually ---
    strategy_sharpes = []
    for i in range(archive.grid_size):
        for j in range(archive.grid_size):
            c = archive.grid[i][j]
            if c is None:
                continue
            params  = c.genome.decode()
            signals = generate_signals(df_ind, params).shift(1).fillna(0)
            ret     = signals * close.pct_change().fillna(0)
            cost    = signals.diff().abs().fillna(0) * 0.001
            net     = ret - cost
            sh      = sharpe_ratio(net)
            strategy_sharpes.append({
                "cell": f"V{i}/T{j}",
                "train_sharpe": c.fitness,
                "test_sharpe":  round(sh, 3),
                "degradation":  round(c.fitness - sh, 3),
            })

    if not strategy_sharpes:
        return {"error": "No strategies in archive"}

    # --- Routing test ---
    routing_signals = _routing_signals(archive, df_ind)
    if routing_signals is not None:
        rret    = routing_signals * close.pct_change().fillna(0)
        rcost   = routing_signals.diff().abs().fillna(0) * 0.001
        rnet    = rret - rcost
        r_sh    = sharpe_ratio(rnet)
        equity_r = (1 + rnet).cumprod()
        r_ret   = float(equity_r.iloc[-1] - 1) if len(equity_r) > 0 else 0.0
        r_dd    = float(max_drawdown(equity_r)) if len(equity_r) > 0 else 0.0
    else:
        r_sh, r_ret, r_dd = 0, 0, 0

    # --- Best single strategy test ---
    _candidates = []
    for _i in range(archive.grid_size):
        for _j in range(archive.grid_size):
            _c = archive.grid[_i][_j]
            if _c is not None:
                _candidates.append((_c.fitness, _i, _j, _c))
    best_cell = max(_candidates, key=lambda x: x[0]) if _candidates else None
    if best_cell:
        b_params  = best_cell[3].genome.decode()
        b_signals = generate_signals(df_ind, b_params).shift(1).fillna(0)
        b_ret     = b_signals * close.pct_change().fillna(0)
        b_cost    = b_signals.diff().abs().fillna(0) * 0.001
        b_net     = b_ret - b_cost
        b_sh      = sharpe_ratio(b_net)
        b_total   = float((1 + b_net).cumprod().iloc[-1] - 1)
        b_dd      = float(max_drawdown((1 + b_net).cumprod()))
    else:
        b_sh, b_total, b_dd = 0, 0, 0

    # Aggregate stats
    test_sharpes = [s["test_sharpe"] for s in strategy_sharpes]
    n_positive   = sum(1 for s in test_sharpes if s > 0)

    results = {
        "n_strategies_tested": len(strategy_sharpes),
        "n_positive_oos":      n_positive,
        "pct_positive":        round(n_positive / len(strategy_sharpes) * 100, 1),
        "mean_test_sharpe":    round(np.mean(test_sharpes), 3),
        "mean_train_sharpe":   round(np.mean([s["train_sharpe"] for s in strategy_sharpes]), 3),
        "mean_degradation":    round(np.mean([s["degradation"] for s in strategy_sharpes]), 3),
        "best_single_sharpe":  round(b_sh, 3),
        "best_single_return":  round(b_total, 4),
        "best_single_max_dd":  round(b_dd, 4),
        "routing_sharpe":      round(r_sh, 3),
        "routing_return":      round(r_ret, 4),
        "routing_max_dd":      round(r_dd, 4),
        "strategy_details":    strategy_sharpes,
    }

    if verbose:
        print(f"\n  Out-of-Sample Results ({len(df_test)} days)")
        print(f"  {'-'*55}")
        print(f"  Strategies tested      : {results['n_strategies_tested']}")
        print(f"  Positive OOS Sharpe    : {results['n_positive_oos']} "
              f"({results['pct_positive']}%)")
        print(f"  Mean train Sharpe      : {results['mean_train_sharpe']:+.3f}")
        print(f"  Mean test  Sharpe      : {results['mean_test_sharpe']:+.3f}")
        print(f"  Mean degradation       : {results['mean_degradation']:+.3f}")
        print(f"  {'-'*55}")
        print(f"  Best single strategy   : Sharpe {results['best_single_sharpe']:+.3f}  "
              f"Return {results['best_single_return']*100:+.1f}%  "
              f"MaxDD {results['best_single_max_dd']*100:.1f}%")
        print(f"  Routing strategy       : Sharpe {results['routing_sharpe']:+.3f}  "
              f"Return {results['routing_return']*100:+.1f}%  "
              f"MaxDD {results['routing_max_dd']*100:.1f}%")
        print()

        # Verdict
        if results["pct_positive"] >= 60 and results["mean_test_sharpe"] > 0:
            print(f"  VERDICT: PASSES out-of-sample test  [OK]")
            print(f"  {results['pct_positive']}% of strategies remain profitable on unseen data.")
        elif results["pct_positive"] >= 40:
            print(f"  VERDICT: MIXED -- some strategies survive, some don't")
        else:
            print(f"  VERDICT: FAILS out-of-sample test  [X]")
            print(f"  Strategies overfit to training data.")

    return results


def _routing_signals(archive, df_ind: pd.DataFrame) -> pd.Series:
    """
    Walk through the test data day-by-day.
    On each day, detect regime and use the appropriate archive strategy.
    """
    if not ("vol_pct" in df_ind.columns and "adx_pct" in df_ind.columns):
        return None

    all_signals = pd.Series(0.0, index=df_ind.index)
    gs          = archive.grid_size

    # Pre-compute signals for all archive strategies
    signal_cache = {}
    for i in range(gs):
        for j in range(gs):
            c = archive.grid[i][j]
            if c:
                params = c.genome.decode()
                signal_cache[(i, j)] = generate_signals(df_ind, params)

    # Day by day routing (using a 5-day lookback window for regime detection)
    for t in range(20, len(df_ind)):
        window  = df_ind.iloc[max(0, t-20):t]
        bd1     = float(window["vol_pct"].mean()) if "vol_pct" in window else 0.5
        bd2     = float(window["adx_pct"].mean()) if "adx_pct" in window else 0.5
        bd1     = float(np.clip(bd1, 0, 1))
        bd2     = float(np.clip(bd2, 0, 1))

        cell = archive.get_best_for_regime(bd1, bd2)
        if cell:
            i = int(np.clip(cell.bd1, 0, 0.9999) * gs)
            j = int(np.clip(cell.bd2, 0, 0.9999) * gs)
            key = (i, j)
            if key in signal_cache:
                date = df_ind.index[t]
                if date in signal_cache[key].index:
                    all_signals.iloc[t] = signal_cache[key].loc[date]

    return all_signals