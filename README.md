# QD Trading System
## Quality Diversity MAP-Elites for Autonomous Strategy Discovery

A trading system that **finds its own algorithms** using Quality Diversity evolution.
No reward function defined by humans. No LLM-generated code.
The system discovers and maintains a diverse library of strategies — one per market regime.

---

## Why this is different from RL

| Property | RL | This system |
|---|---|---|
| Fitness defined by | Human (reward function) | Itself (archive pressure) |
| Output | One best strategy | 100 strategies, one per regime |
| When environment changes | Must retrain | Routes to existing strategy |
| Reward hacking | Constant risk | No fixed reward to hack |
| Robustness | Brittle | Built-in fallbacks |

---

## Architecture

```
qd_trading/
├── config.py                   # All parameters
├── run_evolution.py            # Main evolution loop
├── inspect_archive.py          # Inspect + route with saved archive
│
├── data/
│   └── fetcher.py              # yfinance download + disk cache
│
├── strategies/
│   ├── indicators.py           # SMA, EMA, RSI, MACD, BB, ATR, ADX
│   └── signal_generator.py    # Genome → buy/sell signals
│
├── evolution/
│   ├── genome.py               # StrategyGenome + mutation/crossover
│   ├── evaluator.py            # Vectorised backtester + BD computation
│   └── map_elites.py           # MAP-Elites archive (10×10 grid)
│
├── metrics/
│   ├── fitness.py              # Sharpe, Calmar, Sortino, drawdown
│   └── tracker.py              # CSV logging per generation
│
├── router/
│   └── live_router.py          # Detect regime → route to best strategy
│
└── visualization/
    └── dashboard.py            # Heatmaps, equity curves, evolution plots
```

---

## How it works

### The genome
Each strategy is a vector of 22 normalised floats [0,1].
These decode to real parameters: MA periods, RSI thresholds,
MACD settings, stop-loss, take-profit, signal weights.

No code is generated. The genome controls parameters of
a fixed, verified signal framework.

### Behavioral descriptors
Every strategy is characterised by two numbers:
- **BD1** = the average volatility percentile of days it trades
- **BD2** = the average trend strength percentile of days it trades

These tell us: *what market conditions does this strategy operate in?*

### The archive
A 10×10 grid = 100 cells.
Each cell keeps the single best strategy for its (volatility, trend) niche.
Strategies compete within cells only — not across the whole archive.

### The evolution loop
```
for each generation:
    1. Pick a random elite from the archive
    2. Mutate (gaussian noise in gene space)
    3. Backtest on historical data
    4. Compute fitness (Sharpe ratio) and BDs
    5. Place in archive if better than current occupant
```

No external reward function. Filling empty cells IS the pressure.

### Live routing
```python
router = LiveRouter(archive, current_data)
signal = router.get_signal()  # +1 long, -1 short, 0 flat
```
The router detects today's volatility and trend regime,
looks up the best strategy for that regime, and returns its signal.

---

## Quick start

```bash
# Install dependencies
pip install -r requirements.txt

# Run evolution (downloads data automatically)
python run_evolution.py

# Run for more generations
python run_evolution.py --generations 1000

# Resume from saved archive
python run_evolution.py --resume --generations 500

# Inspect results
python inspect_archive.py
```

---

## Outputs

```
output/
├── archive.json          # Saved archive (all strategies)
├── metrics.csv           # Per-generation statistics
└── plots/
    ├── archive_gen*.png  # Archive heatmaps
    ├── evolution_curves.png
    └── top_strategies.png
```

---

## Key metrics

- **Coverage** — what % of the 100 niches are filled
- **QD-Score** — sum of all fitness values (grows as both quality and diversity improve)
- **Max Fitness** — best single strategy found (comparable to RL output)
- **Improvements** — how many times a cell was upgraded (proof of genuine improvement)

QD-Score is the key number. Unlike RL's single fitness value, it grows
every time ANY niche improves — rewarding breadth, not just peak performance.

---

## What the system discovers

After ~500 generations you'll see something like:

```
  Budget volatile markets    → short-term momentum strategy
  Calm trending markets      → slow MA crossover strategy  
  Ranging low-vol markets    → RSI mean-reversion strategy
  Explosive breakout regimes → Bollinger Band breakout strategy
```

Nobody defined these categories. The system found them.
