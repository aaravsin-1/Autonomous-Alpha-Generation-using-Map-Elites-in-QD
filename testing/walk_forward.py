"""
testing/walk_forward.py

Walk-forward validation -- the only honest way to test a strategy.

The idea:
  Split the data into N windows.
  For each window: evolve on the PAST, test on the FUTURE.
  The test periods never overlap with training.
  If the strategy works on every unseen future window,
  it has genuine predictive power -- not just curve fitting.

Example with 5 windows (5 years training, 1 year test):
  Window 1: train 2010-2014, test 2015
  Window 2: train 2010-2015, test 2016
  Window 3: train 2010-2016, test 2017
  Window 4: train 2010-2017, test 2018
  Window 5: train 2010-2018, test 2019
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from strategies.indicators import add_all_indicators
from strategies.signal_generator import generate_signals
from evolution.evaluator import BacktestEngine
from evolution.map_elites import MapElitesArchive
from evolution.genome import random_genome, mutate_and_maybe_crossover
from metrics.fitness import sharpe_ratio, max_drawdown, win_rate
import config as cfg


@dataclass
class WalkForwardResult:
    window:         int
    train_start:    str
    train_end:      str
    test_start:     str
    test_end:       str
    train_sharpe:   float
    test_sharpe:    float
    test_return:    float
    test_max_dd:    float
    test_n_trades:  int
    n_niches_filled: int
    degradation:    float   # train_sharpe - test_sharpe (lower = better)


def run_walk_forward(
    df_full:        pd.DataFrame,
    train_years:    int   = 5,
    test_years:     int   = 1,
    n_windows:      int   = 5,
    generations:    int   = 500,
    seed_n:         int   = 80,
    sigma:          float = 0.15,
    verbose:        bool  = True,
) -> List[WalkForwardResult]:
    """
    Run walk-forward validation across N windows.
    Returns list of results, one per window.
    """
    results = []
    all_dates = df_full.index

    # Anchor: always start from earliest date
    start_year = all_dates[0].year

    for w in range(n_windows):
        train_end_year  = start_year + train_years + w
        test_start_year = train_end_year
        test_end_year   = test_start_year + test_years

        train_mask = (all_dates.year >= start_year) & \
                     (all_dates.year <  train_end_year)
        test_mask  = (all_dates.year >= test_start_year) & \
                     (all_dates.year <  test_end_year)

        if train_mask.sum() < 200 or test_mask.sum() < 50:
            continue

        df_train = df_full[train_mask]
        df_test  = df_full[test_mask]

        if verbose:
            print(f"\n  Window {w+1}/{n_windows}: "
                  f"train {df_train.index[0].year}-{df_train.index[-1].year}  "
                  f"test {df_test.index[0].year}-{df_test.index[-1].year} "
                  f"({len(df_train)}d / {len(df_test)}d)")

        # --- Evolve on training data ---
        df_train_ind = add_all_indicators(df_train)
        engine  = BacktestEngine(df_train_ind)
        archive = MapElitesArchive(grid_size=cfg.GRID_SIZE)

        # Seed
        added = 0
        for _ in range(seed_n * 6):
            g = random_genome()
            r = engine.run(g)
            if archive.try_add(g, r, 0):
                added += 1
            if added >= seed_n:
                break

        # Evolve
        for gen in range(1, generations + 1):
            if np.random.rand() < 0.7 and archive.n_filled > 0:
                elite = archive.select_random_elite()
                child = mutate_and_maybe_crossover(
                    elite.genome, archive.get_all_genomes(),
                    sigma=sigma, crossover_prob=0.3, generation=gen
                )
            else:
                child = random_genome(gen)
            result = engine.run(child, gen)
            archive.try_add(child, result, gen)

        train_sharpe = archive.max_fitness

        # --- Test best strategy on unseen data ---
        # Combine train tail + test for indicator warmup (252 days lookback)
        warmup_days = 300
        df_warmup   = pd.concat([df_train.iloc[-warmup_days:], df_test])
        df_test_ind = add_all_indicators(df_warmup).loc[df_test.index]

        best_cell   = None
        best_fit    = -99

        # Find overall best strategy in archive
        for i in range(archive.grid_size):
            for j in range(archive.grid_size):
                c = archive.grid[i][j]
                if c and c.fitness > best_fit:
                    best_fit  = c.fitness
                    best_cell = c

        if best_cell is None:
            continue

        params  = best_cell.genome.decode()
        signals = generate_signals(df_test_ind, params).shift(1).fillna(0)
        close   = df_test_ind["Close"]
        ret     = (signals * close.pct_change().fillna(0))
        cost    = signals.diff().abs().fillna(0) * 0.001
        net_ret = ret - cost

        test_sh   = sharpe_ratio(net_ret)
        equity_wf = (1 + net_ret).cumprod()
        test_ret  = float(equity_wf.iloc[-1] - 1) if len(equity_wf) > 0 else 0.0
        test_dd   = float(max_drawdown(equity_wf)) if len(equity_wf) > 0 else 0.0
        n_trades  = int((signals.diff().abs() > 0).sum())
        degrad    = train_sharpe - test_sh

        res = WalkForwardResult(
            window          = w + 1,
            train_start     = str(df_train.index[0].date()),
            train_end       = str(df_train.index[-1].date()),
            test_start      = str(df_test.index[0].date()),
            test_end        = str(df_test.index[-1].date()),
            train_sharpe    = round(train_sharpe, 3),
            test_sharpe     = round(test_sh, 3),
            test_return     = round(test_ret, 4),
            test_max_dd     = round(test_dd, 4),
            test_n_trades   = n_trades,
            n_niches_filled = archive.n_filled,
            degradation     = round(degrad, 3),
        )
        results.append(res)

        if verbose:
            verdict = "[OK] PASS" if test_sh > 0 else "[X] FAIL"
            print(f"    Train Sharpe: {train_sharpe:+.3f}  "
                  f"Test Sharpe: {test_sh:+.3f}  "
                  f"Return: {test_ret*100:+.1f}%  "
                  f"MaxDD: {test_dd*100:.1f}%  "
                  f"Niches: {archive.n_filled}  "
                  f"{verdict}")

    return results


def summarise_walk_forward(results: List[WalkForwardResult]) -> dict:
    if not results:
        return {}

    test_sharpes   = [r.test_sharpe  for r in results]
    test_returns   = [r.test_return  for r in results]
    degradations   = [r.degradation  for r in results]
    n_pass         = sum(1 for r in results if r.test_sharpe > 0)

    return {
        "n_windows":        len(results),
        "n_pass":           n_pass,
        "pass_rate":        f"{n_pass}/{len(results)}",
        "mean_test_sharpe": round(np.mean(test_sharpes), 3),
        "std_test_sharpe":  round(np.std(test_sharpes), 3),
        "mean_test_return": round(np.mean(test_returns) * 100, 1),
        "mean_degradation": round(np.mean(degradations), 3),
        "verdict":          "ROBUST" if n_pass >= len(results) * 0.6 else "WEAK",
    }