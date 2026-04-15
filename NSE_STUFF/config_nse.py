"""
config.py — NSE India Configuration
Replace your existing config.py with this when trading NSE.
"""

# ── Instrument ─────────────────────────────────────────────────────────────────
# NSE equivalents of SPY:
#   NIFTYBEES.NS  — Nippon India ETF tracking NIFTY 50 (most liquid, best for algo)
#   JUNIORBEES.NS — NIFTY Next 50
#   BANKBEES.NS   — Bank NIFTY
#   ^NSEI         — NIFTY 50 index (for data only, not tradeable directly)
#
# For individual stocks use: RELIANCE.NS, TCS.NS, INFY.NS, HDFCBANK.NS etc.

TICKERS          = ["NIFTYBEES.NS", "JUNIORBEES.NS", "BANKBEES.NS"]
PRIMARY_TICKER   = "NIFTYBEES.NS"      # Start here. Most liquid NSE ETF.
TRAIN_START      = "2010-01-01"
TRAIN_END        = "2022-12-31"
TEST_START       = "2023-01-01"
TEST_END         = "2024-12-31"
DATA_CACHE_DIR   = "data/cache"

# ── NSE Market Settings ────────────────────────────────────────────────────────
MARKET           = "NSE"
CURRENCY         = "INR"
MARKET_OPEN      = "09:15"             # IST
MARKET_CLOSE     = "15:30"             # IST
TIMEZONE         = "Asia/Kolkata"

# ── MAP-Elites Archive ─────────────────────────────────────────────────────────
GRID_SIZE        = 10

# ── Evolution ──────────────────────────────────────────────────────────────────
POPULATION_SEED  = 200
MAX_GENERATIONS  = 2000
MUTATION_SIGMA   = 0.15
CROSSOVER_PROB   = 0.3
ELITE_MUTATION   = 0.7
RANDOM_INJECTION = 0.3

# ── Fitness ────────────────────────────────────────────────────────────────────
MIN_TRADES       = 10
RISK_FREE_RATE   = 0.065              # India 10-yr govt bond yield ~6.5%
                                       # (higher than US 4% — this matters for Sharpe)
FITNESS_METRIC   = "calmar"           # Calmar recommended for India
                                       # Indian markets have sharper crashes than US
                                       # Calmar penalises drawdowns more heavily

# ── Transaction Costs — NSE Reality ──────────────────────────────────────────
# NSE costs are HIGHER than US markets. Be conservative.
#
# Zerodha example (per trade):
#   Brokerage     : 0.03% or Rs 20 max (intraday)
#   STT           : 0.1% on sell side (delivery)
#   Exchange fee  : 0.00345%
#   SEBI fee      : 0.0001%
#   Stamp duty    : 0.015% on buy side
#   GST           : 18% on brokerage
#
# Total round-trip for delivery equity: ~0.4-0.5%
# For ETFs slightly less but still higher than US

TRANSACTION_COST = 0.003              # 0.3% per trade (one-way). Conservative.
SLIPPAGE         = 0.001              # 0.1% slippage. NSE is less liquid than NYSE.

# ── Stop-loss bounds — NSE specific ──────────────────────────────────────────
# Indian markets have circuit breakers (10%, 15%, 20%) but individual
# stocks can move 5-10% intraday easily. Use wider stops than SPY.
# Minimum stop 1.5% to survive intraday noise.

GENOME_BOUNDS = {
    "fast_ma":         (5,   50),
    "slow_ma":         (20,  200),
    "rsi_period":      (5,   30),
    "rsi_overbought":  (60,  85),
    "rsi_oversold":    (15,  40),
    "macd_fast":       (5,   20),
    "macd_slow":       (15,  50),
    "macd_signal":     (5,   15),
    "bb_period":       (10,  30),
    "bb_std":          (1.5, 3.0),
    "atr_multiplier":  (1.0, 4.0),
    "atr_period":      (7,   21),
    "w_ma":            (0.0, 1.0),
    "w_rsi":           (0.0, 1.0),
    "w_macd":          (0.0, 1.0),
    "w_bb":            (0.0, 1.0),
    "stop_loss":       (0.015, 0.10),  # MINIMUM 1.5% for NSE (was 0.5% for SPY)
    "take_profit":     (0.03,  0.30),  # Wider targets for NSE volatility
    "position_size":   (0.2,   0.8),   # Max 80% — keep 20% cash buffer for margin
    "trend_filter":    (0.0,   1.0),
    "vol_filter":      (0.0,   1.0),
    "dummy":           (0.0,   1.0),
}

GENOME_KEYS = list(GENOME_BOUNDS.keys())
GENOME_DIM  = len(GENOME_KEYS)

# ── Broker Integration ─────────────────────────────────────────────────────────
# Supported brokers: "zerodha" | "upstox" | "angel" | "fyers" | "paper"
BROKER           = "paper"            # Start with paper. Change when ready.

# Zerodha Kite credentials (fill these in when going live)
ZERODHA_API_KEY     = ""              # Get from kite.trade developer console
ZERODHA_API_SECRET  = ""
ZERODHA_USER_ID     = ""

# Upstox credentials (alternative)
UPSTOX_API_KEY      = ""
UPSTOX_API_SECRET   = ""

# Angel Broking SmartAPI (free, good for beginners)
ANGEL_API_KEY       = ""
ANGEL_CLIENT_ID     = ""
ANGEL_PASSWORD      = ""
ANGEL_TOTP_SECRET   = ""             # For 2FA automation

# ── Position sizing ────────────────────────────────────────────────────────────
MAX_CAPITAL_INR     = 100000         # Rs 1 lakh default. Change to your actual capital.
MAX_POSITION_PCT    = 0.80           # Never deploy more than 80% at once
MIN_TRADE_VALUE_INR = 5000           # Minimum trade size (below this, skip)

# ── Logging & Output ───────────────────────────────────────────────────────────
LOG_EVERY        = 50
SAVE_EVERY       = 200
OUTPUT_DIR       = "output"
ARCHIVE_FILE     = "archive.json"
METRICS_FILE     = "metrics.csv"
