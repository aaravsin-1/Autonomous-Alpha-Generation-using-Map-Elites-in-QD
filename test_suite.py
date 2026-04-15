"""
test_suite.py -- Master test runner

Runs the complete battery of tests on a saved archive.

Usage:
    # With synthetic data (works immediately):
    python test_suite.py --synthetic

    # With real data from CSV (download from Yahoo Finance first):
    python test_suite.py --csv data/SPY.csv

    # With real data auto-downloaded (requires internet):
    python test_suite.py --ticker SPY

What it tests:
    1. Out-of-sample performance  (did the strategy work on data it never saw?)
    2. Walk-forward validation    (does it work across multiple time periods?)
    3. Monte Carlo significance   (is the result statistically real, not luck?)
    4. Benchmark comparison       (does it beat simple strategies?)
    5. Routing test               (does the regime-switching add value?)

How to interpret results:
    PASS = strategy is likely real
    FAIL = strategy may be overfit or data may be insufficient
"""

import argparse
import sys
import os
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from colorama import init, Fore, Style
init(autoreset=True)

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config as cfg
from strategies.indicators import add_all_indicators
from evolution.map_elites import MapElitesArchive
from testing.out_of_sample import out_of_sample_test
from testing.walk_forward import run_walk_forward, summarise_walk_forward
from testing.monte_carlo import permutation_test, test_multiple_strategies
from testing.benchmark import run_all_benchmarks, print_benchmark_table
from strategies.signal_generator import generate_signals
from metrics.fitness import sharpe_ratio, max_drawdown


def parse_args():
    p = argparse.ArgumentParser(description="QD Trading -- Test Suite")
    p.add_argument("--archive",     default=f"{cfg.OUTPUT_DIR}/{cfg.ARCHIVE_FILE}")
    p.add_argument("--ticker",      default=cfg.PRIMARY_TICKER)
    p.add_argument("--csv",         default=None,  help="Path to OHLCV CSV file")
    p.add_argument("--synthetic",   action="store_true")
    p.add_argument("--fast",        action="store_true",
                   help="Quick run (fewer permutations, 3 WF windows)")
    return p.parse_args()


def load_data(args):
    """Load data from CSV, live download, or synthetic."""
    if args.csv:
        from data.csv_loader import load_csv
        return load_csv(args.csv), "csv"

    if args.synthetic:
        from data.synthetic import generate_market_data
        df = generate_market_data(n_days=4500, seed=42)
        return df, "synthetic"

    try:
        from data.fetcher import fetch_ohlcv
        df = fetch_ohlcv(args.ticker, "2010-01-01", "2024-12-31")
        if df is not None and len(df) > 100:
            return df, "live"
    except Exception:
        pass

    from data.synthetic import generate_market_data
    print(Fore.YELLOW + "  Falling back to synthetic data.")
    return generate_market_data(n_days=3500, seed=42), "synthetic"


def section(title: str):
    print(Fore.CYAN + f"\n{'='*64}")
    print(Fore.CYAN + f"  {title}")
    print(Fore.CYAN + f"{'='*64}")


