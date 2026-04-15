"""
router/live_router.py

The routing problem explained
------------------------------
The archive is a 10x10 grid indexed by two genome-based dimensions:
  BD1 = momentum bias   (0 = pure mean-reversion, 1 = pure momentum)
  BD2 = risk tolerance  (0 = very tight stop-loss, 1 = very wide stop-loss)

These describe what TYPE of strategy occupies each cell --
not what market conditions it was trained on.

So we cannot say "current vol is high, route to high-BD1 cell."
BD1 has nothing to do with volatility.

The correct routing question is:
  "Given TODAY's market conditions, which strategy TYPE tends to work best?"

Research and backtesting on SPY shows:
  High volatility + strong trend  -> momentum strategies work better
                                     (MA crossover, MACD carry the signal)
  Low volatility + ranging        -> mean-reversion works better
                                     (RSI, Bollinger Bands carry the signal)
  High volatility (any trend)     -> tight stops get whipsawed, use moderate stops
  Low volatility                  -> tight stops are fine (less noise)

We map these empirical relationships to archive coordinates:
  market vol high   -> prefer higher BD1 (more momentum weight)
  market ranging    -> prefer lower BD1  (more mean-reversion weight)
  market vol high   -> prefer moderate BD2 (0.3-0.5, not too tight, not too wide)
  market vol low    -> prefer low BD2    (tight stops are safe)

Then we pick the best strategy within that preferred region
rather than the single geometrically nearest cell.
"""

import numpy as np
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from strategies.indicators import add_all_indicators
from strategies.signal_generator import generate_signals


