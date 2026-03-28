"""
visualize.py — context-window-ai/cache-hit-demo

Reads results/cache_benchmark_results.json and produces a 2×2 chart:
  - Cost per turn
  - Latency per turn
  - Cache hit rate per turn (B & C only)
  - Total cost comparison (bar chart with savings annotation)

Usage:
    python visualize.py
    python visualize.py --no-show   # save only, don't open window
"""

import argparse
import json
import os
import sys

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

RESULTS_PATH = "results/cache_benchmark_results.json"
OUTPUT_PATH = "results/benchmark_chart.png"

# Brand palette
COLORS = {
    "A": "#ef4444",  # red   — no cache
    "B": "#3b82f6",  # blue  — cached, Anthropic
    "C": "#10b981",  # green — cached, Bedrock
}
LABELS = {
    "A": "No Cache (Anthropic)",
    "B": "Cache ON — Anthropic",
    "C": "Cache ON — Bedrock",
}
MARKERS = {"A": "o", "B": "s", "C": "^"}


def load_results(path: str = RESULTS_PATH) -> dict:
    if not os.path.exists(path):
        print(f"❌  Results file not found: {path}")
        print("    Run benchmark.py first.")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def make_charts(data: dict, show: bool = True) -> str:
    runs = {k: data[k] for k in ["A", "B", "C"]}
    turns = list(range(1, len(runs["A"]) + 1))

    meta = data.get("meta", {})
    model = meta.get("model", "unknown model")
    ts = meta.get("timestamp", "")
    subtitle = f"{model}  ·  {len(turns)} questions  ·  {ts}" if ts else model

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle(
        "OpenRouter Prompt Cache Benchmark",
        fontsize=16,
        fontweight="bold",
        y=0.99,
    )
    fig.text(0.5, 0.96, subtitle, ha="center", fontsize=10, color="#6b7280")

    # ── 1. Cost per turn ──────────────────────────────────────────────────────
    ax1 = axes[0, 0]
    for key, results in runs.items():
        costs = [r["cost_usd"] for r in results]
        ax1.plot(
            turns,
            costs,
            color=COLORS[key],
            label=LABELS[key],
            marker=MARKERS[key],
            markersize=5,
            linewidth=2,
        )
    ax1.set_title("Cost per Turn", fontweight="semibold")
    ax1.set_xlabel("Turn")
    ax1.set_ylabel("Cost (USD)")
    ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter("$%.4f"))
    ax1.legend(fontsize=9)
    ax1.grid(alpha=0.25)
    ax1.set_xticks(turns)

    # ── 2. Latency per turn ───────────────────────────────────────────────────
    ax2 = axes[0, 1]
    for key, results in runs.items():
        latencies = [r["latency_s"] for r in results]
        ax2.plot(
            turns,
            latencies,
            color=COLORS[key],
            label=LABELS[key],
            marker=MARKERS[key],
            markersize=5,
            linewidth=2,
        )
    ax2.set_title("Latency per Turn", fontweight="semibold")
    ax2.set_xlabel("Turn")
    ax2.set_ylabel("Latency (s)")
    ax2.legend(fontsize=9)
    ax2.grid(alpha=0.25)
    ax2.set_xticks(turns)

    # ── 3. Cache hit rate — B & C only ───────────────────────────────────────
    ax3 = axes[1, 0]
    for key in ["B", "C"]:
        results = runs[key]
        hit_rates = [r["cache_hit_rate"] * 100 for r in results]
        ax3.plot(
            turns,
            hit_rates,
            color=COLORS[key],
            label=LABELS[key],
            marker=MARKERS[key],
            markersize=5,
            linewidth=2,
        )
    ax3.axhline(
        y=80, color="#9ca3af", linestyle="--", linewidth=1, label="80% reference"
    )
    ax3.set_title("Cache Hit Rate by Turn", fontweight="semibold")
    ax3.set_xlabel("Turn")
    ax3.set_ylabel("Cache Hit Rate (%)")
    ax3.set_ylim(-5, 110)
    ax3.yaxis.set_major_formatter(mticker.PercentFormatter())
    ax3.legend(fontsize=9)
    ax3.grid(alpha=0.25)
    ax3.set_xticks(turns)
    # Annotate Turn 1 miss
    ax3.annotate(
        "Turn 1\nalways cold",
        xy=(1, runs["B"][0]["cache_hit_rate"] * 100),
        xytext=(2.2, 12),
        fontsize=8,
        color="#6b7280",
        arrowprops=dict(arrowstyle="->", color="#9ca3af", lw=0.8),
    )

    # ── 4. Total cost bar chart ───────────────────────────────────────────────
    ax4 = axes[1, 1]
    keys = ["A", "B", "C"]
    total_costs = [sum(r["cost_usd"] for r in runs[k]) for k in keys]
    x = np.arange(len(keys))
    bars = ax4.bar(
        x,
        total_costs,
        color=[COLORS[k] for k in keys],
        width=0.5,
        edgecolor="white",
        linewidth=0.8,
    )
    ax4.set_xticks(x)
    ax4.set_xticklabels([LABELS[k] for k in keys], fontsize=9)
    ax4.set_title(f"Total Cost for {len(turns)} Questions", fontweight="semibold")
    ax4.set_ylabel("Total Cost (USD)")
    ax4.yaxis.set_major_formatter(mticker.FormatStrFormatter("$%.3f"))
    ax4.grid(alpha=0.25, axis="y")

    # Value labels on bars
    for bar, cost in zip(bars, total_costs):
        ax4.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(total_costs) * 0.015,
            f"${cost:.4f}",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )

    # Savings annotation box
    if total_costs[0] > 0:
        savings_lines = []
        for i in range(1, len(keys)):
            pct = (1 - total_costs[i] / total_costs[0]) * 100
            savings_lines.append(f"{keys[i]} saves {pct:.0f}% vs A")
        ax4.text(
            0.97,
            0.97,
            "\n".join(savings_lines),
            transform=ax4.transAxes,
            ha="right",
            va="top",
            fontsize=9,
            color="#374151",
            bbox=dict(
                boxstyle="round,pad=0.4",
                facecolor="#f9fafb",
                edgecolor="#e5e7eb",
                linewidth=0.8,
            ),
        )

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight")
    print(f"✅  Chart saved → {OUTPUT_PATH}")

    if show:
        plt.show()

    return OUTPUT_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize cache benchmark results")
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Save chart without opening a window",
    )
    parser.add_argument(
        "--results",
        default=RESULTS_PATH,
        help=f"Path to results JSON (default: {RESULTS_PATH})",
    )
    args = parser.parse_args()

    data = load_results(args.results)
    make_charts(data, show=not args.no_show)


if __name__ == "__main__":
    main()
