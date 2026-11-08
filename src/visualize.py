"""Publication-ready figures (vector PDF + 300 DPI PNG).

Rules of scientific visualization applied everywhere:
  1. Labelled axes with units / scale descriptions (log scale for odds ratios).
  2. Uncertainty always shown (Wilson CI bands/bars, bootstrap CI, 95 % CI of odds ratios).
  3. Colour-blind-safe palette + distinct markers / linestyles / hatches.

Figures (file names follow the Task 3 template):
  fig1_latency_vs_load          difficulty falling asleep (sleep-latency proxy) vs. stress level
  fig2_distribution_boxplot     stress-level distribution by self-rated sleep quality
  fig3_device_use_vs_sleep_quality   RQ1: share of good sleepers by pre-bedtime device use
  fig4_odds_ratios_forest       RQ2 / RQ3: adjusted odds ratios with 95 % CI
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns

from src import process_data as pdta

FIG_DIR = Path("reports/figures")
DPI = 300
SEED = 42
PALETTE = sns.color_palette("colorblind")
HATCH = ["//", "..", "xx"]


def _setup() -> None:
    sns.set_theme(style="whitegrid", context="paper", font_scale=1.2)
    plt.rcParams.update({"figure.dpi": 120, "savefig.bbox": "tight"})


def _save(fig, name: str, fig_dir: Path = FIG_DIR) -> None:
    fig_dir = Path(fig_dir)
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_dir / f"{name}.pdf")             # vector
    fig.savefig(fig_dir / f"{name}.png", dpi=DPI)    # raster, >= 300 DPI
    plt.close(fig)


def fig_latency_vs_load(d: pd.DataFrame, fig_dir: Path = FIG_DIR) -> None:
    """% of students with frequent difficulty falling asleep (Often / Almost always)
    by stress level, split by night-time caffeine use; Wilson 95 % CI bands."""
    _setup()
    styles = {0: dict(color=PALETTE[0], marker="o", linestyle="-", label="No night-time caffeine"),
              1: dict(color=PALETTE[3], marker="^", linestyle="--", label="Night-time caffeine")}
    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    levels = [1, 2, 3, 4, 5]
    for cf, s in styles.items():
        pts, lo, hi = [], [], []
        for lv in levels:
            g = d[(d.caffeine == cf) & (d.stress == lv)]
            k, n = int(g.freq_difficulty.sum()), len(g)
            l, h = pdta.wilson(k, n)
            pts.append(100 * k / n); lo.append(100 * l); hi.append(100 * h)
        ax.plot(levels, pts, color=s["color"], marker=s["marker"], linestyle=s["linestyle"],
                lw=2, label=f"{s['label']} (n={int((d.caffeine == cf).sum())})")
        ax.fill_between(levels, lo, hi, color=s["color"], alpha=0.2)
    ax.set_xticks(levels)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Current stress level (self-rated, 1-5 scale)")
    ax.set_ylabel("Frequent difficulty falling asleep (% of students)")
    ax.set_title("Difficulty falling asleep vs. stress (shaded: 95 % Wilson CI)")
    ax.legend(frameon=True, fontsize=9, loc="upper left")
    _save(fig, "fig1_latency_vs_load", fig_dir)


def fig_distribution_boxplot(d: pd.DataFrame, fig_dir: Path = FIG_DIR) -> None:
    """Stress-level distribution by self-rated sleep quality (jittered points + box)."""
    _setup()
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    data = [d.loc[d.Sleep_quality == q, "stress"] for q in pdta.QUAL_ORDER]
    bp = ax.boxplot(data, patch_artist=True, widths=0.55, showfliers=False,
                    medianprops=dict(color="black", lw=1.8))
    for i, box in enumerate(bp["boxes"]):
        box.set(facecolor=PALETTE[i], alpha=0.55, hatch=HATCH[i], edgecolor="black")
    rng = np.random.default_rng(SEED)
    for i, g in enumerate(data, start=1):
        ax.scatter(i + rng.uniform(-0.17, 0.17, len(g)), g + rng.uniform(-0.12, 0.12, len(g)),
                   s=10, color="black", alpha=0.35, zorder=3)
    ax.set_xticklabels([f"{q}\n(n={len(g)})" for q, g in zip(pdta.QUAL_ORDER, data)])
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_xlabel("Self-rated sleep quality")
    ax.set_ylabel("Current stress level (1-5 scale)")
    ax.set_title("Stress by sleep quality (box: p25-p75, line: median)")
    _save(fig, "fig2_distribution_boxplot", fig_dir)


def fig_device_vs_quality(d: pd.DataFrame, fig_dir: Path = FIG_DIR) -> None:
    """RQ1: share of good sleepers with Wilson 95 % CI by pre-bedtime device use."""
    _setup()
    g = pdta.share_by_device(d)
    pct, lo, hi = g.rate * 100, g.ci_low * 100, g.ci_high * 100
    fig, ax = plt.subplots(figsize=(5.6, 4.2))
    for i in range(len(g)):
        ax.bar(i, pct[i], width=0.55, color=PALETTE[i], alpha=0.6, hatch=HATCH[i], edgecolor="black")
    ax.errorbar(range(len(g)), pct, yerr=[pct - lo, hi - pct], fmt="D", color="black", capsize=6,
                lw=1.6, markersize=6, label="95 % Wilson CI")
    for i, (p, h, n) in enumerate(zip(pct, hi, g.n)):
        ax.text(i, h + 2, f"{p:.0f} % (n={n})", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(range(len(g)))
    ax.set_xticklabels(g.group)
    ax.set_ylim(0, 105)
    ax.set_xlabel("Electronic device use before bed")
    ax.set_ylabel("Students with good sleep quality (%)")
    ax.set_title("RQ1: good sleep quality by pre-bedtime device use")
    ax.legend(frameon=True, fontsize=9, loc="upper left")
    _save(fig, "fig3_device_use_vs_sleep_quality", fig_dir)


def fig_forest(tests: pd.DataFrame, fig_dir: Path = FIG_DIR) -> None:
    """RQ2 / RQ3: adjusted odds ratios (log scale) with 95 % CI."""
    _setup()
    panels = [("RQ2 ordinal logit", "RQ2: difficulty falling asleep\n(ordered logit, OR > 1 = more difficulty)",
               PALETTE[0], "o"),
              ("RQ3 logistic", "RQ3: good sleep quality\n(logistic, OR > 1 = higher odds)",
               PALETTE[3], "s")]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharex=True)
    for ax, (model, title, col, mk) in zip(axes, panels):
        t = tests[tests.model == model].iloc[::-1]
        y = np.arange(len(t))
        ax.errorbar(t.estimate, y, xerr=[t.estimate - t.ci_low, t.ci_high - t.estimate], fmt=mk,
                    color=col, ecolor="black", capsize=4, markersize=7, lw=1.4)
        ax.axvline(1, color="gray", linestyle="--", lw=1.1)
        ax.set_yticks(y)
        ax.set_yticklabels(t.term, fontsize=9)
        ax.set_xscale("log")
        ax.set_xticks([0.25, 0.5, 1, 2, 4])
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.xaxis.set_minor_formatter(mticker.NullFormatter())
        ax.set_xlabel("Adjusted odds ratio (log scale, 95 % CI)")
        ax.set_title(title, fontsize=10)
    fig.tight_layout(w_pad=3)
    _save(fig, "fig4_odds_ratios_forest", fig_dir)


def make_all(d: pd.DataFrame, tests: pd.DataFrame, fig_dir: Path = FIG_DIR) -> None:
    fig_latency_vs_load(d, fig_dir)
    fig_distribution_boxplot(d, fig_dir)
    fig_device_vs_quality(d, fig_dir)
    fig_forest(tests, fig_dir)


if __name__ == "__main__":
    d, _, _, tests = pdta.run()
    make_all(d, tests)
    print("Figures written to", FIG_DIR)