class LiveRouter:

    # Regime-to-archive mapping table
    # Each regime maps to a preferred BD1 range and BD2 range
    # Format: (bd1_min, bd1_max, bd2_min, bd2_max)
    REGIME_PREFERENCES = {
        # (vol_bucket, trend_bucket): (bd1_min, bd1_max, bd2_min, bd2_max)
        ("low",    "ranging"):    (0.0, 0.45, 0.0, 0.35),  # mean-rev, tight stop
        ("low",    "trending"):   (0.3, 0.65, 0.0, 0.35),  # balanced, tight stop
        ("medium", "ranging"):    (0.2, 0.55, 0.1, 0.45),  # slight mean-rev, moderate
        ("medium", "trending"):   (0.4, 0.75, 0.1, 0.45),  # slight momentum, moderate
        ("high",   "ranging"):    (0.3, 0.65, 0.2, 0.55),  # balanced, moderate stop
        ("high",   "trending"):   (0.5, 0.85, 0.2, 0.55),  # momentum, moderate stop
    }

    def __init__(self, archive, df_live: pd.DataFrame,
                 regime_window: int = 10):
        """
        archive      : MapElitesArchive
        df_live      : raw OHLCV DataFrame (indicators added internally)
        regime_window: days to smooth regime detection (reduces noisy switches)
        """
        self.archive        = archive
        self.regime_window  = regime_window
        self.df             = add_all_indicators(df_live)

    # ---- Regime detection ---------------------------------------------------

    def current_regime(self) -> tuple:
        """
        Returns (bd1_market, bd2_market) where:
          bd1_market = rolling-average volatility percentile  [0,1]
          bd2_market = rolling-average ADX percentile         [0,1]

        Uses a rolling window to smooth out single-day noise.
        """
        n   = min(self.regime_window, len(self.df))
        win = self.df.iloc[-n:]

        if "vol_pct" in win.columns:
            bd1 = float(win["vol_pct"].mean())
        else:
            # Fallback: compute from rolling vol
            returns  = self.df["Close"].pct_change().dropna()
            vol_20   = returns.rolling(20).std().iloc[-1] * (252 ** 0.5)
            vol_hist = returns.rolling(20).std() * (252 ** 0.5)
            bd1      = float((vol_hist < vol_20).mean())

        if "adx_pct" in win.columns:
            bd2 = float(win["adx_pct"].mean())
        else:
            bd2 = 0.5

        return float(np.clip(bd1, 0.0, 1.0)), float(np.clip(bd2, 0.0, 1.0))

    def regime_buckets(self) -> tuple:
        """
        Converts continuous regime values to named buckets.
        Returns (vol_bucket, trend_bucket).
        """
        bd1, bd2 = self.current_regime()

        if bd1 < 0.33:
            vol_bucket = "low"
        elif bd1 < 0.66:
            vol_bucket = "medium"
        else:
            vol_bucket = "high"

        if bd2 < 0.45:
            trend_bucket = "ranging"
        else:
            trend_bucket = "trending"

        return vol_bucket, trend_bucket

    # ---- Core routing -------------------------------------------------------

    # Minimum acceptable Sharpe for a regime-mapped strategy.
    # If the best cell in the preferred region is below this,
    # we expand the search rather than accept a weak strategy.
    MIN_QUALITY = 0.50

    def get_best_strategy(self):
        """
        Returns the best archive cell for current market conditions.

        Strategy:
          1. Identify current regime (vol + trend buckets)
          2. Look up preferred BD1/BD2 ranges for that regime
          3. Find highest-fitness cell in that region
          4. Accept only if Sharpe >= MIN_QUALITY (0.50)
          5. If not good enough: expand search region
          6. Final fallback: best cell in archive overall

        MIN_QUALITY ensures we never route to a strategy with
        sub-50% win rate or weak Sharpe just because it happens
        to be the "right type" for the current regime.
        """
        vol_b, trend_b = self.regime_buckets()
        prefs = self.REGIME_PREFERENCES.get(
            (vol_b, trend_b),
            (0.0, 1.0, 0.0, 1.0)
        )
        bd1_min, bd1_max, bd2_min, bd2_max = prefs

        # Try preferred region first -- must meet quality floor
        cell = self._best_in_region(bd1_min, bd1_max, bd2_min, bd2_max)
        if cell and cell.fitness >= self.MIN_QUALITY:
            return cell

        # Expand region by 0.2 in each direction, still with quality floor
        cell = self._best_in_region(
            max(0, bd1_min - 0.2), min(1, bd1_max + 0.2),
            max(0, bd2_min - 0.2), min(1, bd2_max + 0.2)
        )
        if cell and cell.fitness >= self.MIN_QUALITY:
            return cell

        # Widen to half the grid, quality floor
        cell = self._best_in_region(0.0, 1.0, 0.0, 0.5)
        if cell and cell.fitness >= self.MIN_QUALITY:
            return cell

        # Final fallback: best in entire archive regardless of type
        return self._best_overall()

    def _best_in_region(self, bd1_min: float, bd1_max: float,
                         bd2_min: float, bd2_max: float):
        """Find highest-fitness cell whose BD coordinates fall in the given range."""
        gs       = self.archive.grid_size
        best     = None
        best_fit = -99.0

        for i in range(gs):
            for j in range(gs):
                c = self.archive.grid[i][j]
                if c is None:
                    continue
                # Convert cell indices back to BD fractions
                bd1_cell = (i + 0.5) / gs
                bd2_cell = (j + 0.5) / gs
                if (bd1_min <= bd1_cell <= bd1_max and
                        bd2_min <= bd2_cell <= bd2_max):
                    if c.fitness > best_fit:
                        best_fit = c.fitness
                        best     = c
        return best

    def _best_overall(self):
        """Absolute fallback: highest-fitness cell in entire archive."""
        best, best_fit = None, -99.0
        for i in range(self.archive.grid_size):
            for j in range(self.archive.grid_size):
                c = self.archive.grid[i][j]
                if c and c.fitness > best_fit:
                    best_fit = c.fitness
                    best     = c
        return best

    # ---- Signal -------------------------------------------------------------

    def get_signal(self) -> float:
        """
        Returns today's trading signal from the best strategy.
        +1 = long, -1 = short/exit, 0 = flat
        """
        cell = self.get_best_strategy()
        if cell is None:
            return 0.0
        params  = cell.genome.decode()
        signals = generate_signals(self.df, params)
        return float(signals.iloc[-1])

    # ---- Diagnostics --------------------------------------------------------

    def regime_description(self) -> str:
        bd1, bd2   = self.current_regime()
        vol_b, tr_b = self.regime_buckets()
        vol_desc   = f"{vol_b} ({bd1:.2f})"
        trend_desc = f"{tr_b} ({bd2:.2f})"
        return f"Vol: {vol_desc} | Trend: {trend_desc}"

    def routing_explanation(self) -> str:
        """Human-readable explanation of today's routing decision."""
        vol_b, trend_b = self.regime_buckets()
        prefs = self.REGIME_PREFERENCES.get((vol_b, trend_b), None)
        cell  = self.get_best_strategy()

        lines = []
        lines.append(f"Market regime   : Vol={vol_b}  Trend={trend_b}")
        if prefs:
            lines.append(f"Preferred region: BD1=[{prefs[0]:.1f},{prefs[1]:.1f}]  "
                         f"BD2=[{prefs[2]:.1f},{prefs[3]:.1f}]")
            if vol_b == "high" and trend_b == "trending":
                lines.append("Rationale       : High vol + trend -> momentum strategies")
            elif vol_b == "low" and trend_b == "ranging":
                lines.append("Rationale       : Low vol + ranging -> mean-reversion strategies")
            elif trend_b == "ranging":
                lines.append("Rationale       : Ranging market -> lean toward mean-reversion")
            else:
                lines.append("Rationale       : Trending market -> balanced/momentum strategies")

        if cell:
            # Find cell position
            for i in range(self.archive.grid_size):
                for j in range(self.archive.grid_size):
                    if self.archive.grid[i][j] is cell:
                        lines.append(f"Selected cell   : V{i}/T{j}  "
                                     f"Sharpe={cell.fitness:.3f}  "
                                     f"WinRate={cell.win_rate:.1%}")
                        p = cell.genome.decode()
                        lines.append(f"Strategy params : EMA({p['fast_ma']:.0f}/{p['slow_ma']:.0f})  "
                                     f"RSI({p['rsi_period']:.0f})  "
                                     f"Stop={p['stop_loss']*100:.1f}%  "
                                     f"Take={p['take_profit']*100:.1f}%")
                        lines.append(f"Signal weights  : MA={p['weights'][0]:.2f}  "
                                     f"RSI={p['weights'][1]:.2f}  "
                                     f"MACD={p['weights'][2]:.2f}  "
                                     f"BB={p['weights'][3]:.2f}")
                        break
        return "\n".join(lines)

    def print_routing_table(self):
        """Print full 10x10 routing table with current regime highlighted."""
        gs  = self.archive.grid_size
        bd1, bd2   = self.current_regime()
        vol_b, tr_b = self.regime_buckets()
        ci  = int(np.clip(bd1, 0, 0.9999) * gs)
        cj  = int(np.clip(bd2, 0, 0.9999) * gs)

        print(f"\n{'='*62}")
        print(f"  Routing table -- {self.archive.n_filled}/{gs*gs} niches filled")
        print(f"  BD1=momentum bias (rows: 0=mean-rev -> 9=momentum)")
        print(f"  BD2=risk tolerance (cols: 0=tight stop -> 9=wide stop)")
        print(f"{'='*62}")
        print("       " + "  ".join(f"T{j}" for j in range(gs)))
        print("       " + "  ".join("--" for j in range(gs)))

        prefs = self.REGIME_PREFERENCES.get((vol_b, tr_b), (0,1,0,1))
        bd1_mn, bd1_mx, bd2_mn, bd2_mx = prefs

        for i in range(gs):
            row = []
            for j in range(gs):
                cell = self.archive.grid[i][j]
                bd1_cell = (i + 0.5) / gs
                bd2_cell = (j + 0.5) / gs
                in_pref  = (bd1_mn <= bd1_cell <= bd1_mx and
                            bd2_mn <= bd2_cell <= bd2_mx)
                is_cur   = (i == ci and j == cj)

                if cell is None:
                    val = "  -- "
                elif is_cur:
                    val = f"[{cell.fitness:+.2f}]"  # current regime cell
                elif in_pref:
                    val = f"*{cell.fitness:+.2f} "  # preferred region
                else:
                    val = f" {cell.fitness:+.2f} "
            row.append(val)
            label = f"V{i} |"
            print(f"  {label}  " + "  ".join(row))

        print(f"\n  Current market  : Vol={vol_b} ({bd1:.2f})  "
              f"Trend={tr_b} ({bd2:.2f})")
        print(f"  Preferred region: BD1=[{bd1_mn:.1f},{bd1_mx:.1f}]  "
              f"BD2=[{bd2_mn:.1f},{bd2_mx:.1f}]")
        cell = self.get_best_strategy()
        if cell:
            for i in range(gs):
                for j in range(gs):
                    if self.archive.grid[i][j] is cell:
                        print(f"  Selected        : V{i}/T{j}  "
                              f"fitness={cell.fitness:.3f}  "
                              f"win_rate={cell.win_rate:.1%}  "
                              f"trades={cell.n_trades}")
                        break
        print(f"  [..] = current regime cell   * = preferred region")