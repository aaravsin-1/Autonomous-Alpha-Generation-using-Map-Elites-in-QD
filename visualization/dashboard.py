"""
visualization/dashboard.py
Generates all diagnostic plots for the QD system.
Saves to output/plots/
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from pathlib import Path
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import OUTPUT_DIR, GRID_SIZE


PLOTS_DIR = Path(OUTPUT_DIR) / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)


def plot_archive_heatmap(archive, generation: int = 0, save: bool = True):
    """
    Heatmap of archive fitness values.
    X-axis = BD2 (Trend strength), Y-axis = BD1 (Volatility).
    """
    grid = archive.fitness_grid()

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(f"MAP-Elites Archive — Generation {generation}", fontsize=13)

    # Fitness heatmap
    ax = axes[0]
    masked = np.ma.masked_invalid(grid)
    cmap   = plt.cm.RdYlGn
    cmap.set_bad(color="#f0f0f0")
    im = ax.imshow(masked, cmap=cmap, vmin=-1, vmax=2,
                   origin="lower", aspect="auto")
    plt.colorbar(im, ax=ax, label="Fitness (Sharpe)")
    ax.set_xlabel("BD2: Trend strength →")
    ax.set_ylabel("BD1: Volatility →")
    ax.set_title(f"Fitness per niche  "
                 f"({archive.n_filled}/{GRID_SIZE**2} filled, "
                 f"{archive.coverage*100:.0f}%)")
    ax.set_xticks(range(GRID_SIZE))
    ax.set_yticks(range(GRID_SIZE))
    ax.set_xticklabels([f"{i/GRID_SIZE:.1f}" for i in range(GRID_SIZE)], fontsize=7)
    ax.set_yticklabels([f"{i/GRID_SIZE:.1f}" for i in range(GRID_SIZE)], fontsize=7)

    # Win-rate heatmap
    ax2 = axes[1]
    wr_grid = np.full((GRID_SIZE, GRID_SIZE), np.nan)
    for i in range(GRID_SIZE):
        for j in range(GRID_SIZE):
            if archive.grid[i][j] is not None:
                wr_grid[i][j] = archive.grid[i][j].win_rate

    masked2 = np.ma.masked_invalid(wr_grid)
    im2 = ax2.imshow(masked2, cmap=plt.cm.Blues, vmin=0, vmax=1,
                     origin="lower", aspect="auto")
    plt.colorbar(im2, ax=ax2, label="Win Rate")
    ax2.set_xlabel("BD2: Trend strength →")
    ax2.set_ylabel("BD1: Volatility →")
    ax2.set_title("Win Rate per niche")
    ax2.set_xticks(range(GRID_SIZE))
    ax2.set_yticks(range(GRID_SIZE))
    ax2.set_xticklabels([f"{i/GRID_SIZE:.1f}" for i in range(GRID_SIZE)], fontsize=7)
    ax2.set_yticklabels([f"{i/GRID_SIZE:.1f}" for i in range(GRID_SIZE)], fontsize=7)

    plt.tight_layout()
    if save:
        p = PLOTS_DIR / f"archive_gen{generation:05d}.png"
        plt.savefig(p, dpi=120, bbox_inches="tight")
        plt.close()
        return str(p)
    else:
        plt.show()
        return None


def plot_evolution_curves(metrics_csv: str, save: bool = True):
    """
    Line charts of QD-Score, Coverage, and Max Fitness over generations.
    """
    df = pd.read_csv(metrics_csv)
    if df.empty:
        return

    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    fig.suptitle("Evolution Progress", fontsize=13)

    axes[0].plot(df["generation"], df["qd_score"], color="#2196F3", lw=1.5)
    axes[0].set_ylabel("QD-Score")
    axes[0].set_title("QD-Score (total fitness across all niches)")
    axes[0].grid(alpha=0.3)

    axes[1].plot(df["generation"], df["coverage_pct"], color="#4CAF50", lw=1.5)
    axes[1].set_ylabel("Coverage (%)")
    axes[1].set_title("Archive Coverage")
    axes[1].set_ylim(0, 105)
    axes[1].grid(alpha=0.3)

    axes[2].plot(df["generation"], df["max_fitness"], color="#FF5722",
                 lw=1.5, label="Max")
    axes[2].plot(df["generation"], df["mean_fitness"], color="#FF9800",
                 lw=1, ls="--", label="Mean")
    axes[2].set_ylabel("Fitness")
    axes[2].set_xlabel("Generation")
    axes[2].set_title("Max / Mean Fitness")
    axes[2].legend()
    axes[2].grid(alpha=0.3)

    plt.tight_layout()
    if save:
        p = PLOTS_DIR / "evolution_curves.png"
        plt.savefig(p, dpi=120, bbox_inches="tight")
        plt.close()
        return str(p)
    else:
        plt.show()
        return None


def plot_top_strategies(archive, df_full: pd.DataFrame,
                        n: int = 5, save: bool = True):
    """
    Equity curves for the top-N strategies in the archive.
    """
    from strategies.indicators import add_all_indicators
    from strategies.signal_generator import generate_signals

    filled  = []
    for i in range(archive.grid_size):
        for j in range(archive.grid_size):
            c = archive.grid[i][j]
            if c is not None:
                filled.append((c.fitness, i, j, c))
    filled.sort(key=lambda x: -x[0])
    top    = filled[:n]

    df     = add_all_indicators(df_full)
    close  = df["Close"]
    bh_ret = (1 + close.pct_change().fillna(0)).cumprod()

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(bh_ret.index, bh_ret.values, color="gray",
            lw=1, ls="--", label="Buy & Hold", alpha=0.7)

    colors = plt.cm.tab10(np.linspace(0, 1, n))
    for idx, (fit, i, j, cell) in enumerate(top):
        params  = cell.genome.decode()
        signals = generate_signals(df, params).shift(1).fillna(0)
        ret     = signals * close.pct_change().fillna(0)
        equity  = (1 + ret).cumprod()
        label   = f"V{i}/T{j} f={fit:.2f} sr={cell.sharpe:.2f}"
        ax.plot(equity.index, equity.values,
                color=colors[idx], lw=1.2, label=label)

    ax.set_title(f"Top {n} Strategy Equity Curves")
    ax.set_ylabel("Equity (1 = start)")
    ax.set_xlabel("Date")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    plt.tight_layout()
    if save:
        p = PLOTS_DIR / "top_strategies.png"
        plt.savefig(p, dpi=120, bbox_inches="tight")
        plt.close()
        return str(p)
    else:
        plt.show()
        return None
