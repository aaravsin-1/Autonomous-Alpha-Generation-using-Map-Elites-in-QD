"""
morning.py -- Complete automated morning routine for QD Trading System

Handles everything:
  - Downloads latest SPY data (or uses existing CSV)
  - Checks if market is open today
  - Runs daily signal with full routing logic
  - Logs everything to logs/daily_log.txt
  - Maintains paper trading journal in journal/paper_trades.csv
  - Tracks open positions and calculates running P&L
  - Runs monthly test suite on the 1st of each month
  - Triggers re-evolution if OOS% has been below 55% for 2 months
  - Runs extra generations if mean Sharpe is improving
  - Saves a human-readable summary to logs/latest_summary.txt

Usage:
    python morning.py
    python morning.py --csv data/SPY.csv    (skip download, use existing file)
    python morning.py --force-test          (force run full test suite today)
    python morning.py --force-evolve        (force run 500 new generations)
"""

import os
import sys
import json
import csv
import argparse
import datetime
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# -- Colorama for pretty terminal output --------------------------------------
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    class Fore:
        RED=GREEN=YELLOW=CYAN=WHITE=BLUE=MAGENTA=""
    HAS_COLOR = False

# -- Directory setup ------------------------------------------------------------
BASE_DIR    = Path(__file__).parent
LOG_DIR     = BASE_DIR / "logs"
JOURNAL_DIR = BASE_DIR / "journal"
OUTPUT_DIR  = BASE_DIR / "output"
DATA_DIR    = BASE_DIR / "data"

for d in [LOG_DIR, JOURNAL_DIR, OUTPUT_DIR, DATA_DIR]:
    d.mkdir(exist_ok=True)

DAILY_LOG_FILE    = LOG_DIR / "daily_log.txt"
SUMMARY_FILE      = LOG_DIR / "latest_summary.txt"
JOURNAL_FILE      = JOURNAL_DIR / "paper_trades.csv"
OOS_TRACKER_FILE  = LOG_DIR / "oos_tracker.json"
ARCHIVE_FILE      = OUTPUT_DIR / "archive.json"
CSV_FILE          = DATA_DIR / "SPY.csv"

TODAY = datetime.date.today()
NOW   = datetime.datetime.now()


# ==============================================================================
# LOGGING
# ==============================================================================

class Logger:
    """Writes to both terminal and log file simultaneously."""

    def __init__(self, log_file: Path):
        self.log_file = log_file
        self.lines = []

    def log(self, text: str = "", color: str = "", indent: int = 0):
        prefix = "  " * indent
        full   = prefix + text
        # Terminal (with color)
        print(color + full)
        # File (without color codes)
        self.lines.append(full)

    def sep(self, char="=", width=60, color=Fore.CYAN):
        self.log(char * width, color)

    def flush(self):
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"  SESSION: {NOW.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*60}\n")
            for line in self.lines:
                f.write(line + "\n")
            f.write("\n")


log = Logger(DAILY_LOG_FILE)


# ==============================================================================
# MARKET CALENDAR -- US holidays (approximate)
# ==============================================================================

US_HOLIDAYS_2025_2026 = {
    datetime.date(2025, 1, 1),   # New Year's Day
    datetime.date(2025, 1, 20),  # MLK Day
    datetime.date(2025, 2, 17),  # Presidents Day
    datetime.date(2025, 4, 18),  # Good Friday
    datetime.date(2025, 5, 26),  # Memorial Day
    datetime.date(2025, 6, 19),  # Juneteenth
    datetime.date(2025, 7, 4),   # Independence Day
    datetime.date(2025, 9, 1),   # Labor Day
    datetime.date(2025, 11, 27), # Thanksgiving
    datetime.date(2025, 12, 25), # Christmas
    datetime.date(2026, 1, 1),   # New Year's Day
    datetime.date(2026, 1, 19),  # MLK Day
    datetime.date(2026, 2, 16),  # Presidents Day
    datetime.date(2026, 4, 3),   # Good Friday
    datetime.date(2026, 5, 25),  # Memorial Day
    datetime.date(2026, 6, 19),  # Juneteenth
    datetime.date(2026, 7, 3),   # Independence Day (observed)
    datetime.date(2026, 9, 7),   # Labor Day
    datetime.date(2026, 11, 26), # Thanksgiving
    datetime.date(2026, 12, 25), # Christmas
}


