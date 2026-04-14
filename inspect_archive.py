"""
inspect_archive.py
Load a saved archive and print a full diagnostic report.
Usage:  python inspect_archive.py
        python inspect_archive.py --archive output/archive.json
"""

import argparse
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from pathlib import Path
from colorama import init, Fore
init(autoreset=True)

import config as cfg
from data.fetcher import fetch_ohlcv
from strategies.indicators import add_all_indicators
from evolution.map_elites import MapElitesArchive
from router.live_router import LiveRouter
from visualization.dashboard import plot_archive_heatmap, plot_top_strategies


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--archive", default=f"{cfg.OUTPUT_DIR}/{cfg.ARCHIVE_FILE}")
    p.add_argument("--ticker",  default=cfg.PRIMARY_TICKER)
    p.add_argument("--csv",     default=None,
                   help="Path to OHLCV CSV file e.g. data/SPY.csv")
    return p.parse_args()


def print_archive_report(archive: MapElitesArchive):
    s = archive.summary()
    print(Fore.CYAN + "\n" + "=" * 64)
    print(Fore.CYAN + "  ARCHIVE REPORT")
    print(Fore.CYAN + "=" * 64)
    print(f"  Niches filled : {s['n_filled']}/100  ({s['coverage']}%)")
    print(f"  QD-Score      : {s['qd_score']}")
    print(f"  Best Sharpe   : {s['max_fitness']}")
    print(f"  Mean Sharpe   : {s['mean_fitness']}")
    print(f"  Improvements  : {s['improvements']}")

    print(Fore.CYAN + "\n  Top 10 strategies by fitness:")
    print(f"  {'Cell':8} {'Fitness':>8} {'Sharpe':>8} "
          f"{'Ret%':>8} {'MaxDD%':>8} {'WinR%':>8} {'Trades':>7}")
    print("  " + "-" * 58)

    cells = []
    for i in range(archive.grid_size):
        for j in range(archive.grid_size):
            c = archive.grid[i][j]
            if c is not None:
                cells.append((c.fitness, i, j, c))
    cells.sort(key=lambda x: -x[0])

    for fit, i, j, c in cells[:10]:
        print(
            f"  V{i:1d}/T{j:1d}    "
            f"{c.fitness:+8.3f} "
            f"{c.sharpe:+8.3f} "
            f"{c.total_return*100:+8.1f} "
            f"{c.max_dd*100:+8.1f} "
            f"{c.win_rate*100:+8.1f} "
            f"{c.n_trades:7d}"
        )

    # Strategy genome breakdown for best strategy
    best = cells[0][3]
    params = best.genome.decode()
    print(Fore.CYAN + "\n  Best strategy genome (decoded):")
    print(f"  Signal weights  : MA={params['weights'][0]:.2f} "
          f"RSI={params['weights'][1]:.2f} "
          f"MACD={params['weights'][2]:.2f} "
          f"BB={params['weights'][3]:.2f}")
    print(f"  MA crossover    : EMA({params['fast_ma']}) vs EMA({params['slow_ma']})")
    print(f"  RSI             : period={params['rsi_period']} "
          f"OB={params['rsi_overbought']:.0f} OS={params['rsi_oversold']:.0f}")
    print(f"  MACD            : {params['macd_fast']}/{params['macd_slow']}/{params['macd_signal']}")
    print(f"  Stop-loss       : {params['stop_loss']*100:.1f}%")
    print(f"  Take-profit     : {params['take_profit']*100:.1f}%")
    print(f"  Position size   : {params['position_size']*100:.0f}%")
    print(f"  Trend filter    : {params['trend_filter']:.2f}")


def run_inspect(args):
    if not Path(args.archive).exists():
        print(Fore.RED + f"  Archive not found: {args.archive}")
        print("  Run python run_evolution.py first.")
        return

    print(Fore.CYAN + f"  Loading archive: {args.archive}")
    archive = MapElitesArchive.load(args.archive)

    print(Fore.CYAN + f"  Loading market data for routing table...")
    if args.csv:
        from data.csv_loader import load_csv
        df_raw = load_csv(args.csv)
    else:
        df_raw = fetch_ohlcv(args.ticker, cfg.TEST_START, cfg.TEST_END)
    df     = add_all_indicators(df_raw)

    print_archive_report(archive)

    # Live routing
    router = LiveRouter(archive, df_raw)
    print(Fore.CYAN + f"\n  Current regime (latest data): {router.regime_description()}")
    router.print_routing_table()

    # Generate updated plots
    print(Fore.CYAN + "\n  Generating plots...")
    p1 = plot_archive_heatmap(archive, generation=archive.improvements, save=True)
    p2 = plot_top_strategies(archive, df_raw, n=5, save=True)
    print(Fore.GREEN + f"  Plots: {p1}")
    print(Fore.GREEN + f"         {p2}")


if __name__ == "__main__":
    args = parse_args()
    run_inspect(args)