"""
QD Trading System — Central Configuration
All parameters in one place. Change here, propagates everywhere.
"""

# ── Data ─────────────────────────────────────────────────────────────────────
TICKERS          = ["SPY", "QQQ", "IWM"]   # instruments to trade
PRIMARY_TICKER   = "SPY"
TRAIN_START      = "2010-01-01"
TRAIN_END        = "2022-12-31"
TEST_START       = "2023-01-01"
TEST_END         = "2024-12-31"
DATA_CACHE_DIR   = "data/cache"

# ── MAP-Elites Archive ────────────────────────────────────────────────────────
GRID_SIZE        = 10          # 10x10 = 100 niches
# BD1 = volatility regime   (0 = calm,  1 = explosive)
# BD2 = trend regime        (0 = ranging, 1 = strong trend)

# ── Evolution ─────────────────────────────────────────────────────────────────
POPULATION_SEED  = 200         # initial random strategies to seed archive
MAX_GENERATIONS  = 2000        # total evolution steps
MUTATION_SIGMA   = 0.15        # gaussian mutation std (normalised space)
CROSSOVER_PROB   = 0.3         # probability of crossover vs pure mutation
ELITE_MUTATION   = 0.7         # probability of mutating an existing elite
RANDOM_INJECTION = 0.3         # probability of generating a brand-new random

# ── Fitness ────────────────────────────────────────────────────────────────────
MIN_TRADES       = 10          # discard strategies with fewer trades
RISK_FREE_RATE   = 0.04        # annual risk-free rate for Sharpe
FITNESS_METRIC   = "sharpe"    # "sharpe" | "calmar" | "sortino"

# ── Strategy Genome Bounds ─────────────────────────────────────────────────────
# Each gene is normalised to [0, 1] internally; bounds below are the real values
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
    # Signal weights (raw, softmax'd before use)
    "w_ma":            (0.0, 1.0),
    "w_rsi":           (0.0, 1.0),
    "w_macd":          (0.0, 1.0),
    "w_bb":            (0.0, 1.0),
    # Risk management
    "stop_loss":       (0.005, 0.08),
    "take_profit":     (0.01,  0.25),
    "position_size":   (0.2,   1.0),
    # Trend filter
    "trend_filter":    (0.0,   1.0),   # 0 = no filter, 1 = strong trend only
    "vol_filter":      (0.0,   1.0),   # 0 = trade all vol, 1 = only low vol
}

GENOME_KEYS = list(GENOME_BOUNDS.keys())
GENOME_DIM  = len(GENOME_KEYS)

# ── Logging & Output ──────────────────────────────────────────────────────────
LOG_EVERY        = 50          # print progress every N generations
SAVE_EVERY       = 200         # save archive every N generations
OUTPUT_DIR       = "output"
ARCHIVE_FILE     = "archive.json"
METRICS_FILE     = "metrics.csv"