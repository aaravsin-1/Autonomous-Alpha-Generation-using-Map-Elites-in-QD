Phase 2 — Operation, Observation, Incremental Improvement

Part 1 — Daily paper trading (start today)
What paper trading means: You follow the system's signals but use fake money. You record every trade you would have made. After 3-6 months you have real evidence about whether the system works going forward — not just in backtests.
Your daily routine — takes 5 minutes:
Every morning before markets open (or the evening before):
powershellpython inspect_archive.py --csv data/SPY.csv
Look at one line in the output:
Current regime → cell V5/T0
Best strategy fitness=+1.341  win_rate=57.8%
The system is telling you which strategy is most appropriate for today's market conditions. Then check what signal that strategy would give. To get the actual signal add this to the bottom of your daily check — create a new file called daily_signal.py:
pythonimport sys
sys.path.insert(0, '.')

from data.csv_loader import load_csv
from strategies.indicators import add_all_indicators
from strategies.signal_generator import generate_signals
from evolution.map_elites import MapElitesArchive

archive = MapElitesArchive.load("output/archive.json")
df_raw  = load_csv("data/SPY.csv")
df      = add_all_indicators(df_raw)

# Get best strategy for current conditions
bd1 = float(df["vol_pct"].iloc[-1]) if "vol_pct" in df.columns else 0.5
bd2 = float(df["adx_pct"].iloc[-1]) if "adx_pct" in df.columns else 0.5

cell   = archive.get_best_for_regime(bd1, bd2)
params = cell.genome.decode()
signals = generate_signals(df, params)

today  = df.index[-1]
signal = signals.iloc[-1]

print(f"\nDate:     {today.date()}")
print(f"Signal:   {'+1 LONG' if signal > 0 else ('-1 SHORT/FLAT' if signal < 0 else '0 FLAT')}")
print(f"Strategy: Sharpe {cell.fitness:.3f}  WinRate {cell.win_rate:.1%}")
print(f"Regime:   Vol={bd1:.2f}  Trend={bd2:.2f}")

p = params
print(f"Params:   EMA({p['fast_ma']:.0f}/{p['slow_ma']:.0f})  "
      f"RSI({p['rsi_period']:.0f})  "
      f"Stop={p['stop_loss']*100:.1f}%  "
      f"Take={p['take_profit']*100:.1f}%")
Run it:
powershellpython daily_signal.py
Your paper trading journal — keep a simple spreadsheet:
DateSignalStrategy CellEntry PriceExit PriceP&L %Notes2026-04-14LONGV5/T0543.21——Entered2026-04-18FLATV5/T0—551.40+1.51%Exited — stop hit
Update it every day you have an open position or a new signal. After 90 days you'll have a real track record.
Rules for paper trading:

Only trade the top 3 strategies — V5/T0, V6/T0, V4/T0
When the system says FLAT — you are out of the market, holding cash
When the system says LONG — you are 61% invested (the position_size parameter)
Never override the signal based on your own opinion — that defeats the purpose
If the routing falls to a cell with fitness below 0 — treat that as FLAT


Part 2 — Fix the routing fallback (one code change)
Right now when the system lands in an empty or bad cell it finds the geometrically nearest cell. That's why you got routed to V8/T8 with -0.354 fitness. The fix is to always fall back to the best strategy in the T0 column — which is consistently your strongest region.
Open router/live_router.py and find the get_best_strategy method. Replace it with this:
pythondef get_best_strategy(self):
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
This single change means when conditions are unusual or the archive has no good match, it defaults to your best overall strategy rather than a bad nearby one. Run the test suite after this change — the routing Sharpe should improve significantly.

Part 3 — Monthly review process
On the first of every month, run these three commands:
powershell# 1. Update your data first
#    Go to Yahoo Finance, download fresh SPY.csv, replace the old one

# 2. Check how the archive performs on the new month of data
python test_suite.py --csv data/SPY.csv

