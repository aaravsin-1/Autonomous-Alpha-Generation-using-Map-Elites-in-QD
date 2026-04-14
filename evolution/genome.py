"""
evolution/genome.py
A StrategyGenome is the "DNA" of a trading strategy.
All genes are stored as normalised floats [0, 1].
They are decoded to real values only when the strategy runs.
"""

import json
import numpy as np
from dataclasses import dataclass, asdict, field
from typing import List
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import GENOME_BOUNDS, GENOME_KEYS, GENOME_DIM


@dataclass
class StrategyGenome:
    """
    All genes live in [0, 1] (normalised).
    Use decode() to get real parameter values.
    """
    genes: List[float] = field(default_factory=lambda: [0.5] * GENOME_DIM)
    generation_born: int = 0
    parent_cells: list = field(default_factory=list)

    # ── Decode ────────────────────────────────────────────────────────────────
    def decode(self) -> dict:
        """Return dict of real-valued parameters."""
        params = {}
        for i, key in enumerate(GENOME_KEYS):
            lo, hi = GENOME_BOUNDS[key]
            params[key] = lo + self.genes[i] * (hi - lo)

        # Integer genes
        for k in ["fast_ma", "slow_ma", "rsi_period", "macd_fast",
                  "macd_slow", "macd_signal", "bb_period", "atr_period"]:
            params[k] = max(2, int(round(params[k])))

        # Ensure fast < slow
        if params["fast_ma"] >= params["slow_ma"]:
            params["slow_ma"] = params["fast_ma"] + 10
        if params["macd_fast"] >= params["macd_slow"]:
            params["macd_slow"] = params["macd_fast"] + 5

        # Ensure rsi_os < rsi_ob
        if params["rsi_oversold"] >= params["rsi_overbought"]:
            params["rsi_oversold"]  = 30.0
            params["rsi_overbought"] = 70.0

        # Softmax signal weights
        raw_w = np.array([params[k] for k in ["w_ma", "w_rsi", "w_macd", "w_bb"]])
        exp_w = np.exp(raw_w - raw_w.max())
        params["weights"] = (exp_w / exp_w.sum()).tolist()

        return params

    # ── Serialisation ─────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "genes":          self.genes,
            "generation_born": self.generation_born,
            "parent_cells":   self.parent_cells,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyGenome":
        g = cls()
        g.genes           = d["genes"]
        g.generation_born = d.get("generation_born", 0)
        g.parent_cells    = d.get("parent_cells", [])
        return g


# ── Factory functions ─────────────────────────────────────────────────────────

def random_genome(generation: int = 0) -> StrategyGenome:
    """Create a completely random genome."""
    return StrategyGenome(
        genes=np.random.uniform(0, 1, GENOME_DIM).tolist(),
        generation_born=generation,
    )


def mutate(genome: StrategyGenome, sigma: float = 0.15,
           generation: int = 0) -> StrategyGenome:
    """
    Gaussian mutation in normalised space.
    Each gene is perturbed independently, then clipped to [0, 1].
    """
    genes   = np.array(genome.genes)
    noise   = np.random.normal(0, sigma, GENOME_DIM)
    mutated = np.clip(genes + noise, 0.0, 1.0)
    return StrategyGenome(
        genes=mutated.tolist(),
        generation_born=generation,
        parent_cells=genome.parent_cells[:],
    )


def crossover(parent_a: StrategyGenome,
              parent_b: StrategyGenome,
              generation: int = 0) -> StrategyGenome:
    """
    Uniform crossover: each gene randomly from either parent.
    """
    mask  = np.random.rand(GENOME_DIM) > 0.5
    genes = np.where(mask, parent_a.genes, parent_b.genes)
    return StrategyGenome(
        genes=genes.tolist(),
        generation_born=generation,
    )


def mutate_and_maybe_crossover(elite: StrategyGenome,
                                archive_elites: list,
                                sigma: float,
                                crossover_prob: float,
                                generation: int) -> StrategyGenome:
    """
    Combines mutation with occasional crossover from a random archive elite.
    """
    if len(archive_elites) > 1 and np.random.rand() < crossover_prob:
        other = np.random.choice(archive_elites)
        child = crossover(elite, other, generation)
        return mutate(child, sigma * 0.5, generation)
    return mutate(elite, sigma, generation)


def genome_behavioral_descriptors(genome: "StrategyGenome") -> tuple:
    """
    Compute behavioral descriptors directly from genome genes.
    No backtest needed — these characterise the strategy's TYPE:

    BD1 = momentum bias vs mean-reversion bias
          0 = pure mean-reversion (RSI+BB dominate)
          1 = pure momentum (MA+MACD dominate)

    BD2 = risk tolerance (stop-loss width)
          0 = tight stop-loss (0.5%)
          1 = wide stop-loss  (8%)

    These are independent, always in [0,1], and spread evenly.
    """
    params = genome.decode()
    w      = params["weights"]   # [w_ma, w_rsi, w_macd, w_bb]

    # BD1: momentum fraction of total signal weight
    momentum_w     = w[0] + w[2]   # MA + MACD
    mean_rev_w     = w[1] + w[3]   # RSI + BB
    bd1 = momentum_w / (momentum_w + mean_rev_w + 1e-9)

    # BD2: stop-loss normalised to [0,1]
    lo, hi = 0.005, 0.08
    bd2 = (params["stop_loss"] - lo) / (hi - lo)
    bd2 = float(np.clip(bd2, 0.0, 1.0))

    return float(np.clip(bd1, 0.0, 1.0)), bd2
