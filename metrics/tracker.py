"""
metrics/tracker.py
Tracks and persists evolution metrics across generations.
"""

import csv
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import OUTPUT_DIR


@dataclass
class GenerationRecord:
    generation:   int
    n_filled:     int
    coverage:     float
    qd_score:     float
    mean_fitness: float
    max_fitness:  float
    improvements: int
    elapsed_s:    float


class EvolutionTracker:
    def __init__(self, output_dir: str = OUTPUT_DIR):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.records: List[GenerationRecord] = []
        self.start_time = time.time()
        self._csv_path  = self.output_dir / "metrics.csv"
        self._init_csv()

    def _init_csv(self):
        with open(self._csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["generation", "n_filled", "coverage_pct",
                        "qd_score", "mean_fitness", "max_fitness",
                        "improvements", "elapsed_s"])

    def log(self, generation: int, archive):
        elapsed = time.time() - self.start_time
        s       = archive.summary()
        rec     = GenerationRecord(
            generation   = generation,
            n_filled     = s["n_filled"],
            coverage     = s["coverage"],
            qd_score     = s["qd_score"],
            mean_fitness = s["mean_fitness"],
            max_fitness  = s["max_fitness"],
            improvements = s["improvements"],
            elapsed_s    = round(elapsed, 1),
        )
        self.records.append(rec)
        with open(self._csv_path, "a", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                rec.generation, rec.n_filled, rec.coverage,
                rec.qd_score, rec.mean_fitness, rec.max_fitness,
                rec.improvements, rec.elapsed_s,
            ])
        return rec

    def latest(self) -> GenerationRecord:
        return self.records[-1] if self.records else None
