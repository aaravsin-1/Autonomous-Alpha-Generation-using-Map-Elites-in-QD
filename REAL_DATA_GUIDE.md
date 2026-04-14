# How to Test on Real Data — Complete Guide

## Why the synthetic tests failed (and why that's correct)

When you run the test suite on synthetic data, it produces 0/4 failures. This is
not a bug — it is the test suite doing exactly what it should.

Here's what was actually discovered:

```
Regime distribution in training data (2010-2022):
  bull    50.8%
  choppy  26.4%
  bear    19.9%
  ranging  2.9%

Regime distribution in test data (2023-2027):
  bull    59.3%
  ranging 40.7%
  choppy   0.0%
  bear     0.0%
```

The training data had significant choppy and bear markets. The strategies evolved
to profit from those conditions. The test period has none of those conditions —
it is entirely bull and ranging. Of course the strategies fail.

This is called **regime shift**. It is the most common real-world failure mode
for trading strategies. Real markets are more consistent over long periods because
they are driven by persistent structural forces (economic cycles, institutional
behaviour, earnings patterns). Synthetic data has no such persistence — the next
generated "bear market" is completely statistically independent from the last one.

**What this means:** Synthetic data is sufficient to build and debug the system.
It is not sufficient to validate it. For that you need real market data.

---

## Step 1 — Download real data

**Option A — Yahoo Finance (free, manual)**
1. Go to https://finance.yahoo.com/quote/SPY/history/
2. Set date range: 2010-01-01 to today
3. Click Download CSV
4. Save as `qd_trading/data/SPY.csv`

Also useful to download:
- QQQ (tech-heavy, higher volatility)
- IWM (small-cap, different regime behaviour)
- GLD (gold, low correlation to equities)

**Option B — Python download (if your machine has internet)**
```python
import yfinance as yf
df = yf.download("SPY", start="2010-01-01", auto_adjust=True)
df.to_csv("data/SPY.csv")
```

**What the CSV should look like:**
```
Date,Open,High,Low,Close,Adj Close,Volume
2010-01-04,113.33,113.71,112.65,113.71,88.91,103944600
2010-01-05,113.63,114.38,113.38,114.38,89.43,104798700
...
```

---

## Step 2 — Run evolution on real data

```bash
# Basic run (recommended starting point)
python run_evolution.py --csv data/SPY.csv --generations 2000

# More thorough run
python run_evolution.py --csv data/SPY.csv --generations 5000 --seed 300

# Resume if interrupted
python run_evolution.py --csv data/SPY.csv --generations 3000 --resume
```

**What to watch during evolution:**
- Coverage should reach 50-75% by generation 2000
- QD-Score should be clearly positive (>10) by generation 1000
- Best Sharpe should stabilise above 0.8
- Mean Sharpe should cross zero and stay positive

**Red flags — stop and adjust if you see these:**
- Best Sharpe > 3.0 at generation 500 → likely overfit, increase sigma
- Coverage stuck below 20% → reduce MIN_TRADES in config.py
- QD-Score never goes positive → market data may have issues

---

## Step 3 — Run the full test suite

```bash
# Full test (takes 5-15 minutes on real data)
python test_suite.py --csv data/SPY.csv

# Quick test (3 MC permutations, 3 WF windows)
python test_suite.py --csv data/SPY.csv --fast
```

---

## What passing results look like on real SPY data

Based on known QD performance characteristics and real market research, you
should expect results in this range after a clean evolution:

**Test 1 — Out-of-Sample**
```
Positive OOS Sharpe  : 55-70%    (target: ≥60%)
Mean train Sharpe    : +0.6-1.2
Mean test  Sharpe    : +0.1-0.5  (some degradation is normal)
Mean degradation     : 0.3-0.8   (target: <1.0)
```

**Test 2 — Benchmarks**
```
QD Best Sharpe should beat:
  Buy & Hold (historically ~0.6-0.8 on SPY)
  MA 50/200  (historically ~0.4-0.7 on SPY)
```

**Test 3 — Monte Carlo**
```
Significant strategies: 3-5 of top 5   (target: ≥3)
p-values:               0.01-0.04       (target: <0.05)
```

**Test 4 — Walk-Forward**
```
Pass rate:          3-5 of 5 windows   (target: ≥3)
Mean degradation:   0.3-0.9            (target: <1.5)
Verdict:            ROBUST
```

---

## Interpreting the routing table on real data

After evolution on SPY, the routing table will look something like this:

```
      T0    T1    T2    T3    T4    T5    T6    T7    T8    T9
      ← tight stop                                  wide stop →

V0  +0.82 +0.61 +0.44 +0.21  --    --    --    --    --    --
V1  +0.91 +0.78 +0.55 +0.33 +0.11  --    --    --    --    --
V2  +1.12 +0.94 +0.71 +0.52 +0.28 +0.05  --    --    --    --
V3  +1.34 +1.18 +0.87 +0.61 +0.41 +0.18  --    --    --    --   ← mid-momentum
V4  +1.45 +1.22 +0.95 +0.71 +0.49 +0.22 +0.04  --    --    --
V5  +1.31 +1.15 +0.82 +0.58 +0.38 +0.19  --    --    --    --
V6  +0.89 +0.74 +0.52 +0.31 +0.11  --    --    --    --    --
V7  +0.44 +0.28 +0.12  --    --    --    --    --    --    --
V8    --  +0.09  --    --    --    --    --    --    --    --
V9    --    --    --    --    --    --    --    --    --    --
↑ pure           ↑ balanced           pure
mean-rev                              momentum
```

**Reading this table on real data:**
- Best performance typically at V3-V5, T0-T2 (balanced momentum, tight stops)
- Right side empties out — wide stops consistently underperform on equities
- Bottom rows empty — pure momentum strategies with no mean-reversion tend to fail
- The table reveals the structure of what actually works in real markets

---

## Running with different instruments

The system works on any liquid instrument with OHLCV data:

```bash
# US equities
python run_evolution.py --csv data/QQQ.csv   # tech-heavy
python run_evolution.py --csv data/IWM.csv   # small-cap

# Run on multiple instruments, combine archives
python run_evolution.py --csv data/SPY.csv --generations 2000
python inspect_archive.py --csv data/SPY.csv   # see results
```

**Which instruments work best:**
- SPY: best starting point (most liquid, cleanest data)
- QQQ: higher volatility = more extreme strategies survive
- GLD: completely different regime structure (safe haven dynamics)
- BTC: extremely high volatility, strategies will look very different

---

## Tuning for real data

If evolution is slow to find good strategies, adjust `config.py`:

```python
# More aggressive exploration
MUTATION_SIGMA   = 0.20     # default 0.15 — increase for more diversity
POPULATION_SEED  = 300      # more initial random strategies

# Accept more strategies (if coverage is stuck low)
MIN_TRADES       = 8        # default 10

# Better fitness for real markets
FITNESS_METRIC   = "calmar"  # calmar handles drawdown better than sharpe
                             # for long-only equity strategies
```

---

## Common issues with real data

**"No data returned for SPY"**
Download manually from Yahoo Finance and use `--csv data/SPY.csv`

**Coverage stuck below 20% after 1000 generations**
Lower MIN_TRADES to 8, or increase MUTATION_SIGMA to 0.20

**Best Sharpe above 3.0 early on**
This is overfit. Increase MUTATION_SIGMA, reduce MAX_GENERATIONS, or
check that transaction costs are set realistically (0.001 = 0.1% per trade)

**Walk-forward consistently failing**
This usually means the market structure changed significantly between
your training windows. Try using a shorter train_years=3 in the
walk_forward.py call, or run with more generations per window.
