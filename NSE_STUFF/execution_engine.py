"""
execution_engine.py
The production brain of the system.

Flow:
  1. Fetch latest market data from broker
  2. Load QD archive
  3. Detect current market regime
  4. Get signal from best strategy
  5. Compare to current position
  6. If action needed → place order via broker
  7. Log everything

This is what runs in production instead of daily_signal.py
"""

import os
import sys
import json
import datetime
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ── Logging setup ─────────────────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level    = logging.INFO,
    format   = "%(asctime)s  %(levelname)s  %(message)s",
    handlers = [
        logging.FileHandler("logs/execution.log"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("QD-Execution")


# ══════════════════════════════════════════════════════════════════════════════
# EXECUTION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class ExecutionEngine:

    def __init__(self, dry_run: bool = True):
        """
        dry_run=True  → compute signals and log, but DO NOT place real orders
        dry_run=False → place real orders via broker API
        Always start with dry_run=True until you are 100% confident.
        """
        self.dry_run = dry_run
        self._load_config()
        self._load_archive()
        self._load_broker()

        if dry_run:
            log.info("=" * 55)
            log.info("  MODE: DRY RUN — signals computed, NO orders placed")
            log.info("=" * 55)
        else:
            log.warning("=" * 55)
            log.warning("  MODE: LIVE — REAL ORDERS WILL BE PLACED")
            log.warning("=" * 55)

    def _load_config(self):
        try:
            import config as cfg
            self.ticker          = cfg.PRIMARY_TICKER
            self.max_capital     = cfg.MAX_CAPITAL_INR
            self.max_pos_pct     = cfg.MAX_POSITION_PCT
            self.min_trade_value = cfg.MIN_TRADE_VALUE_INR
            self.broker_name     = cfg.BROKER
            log.info(f"Config loaded: {self.ticker}  Capital=Rs {self.max_capital:,.0f}  "
                     f"Broker={self.broker_name}")
        except Exception as e:
            log.error(f"Config load error: {e}")
            raise

    def _load_archive(self):
        archive_path = Path("output/archive.json")
        if not archive_path.exists():
            raise FileNotFoundError(
                "Archive not found. Run evolution first:\n"
                "  python run_evolution.py --csv data/NIFTYBEES.csv --generations 2000"
            )
        from evolution.map_elites import MapElitesArchive
        self.archive = MapElitesArchive.load(str(archive_path))
        s = self.archive.summary()
        log.info(f"Archive loaded: {s['n_filled']}/100 niches  "
                 f"Best={s['max_fitness']:.3f}  Mean={s['mean_fitness']:.3f}")

    def _load_broker(self):
        from broker.broker import get_broker
        self.broker = get_broker(self.broker_name)
        funds = self.broker.get_funds()
        log.info(f"Broker ready: available_cash=Rs {funds.get('available_cash', 0):,.0f}")

    # ── Core: build price DataFrame from broker live data ────────────────────

    def _build_dataframe(self) -> "pd.DataFrame":
        """
        Fetches recent historical data and appends today's live quote.
        This gives the indicator calculations a full lookback window.
        """
        import pandas as pd
        import numpy as np
        from strategies.indicators import add_all_indicators
        from data.csv_loader import load_csv

        # Load historical data from CSV for indicator warmup
        csv_path = Path(f"data/{self.ticker.replace('.NS','').replace('^','')}.csv")
        if not csv_path.exists():
            csv_path = Path("data/NIFTYBEES.csv")

        if csv_path.exists():
            df = load_csv(str(csv_path))
        else:
            # Download via yfinance as fallback
            import yfinance as yf
            raw = yf.download(self.ticker, period="2y", auto_adjust=True, progress=False)
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            df = raw[["Open","High","Low","Close","Volume"]].dropna()

        # Append today's live quote as the last row
        quote = self.broker.get_quote(self.ticker)
        if quote.get("ltp", 0) > 0:
            today = pd.Timestamp(datetime.date.today())
            if today not in df.index:
                new_row = pd.DataFrame({
                    "Open":   [quote.get("open",  quote["ltp"])],
                    "High":   [quote.get("high",  quote["ltp"])],
                    "Low":    [quote.get("low",   quote["ltp"])],
                    "Close":  [quote["ltp"]],
                    "Volume": [quote.get("volume", 0)],
                }, index=[today])
                df = pd.concat([df, new_row])
                log.info(f"Appended live quote: {self.ticker} = Rs {quote['ltp']:.2f}")

        df = add_all_indicators(df)
        return df

    # ── Core: compute today's signal ─────────────────────────────────────────

    def compute_signal(self) -> dict:
        """
        Full signal computation pipeline.
        Returns a signal dict with all context.
        """
        import numpy as np
        from strategies.signal_generator import generate_signals

        df = self._build_dataframe()

        # Regime detection
        bd1 = float(np.clip(df["vol_pct"].iloc[-1]  if "vol_pct" in df.columns else 0.5, 0, 1))
        bd2 = float(np.clip(df["adx_pct"].iloc[-1]  if "adx_pct" in df.columns else 0.5, 0, 1))

        vol_desc   = "LOW"     if bd1 < 0.33 else "MEDIUM"     if bd1 < 0.66 else "HIGH"
        trend_desc = "RANGING" if bd2 < 0.33 else "MILD TREND" if bd2 < 0.66 else "STRONG TREND"

        # Route to best strategy with fallback
        cell    = self.archive.get_best_for_regime(bd1, bd2)
        routing = "DIRECT"
        cell_i, cell_j = 0, 0
        for i in range(self.archive.grid_size):
            for j in range(self.archive.grid_size):
                if self.archive.grid[i][j] is cell:
                    cell_i, cell_j = i, j

        if cell is None or cell.fitness < 0.3:
            best_c, best_f = None, -99
            for i in range(self.archive.grid_size):
                for j in range(self.archive.grid_size):
                    c = self.archive.grid[i][j]
                    if c and c.fitness > best_f:
                        best_f, best_c = c.fitness, c
                        cell_i, cell_j = i, j
            cell    = best_c
            routing = "FALLBACK"

        params     = cell.genome.decode()
        signals    = generate_signals(df, params)
        raw_signal = float(signals.iloc[-1])
        spy_price  = float(df["Close"].iloc[-1])

        signal_str = "LONG" if raw_signal > 0 else ("FLAT/EXIT" if raw_signal < 0 else "FLAT")

        result = {
            "date":          str(datetime.date.today()),
            "ticker":        self.ticker,
            "price":         spy_price,
            "signal":        signal_str,
            "raw_signal":    raw_signal,
            "bd1":           bd1,
            "bd2":           bd2,
            "vol_regime":    vol_desc,
            "trend_regime":  trend_desc,
            "routing":       routing,
            "cell":          f"V{cell_i}/T{cell_j}",
            "cell_sharpe":   cell.fitness,
            "cell_winrate":  cell.win_rate,
            "params":        {
                "fast_ma":      params["fast_ma"],
                "slow_ma":      params["slow_ma"],
                "stop_loss":    params["stop_loss"],
                "take_profit":  params["take_profit"],
                "position_size":params["position_size"],
            },
        }

        log.info(f"Signal: {signal_str}  |  {self.ticker}=Rs {spy_price:.2f}  |  "
                 f"Vol={vol_desc} Trend={trend_desc}  |  "
                 f"Cell={result['cell']} Sharpe={cell.fitness:.3f}  |  "
                 f"Routing={routing}")

        return result

    # ── Core: execute the signal ──────────────────────────────────────────────

    def execute(self) -> dict:
        """
        Full pipeline: signal → position check → order if needed.
        This is the function you call in production.
        """
        signal_data = self.compute_signal()
        signal      = signal_data["signal"]
        price       = signal_data["price"]
        pos_pct     = signal_data["params"]["position_size"]

        # Current positions
        positions   = self.broker.get_positions()
        has_position = any(p["symbol"] == self.ticker.replace(".NS","") or
                           p["symbol"] == self.ticker
                           for p in positions)

        funds       = self.broker.get_funds()
        cash        = funds.get("available_cash", 0)

        action_taken = "NONE"

        # ── Decision logic ──────────────────────────────────────────────────
        if signal == "LONG" and not has_position:
            # Enter long
            deploy  = min(self.max_capital * pos_pct * self.max_pos_pct, cash)
            qty     = int(deploy / price)

            if qty > 0 and deploy >= self.min_trade_value:
                log.info(f"ENTER LONG: {qty} x {self.ticker} @ Rs {price:.2f}  "
                         f"(deploy Rs {deploy:,.0f})")
                if not self.dry_run:
                    order = self.broker.place_order(self.ticker, "BUY", qty)
                    log.info(f"Order placed: {order}")
                else:
                    log.info(f"[DRY RUN] Would place: BUY {qty} {self.ticker}")
                action_taken = f"ENTERED LONG {qty} @ {price:.2f}"
            else:
                log.warning(f"Skipping — qty={qty} or value too small")

        elif signal in ("FLAT", "FLAT/EXIT") and has_position:
            # Exit position
            for pos in positions:
                if self.ticker.replace(".NS","") in pos["symbol"] or \
                   self.ticker in pos["symbol"]:
                    qty = pos["qty"]
                    pnl = pos.get("pnl_pct", 0)
                    log.info(f"EXIT: {qty} x {self.ticker}  "
                             f"Unrealised P&L: {pnl:+.2f}%")
                    if not self.dry_run:
                        order = self.broker.place_order(self.ticker, "SELL", qty)
                        log.info(f"Order placed: {order}")
                    else:
                        log.info(f"[DRY RUN] Would place: SELL {qty} {self.ticker}")
                    action_taken = f"EXITED {qty} @ {price:.2f} (PnL {pnl:+.2f}%)"

        elif signal == "LONG" and has_position:
            for pos in positions:
                if self.ticker.replace(".NS","") in pos["symbol"]:
                    pnl = pos.get("pnl_pct", 0)
                    log.info(f"HOLD: already long  Unrealised P&L: {pnl:+.2f}%")
            action_taken = "HOLDING"

        else:
            log.info(f"FLAT — no position, no action")
            action_taken = "FLAT"

        # Save execution record
        record = {**signal_data, "action": action_taken,
                  "dry_run": self.dry_run,
                  "funds":   funds}
        record_path = Path("logs") / f"exec_{datetime.date.today()}.json"
        with open(record_path, "w") as f:
            json.dump(record, f, indent=2, default=str)

        return record


# ══════════════════════════════════════════════════════════════════════════════
# CLI — can run directly
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true",
                   help="Place real orders (default: dry run only)")
    args = p.parse_args()

    if args.live:
        print("\n  WARNING: --live flag set. Real orders will be placed.")
        confirm = input("  Type 'YES' to confirm: ")
        if confirm != "YES":
            print("  Aborted.")
            sys.exit(0)

    engine = ExecutionEngine(dry_run=not args.live)
    result = engine.execute()

    print(f"\n  Result: {result['action']}")
    print(f"  Signal: {result['signal']}")
    print(f"  Price : Rs {result['price']:.2f}")
    print(f"  Regime: Vol={result['vol_regime']}  Trend={result['trend_regime']}")
