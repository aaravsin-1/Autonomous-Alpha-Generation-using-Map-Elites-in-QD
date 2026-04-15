# NSE Production Setup Guide
## From Paper Trading to Live NSE Execution

---

## The Architecture

```
Yahoo Finance / Broker API
         ↓
   NIFTYBEES.csv  (your price data)
         ↓
   add_all_indicators()  (RSI, MACD, EMA, ADX, etc.)
         ↓
   MapElitesArchive  (your evolved strategies)
         ↓
   regime detection  (bd1=volatility, bd2=trend)
         ↓
   best strategy for current regime
         ↓
   generate_signals()  → LONG / FLAT
         ↓
   ExecutionEngine  (compares to current position)
         ↓
   broker.place_order()  → Zerodha / Angel / Paper
```

---

## Phase 1 — Data Setup (do this first)

### Get NIFTYBEES historical data

NIFTYBEES.NS is Nippon India ETF tracking NIFTY 50.
It is the SPY equivalent for NSE — most liquid, cleanest data.

Download from Yahoo Finance:
  URL: https://finance.yahoo.com/quote/NIFTYBEES.NS/history/
  Date range: 2010-01-01 to today
  Save as: data/NIFTYBEES.csv

Or run this Python script once:

```python
import yfinance as yf
df = yf.download("NIFTYBEES.NS", start="2010-01-01", auto_adjust=True)
df.to_csv("data/NIFTYBEES.csv")
print(f"Downloaded {len(df)} rows")
```

---

## Phase 2 — Evolution on NSE Data

Replace config.py with config_nse.py, then run evolution:

```powershell
# Copy NSE config over your existing config
copy config_nse.py config.py

# Run evolution on NIFTYBEES data
python run_evolution.py --csv data/NIFTYBEES.csv --generations 3000

# Test results
python test_suite.py --csv data/NIFTYBEES.csv

# Inspect routing table
python inspect_archive.py --csv data/NIFTYBEES.csv
```

Key differences vs SPY evolution:
- Risk-free rate is 6.5% not 4% (affects Sharpe calculation)
- Stop-loss minimum is 1.5% not 0.5% (NSE is more volatile intraday)
- Transaction costs are 0.3% not 0.1% (NSE costs are higher)
- Calmar fitness recommended (Indian markets crash harder)

---

## Phase 3 — Paper Trading on NSE

Run morning.py with your NIFTYBEES CSV.
Everything works exactly as before but:
- Prices are in INR
- NSE holidays are checked automatically
- IST timezone used for market hours

```powershell
python morning.py --csv data/NIFTYBEES.csv
```

Or double-click nse_morning.bat every day at 9:00 AM IST.

The paper_trades.csv journal will track:
- Entry price in INR
- Exit price in INR
- P&L in % (broker-agnostic)
- Which regime the trade was taken in

---

## Phase 4 — Connecting a Real Broker

### Option A: Zerodha (recommended — most popular in India)

1. Open a Zerodha account at zerodha.com
2. Apply for Kite Connect API access at kite.trade
   (Rs 2000/month for API access)
3. Install: pip install kiteconnect
4. Fill in config.py:

```python
BROKER              = "zerodha"
ZERODHA_API_KEY     = "your_api_key"
ZERODHA_API_SECRET  = "your_api_secret"
ZERODHA_USER_ID     = "your_zerodha_id"
```

5. Each morning, log in and get today's access token:

```python
from broker.broker import get_broker
broker = get_broker("zerodha")
# First time each day — generates login URL
login_url = broker.kite.login_url()
print(f"Login here: {login_url}")
# After login, you get redirected with a request_token in the URL
request_token = "paste_from_redirect_url"
access_token  = broker.generate_session(request_token, "your_api_secret")
print(f"Token saved: {access_token}")
```

### Option B: Angel Broking SmartAPI (free — good to start)

