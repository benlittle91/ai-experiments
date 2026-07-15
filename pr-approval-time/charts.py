"""Matplotlib chart rendering for pr_compare.

Kept separate from report.py so that --no-plot users never trigger a
matplotlib import.
"""

from __future__ import annotations

from pathlib import Path

from models import Snapshot, SpGroup


def plot_comparison(a: Snapshot, b: Snapshot, output_dir: str, ai_adoption: bool = False) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("  matplotlib not available — skipping plots.")
        print("  Install with: pip install matplotlib")
        return

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if ai_adoption:
        label_a = f"Baseline ({a.period.from_} → {a.period.to})"
        label_b = f"Post-AI ({b.period.from_} → {b.period.to})"
        main_title = "PR Time to 2nd Approval — Pre-AI Baseline vs Post-Copilot Adoption"
    else:
        label_a = f"{a.period.from_} → {a.period.to}"
        label_b = f"{b.period.from_} → {b.period.to}"
        main_title = "PR Time to 2nd Approval — Period Comparison"
    COLOR_A = "#4C72B0"
    COLOR_B = "#DD8452"

    def _annotate_bars(ax, bars):
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.annotate(
                    f"{h:.2f}",
                    xy=(bar.get_x() + bar.get_width() / 2, h),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )

    # --- Plot 1: Overall stats (days + days/SP side by side) ---
    metrics = ["median", "p75", "avg"]
    metric_labels = ["Median", "P75", "Avg"]
    x = np.arange(len(metrics))
    width = 0.35

    stat_keys = [("days", "Days to 2nd Approval"), ("days_per_sp", "Days per Story Point")]
    has_dsp = any(
        v is not None
        for d in (a.days_per_sp.as_dict(), b.days_per_sp.as_dict())
        for v in d.values()
    )
    active_stats = stat_keys if has_dsp else stat_keys[:1]

    fig, axes = plt.subplots(1, len(active_stats), figsize=(7 * len(active_stats), 5))
    if len(active_stats) == 1:
        axes = [axes]
    fig.suptitle(main_title, fontsize=14, fontweight="bold")

    for ax, (key, title) in zip(axes, active_stats):
        sa = getattr(a, key).as_dict()
        sb = getattr(b, key).as_dict()
        vals_a = [sa.get(m) or 0 for m in metrics]
        vals_b = [sb.get(m) or 0 for m in metrics]
        bars_a = ax.bar(x - width / 2, vals_a, width, label=label_a, color=COLOR_A, alpha=0.85)
        bars_b = ax.bar(x + width / 2, vals_b, width, label=label_b, color=COLOR_B, alpha=0.85)
        _annotate_bars(ax, list(bars_a) + list(bars_b))
        ax.set_title(title, fontsize=12)
        ax.set_xticks(x)
        ax.set_xticklabels(metric_labels)
        ax.set_ylabel("Days")
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    p1 = out / "overall_stats.png"
    plt.savefig(p1, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {p1}")

    # --- Plot 2: Per-repo avg days ---
    repos_a = {r.name: r.avg_days for r in a.repos}
    repos_b = {r.name: r.avg_days for r in b.repos}
    repos_with_data = sorted(
        r for r in set(repos_a) | set(repos_b)
        if repos_a.get(r) is not None or repos_b.get(r) is not None
    )

    if repos_with_data:
        fig_w = max(10, len(repos_with_data) * 0.9 + 2)
        fig, ax = plt.subplots(figsize=(fig_w, 6))
        x = np.arange(len(repos_with_data))
        bars_a = ax.bar(x - width / 2, [repos_a.get(r) or 0 for r in repos_with_data],
                        width, label=label_a, color=COLOR_A, alpha=0.85)
        bars_b = ax.bar(x + width / 2, [repos_b.get(r) or 0 for r in repos_with_data],
                        width, label=label_b, color=COLOR_B, alpha=0.85)
        _annotate_bars(ax, list(bars_a) + list(bars_b))
        ax.set_title("Per-Repo Avg Days to 2nd Approval", fontsize=13, fontweight="bold")
        ax.set_xticks(x)
        short_names = [r[:28] + "…" if len(r) > 28 else r for r in repos_with_data]
        ax.set_xticklabels(short_names, rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("Avg Days")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        p2 = out / "per_repo_avg.png"
        plt.savefig(p2, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: {p2}")

    # --- Plot 3: Story point groups — median days ---
    sp_a = a.storypoint_groups
    sp_b = b.storypoint_groups
    all_sp = sorted(
        set(sp_a) | set(sp_b),
        key=lambda x: (0, float(x)) if x.replace(".", "", 1).isdigit() else (1, x),
    )
    if all_sp:
        fig, ax = plt.subplots(figsize=(max(8, len(all_sp) * 1.4 + 2), 5))
        x = np.arange(len(all_sp))
        bars_a = ax.bar(x - width / 2, [sp_a.get(sp, SpGroup()).median_days or 0 for sp in all_sp],
                        width, label=label_a, color=COLOR_A, alpha=0.85)
        bars_b = ax.bar(x + width / 2, [sp_b.get(sp, SpGroup()).median_days or 0 for sp in all_sp],
                        width, label=label_b, color=COLOR_B, alpha=0.85)
        _annotate_bars(ax, list(bars_a) + list(bars_b))
        ax.set_title("Median Days to 2nd Approval by Story Points", fontsize=13, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels([f"{sp} SP" for sp in all_sp])
        ax.set_ylabel("Median Days")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        p3 = out / "storypoints.png"
        plt.savefig(p3, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: {p3}")

    # --- Plot 4: Story point groups — median days per SP ---
    if all_sp and any(
        sp_a.get(sp, SpGroup()).median_dsp is not None
        or sp_b.get(sp, SpGroup()).median_dsp is not None
        for sp in all_sp
    ):
        fig, ax = plt.subplots(figsize=(max(8, len(all_sp) * 1.4 + 2), 5))
        x = np.arange(len(all_sp))
        bars_a = ax.bar(x - width / 2, [sp_a.get(sp, SpGroup()).median_dsp or 0 for sp in all_sp],
                        width, label=label_a, color=COLOR_A, alpha=0.85)
        bars_b = ax.bar(x + width / 2, [sp_b.get(sp, SpGroup()).median_dsp or 0 for sp in all_sp],
                        width, label=label_b, color=COLOR_B, alpha=0.85)
        _annotate_bars(ax, list(bars_a) + list(bars_b))
        ax.set_title("Median Days per Story Point by Story Point Size", fontsize=13, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels([f"{sp} SP" for sp in all_sp])
        ax.set_ylabel("Median Days / SP")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        p4 = out / "storypoints_dsp.png"
        plt.savefig(p4, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: {p4}")

