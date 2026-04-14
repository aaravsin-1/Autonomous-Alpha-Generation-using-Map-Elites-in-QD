import sys
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