# 3. Check today's signal
python daily_signal.py
What to look for in the monthly test suite:
Track these three numbers in a spreadsheet month by month:
Month       OOS%    Best OOS Sharpe    Mean Degradation
Apr 2026     75%         0.482             -0.020
May 2026     ??%          ??               ??
Jun 2026     ??%          ??               ??
If OOS% stays above 65% — the system is holding up. Keep going as-is.
If OOS% drops below 55% for two consecutive months — the market has changed enough that a re-evolution is warranted. Run:
powershellpython run_evolution.py --csv data/SPY.csv --generations 3000
If OOS% is climbing month over month — the system is getting stronger as more data accumulates. Leave it alone.
When to re-evolve vs when to leave it:
Re-evolve when:

OOS% drops below 55% for two months in a row
A major market structure change happens (new Fed policy regime, major index rebalancing)
You have a full new year of data and want to retrain with the extended history

Do NOT re-evolve just because one month is bad. One bad month is noise. Two consecutive bad months is signal.

Part 4 — QQQ expansion (do this once, then monthly)
Download QQQ data from Yahoo Finance the same way you got SPY. Save it as data/QQQ.csv.
Run a fresh evolution:
powershellpython run_evolution.py --csv data/QQQ.csv --generations 3000
This creates a separate archive for QQQ. Save it separately:
powershellcopy output\archive.json output\archive_qqq.json
Then compare the two routing tables side by side:
powershell# Check SPY archive
copy output\archive_sharpe_5000.json output\archive.json
python inspect_archive.py --csv data/SPY.csv

# Check QQQ archive  
copy output\archive_qqq.json output\archive.json
python inspect_archive.py --csv data/QQQ.csv
What to look for in the comparison:
If both SPY and QQQ archives show LONG signal on the same day — that's a high-confidence signal. Two independent systems trained on different instruments agreeing is stronger evidence than either alone.
If they disagree — SPY says LONG, QQQ says FLAT — reduce position size to half. The disagreement means uncertainty.
If both say FLAT — stay out entirely.
This two-archive confirmation is one of the most practical improvements you can make without rebuilding anything.

Part 5 — The 6-month statistical significance check
In October 2026 — exactly 6 months from now — run:
powershellpython test_suite.py --csv data/SPY.csv
By then you'll have approximately 4.5 years of out-of-sample data. The Monte Carlo confidence intervals will have narrowed enough that statistical significance becomes achievable. Look at the p-values — if any strategy shows p-value below 0.05, you have the first statistically rigorous confirmation that the signal is real.
Keep a record of p-values each month:
Month       Best p-value    Significant?
Apr 2026      0.054            No
May 2026       ??              ??
Oct 2026       ??              ??

Part 6 — What genuine improvement looks like over 12 months
Here's what success looks like if the system is working:
3 months (July 2026)

Paper trading journal shows positive P&L on at least 55% of completed trades
OOS% holding above 65% in monthly test suite
QQQ archive built and showing corroborating signals

6 months (October 2026)

First Monte Carlo p-values approaching significance (below 0.10)
Enough paper trading data to calculate your own real forward Sharpe ratio
Decision point — if paper trading Sharpe is above 0.5 and MC approaching significance, consider allocating a very small real amount (1-2% of what you'd eventually want to trade)

12 months (April 2027)

Full year of forward data
Re-evolve with the full 2010-2026 dataset as training, use 2027 as new test year
Statistical significance likely achievable
Real track record to evaluate against


The complete daily workflow in one place
Every morning (2 minutes):
  python daily_signal.py
  → Record signal in journal
  → If signal changed from yesterday, note entry/exit price

First of every month (10 minutes):
  → Download fresh SPY.csv from Yahoo Finance
  → python test_suite.py --csv data/SPY.csv
  → Record OOS%, best OOS Sharpe, mean degradation
  → Compare to last month

Every 3 months (30 minutes):
  → Review paper trading journal P&L
  → If OOS% declining, consider re-evolution
  → Run QQQ comparison for confirmation signals

At 6 months:
  → Check Monte Carlo p-values
  → Make decision about real capital allocation

At 12 months:
  → Full re-evolution with extended dataset
  → Compare new archive to original
  → Evaluate whether the system has improved with more data
That's the complete operational plan. The system is done being built. Everything from here is running it, watching it, and making small targeted adjustments based on what the data tells you.