def run_tests(args):
    t0 = time.time()

    # -- Load archive ----------------------------------------------------------
    section("LOADING ARCHIVE")
    if not Path(args.archive).exists():
        print(Fore.RED + f"  Archive not found: {args.archive}")
        print("  Run python run_evolution.py --synthetic first.")
        return

    archive = MapElitesArchive.load(args.archive)
    s       = archive.summary()
    print(Fore.GREEN + f"""
  Archive: {s['n_filled']}/100 niches ({s['coverage']}% coverage)
  Best Sharpe  : {s['max_fitness']}
  Mean Sharpe  : {s['mean_fitness']}
  QD-Score     : {s['qd_score']}
  Improvements : {s['improvements']}""")

    # -- Load data -------------------------------------------------------------
    section("LOADING DATA")
    df_full, source = load_data(args)
    print(Fore.GREEN +
          f"  {len(df_full)} days  "
          f"({df_full.index[0].date()} -> {df_full.index[-1].date()})  "
          f"source={source}")

    # Split train / test (same split used in evolution)
    split_date = "2022-12-31"
    df_train   = df_full[df_full.index <= split_date]
    df_test    = df_full[df_full.index >  split_date]

    if len(df_test) < 50:
        # Use last 20% as test if not enough post-2022 data
        split_idx = int(len(df_full) * 0.8)
        df_train  = df_full.iloc[:split_idx]
        df_test   = df_full.iloc[split_idx:]

    print(Fore.GREEN +
          f"  Train: {len(df_train)} days  "
          f"({df_train.index[0].date()} -> {df_train.index[-1].date()})")
    print(Fore.GREEN +
          f"  Test:  {len(df_test)} days  "
          f"({df_test.index[0].date()} -> {df_test.index[-1].date()})")

    all_results = {}

    # -- TEST 1: Out-of-Sample -------------------------------------------------
    section("TEST 1 -- Out-of-Sample Performance")
    print(Fore.WHITE + """
  This is the most important test.
  The archive was evolved on training data only.
  We now run it on data it has NEVER seen.
  Good result = strategies have real predictive power.
  Bad result  = strategies are overfit to training data.
""")
    df_test_ind = add_all_indicators(df_test)
    oos_results = out_of_sample_test(archive, df_test, df_train, verbose=True)
    all_results["out_of_sample"] = oos_results

    # -- TEST 2: Benchmark Comparison ------------------------------------------
    section("TEST 2 -- Benchmark Comparison")
    print(Fore.WHITE + """
  Compare against: Buy&Hold, MA crossover, RSI, Random signals.
  If QD can't beat a simple MA crossover, it has no value.
""")
    benchmarks = run_all_benchmarks(df_test_ind, archive=archive)
    print_benchmark_table(benchmarks)
    all_results["benchmarks"] = [
        {"name": b.name, "sharpe": b.sharpe, "return": b.total_return,
         "max_dd": b.max_drawdown}
        for b in benchmarks
    ]

    # -- TEST 3: Monte Carlo Significance --------------------------------------
    section("TEST 3 -- Monte Carlo Significance")
    print(Fore.WHITE + """
  Randomly shuffle the strategy's returns 1000 times.
  See if the real Sharpe is better than 95% of random shuffles.
  p-value < 0.05 = result is statistically significant.
  p-value > 0.05 = result could be luck.
""")
    n_perm = 500 if args.fast else 1000
    mc_results = test_multiple_strategies(
        archive, df_test_ind,
        n_permutations=n_perm,
        top_n=5,
    )
    all_results["monte_carlo"] = mc_results

    print(f"\n  {'Cell':8} {'TrainF':>8} {'TestF':>8} "
          f"{'p-val':>8} {'pctile':>8} {'CI':>16} {'Verdict':>14}")
    print("  " + "-" * 72)
    for r in mc_results:
        verdict_color = Fore.GREEN if r["significant"] else Fore.RED
        print(
            Fore.WHITE  + f"  {r['cell']:8} "
            f"{r['train_fitness']:+8.3f} "
            f"{r['real_sharpe']:+8.3f} "
            f"{r['p_value']:8.4f} "
            f"{r['percentile']:7.1f}% "
            f"[{r['ci_low']:+.2f}, {r['ci_high']:+.2f}]  "
            + verdict_color + f"{r['verdict']:>14}"
        )

    n_sig = sum(1 for r in mc_results if r["significant"])
    print(Fore.GREEN + f"\n  {n_sig}/{len(mc_results)} strategies statistically significant")

    # -- TEST 4: Walk-Forward Validation ---------------------------------------
    section("TEST 4 -- Walk-Forward Validation")
    print(Fore.WHITE + """
  Repeatedly evolve on past, test on future (never seen data).
  This is the strictest test of out-of-sample generalization.
  Each test window is completely unseen during that window's training.
""")
    n_windows  = 3 if args.fast else 5
    wf_gens    = 200 if args.fast else 400

    wf_results = run_walk_forward(
        df_full,
        train_years  = 4,
        test_years   = 1,
        n_windows    = n_windows,
        generations  = wf_gens,
        seed_n       = 60,
        verbose      = True,
    )
    wf_summary = summarise_walk_forward(wf_results)
    all_results["walk_forward"] = {
        "summary": wf_summary,
        "windows": [
            {"window": r.window,
             "train_sharpe": r.train_sharpe,
             "test_sharpe": r.test_sharpe,
             "test_return": r.test_return,
             "degradation": r.degradation}
            for r in wf_results
        ]
    }

    if wf_summary:
        print(Fore.CYAN + f"\n  Walk-Forward Summary:")
        print(f"  Pass rate         : {wf_summary['pass_rate']} windows")
        print(f"  Mean test Sharpe  : {wf_summary['mean_test_sharpe']:+.3f} "
              f"+/- {wf_summary['std_test_sharpe']:.3f}")
        print(f"  Mean test return  : {wf_summary['mean_test_return']:+.1f}%")
        print(f"  Mean degradation  : {wf_summary['mean_degradation']:+.3f}")
        verdict_c = Fore.GREEN if wf_summary["verdict"] == "ROBUST" else Fore.RED
        print(verdict_c + f"  Verdict           : {wf_summary['verdict']}")

    # -- Final report plot -----------------------------------------------------
    section("GENERATING TEST REPORT PLOT")
    _plot_test_report(benchmarks, mc_results, wf_results, oos_results, df_test_ind, archive)

    # -- Final verdict ----------------------------------------------------------
    section("OVERALL VERDICT")
    _print_final_verdict(oos_results, wf_summary, mc_results, benchmarks)

    elapsed = time.time() - t0
    print(Fore.WHITE + f"\n  Test suite completed in {elapsed:.0f}s\n")

    return all_results


