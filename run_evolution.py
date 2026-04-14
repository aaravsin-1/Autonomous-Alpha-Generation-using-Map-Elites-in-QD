"""
run_evolution.py — QD Trading System main loop
Usage:
    python run_evolution.py --synthetic --generations 400
    python run_evolution.py --resume --synthetic
"""

import argparse, time, os, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from colorama import init, Fore
init(autoreset=True)
import numpy as np

import config as cfg
from strategies.indicators import add_all_indicators
from evolution.genome import random_genome, mutate_and_maybe_crossover
from evolution.evaluator import BacktestEngine
from evolution.map_elites import MapElitesArchive
from metrics.tracker import EvolutionTracker
from visualization.dashboard import (
    plot_archive_heatmap, plot_evolution_curves, plot_top_strategies
)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--ticker",      default=cfg.PRIMARY_TICKER)
    p.add_argument("--generations", type=int,   default=cfg.MAX_GENERATIONS)
    p.add_argument("--seed",        type=int,   default=cfg.POPULATION_SEED)
    p.add_argument("--sigma",       type=float, default=cfg.MUTATION_SIGMA)
    p.add_argument("--resume",      action="store_true")
    p.add_argument("--grid",        type=int,   default=cfg.GRID_SIZE)
    p.add_argument("--synthetic",   action="store_true",
                   help="Use synthetic data (no internet needed)")
    p.add_argument("--csv",         default=None,
                   help="Path to OHLCV CSV file e.g. data/SPY.csv")
    return p.parse_args()


def load_data(ticker, use_synthetic=False, csv_path=None):
    if csv_path:
        from data.csv_loader import load_csv
        df = load_csv(csv_path)
        return df, "csv"
    if not use_synthetic:
        try:
            from data.fetcher import fetch_ohlcv
            df = fetch_ohlcv(ticker, cfg.TRAIN_START, cfg.TRAIN_END)
            if df is not None and len(df) > 100:
                return df, "live"
        except Exception:
            print(Fore.YELLOW + "  Live data unavailable — using synthetic data.")
    from data.synthetic import generate_market_data
    df = generate_market_data(n_days=3000, seed=42)
    return df, "synthetic"


def seed_archive(engine, archive, n, sigma):
    added, attempts = 0, 0
    print(Fore.YELLOW + f"  Seeding with {n} random strategies...")
    while added < n and attempts < n * 8:
        attempts += 1
        g = random_genome(generation=0)
        r = engine.run(g)
        if archive.try_add(g, r, 0):
            added += 1
    print(Fore.GREEN +
          f"  Seeded → {archive.n_filled}/{cfg.GRID_SIZE**2} niches "
          f"({archive.coverage*100:.0f}%) in {attempts} evaluations\n")


def run_evolution(args):
    output_dir   = Path(cfg.OUTPUT_DIR)
    archive_path = str(output_dir / cfg.ARCHIVE_FILE)
    metrics_path = str(output_dir / cfg.METRICS_FILE)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(Fore.CYAN + "=" * 64)
    print(Fore.CYAN + "  QD TRADING SYSTEM — MAP-Elites Evolution Engine")
    print(Fore.CYAN + "=" * 64)
    print(f"  Grid: {cfg.GRID_SIZE}x{cfg.GRID_SIZE}={cfg.GRID_SIZE**2} niches  "
          f"Fitness: {cfg.FITNESS_METRIC}  Sigma: {args.sigma}")
    print(f"  BD1=volatility regime  BD2=trend regime")
    print(Fore.CYAN + "=" * 64 + "\n")

    # 1. Data
    print(Fore.CYAN + "  [1/4] Loading data...")
    df_raw, source = load_data(args.ticker, use_synthetic=args.synthetic, csv_path=args.csv)
    df = add_all_indicators(df_raw)
    print(Fore.GREEN + f"  {len(df)} trading days  (source={source})\n")

    # 2. Archive
    print(Fore.CYAN + "  [2/4] Initialising archive...")
    if args.resume and Path(archive_path).exists():
        archive = MapElitesArchive.load(archive_path)
        print(Fore.GREEN + f"  Resumed: {archive.n_filled} cells\n")
    else:
        archive = MapElitesArchive(grid_size=args.grid)

    engine  = BacktestEngine(df)
    tracker = EvolutionTracker(output_dir=str(output_dir))

    # 3. Seed
    print(Fore.CYAN + "  [3/4] Seeding archive...")
    if archive.n_filled < args.seed // 2:
        seed_archive(engine, archive, args.seed, args.sigma)

    # 4. Evolution loop
    print(Fore.CYAN + f"  [4/4] Evolving for {args.generations} generations...\n")
    print(Fore.WHITE + f"  {'Gen':>5}  {'Filled':>7}  {'Cov%':>5}  "
          f"{'QD-Score':>9}  {'BestF':>7}  {'MeanF':>7}  {'Impr':>5}  {'g/s':>5}")
    print("  " + "-" * 60)

    t0 = time.time()

    for gen in range(1, args.generations + 1):
        # Select + vary
        if np.random.rand() < cfg.ELITE_MUTATION and archive.n_filled > 0:
            elite = archive.select_random_elite()
            all_g = archive.get_all_genomes()
            child = mutate_and_maybe_crossover(
                elite.genome, all_g,
                sigma=args.sigma,
                crossover_prob=cfg.CROSSOVER_PROB,
                generation=gen,
            )
        else:
            child = random_genome(generation=gen)

        result = engine.run(child, generation=gen)
        archive.try_add(child, result, gen)

        # Log
        if gen % cfg.LOG_EVERY == 0 or gen == 1:
            rec     = tracker.log(gen, archive)
            elapsed = time.time() - t0
            rate    = gen / max(elapsed, 0.001)
            print(
                Fore.WHITE  + f"  {gen:5d}  "
                + Fore.GREEN  + f"{rec.n_filled:5d}/100  "
                + Fore.CYAN   + f"{rec.coverage:4.1f}%  "
                + Fore.YELLOW + f"{rec.qd_score:9.2f}  "
                + Fore.WHITE  + f"{rec.max_fitness:+7.3f}  "
                + f"{rec.mean_fitness:+7.3f}  "
                + Fore.BLUE   + f"{rec.improvements:5d}  "
                + Fore.WHITE  + f"{rate:5.1f}"
            )

        # Periodic save
        if gen % cfg.SAVE_EVERY == 0:
            archive.save(archive_path)
            plot_archive_heatmap(archive, generation=gen, save=True)
            plot_evolution_curves(metrics_path, save=True)
            print(Fore.BLUE + f"  → Checkpoint saved  (gen {gen})")

    # Final
    archive.save(archive_path)
    elapsed = time.time() - t0
    s = archive.summary()

    print(Fore.CYAN + "\n" + "=" * 64)
    print(Fore.GREEN + f"""
  EVOLUTION COMPLETE
  Generations    : {args.generations}  ({elapsed:.0f}s  {args.generations/elapsed:.1f} gen/s)
  Niches filled  : {s['n_filled']}/100  ({s['coverage']}%)
  QD-Score       : {s['qd_score']}
  Best Sharpe    : {s['max_fitness']}
  Mean Sharpe    : {s['mean_fitness']}
  Improvements   : {s['improvements']}
""")

    p1 = plot_archive_heatmap(archive, generation=args.generations)
    p2 = plot_evolution_curves(metrics_path)
    p3 = plot_top_strategies(archive, df_raw, n=5)
    print(Fore.BLUE + "  Plots saved to output/plots/")

    return archive, df_raw


if __name__ == "__main__":
    args = parse_args()
    run_evolution(args)