def is_trading_day(date: datetime.date = None) -> bool:
    if date is None:
        date = TODAY
    if date.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    if date in US_HOLIDAYS_2025_2026:
        return False
    return True


def next_trading_day(from_date: datetime.date = None) -> datetime.date:
    if from_date is None:
        from_date = TODAY
    d = from_date + datetime.timedelta(days=1)
    while not is_trading_day(d):
        d += datetime.timedelta(days=1)
    return d


# ==============================================================================
# DATA DOWNLOAD
# ==============================================================================

def download_or_update_data(csv_path: Path) -> bool:
    """
    Try to download fresh SPY data via yfinance.
    Returns True if data is available (downloaded or already present).
    """
    try:
        import yfinance as yf
        log.log("Downloading latest SPY data from Yahoo Finance...", Fore.CYAN, 1)
        raw = yf.download("SPY", start="2010-01-01", auto_adjust=True, progress=False)
        if raw is None or len(raw) < 100:
            raise ValueError("No data returned")

        if isinstance(raw.columns, __import__('pandas').MultiIndex):
            raw.columns = raw.columns.get_level_values(0)

        raw = raw[["Open","High","Low","Close","Volume"]].dropna()
        raw.to_csv(csv_path)
        log.log(f"Downloaded {len(raw)} rows  "
                f"({raw.index[0].date()} to {raw.index[-1].date()})",
                Fore.GREEN, 1)
        return True

    except Exception as e:
        log.log(f"Live download failed: {e}", Fore.YELLOW, 1)
        if csv_path.exists():
            log.log("Using existing CSV file.", Fore.YELLOW, 1)
            return True
        else:
            log.log("No data available. Cannot continue.", Fore.RED, 1)
            return False


# ==============================================================================
# PAPER TRADING JOURNAL
# ==============================================================================

JOURNAL_HEADERS = [
    "date", "signal", "spy_price", "action",
    "position_open", "entry_price", "entry_date",
    "strategy_cell", "strategy_sharpe", "strategy_winrate",
    "vol_regime", "trend_regime",
    "exit_price", "exit_date", "pnl_pct", "pnl_status",
    "notes"
]


