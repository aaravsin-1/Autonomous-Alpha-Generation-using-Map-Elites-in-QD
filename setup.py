"""
setup_project.py
Run this ONCE from the folder where all your .py files are.
It creates the proper directory structure and moves everything into place.

Usage:
    python setup_project.py
"""

import os
import shutil
from pathlib import Path

HERE = Path(__file__).parent

# ── Files that need to move into subdirectories ───────────────────────────────
MOVES = {
    # evolution/
    "evaluator.py":      "evolution/evaluator.py",
    "genome.py":         "evolution/genome.py",
    "map_elites.py":     "evolution/map_elites.py",

    # strategies/
    "signal_generator.py": "strategies/signal_generator.py",
    "indicators.py":        "strategies/indicators.py",

    # metrics/
    "fitness.py":   "metrics/fitness.py",
    "tracker.py":   "metrics/tracker.py",

    # router/
    "live_router.py": "router/live_router.py",

    # data/
    "fetcher.py":      "data/fetcher.py",
    "synthetic.py":    "data/synthetic.py",
    "csv_loader.py":   "data/csv_loader.py",
    "downlaod_data.py": "data/downlaod_data.py",   # typo in original

    # testing/
    "benchmark.py":     "testing/benchmark.py",
    "monte_carlo.py":   "testing/monte_carlo.py",
    "out_of_sample.py": "testing/out_of_sample.py",
    "walk_forward.py":  "testing/walk_forward.py",

    # visualization/
    "dashboard.py": "visualization/dashboard.py",
}

# ── CSV data file ─────────────────────────────────────────────────────────────
DATA_MOVES = {
    "SPY.csv": "data/SPY.csv",
}

# ── Directories to create ─────────────────────────────────────────────────────
DIRS = [
    "data", "evolution", "strategies", "metrics",
    "router", "testing", "visualization", "output/plots",
]


def run():
    print("=" * 55)
    print("  QD Trading — Project Setup")
    print("=" * 55)

    # 1. Create directories
    print("\n  Creating directories...")
    for d in DIRS:
        (HERE / d).mkdir(parents=True, exist_ok=True)
        init = HERE / d / "__init__.py"
        if not init.exists():
            init.touch()
        print(f"    ✓ {d}/")

    # 2. Move Python files
    print("\n  Moving files to correct locations...")
    moved, missing = [], []

    for src_name, dst_rel in {**MOVES, **DATA_MOVES}.items():
        src = HERE / src_name
        dst = HERE / dst_rel
        if src.exists():
            shutil.move(str(src), str(dst))
            moved.append(f"  {src_name} → {dst_rel}")
        else:
            # Already in place, or genuinely missing
            if dst.exists():
                moved.append(f"  {dst_rel} already in place")
            else:
                missing.append(src_name)

    for m in moved:
        print(f"    ✓ {m}")

    # 3. Report missing files
    if missing:
        print(f"\n  ⚠  These files were not found (may already be in place):")
        for f in missing:
            print(f"     - {f}")

    # 4. Check config.py
    config_path = HERE / "config.py"
    if not config_path.exists():
        print("\n  ✗  config.py is MISSING. Download it from the link below")
        print("     or the next step will fail.")
    else:
        print(f"\n    ✓ config.py found")

    # 5. Quick import test
    print("\n  Testing imports...")
    import sys
    sys.path.insert(0, str(HERE))
    errors = []
    tests = [
        ("config",                   "config"),
        ("evolution.genome",         "genome"),
        ("evolution.map_elites",     "map_elites"),
        ("evolution.evaluator",      "evaluator"),
        ("strategies.indicators",    "indicators"),
        ("strategies.signal_generator", "signal_generator"),
        ("metrics.fitness",          "fitness"),
        ("data.synthetic",           "synthetic"),
    ]
    for module, label in tests:
        try:
            __import__(module)
            print(f"    ✓ {module}")
        except Exception as e:
            errors.append((module, str(e)))
            print(f"    ✗ {module}  ← {e}")

    print()
    if errors:
        print(f"  {len(errors)} import error(s). Check the files listed above.")
    else:
        print("  All imports OK. You're ready to run:")
        print()
        print("    python run_evolution.py --csv data/SPY.csv --generations 2000")
        print("    python test_suite.py --csv data/SPY.csv")
        print()

    print("=" * 55)


if __name__ == "__main__":
    run()