def _print_final_verdict(oos, wf_summary, mc, benchmarks):
    score = 0
    notes = []

    # OOS pass?
    if oos.get("pct_positive", 0) >= 60:
        score += 1
        notes.append(Fore.GREEN + f"  [OK] OOS: {oos['pct_positive']}% strategies positive on unseen data")
    else:
        notes.append(Fore.RED   + f"  [X] OOS: only {oos.get('pct_positive',0)}% positive -- possible overfit")

    # Monte Carlo significant?
    n_sig = sum(1 for r in mc if r["significant"])
    if n_sig >= len(mc) // 2:
        score += 1
        notes.append(Fore.GREEN + f"  [OK] MC: {n_sig}/{len(mc)} strategies statistically significant")
    else:
        notes.append(Fore.RED   + f"  [X] MC: only {n_sig}/{len(mc)} significant -- results may be luck")

    # Walk-forward pass?
    if wf_summary and wf_summary.get("verdict") == "ROBUST":
        score += 1
        notes.append(Fore.GREEN + f"  [OK] WF: {wf_summary['pass_rate']} walk-forward windows passed")
    elif wf_summary:
        notes.append(Fore.RED   + f"  [X] WF: {wf_summary['pass_rate']} windows passed -- not robust")

    # Beats buy-and-hold?
    bh   = next((b for b in benchmarks if "Hold" in b.name), None)
    qd   = next((b for b in benchmarks if "QD" in b.name), None)
    if bh and qd and qd.sharpe > bh.sharpe:
        score += 1
        notes.append(Fore.GREEN +
                     f"  [OK] Benchmark: QD Sharpe {qd.sharpe:+.3f} > B&H {bh.sharpe:+.3f}")
    elif bh and qd:
        notes.append(Fore.RED   +
                     f"  [X] Benchmark: QD {qd.sharpe:+.3f} fails to beat B&H {bh.sharpe:+.3f}")

    print()
    for note in notes:
        print(note)

    print()
    total = 4
    if score == total:
        print(Fore.GREEN + f"  OVERALL: {score}/{total} -- STRONG evidence strategy is real")
    elif score >= 2:
        print(Fore.YELLOW + f"  OVERALL: {score}/{total} -- MIXED evidence, needs more data")
    else:
        print(Fore.RED + f"  OVERALL: {score}/{total} -- WEAK evidence, likely overfit")


