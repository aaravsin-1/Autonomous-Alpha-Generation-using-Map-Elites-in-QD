"""
router/live_router.py
Given current market data, detects the regime and returns
the best strategy from the archive for that regime.
"""

import numpy as np
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from strategies.indicators import add_all_indicators
from strategies.signal_generator import generate_signals


class LiveRouter:
    """
    Wraps the MAP-Elites archive for live (or paper-trading) use.
    """

    def __init__(self, archive, df_live: pd.DataFrame):
        self.archive = archive
        self.df      = add_all_indicators(df_live)

    def current_regime(self) -> tuple:
        """
        Returns (bd1, bd2) for the most recent available data.
        bd1 = current volatility percentile
        bd2 = current trend strength percentile
        """
        row = self.df.iloc[-1]
        bd1 = float(row.get("vol_pct", 0.5))
        bd2 = float(row.get("adx_pct", 0.5))
        bd1 = float(np.clip(bd1, 0.0, 1.0))
        bd2 = float(np.clip(bd2, 0.0, 1.0))
        return bd1, bd2

    def get_best_strategy(self):
    bd1, bd2 = self.current_regime()
    cell = self.archive.get_best_for_regime(bd1, bd2)
    
    # If the routed cell is weak (fitness below 0.3), 
    # fall back to the best strategy overall
    if cell is None or cell.fitness < 0.3:
        best = None
        best_fit = -99
        for i in range(self.archive.grid_size):
            for j in range(self.archive.grid_size):
                c = self.archive.grid[i][j]
                if c and c.fitness > best_fit:
                    best_fit = c.fitness
                    best = c
        return best
    return cell

    def get_signal(self) -> float:
        """
        Returns the current trading signal from the best strategy.
        +1 = long, -1 = short, 0 = flat
        """
        cell = self.get_best_strategy()
        if cell is None:
            return 0.0

        params  = cell.genome.decode()
        signals = generate_signals(self.df, params)
        return float(signals.iloc[-1])

    def regime_description(self) -> str:
        bd1, bd2 = self.current_regime()
        vol_desc  = "low" if bd1 < 0.33 else "medium" if bd1 < 0.66 else "high"
        trend_desc = "ranging" if bd2 < 0.33 else "mild trend" if bd2 < 0.66 else "strong trend"
        return f"Vol: {vol_desc} ({bd1:.2f}) | Trend: {trend_desc} ({bd2:.2f})"

    def print_routing_table(self):
        """Print the full 10x10 routing table."""
        gs = self.archive.grid_size
        print(f"\n{'='*60}")
        print(f"  Routing table — {self.archive.n_filled}/{gs*gs} niches filled")
        print(f"  BD1=Volatility (rows, low→high)  BD2=Trend (cols, weak→strong)")
        print(f"{'='*60}")
        print("      " + " ".join(f"T{j}" for j in range(gs)))
        for i in range(gs):
            row_cells = []
            for j in range(gs):
                cell = self.archive.grid[i][j]
                if cell is None:
                    row_cells.append("  -- ")
                else:
                    row_cells.append(f"{cell.fitness:+.2f}")
            print(f"V{i}  " + " ".join(row_cells))
        bd1, bd2 = self.current_regime()
        i = int(np.clip(bd1, 0, 0.9999) * gs)
        j = int(np.clip(bd2, 0, 0.9999) * gs)
        print(f"\n  Current regime → cell V{i}/T{j}")
        cell = self.archive.get_best_for_regime(bd1, bd2)
        if cell:
            print(f"  Best strategy fitness={cell.fitness:.3f} "
                  f"sharpe={cell.sharpe:.3f} "
                  f"trades={cell.n_trades} "
                  f"win_rate={cell.win_rate:.1%}")
