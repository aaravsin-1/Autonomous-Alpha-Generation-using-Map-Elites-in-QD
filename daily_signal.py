"""
daily_signal.py
Run every morning before markets open.
Prints today's trading signal, current regime, and strategy details.

Usage:
    python daily_signal.py
    python daily_signal.py --csv data/SPY.csv
"""

import sys
import os
import argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from colorama import init, Fore
init(autoreset=True)

import numpy as np


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--csv",     default="data/SPY.csv")
    p.add_argument("--archive", default="output/archive.json")
    return p.parse_args()


def main():
    args = parse_args()

    # Load archive
    from evolution.map_elites import MapElitesArchive
    if not os.path.exists(args.archive):
        print(Fore.RED + f"\n  Archive not found: {args.archive}")
        print("  Run: python run_evolution.py --csv data/SPY.csv --generations 2000\n")
        return

    archive = MapElitesArchive.load(args.archive)

    # Load data
    from data.csv_loader import load_csv
    from strategies.indicators import add_all_indicators
    from strategies.signal_generator import generate_signals

    df_raw = load_csv(args.csv)
    df     = add_all_indicators(df_raw)

    # Detect regime
    bd1 = float(df["vol_pct"].iloc[-1]) if "vol_pct" in df.columns else 0.5
    bd2 = float(df["adx_pct"].iloc[-1]) if "adx_pct" in df.columns else 0.5
    bd1 = float(np.clip(bd1, 0, 1))
    bd2 = float(np.clip(bd2, 0, 1))

    vol_desc   = "LOW"    if bd1 < 0.33 else "MEDIUM" if bd1 < 0.66 else "HIGH"
    trend_desc = "RANGING" if bd2 < 0.33 else "MILD TREND" if bd2 < 0.66 else "STRONG TREND"

    # Route to best strategy — with fallback
    cell    = archive.get_best_for_regime(bd1, bd2)
    routing = "DIRECT"
    if cell is None or cell.fitness < 0.3:
        best_cell, best_fit = None, -99
        for i in range(archive.grid_size):
            for j in range(archive.grid_size):
                c = archive.grid[i][j]
                if c and c.fitness > best_fit:
                    best_fit, best_cell = c.fitness, c
        cell    = best_cell
        routing = "FALLBACK (using best overall strategy)"

    if cell is None:
        print(Fore.RED + "\n  No strategies in archive. Run evolution first.\n")
        return

    # Generate signal
    params  = cell.genome.decode()
    signals = generate_signals(df, params)
    signal  = float(signals.iloc[-1])

    if signal > 0:
        signal_text, signal_color = "LONG",       Fore.GREEN
        action_text = f"Buy/Hold SPY at {params['position_size']*100:.0f}% position size"
    elif signal < 0:
        signal_text, signal_color = "FLAT/EXIT",  Fore.RED
        action_text = "Exit any long position. Hold cash."
    else:
        signal_text, signal_color = "FLAT",       Fore.YELLOW
        action_text = "No position. Hold cash."

    latest = df.iloc[-1]

    print()
    print(Fore.CYAN  + "=" * 56)
    print(Fore.CYAN  + "  QD TRADING SYSTEM - Daily Signal")
    print(Fore.CYAN  + "=" * 56)
    print()
    print(Fore.WHITE + f"  Date      : {df.index[-1].date()}")
    print(Fore.WHITE + f"  SPY Close : ${latest['Close']:.2f}")
    print()
    print(Fore.WHITE + f"  Regime    : Vol={vol_desc} ({bd1:.2f})  Trend={trend_desc} ({bd2:.2f})")
    print(Fore.WHITE + f"  Routing   : {routing}")
    print()
    print(signal_color + f"  SIGNAL    : *** {signal_text} ***")
    print(signal_color + f"  ACTION    : {action_text}")
    print()
    print(Fore.WHITE + f"  Strategy  : Sharpe={cell.fitness:.3f}  "
          f"WinRate={cell.win_rate:.1%}  Trades={cell.n_trades}")
    print(Fore.WHITE + f"  Params    : EMA({params['fast_ma']:.0f}/{params['slow_ma']:.0f})  "
          f"RSI({params['rsi_period']:.0f})  "
          f"Stop={params['stop_loss']*100:.1f}%  "
          f"Take={params['take_profit']*100:.1f}%")
    print()
    print(Fore.CYAN  + "=" * 56)
    print()
    print(Fore.WHITE + "  Journal entry:")
    print(f"    {df.index[-1].date()} | {signal_text} | ${latest['Close']:.2f} | "
          f"Vol={vol_desc} Trend={trend_desc}")
    print()


if __name__ == "__main__":
    main()