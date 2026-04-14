"""
evolution/map_elites.py
MAP-Elites archive.
A GRID_SIZE x GRID_SIZE grid where each cell holds:
  - the best strategy found for that (volatility, trend) regime
  - its fitness, behavioral descriptors, and performance stats
"""

import json
import numpy as np
from pathlib import Path
from typing import Optional, List, Tuple
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import GRID_SIZE
from evolution.genome import StrategyGenome


class ArchiveCell:
    __slots__ = ["genome", "fitness", "bd1", "bd2",
                 "sharpe", "total_return", "max_dd",
                 "n_trades", "win_rate", "profit_factor",
                 "generation_added"]

    def __init__(self, genome, result, generation: int):
        self.genome          = genome
        self.fitness         = result.fitness
        self.bd1             = result.bd1
        self.bd2             = result.bd2
        self.sharpe          = result.sharpe
        self.total_return    = result.total_return
        self.max_dd          = result.max_drawdown
        self.n_trades        = result.n_trades
        self.win_rate        = result.win_rate
        self.profit_factor   = result.profit_factor
        self.generation_added = generation

    def to_dict(self) -> dict:
        return {
            "genome":           self.genome.to_dict(),
            "fitness":          self.fitness,
            "bd1":              self.bd1,
            "bd2":              self.bd2,
            "sharpe":           self.sharpe,
            "total_return":     self.total_return,
            "max_dd":           self.max_dd,
            "n_trades":         self.n_trades,
            "win_rate":         self.win_rate,
            "profit_factor":    self.profit_factor,
            "generation_added": self.generation_added,
        }

    @classmethod
    def from_dict(cls, d: dict):
        from evolution.evaluator import BacktestResult
        genome = StrategyGenome.from_dict(d["genome"])
        result = BacktestResult(
            fitness      = d["fitness"],
            bd1          = d["bd1"],
            bd2          = d["bd2"],
            sharpe       = d["sharpe"],
            total_return = d["total_return"],
            max_drawdown = d["max_dd"],
            n_trades     = d["n_trades"],
            win_rate     = d["win_rate"],
            profit_factor = d["profit_factor"],
        )
        cell = cls.__new__(cls)
        cell.genome           = genome
        cell.fitness          = d["fitness"]
        cell.bd1              = d["bd1"]
        cell.bd2              = d["bd2"]
        cell.sharpe           = d["sharpe"]
        cell.total_return     = d["total_return"]
        cell.max_dd           = d["max_dd"]
        cell.n_trades         = d["n_trades"]
        cell.win_rate         = d["win_rate"]
        cell.profit_factor    = d["profit_factor"]
        cell.generation_added = d.get("generation_added", 0)
        return cell