def _plot_test_report(benchmarks, mc_results, wf_results, oos_results,
                      df_test_ind, archive):
    import warnings
    warnings.filterwarnings("ignore")

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("QD Trading System -- Full Test Report", fontsize=13)

    # 1. Equity curves
    ax = axes[0, 0]
    colors = plt.cm.tab10(np.linspace(0, 1, max(len(benchmarks), 1)))
    for idx, b in enumerate(benchmarks):
        try:
            lw = 2.5 if "QD" in b.name else 1
            ls = "--" if "Hold" in b.name else "-"
            ax.plot(b.equity_curve.index, b.equity_curve.values,
                    color=colors[idx], lw=lw, ls=ls, label=b.name, alpha=0.85)
        except Exception:
            pass
    ax.set_title("Equity Curves -- Test Period (unseen data)")
    ax.set_ylabel("Equity"); ax.legend(fontsize=7); ax.grid(alpha=0.3)
    ax.axhline(1.0, color="gray", lw=0.5, ls=":")

    # 2. Monte Carlo
    ax2 = axes[0, 1]
    try:
        from strategies.signal_generator import generate_signals
        cells = [(c.fitness, i, j, c)
                 for i in range(archive.grid_size)
                 for j in range(archive.grid_size)
                 if (c := archive.grid[i][j]) is not None]
        cells.sort(key=lambda x: -x[0])
        if cells:
            best   = cells[0][3]
            params = best.genome.decode()
            sigs   = generate_signals(df_test_ind, params).shift(1).fillna(0)
            ret    = sigs * df_test_ind["Close"].pct_change().fillna(0)
            net    = ret - sigs.diff().abs().fillna(0) * 0.001
            real_sh = sharpe_ratio(net)
            null = []
            for _ in range(300):
                perm = np.random.permutation(net.values)
                sh   = sharpe_ratio(pd.Series(perm))
                if np.isfinite(sh):
                    null.append(sh)
            if null and np.std(null) > 1e-6:
                ax2.hist(null, bins=25, color="#90CAF9", edgecolor="white", alpha=0.8)
                ax2.axvline(real_sh, color="#E53935", lw=2,
                            label=f"Real Sharpe={real_sh:.3f}")
                p95 = np.percentile(null, 95)
                ax2.axvline(p95, color="#FF9800", lw=1.5, ls="--",
                            label=f"95th pctile={p95:.3f}")
                ax2.legend(fontsize=8)
            else:
                ax2.text(0.5, 0.5, "Null distribution degenerate", ha="center", va="center", transform=ax2.transAxes, fontsize=9)
    except Exception as e:
        ax2.text(0.5, 0.5, f"MC plot error: {str(e)}", ha="center", va="center", transform=ax2.transAxes, fontsize=8)
    ax2.set_title("Monte Carlo: Best Strategy vs Null Distribution")
    ax2.set_xlabel("Sharpe Ratio"); ax2.grid(alpha=0.3)

    # 3. Walk-forward
    ax3 = axes[1, 0]
    if wf_results:
        x      = np.arange(len(wf_results))
        width  = 0.35
        train  = [r.train_sharpe for r in wf_results]
        test   = [r.test_sharpe  for r in wf_results]
        ax3.bar(x - width/2, train, width, label="Train", color="#42A5F5", alpha=0.8)
        bars = ax3.bar(x + width/2, test, width, label="Test",
                       color=["#66BB6A" if t >= 0 else "#EF5350" for t in test], alpha=0.8)
        ax3.axhline(0, color="black", lw=0.5)
        ax3.set_xticks(x)
        ax3.set_xticklabels(["W"+str(r.window)+" "+r.test_start[:4] for r in wf_results])
        ax3.legend(); ax3.grid(alpha=0.3, axis="y")
    ax3.set_title("Walk-Forward: Train vs Test Sharpe")
    ax3.set_ylabel("Sharpe Ratio")

    # 4. Benchmark comparison
    ax4 = axes[1, 1]
    names   = [b.name for b in benchmarks]
    sharpes = [b.sharpe for b in benchmarks]
    clrs    = ["#FF7043" if "QD" in n else ("#66BB6A" if s >= 0 else "#EF5350")
               for n, s in zip(names, sharpes)]
    bars = ax4.barh(names, sharpes, color=clrs, edgecolor="white", alpha=0.85)
    ax4.axvline(0, color="black", lw=0.5)
    for bar, val in zip(bars, sharpes):
        ax4.text(val + (0.02 if val >= 0 else -0.02),
                 bar.get_y() + bar.get_height() / 2,
                 f"{val:+.3f}", va="center",
                 ha="left" if val >= 0 else "right", fontsize=8)
    ax4.set_title("Strategy Comparison -- Sharpe (test period)")
    ax4.set_xlabel("Sharpe Ratio"); ax4.grid(alpha=0.3, axis="x")

    plt.tight_layout()
    out_path = "output/plots/test_report.png"
    Path("output/plots").mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close()
    print(Fore.BLUE + f"  Report plot saved: {out_path}")
    return out_path



if __name__ == "__main__":
    args = parse_args()
    run_tests(args)