def load_journal() -> list:
    if not JOURNAL_FILE.exists():
        return []
    rows = []
    with open(JOURNAL_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def save_journal(rows: list):
    with open(JOURNAL_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=JOURNAL_HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def get_open_position(journal: list) -> dict:
    """Return the most recent open position, or None."""
    for row in reversed(journal):
        if row.get("pnl_status") == "OPEN":
            return row
    return None


def update_journal(journal: list, signal: str, spy_price: float,
                   cell_label: str, cell_sharpe: float, cell_winrate: float,
                   vol_desc: str, trend_desc: str) -> tuple:
    """
    Updates journal based on today's signal.
    Returns (updated_journal, action_taken, pnl_if_closed).
    """
    open_pos   = get_open_position(journal)
    action     = ""
    pnl_closed = None

    # -- Close logic --------------------------------------------------------
    if open_pos and signal != "LONG":
        # Close the open position
        entry_price = float(open_pos["entry_price"])
        pnl_pct     = (spy_price - entry_price) / entry_price * 100
        pnl_closed  = round(pnl_pct, 3)
        action      = f"EXIT  (P&L: {pnl_pct:+.2f}%)"

        # Update the open row
        for row in reversed(journal):
            if row.get("pnl_status") == "OPEN":
                row["exit_price"]  = f"{spy_price:.2f}"
                row["exit_date"]   = str(TODAY)
                row["pnl_pct"]     = f"{pnl_pct:+.3f}%"
                row["pnl_status"]  = "WIN" if pnl_pct > 0 else "LOSS"
                break

    # -- Open logic ---------------------------------------------------------
    if signal == "LONG" and (open_pos is None):
        action = "ENTER LONG"
        new_row = {
            "date":             str(TODAY),
            "signal":           signal,
            "spy_price":        f"{spy_price:.2f}",
            "action":           action,
            "position_open":    "YES",
            "entry_price":      f"{spy_price:.2f}",
            "entry_date":       str(TODAY),
            "strategy_cell":    cell_label,
            "strategy_sharpe":  f"{cell_sharpe:.3f}",
            "strategy_winrate": f"{cell_winrate:.1%}",
            "vol_regime":       vol_desc,
            "trend_regime":     trend_desc,
            "exit_price":       "",
            "exit_date":        "",
            "pnl_pct":          "",
            "pnl_status":       "OPEN",
            "notes":            "",
        }
        journal.append(new_row)

    elif signal == "LONG" and open_pos:
        action = "HOLD (already long)"
        # Log a monitoring row
        new_row = {
            "date":             str(TODAY),
            "signal":           signal,
            "spy_price":        f"{spy_price:.2f}",
            "action":           action,
            "position_open":    "YES",
            "entry_price":      open_pos["entry_price"],
            "entry_date":       open_pos["entry_date"],
            "strategy_cell":    cell_label,
            "strategy_sharpe":  f"{cell_sharpe:.3f}",
            "strategy_winrate": f"{cell_winrate:.1%}",
            "vol_regime":       vol_desc,
            "trend_regime":     trend_desc,
            "exit_price":       "",
            "exit_date":        "",
            "pnl_pct":          f"{(spy_price - float(open_pos['entry_price']))/float(open_pos['entry_price'])*100:+.3f}% (unrealised)",
            "pnl_status":       "OPEN",
            "notes":            "",
        }
        journal.append(new_row)

    else:
        # FLAT -- log a monitoring row
        if not action:
            action = "FLAT (no position)"
        new_row = {
            "date":             str(TODAY),
            "signal":           signal,
            "spy_price":        f"{spy_price:.2f}",
            "action":           action,
            "position_open":    "NO",
            "entry_price":      "",
            "entry_date":       "",
            "strategy_cell":    cell_label,
            "strategy_sharpe":  f"{cell_sharpe:.3f}",
            "strategy_winrate": f"{cell_winrate:.1%}",
            "vol_regime":       vol_desc,
            "trend_regime":     trend_desc,
            "exit_price":       "",
            "exit_date":        "",
            "pnl_pct":          "",
            "pnl_status":       "FLAT",
            "notes":            "",
        }
        journal.append(new_row)

    return journal, action, pnl_closed


def journal_stats(journal: list) -> dict:
    """Compute running stats from the journal."""
    closed = [r for r in journal if r.get("pnl_status") in ("WIN","LOSS")]
    if not closed:
        return {"trades": 0}

    pnls  = []
    for r in closed:
        try:
            pnls.append(float(r["pnl_pct"].replace("%","").replace("+","")))
        except Exception:
            pass

    wins       = [p for p in pnls if p > 0]
    losses     = [p for p in pnls if p <= 0]
    win_rate   = len(wins) / len(pnls) if pnls else 0
    avg_win    = sum(wins)   / len(wins)   if wins   else 0
    avg_loss   = sum(losses) / len(losses) if losses else 0
    total_pnl  = sum(pnls)

    # Running equity (compound)
    equity = 100.0
    for p in pnls:
        equity *= (1 + p/100)
    equity_return = equity - 100

    return {
        "trades":        len(pnls),
        "wins":          len(wins),
        "losses":        len(losses),
        "win_rate":      win_rate,
        "avg_win":       avg_win,
        "avg_loss":      avg_loss,
        "total_pnl":     total_pnl,
        "equity_return": equity_return,
    }


# ==============================================================================
# OOS TRACKER -- tracks monthly test results
# ==============================================================================

def load_oos_tracker() -> dict:
    if OOS_TRACKER_FILE.exists():
        with open(OOS_TRACKER_FILE) as f:
            return json.load(f)
    return {"months": [], "last_test_date": None, "last_evolve_date": None}


def save_oos_tracker(data: dict):
    with open(OOS_TRACKER_FILE, "w") as f:
        json.dump(data, f, indent=2)


def should_run_test(tracker: dict, force: bool = False) -> bool:
    if force:
        return True
    if tracker.get("last_test_date") is None:
        return True
    last = datetime.date.fromisoformat(tracker["last_test_date"])
    # Run if it's been 28+ days
    return (TODAY - last).days >= 28


def should_run_evolution(tracker: dict, force: bool = False) -> bool:
    if force:
        return True
    months = tracker.get("months", [])
    if len(months) < 2:
        return False
    # Re-evolve if last 2 months both had OOS% below 55
    last_two = [m["oos_pct"] for m in months[-2:]]
    return all(p < 55 for p in last_two)


# ==============================================================================
# MAIN MORNING ROUTINE
# ==============================================================================

def run_morning(args):
    log.sep()
    log.log("  QD TRADING SYSTEM -- Morning Routine", Fore.CYAN)
    log.log(f"  {NOW.strftime('%A, %B %d %Y  %H:%M')}", Fore.WHITE)
    log.sep()

    # -- 1. Market calendar check ---------------------------------------------
    log.log("")
    log.log("[STEP 1] Market calendar check", Fore.CYAN)

    if not is_trading_day(TODAY):
        if TODAY.weekday() == 5:
            reason = "Saturday"
        elif TODAY.weekday() == 6:
            reason = "Sunday"
        elif TODAY in US_HOLIDAYS_2025_2026:
            reason = "US market holiday"
        else:
            reason = "non-trading day"
        log.log(f"  Today ({TODAY}) is a {reason}.", Fore.YELLOW, 1)
        next_day = next_trading_day(TODAY)
        log.log(f"  Next trading day: {next_day}", Fore.YELLOW, 1)
        log.log("  No signal needed. Have a good day.", Fore.GREEN, 1)
        log.flush()
        return

    log.log(f"  Today is a trading day.", Fore.GREEN, 1)

    # -- 2. Data update -------------------------------------------------------
    log.log("")
    log.log("[STEP 2] Market data", Fore.CYAN)

    csv_path = Path(args.csv) if args.csv else CSV_FILE

    if args.csv and Path(args.csv).exists():
        log.log(f"  Using provided CSV: {args.csv}", Fore.GREEN, 1)
        data_ok = True
    else:
        data_ok = download_or_update_data(csv_path)

    if not data_ok:
        log.log("  FATAL: No market data. Cannot run morning routine.", Fore.RED, 1)
        log.flush()
        return

    # -- 3. Load archive ------------------------------------------------------
    log.log("")
    log.log("[STEP 3] Loading archive", Fore.CYAN)

    if not ARCHIVE_FILE.exists():
        log.log("  Archive not found. Run evolution first:", Fore.RED, 1)
        log.log("  python run_evolution.py --csv data/SPY.csv --generations 2000", Fore.WHITE, 2)
        log.flush()
        return

    from evolution.map_elites import MapElitesArchive
    archive = MapElitesArchive.load(str(ARCHIVE_FILE))
    s = archive.summary()
    log.log(f"  Archive: {s['n_filled']}/100 niches  "
            f"Best Sharpe={s['max_fitness']}  "
            f"Mean={s['mean_fitness']}", Fore.GREEN, 1)

    # -- 4. Compute signal ----------------------------------------------------
    log.log("")
    log.log("[STEP 4] Computing today's signal", Fore.CYAN)

    import numpy as np
    from data.csv_loader import load_csv
    from router.live_router import LiveRouter

    df_raw = load_csv(str(csv_path))
    router = LiveRouter(archive, df_raw)
    df     = router.df   # already has indicators added

    # Regime
    bd1, bd2     = router.current_regime()
    vol_b, tr_b  = router.regime_buckets()
    vol_desc     = vol_b.upper()
    trend_desc   = tr_b.upper()

    # Route using the new regime-aware logic
    cell    = router.get_best_strategy()
    cell_i, cell_j = 0, 0
    for i in range(archive.grid_size):
        for j in range(archive.grid_size):
            if archive.grid[i][j] is cell:
                cell_i, cell_j = i, j
                break

    # Determine routing label
    from config import GENOME_BOUNDS
    prefs   = router.REGIME_PREFERENCES.get((vol_b, tr_b), None)
    routing = "REGIME-MAPPED"
    if prefs:
        bd1_cell = (cell_i + 0.5) / archive.grid_size
        bd2_cell = (cell_j + 0.5) / archive.grid_size
        in_pref  = (prefs[0] <= bd1_cell <= prefs[1] and
                    prefs[2] <= bd2_cell <= prefs[3])
        routing  = "REGIME-MAPPED" if in_pref else "EXPANDED SEARCH"

    params     = cell.genome.decode()
    from strategies.signal_generator import generate_signals
    signals    = generate_signals(df, params)
    raw_signal = float(signals.iloc[-1])
    spy_price  = float(df["Close"].iloc[-1])
    cell_label = f"V{cell_i}/T{cell_j}"

    if raw_signal > 0:
        signal_str, signal_color = "LONG",      Fore.GREEN
    elif raw_signal < 0:
        signal_str, signal_color = "FLAT/EXIT", Fore.RED
    else:
        signal_str, signal_color = "FLAT",      Fore.YELLOW

    log.log(f"  Regime  : Vol={vol_desc} ({bd1:.2f})  Trend={trend_desc} ({bd2:.2f})", Fore.WHITE, 1)
    log.log(f"  Routing : {routing} -> {cell_label}", Fore.WHITE, 1)
    log.log(f"  Why     : {vol_b} vol + {tr_b} -> prefers BD1={prefs[0]:.1f}-{prefs[1]:.1f}  BD2={prefs[2]:.1f}-{prefs[3]:.1f}" if prefs else "  Why     : fallback", Fore.WHITE, 1)
    log.log(f"  Strategy: Sharpe={cell.fitness:.3f}  WinRate={cell.win_rate:.1%}  Trades={cell.n_trades}", Fore.WHITE, 1)
    log.log(f"  Params  : EMA({params['fast_ma']:.0f}/{params['slow_ma']:.0f})  "
            f"RSI({params['rsi_period']:.0f})  "
            f"Stop={params['stop_loss']*100:.1f}%  "
            f"Take={params['take_profit']*100:.1f}%", Fore.WHITE, 1)
    log.log(f"  Weights : MA={params['weights'][0]:.2f}  RSI={params['weights'][1]:.2f}  "
            f"MACD={params['weights'][2]:.2f}  BB={params['weights'][3]:.2f}", Fore.WHITE, 1)
    log.log("")
    log.log(f"  SPY CLOSE  : ${spy_price:.2f}", Fore.WHITE, 1)
    log.log(f"  SIGNAL     : {signal_str}", signal_color, 1)

    # Cap position size at 80% regardless of genome value
    MAX_POS = 0.80
    actual_pos_pct = min(params["position_size"], MAX_POS) * 100

    action_text = {
        "LONG":      f"Buy/Hold SPY at {actual_pos_pct:.0f}% position size",
        "FLAT/EXIT":  "Exit any existing long. Hold cash.",
        "FLAT":       "No position. Hold cash.",
    }.get(signal_str, "")
    log.log(f"  ACTION     : {action_text}", signal_color, 1)

    # Warn if genome wanted more than 80%
    if params["position_size"] > MAX_POS and signal_str == "LONG":
        log.log(f"  NOTE       : Genome position={params['position_size']*100:.0f}% capped at {MAX_POS*100:.0f}%.", Fore.YELLOW, 1)

    # Warn if stop-loss is too tight for real execution
    if params["stop_loss"] < 0.015 and signal_str == "LONG":
        log.log(f"  WARNING    : Stop={params['stop_loss']*100:.1f}% is tight for live trading.", Fore.YELLOW, 1)
        log.log(f"             : Paper trade only. Re-evolve with stop_loss min 0.015 in config.", Fore.YELLOW, 1)

    # -- 5. Paper trading journal update --------------------------------------
    log.log("")
    log.log("[STEP 5] Paper trading journal", Fore.CYAN)

    journal = load_journal()
    journal, action_taken, pnl_closed = update_journal(
        journal, signal_str, spy_price,
        cell_label, cell.fitness, cell.win_rate,
        vol_desc, trend_desc
    )
    save_journal(journal)

    stats = journal_stats(journal)
    open_pos = get_open_position(journal)

    if pnl_closed is not None:
        result_color = Fore.GREEN if pnl_closed > 0 else Fore.RED
        log.log(f"  Trade closed: P&L = {pnl_closed:+.2f}%", result_color, 1)

    log.log(f"  Action recorded: {action_taken}", Fore.WHITE, 1)

    if open_pos:
        entry = float(open_pos["entry_price"])
        unrealised = (spy_price - entry) / entry * 100
        days_held  = (TODAY - datetime.date.fromisoformat(open_pos["entry_date"])).days
        u_color    = Fore.GREEN if unrealised > 0 else Fore.RED
        log.log(f"  Open position : Entered ${entry:.2f} on {open_pos['entry_date']} "
                f"({days_held} days)", Fore.WHITE, 1)
        log.log(f"  Unrealised P&L: {unrealised:+.2f}%", u_color, 1)

    if stats.get("trades", 0) > 0:
        wr_color = Fore.GREEN if stats["win_rate"] >= 0.5 else Fore.RED
        eq_color = Fore.GREEN if stats["equity_return"] > 0 else Fore.RED
        log.log(f"  --- Running stats ({stats['trades']} closed trades) ---", Fore.WHITE, 1)
        log.log(f"  Win rate        : {stats['win_rate']:.1%}  "
                f"({stats['wins']}W / {stats['losses']}L)", wr_color, 1)
        log.log(f"  Avg win / loss  : {stats['avg_win']:+.2f}% / {stats['avg_loss']:+.2f}%", Fore.WHITE, 1)
        log.log(f"  Total P&L       : {stats['total_pnl']:+.2f}%", eq_color, 1)
        log.log(f"  Equity return   : {stats['equity_return']:+.2f}%", eq_color, 1)
        log.log(f"  Journal file    : {JOURNAL_FILE}", Fore.WHITE, 1)

    # -- 6. Monthly test suite -------------------------------------------------
    log.log("")
    log.log("[STEP 6] Monthly health check", Fore.CYAN)

    tracker = load_oos_tracker()
    run_test = should_run_test(tracker, force=args.force_test)

    # Also run on first trading day of month
    if TODAY.day <= 3 and not should_run_test(tracker):
        first_of_month = TODAY.replace(day=1)
        last_test      = datetime.date.fromisoformat(tracker["last_test_date"]) if tracker.get("last_test_date") else None
        if last_test and last_test.month < TODAY.month:
            run_test = True

    if run_test:
        log.log("  Running full test suite (this takes ~5 minutes)...", Fore.YELLOW, 1)
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "test_suite.py", "--csv", str(csv_path), "--fast"],
                capture_output=True, text=True, timeout=600, cwd=str(BASE_DIR),
                encoding="utf-8", errors="replace"
            )
            # Combine stdout and stderr -- Windows sometimes mixes them
            output = (result.stdout or "") + (result.stderr or "")

            # Always save raw output so we can inspect if parsing fails
            raw_log = LOG_DIR / f"test_raw_{TODAY}.txt"
            with open(raw_log, "w", encoding="utf-8", errors="replace") as f:
                f.write(f"returncode: {result.returncode}\n")
                f.write(f"stdout:\n{result.stdout}\n")
                f.write(f"stderr:\n{result.stderr}\n")

            # Extract OOS% -- try multiple patterns for robustness
            oos_pct = None
            for line in output.split("\n"):
                if "Positive OOS Sharpe" in line and "(" in line:
                    try:
                        pct_str = line.split("(")[1].split("%")[0].strip()
                        oos_pct = float(pct_str)
                        break
                    except Exception:
                        pass
                # Fallback pattern: "75.0% strategies positive"
                if "strategies positive" in line or "strategies remain" in line:
                    import re
                    m = re.search(r"(\d+\.?\d*)%", line)
                    if m:
                        try:
                            oos_pct = float(m.group(1))
                            break
                        except Exception:
                            pass

            if oos_pct is None and result.returncode != 0:
                log.log(f"  Test suite failed (exit {result.returncode}). See: {raw_log}", Fore.RED, 1)
            elif oos_pct is None:
                log.log(f"  Test ran but OOS% not found. Raw output: {raw_log}", Fore.YELLOW, 1)

            if oos_pct is not None:
                tracker["months"].append({
                    "date":    str(TODAY),
                    "oos_pct": oos_pct,
                })
                tracker["last_test_date"] = str(TODAY)
                save_oos_tracker(tracker)

                oos_color = Fore.GREEN if oos_pct >= 65 else (Fore.YELLOW if oos_pct >= 55 else Fore.RED)
                log.log(f"  OOS positive: {oos_pct:.1f}%", oos_color, 1)

                if oos_pct >= 65:
                    log.log("  System is healthy. Strategies generalising well.", Fore.GREEN, 1)
                elif oos_pct >= 55:
                    log.log("  System OK. Watch next month -- if below 55% again, re-evolve.", Fore.YELLOW, 1)
                else:
                    log.log("  WARNING: OOS% below threshold.", Fore.RED, 1)

                # Save test output to log
                test_log = LOG_DIR / f"test_{TODAY}.txt"
                with open(test_log, "w") as f:
                    f.write(output)
                log.log(f"  Full test output saved: {test_log}", Fore.WHITE, 1)
            else:
                log.log("  Test ran but could not parse OOS%. Check logs.", Fore.YELLOW, 1)

        except subprocess.TimeoutExpired:
            log.log("  Test suite timed out (>10 min). Try running manually.", Fore.RED, 1)
        except Exception as e:
            log.log(f"  Test suite error: {e}", Fore.RED, 1)
    else:
        if tracker.get("last_test_date"):
            days_since = (TODAY - datetime.date.fromisoformat(tracker["last_test_date"])).days
            log.log(f"  Last test was {days_since} days ago. Next test in {28-days_since} days.", Fore.WHITE, 1)
        else:
            log.log("  No test run yet. Will run in first monthly check.", Fore.WHITE, 1)

    # -- 7. Evolution check ----------------------------------------------------
    log.log("")
    log.log("[STEP 7] Evolution check", Fore.CYAN)

    run_evo = should_run_evolution(tracker, force=args.force_evolve)

    if run_evo:
        log.log("  OOS% below 55% for 2 consecutive months. Re-evolving...", Fore.YELLOW, 1)
        log.log("  Running 1000 new generations (this takes ~30 minutes)...", Fore.YELLOW, 1)
        try:
            import subprocess
            # Backup current archive first
            import shutil
            backup = OUTPUT_DIR / f"archive_backup_{TODAY}.json"
            if ARCHIVE_FILE.exists():
                shutil.copy(str(ARCHIVE_FILE), str(backup))
                log.log(f"  Archive backed up to: {backup.name}", Fore.WHITE, 1)

            result = subprocess.run(
                [sys.executable, "run_evolution.py",
                 "--csv", str(csv_path),
                 "--generations", "1000",
                 "--resume"],
                capture_output=True, text=True, timeout=3600, cwd=str(BASE_DIR)
            )
            if result.returncode == 0:
                tracker["last_evolve_date"] = str(TODAY)
                save_oos_tracker(tracker)
                log.log("  Evolution complete. Archive updated.", Fore.GREEN, 1)
            else:
                log.log(f"  Evolution error: {result.stderr[-200:]}", Fore.RED, 1)
        except Exception as e:
            log.log(f"  Evolution error: {e}", Fore.RED, 1)
    elif args.force_evolve:
        pass  # handled above
    else:
        months = tracker.get("months", [])
        if months:
            last_oos = months[-1]["oos_pct"]
            oos_color = Fore.GREEN if last_oos >= 65 else Fore.YELLOW
            log.log(f"  No re-evolution needed. Last OOS%: {last_oos:.1f}%", oos_color, 1)
        else:
            log.log("  No evolution history yet. Evolution check will activate after first monthly test.", Fore.WHITE, 1)

    # -- 8. Final summary ------------------------------------------------------
    log.log("")
    log.sep()
    log.log("  MORNING ROUTINE COMPLETE", Fore.CYAN)
    log.sep()
    log.log("")
    log.log(f"  Date      : {TODAY}", Fore.WHITE)
    log.log(f"  SPY Close : ${spy_price:.2f}", Fore.WHITE)
    log.log(f"  Regime    : Vol={vol_desc}  Trend={trend_desc}", Fore.WHITE)

    sig_c = Fore.GREEN if signal_str == "LONG" else (Fore.RED if "EXIT" in signal_str else Fore.YELLOW)
    log.log(f"  SIGNAL    : {signal_str}", sig_c)
    log.log(f"  ACTION    : {action_text}", sig_c)
    log.log("")

    if stats.get("trades", 0) > 0:
        eq_c = Fore.GREEN if stats["equity_return"] > 0 else Fore.RED
        log.log(f"  Paper trading: {stats['trades']} trades  "
                f"Win={stats['win_rate']:.0%}  "
                f"Return={stats['equity_return']:+.1f}%", eq_c)

    log.log(f"  Journal   : {JOURNAL_FILE}", Fore.WHITE)
    log.log(f"  Full log  : {DAILY_LOG_FILE}", Fore.WHITE)
    log.log("")

    # Save human-readable summary
    summary_lines = [
        f"QD TRADING SYSTEM - Daily Summary",
        f"Date: {TODAY}  Time: {NOW.strftime('%H:%M')}",
        f"",
        f"SPY Close   : ${spy_price:.2f}",
        f"Regime      : Vol={vol_desc} ({bd1:.2f})  Trend={trend_desc} ({bd2:.2f})",
        f"Strategy    : {cell_label}  Sharpe={cell.fitness:.3f}",
        f"",
        f"SIGNAL      : {signal_str}",
        f"ACTION      : {action_text}",
        f"",
        f"Paper Trading Stats:",
    ]
    if stats.get("trades", 0) > 0:
        summary_lines += [
            f"  Closed trades : {stats['trades']}",
            f"  Win rate      : {stats['win_rate']:.1%} ({stats['wins']}W/{stats['losses']}L)",
            f"  Avg win       : {stats['avg_win']:+.2f}%",
            f"  Avg loss      : {stats['avg_loss']:+.2f}%",
            f"  Total equity  : {stats['equity_return']:+.2f}%",
        ]
    else:
        summary_lines.append("  No closed trades yet.")

    if open_pos:
        unrealised = (spy_price - float(open_pos["entry_price"])) / float(open_pos["entry_price"]) * 100
        summary_lines += [
            f"",
            f"Open Position:",
            f"  Entry  : ${open_pos['entry_price']} on {open_pos['entry_date']}",
            f"  Current: ${spy_price:.2f}  ({unrealised:+.2f}% unrealised)",
        ]

    summary_lines += [
        f"",
        f"Files:",
        f"  Journal : {JOURNAL_FILE}",
        f"  Log     : {DAILY_LOG_FILE}",
    ]

    with open(SUMMARY_FILE, "w") as f:
        f.write("\n".join(summary_lines))

    log.log(f"  Summary saved: {SUMMARY_FILE}", Fore.WHITE)
    log.log("")

    log.flush()


# ==============================================================================
# ENTRY POINT
# ==============================================================================

def parse_args():
    p = argparse.ArgumentParser(description="QD Trading -- Morning Routine")
    p.add_argument("--csv",           default=None,
                   help="Use existing CSV file (skip download)")
    p.add_argument("--force-test",    action="store_true",
                   help="Force run full test suite today")
    p.add_argument("--force-evolve",  action="store_true",
                   help="Force run 1000 new evolution generations")
    return p.parse_args()


if __name__ == "__main__":
    try:
        args = parse_args()
        run_morning(args)
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n  Interrupted.")
    except Exception as e:
        print(Fore.RED + f"\n  FATAL ERROR: {e}")
        traceback.print_exc()
        log.log(f"FATAL ERROR: {e}", Fore.RED)
        log.flush()