1. Open Angel Broking account at angelbroking.com
2. Register for SmartAPI at smartapi.angelbroking.com (FREE)
3. Install: pip install smartapi-python pyotp
4. Fill in config.py:

```python
BROKER             = "angel"
ANGEL_API_KEY      = "your_api_key"
ANGEL_CLIENT_ID    = "your_client_id"
ANGEL_PASSWORD     = "your_password"
ANGEL_TOTP_SECRET  = "your_2fa_secret"  # From your authenticator app setup
```

5. The TOTP is automated — no manual 2FA needed once set up.

### Option C: Upstox

1. Open Upstox account at upstox.com
2. Get API access from developer.upstox.com
3. Install: pip install upstox-python-sdk
4. Similar setup to Zerodha

---

## Phase 5 — Going Live

### Pre-live checklist

Before changing dry_run=False:

- [ ] Paper traded for at least 3 months
- [ ] Paper trading Sharpe > 0.4
- [ ] Win rate > 50% on at least 15 completed trades
- [ ] Test suite still showing OOS% > 60%
- [ ] Broker API tested in paper mode and orders confirmed working
- [ ] Position sizing correct (never more than 80% of capital in one trade)
- [ ] Stop-loss confirmed working in backtest (min 1.5%)

### First live run — use execution_engine.py

```powershell
# DRY RUN first (default) — signals computed, no orders placed
python execution_engine.py

# LIVE — real orders placed
python execution_engine.py --live
```

The execution_engine.py requires you to type 'YES' explicitly
to confirm live trading. This is intentional.

### Automate with Windows Task Scheduler

To run automatically every morning at 9:05 AM IST:

1. Open Task Scheduler (search in Start menu)
2. Create Basic Task
3. Name: "QD NSE Morning"
4. Trigger: Daily, 9:05 AM
5. Action: Start a program
6. Program: python
7. Arguments: execution_engine.py --live
8. Start in: C:\Users\aarav\Downloads\files (2)

The system will then run automatically every trading morning.
Non-trading days are handled automatically (system exits cleanly).

---

## What the Execution Engine Does

When you run execution_engine.py:

```
1. Downloads latest NIFTYBEES price from broker API
   (or reads from CSV if broker unavailable)

2. Adds all technical indicators with full history

3. Detects current volatility and trend regime

4. Routes to best strategy from your archive

5. Generates signal (LONG or FLAT)

6. Checks your current broker positions

7. If signal = LONG and no position:
   → BUY floor(capital × position_size × 0.8 / price) shares

8. If signal = FLAT and have position:
   → SELL all shares

9. If signal = LONG and already have position:
   → HOLD (no action)

10. Logs everything to logs/exec_YYYY-MM-DD.json
```

---

## Risk Management — Hard Limits in Production

These are enforced by execution_engine.py:

- Never deploy > 80% of capital in one trade (MAX_POSITION_PCT)
- Never trade if order value < Rs 5000 (MIN_TRADE_VALUE_INR)
- Only CNC (delivery) orders — no intraday leverage
- Market orders only — no limit order hunting
- One instrument at a time until system is proven

---

## NSE vs SPY — Key Differences to Expect

After evolving on NIFTYBEES data, expect:

- Higher best Sharpe (NIFTY is more volatile than SPY, more room for momentum)
- Lower OOS% initially (Indian market has harder regime shifts around elections, RBI policy)
- Walk-forward will likely fail around: 2020 (COVID crash), 2022 (FII selling)
- Walk-forward will likely pass around: 2017-2019 (sustained bull), 2023-2024 (bull run)
- Calmar archive will be clearly better than Sharpe archive (verified in testing)

---

## Monitoring in Production

Check these daily:
  logs/execution.log    — every order, signal, and error
  logs/exec_TODAY.json  — today's full signal context
  journal/paper_state.json  — if paper mode: positions and trades

Check these monthly:
  python test_suite.py --csv data/NIFTYBEES.csv
  Look for: OOS% trend, best OOS Sharpe, degradation