class MapElitesArchive:
    """
    The core QD data structure.
    grid[i][j] = ArchiveCell or None
    i = volatility regime bin (BD1)
    j = trend regime bin (BD2)
    """

    def __init__(self, grid_size: int = GRID_SIZE):
        self.grid_size   = grid_size
        self.grid        = [[None] * grid_size for _ in range(grid_size)]
        self._n_filled   = 0
        self.improvements = 0     # total times a cell was improved

    # ── Core operation ────────────────────────────────────────────────────────
    def try_add(self, genome: StrategyGenome,
                result, generation: int) -> bool:
        """
        Try to add a genome to the archive.
        Returns True if the cell was updated (new or improved).
        """
        if not result.is_valid or result.fitness <= -9.0:
            return False

        i, j = self._to_cell(result.bd1, result.bd2)
        current = self.grid[i][j]

        if current is None or result.fitness > current.fitness:
            was_empty = current is None
            self.grid[i][j] = ArchiveCell(genome, result, generation)
            if was_empty:
                self._n_filled += 1
            else:
                self.improvements += 1
            return True
        return False

    # ── Sampling ──────────────────────────────────────────────────────────────
    def select_random_elite(self) -> Optional[ArchiveCell]:
        """Randomly select a filled cell."""
        filled = self._get_filled()
        if not filled:
            return None
        return np.random.choice(filled)

    def select_random_genome(self) -> Optional[StrategyGenome]:
        cell = self.select_random_elite()
        return cell.genome if cell else None

    def get_all_genomes(self) -> List[StrategyGenome]:
        return [c.genome for c in self._get_filled()]

    def get_best_for_regime(self, bd1: float, bd2: float) -> Optional[ArchiveCell]:
        """
        Return the best strategy for a given market regime.
        Falls back to nearest filled cell if the exact one is empty.
        """
        i, j = self._to_cell(bd1, bd2)
        if self.grid[i][j] is not None:
            return self.grid[i][j]

        # Find nearest filled cell (L2 distance in grid space)
        best_cell = None
        best_dist = float("inf")
        for ii in range(self.grid_size):
            for jj in range(self.grid_size):
                if self.grid[ii][jj] is not None:
                    dist = (ii - i) ** 2 + (jj - j) ** 2
                    if dist < best_dist:
                        best_dist = dist
                        best_cell = self.grid[ii][jj]
        return best_cell

    # ── Statistics ────────────────────────────────────────────────────────────
    @property
    def coverage(self) -> float:
        return self._n_filled / (self.grid_size ** 2)

    @property
    def qd_score(self) -> float:
        """Sum of all fitness values in the archive."""
        return sum(c.fitness for c in self._get_filled())

    @property
    def mean_fitness(self) -> float:
        filled = self._get_filled()
        if not filled:
            return 0.0
        return float(np.mean([c.fitness for c in filled]))

    @property
    def max_fitness(self) -> float:
        filled = self._get_filled()
        if not filled:
            return 0.0
        return float(max(c.fitness for c in filled))

    @property
    def n_filled(self) -> int:
        return self._n_filled

    def fitness_grid(self) -> np.ndarray:
        """2D array of fitness values (NaN for empty cells)."""
        grid = np.full((self.grid_size, self.grid_size), np.nan)
        for i in range(self.grid_size):
            for j in range(self.grid_size):
                if self.grid[i][j] is not None:
                    grid[i][j] = self.grid[i][j].fitness
        return grid

    def summary(self) -> dict:
        filled = self._get_filled()
        if not filled:
            return {"n_filled": 0, "coverage": 0.0, "qd_score": 0.0,
                    "mean_fitness": 0.0, "max_fitness": 0.0, "improvements": 0}
        fitnesses = [c.fitness for c in filled]
        sharpes   = [c.sharpe  for c in filled]
        return {
            "n_filled":     self._n_filled,
            "coverage":     round(self.coverage * 100, 1),
            "qd_score":     round(self.qd_score, 3),
            "mean_fitness": round(float(np.mean(fitnesses)), 3),
            "max_fitness":  round(float(max(fitnesses)), 3),
            "mean_sharpe":  round(float(np.mean(sharpes)), 3),
            "improvements": self.improvements,
        }

    # ── Persistence ───────────────────────────────────────────────────────────
    def save(self, path: str):
        data = {
            "grid_size":   self.grid_size,
            "improvements": self.improvements,
            "cells": [],
        }
        for i in range(self.grid_size):
            for j in range(self.grid_size):
                if self.grid[i][j] is not None:
                    data["cells"].append({
                        "i": i, "j": j,
                        "cell": self.grid[i][j].to_dict()
                    })
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str) -> "MapElitesArchive":
        with open(path) as f:
            data = json.load(f)
        archive = cls(grid_size=data["grid_size"])
        archive.improvements = data.get("improvements", 0)
        for entry in data["cells"]:
            i, j = entry["i"], entry["j"]
            archive.grid[i][j] = ArchiveCell.from_dict(entry["cell"])
            archive._n_filled += 1
        return archive

    # ── Internal helpers ──────────────────────────────────────────────────────
    def _to_cell(self, bd1: float, bd2: float) -> Tuple[int, int]:
        i = int(np.clip(bd1, 0.0, 0.9999) * self.grid_size)
        j = int(np.clip(bd2, 0.0, 0.9999) * self.grid_size)
        return i, j

    def _get_filled(self) -> list:
        cells = []
        for row in self.grid:
            for cell in row:
                if cell is not None:
                    cells.append(cell)
        return cells
