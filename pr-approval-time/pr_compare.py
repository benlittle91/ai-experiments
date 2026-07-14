#!/usr/bin/env python3
"""Compare two pr_approval_time.sh snapshots and plot month-over-month changes.

Usage:
  python3 pr_compare.py snapshot_a.json snapshot_b.json
  python3 pr_compare.py snapshot_a.json snapshot_b.json --output-dir ./charts
  python3 pr_compare.py snapshot_a.json snapshot_b.json --no-plot
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# SP buckets with fewer than this many PRs are flagged as low-confidence.
# A median/avg from 1–2 data points is statistically meaningless and can
# swing wildly between periods due to a single outlier PR.
MIN_SP_COUNT = 5


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _fmt(val: float | None, decimals: int = 2) -> str:
    return "—" if val is None else f"{val:.{decimals}f}"


def _delta(a: float | None, b: float | None, decimals: int = 2) -> str:
    if a is None or b is None:
        return "—"
    d = b - a
    sign = "+" if d > 0 else ""
    return f"{sign}{d:.{decimals}f}"


def _delta_int(a: int, b: int) -> str:
    d = b - a
    sign = "+" if d > 0 else ""
    return f"{sign}{d}"


def _trend_word(delta: float | None, lower_is_better: bool = True) -> str:
    """Return a plain-English trend word for a numeric delta."""
    if delta is None:
        return "held steady"
    if abs(delta) < 0.01:
        return "held steady"
    if lower_is_better:
        return "improved" if delta < 0 else "worsened"
    return "improved" if delta > 0 else "worsened"


def _iqr_bounds(vals: list[float], k: float = 3.0) -> tuple[float, float]:
    """Return (lower, upper) outlier fences using k * IQR rule."""
    if len(vals) < 4:
        return (float("-inf"), float("inf"))
    s = sorted(vals)
    n = len(s)
    q1 = s[n // 4]
    q3 = s[(3 * n) // 4]
    iqr = q3 - q1
    return (q1 - k * iqr, q3 + k * iqr)


def _detect_outliers(
    vals: list[float], k: float = 3.0
) -> tuple[list[float], list[float]]:
    """Split vals into (clean, outliers) using k * IQR fences."""
    if not vals:
        return [], []
    _, upper = _iqr_bounds(vals, k)
    clean = [v for v in vals if v <= upper]
    outliers = [v for v in vals if v > upper]
    return clean, outliers


def _stats_dict_from_vals(vals: list[float]) -> dict:
    """Compute avg/median/p75 from a list, returning None-filled dict if empty."""
    from math import floor, ceil

    def pct(s: list[float], p: float) -> float | None:
        if not s:
            return None
        if len(s) == 1:
            return s[0]
        k = (len(s) - 1) * (p / 100.0)
        f, c = floor(k), ceil(k)
        if f == c:
            return s[int(k)]
        return s[f] * (c - k) + s[c] * (k - f)

    if not vals:
        return {"avg": None, "median": None, "p75": None}
    s = sorted(vals)
    return {
        "avg": round(sum(s) / len(s), 4),
        "median": round(pct(s, 50), 4),
        "p75": round(pct(s, 75), 4),
    }


def _period_labels(a: dict, b: dict, ai_adoption: bool) -> tuple[str, str]:
    pa, pb = a["period"], b["period"]
    if ai_adoption:
        return (
            f"{pa['from']} to {pa['to']} (pre-AI baseline, human-only reviews)",
            f"{pb['from']} to {pb['to']} (post-AI adoption, Copilot on every PR)",
        )
    return f"{pa['from']} to {pa['to']}", f"{pb['from']} to {pb['to']}"


def render_ai_impact_summary(a: dict, b: dict) -> str:
    """Print an AI adoption-specific impact narrative."""
    out: list[str] = []
    def w(s: str = "") -> None:
        out.append(s)

    pa, pb = a["period"], b["period"]
    label_a = f"{pa['from']} to {pa['to']}"
    label_b = f"{pb['from']} to {pb['to']}"

    sa, sb = a["stats"]["days"], b["stats"]["days"]
    med_a, med_b = sa.get("median"), sb.get("median")
    p75_a, p75_b = sa.get("p75"), sb.get("p75")
    avg_a, avg_b = sa.get("avg"), sb.get("avg")

    dpa, dpb = a["stats"]["days_per_sp"], b["stats"]["days_per_sp"]
    dsp_med_a, dsp_med_b = dpa.get("median"), dpb.get("median")

    sma, smb = a["summary"], b["summary"]
    vol_a, vol_b = sma.get("total_examined", 0), smb.get("total_examined", 0)
    apr_a, apr_b = sma.get("total_approved", 0), smb.get("total_approved", 0)

    w()
    w("════════════════════════════════════════════════════════════════════════")
    w("  AI ADOPTION IMPACT — COPILOT CODE REVIEW")
    w("════════════════════════════════════════════════════════════════════════")
    w()
    w("  METHODOLOGY")
    w(f"  Baseline  : {label_a}  — human reviewers only")
    w(f"  Post-AI   : {label_b}  — Copilot reviews every PR")
    w()
    w("  This comparison uses a time-based cohort rather than per-PR detection.")
    w("  All PRs in the post-AI period are assumed to have received a Copilot")
    w("  review. This is a reasonable proxy when rollout is team-wide and")
    w("  consistent, but note that other factors (team velocity, PR size,")
    w("  holiday periods) may also influence the delta. One month of post-AI")
    w("  data is early-signal only — treat trends with appropriate caution.")
    w()

    # Headline: median
    w("  HEADLINE — MEDIAN TIME TO 2ND APPROVAL")
    if med_a is not None and med_b is not None:
        med_delta = med_b - med_a
        direction = "decreased" if med_delta < 0 else "increased"
        sign = "" if med_delta < 0 else "+"
        w(
            f"  Median time to second approval {direction} from {med_a:.2f} days (baseline)"
            f" to {med_b:.2f} days (post-AI) — a change of {sign}{med_delta:.2f} days."
        )
        if abs(med_delta) < 0.1:
            w("  This is a negligible shift; median performance is effectively unchanged.")
        elif med_delta < 0:
            w("  The typical PR is moving through review faster after AI adoption.")
        else:
            w("  The typical PR is taking longer to reach a second approval.")
            w("  This does not necessarily indicate AI is slowing reviews — volume")
            w("  changes, PR complexity, or reviewer availability may be contributing.")
    else:
        w("  Insufficient data to compare median times.")
    w()

    # Tail: p75 (most actionable for slow PRs)
    w("  TAIL PERFORMANCE — P75 (SLOWEST QUARTER OF PRS)")
    if p75_a is not None and p75_b is not None:
        p75_delta = p75_b - p75_a
        direction = "decreased" if p75_delta < 0 else "increased"
        sign = "" if p75_delta < 0 else "+"
        w(
            f"  The 75th percentile {direction} from {p75_a:.2f} to {p75_b:.2f} days"
            f" ({sign}{p75_delta:.2f} days)."
        )
        w(
            "  The p75 captures your slowest-moving quarter of PRs — often the ones"
            " most likely to benefit from an AI first-pass that surfaces issues early."
        )
        if p75_delta < -0.5:
            w("  A meaningful drop here suggests AI is helping unblock complex or slow PRs.")
        elif p75_delta > 0.5:
            w("  A rise here warrants monitoring — slow PRs are getting slower.")
    else:
        w("  Insufficient data to compare p75 times.")
    w()

    # Effort-adjusted
    if dsp_med_a is not None and dsp_med_b is not None:
        dsp_delta = dsp_med_b - dsp_med_a
        direction = "decreased" if dsp_delta < 0 else "increased"
        sign = "" if dsp_delta < 0 else "+"
        w("  EFFORT-ADJUSTED — MEDIAN DAYS PER STORY POINT")
        w(
            f"  When normalised for ticket complexity, the median days per story point"
            f" {direction} from {dsp_med_a:.3f} to {dsp_med_b:.3f} ({sign}{dsp_delta:.3f} d/SP)."
        )
        w(
            "  This accounts for whether the team is shipping larger or smaller tickets"
            " between periods, giving a fairer like-for-like comparison."
        )
        w()

    # Volume context
    w("  VOLUME CONTEXT")
    vol_delta = vol_b - vol_a
    apr_delta = apr_b - apr_a
    vol_sign = "+" if vol_delta >= 0 else ""
    apr_sign = "+" if apr_delta >= 0 else ""
    w(f"  PRs examined : {vol_a} (baseline) → {vol_b} (post-AI)  [{vol_sign}{vol_delta}]")
    w(f"  PRs w/ 2+ approvals: {apr_a} → {apr_b}  [{apr_sign}{apr_delta}]")
    w()
    w("  Note: a rising PR volume can inflate average and p75 times independently")
    w("  of AI impact. Interpret deltas in the context of throughput changes.")
    w()

    # What to watch next
    w("  WHAT TO WATCH")
    w("  - Run this comparison monthly as more post-AI data accumulates.")
    w("  - Watch the p75 trend — sustained improvement there is the strongest")
    w("    signal that AI reviews are surfacing issues before human reviewers.")
    w("  - If median days/SP improves while PR volume rises, that is a strong")
    w("    positive signal that the team is delivering more with less review friction.")
    w()
    return "\n".join(out)

def render_executive_summary(a: dict, b: dict, ai_adoption: bool = False) -> str:
    """Print a concise executive and leadership summary in plain prose."""
    out: list[str] = []
    def w(s: str = "") -> None:
        out.append(s)

    label_a, label_b = _period_labels(a, b, ai_adoption)

    sma, smb = a["summary"], b["summary"]
    sa, sb = a["stats"]["days"], b["stats"]["days"]

    med_a, med_b = sa.get("median"), sb.get("median")
    avg_a, avg_b = sa.get("avg"), sb.get("avg")
    p75_a, p75_b = sa.get("p75"), sb.get("p75")

    med_delta = (med_b - med_a) if med_a is not None and med_b is not None else None
    avg_delta = (avg_b - avg_a) if avg_a is not None and avg_b is not None else None
    p75_delta = (p75_b - p75_a) if p75_a is not None and p75_b is not None else None

    vol_a = sma.get("total_examined", 0)
    vol_b = smb.get("total_examined", 0)
    apr_a = sma.get("total_approved", 0)
    apr_b = smb.get("total_approved", 0)
    vol_delta = vol_b - vol_a

    w()
    w("════════════════════════════════════════════════════════════════════════")
    w("  EXECUTIVE SUMMARY")
    w("════════════════════════════════════════════════════════════════════════")
    w()
    w("  This report compares pull request review performance across two periods:")
    w(f"    Period A : {label_a}")
    w(f"               {vol_a} pull requests examined, {apr_a} with two or more approvals")
    w(f"    Period B : {label_b}")
    w(f"               {vol_b} pull requests examined, {apr_b} with two or more approvals")
    w()

    # Headline metric
    w("  HEADLINE METRIC — MEDIAN TIME TO SECOND APPROVAL")
    if med_a is not None and med_b is not None:
        trend = _trend_word(med_delta)
        if trend == "held steady":
            w(f"  The median time for a pull request to receive a second approval held steady")
            w(f"  at {_fmt(med_b)} days across both periods.")
        else:
            direction = "reduced" if med_delta < 0 else "increased"
            w(
                f"  The median time for a pull request to receive a second approval {trend} by"
                f" {abs(med_delta):.2f} days,"
            )
            w(
                f"  {direction} from {_fmt(med_a)} days in Period A to {_fmt(med_b)} days in Period B."
            )
    else:
        w("  Insufficient data to calculate median time to second approval.")
    w()

    # Supporting metrics
    w("  SUPPORTING METRICS")
    if avg_a is not None and avg_b is not None:
        trend = _trend_word(avg_delta)
        if trend == "held steady":
            w(f"  The average time to second approval held steady at {_fmt(avg_b)} days.")
        else:
            direction = "reduced" if avg_delta < 0 else "increased"
            w(
                f"  The average time to second approval {trend} by {abs(avg_delta):.2f} days,"
                f" {direction} from {_fmt(avg_a)} to {_fmt(avg_b)} days."
            )
    if p75_a is not None and p75_b is not None:
        trend = _trend_word(p75_delta)
        if trend == "held steady":
            w(f"  The 75th percentile time to second approval held steady at {_fmt(p75_b)} days.")
        else:
            direction = "reduced" if p75_delta < 0 else "increased"
            w(
                f"  The 75th percentile time to second approval (the slowest quarter of pull requests)"
                f" {trend} by {abs(p75_delta):.2f} days,"
            )
            w(f"  {direction} from {_fmt(p75_a)} to {_fmt(p75_b)} days.")
    if vol_delta == 0:
        w(f"  Pull request volume remained unchanged at {vol_b} examined.")
    elif vol_delta > 0:
        w(
            f"  Pull request volume increased by {vol_delta} pull requests,"
            f" from {vol_a} to {vol_b} examined."
        )
    else:
        w(
            f"  Pull request volume decreased by {abs(vol_delta)} pull requests,"
            f" from {vol_a} to {vol_b} examined."
        )

    # Effort-adjusted metric
    dpa, dpb = a["stats"]["days_per_sp"], b["stats"]["days_per_sp"]
    dsp_med_a, dsp_med_b = dpa.get("median"), dpb.get("median")
    if dsp_med_a is not None and dsp_med_b is not None:
        dsp_delta = dsp_med_b - dsp_med_a
        trend = _trend_word(dsp_delta)
        w()
        w("  EFFORT-ADJUSTED PERFORMANCE — DAYS PER STORY POINT")
        if trend == "held steady":
            w(
                f"  When accounting for work complexity, the median days per story point held steady"
                f" at {_fmt(dsp_med_b)} days per story point."
            )
        else:
            direction = "reduced" if dsp_delta < 0 else "increased"
            w(
                f"  When accounting for work complexity, the median days per story point {trend} by"
                f" {abs(dsp_delta):.2f} days,"
            )
            w(
                f"  {direction} from {_fmt(dsp_med_a)} to {_fmt(dsp_med_b)} days per story point."
            )
    w()
    return "\n".join(out)

def render_delivery_leads_summary(a: dict, b: dict, ai_adoption: bool = False) -> str:
    """Print an operational summary for delivery leads: per-repository movements,
    story point trends, and data coverage observations."""
    out: list[str] = []
    def w(s: str = "") -> None:
        out.append(s)

    label_a, label_b = _period_labels(a, b, ai_adoption)

    sma, smb = a["summary"], b["summary"]

    repos_a = {r["name"]: r for r in a.get("repos", [])}
    repos_b = {r["name"]: r for r in b.get("repos", [])}
    all_repos = sorted(set(repos_a) | set(repos_b))

    # Repositories that gained or lost data between periods
    new_repos = sorted(set(repos_b) - set(repos_a))
    dropped_repos = sorted(set(repos_a) - set(repos_b))

    # Compute per-repository deltas where both periods have data
    repo_deltas: list[tuple[str, float, float, float]] = []  # (name, avg_a, avg_b, delta)
    for repo in all_repos:
        avg_a = repos_a.get(repo, {}).get("avg_days")
        avg_b = repos_b.get(repo, {}).get("avg_days")
        if avg_a is not None and avg_b is not None:
            repo_deltas.append((repo, avg_a, avg_b, avg_b - avg_a))

    most_improved = sorted(repo_deltas, key=lambda x: x[3])[:3]
    most_worsened = sorted(repo_deltas, key=lambda x: x[3], reverse=True)[:3]

    sp_a = a.get("storypoint_groups", {})
    sp_b = b.get("storypoint_groups", {})
    all_sp = sorted(
        set(sp_a) | set(sp_b),
        key=lambda x: (0, float(x)) if x.replace(".", "", 1).isdigit() else (1, x),
    )

    w("════════════════════════════════════════════════════════════════════════")
    w("  DELIVERY LEADS SUMMARY")
    w("════════════════════════════════════════════════════════════════════════")
    w()
    w(f"  Comparing Period A ({label_a}) against Period B ({label_b}).")
    w()

    # --- Per-repository movements ---
    if repo_deltas:
        w("  REPOSITORY PERFORMANCE MOVEMENTS")
        w()
        if most_improved and most_improved[0][3] < -0.01:
            w("  Repositories with the most improved average time to second approval:")
            for name, avg_a_val, avg_b_val, delta in most_improved:
                if delta < -0.01:
                    w(
                        f"    {name}: reduced by {abs(delta):.2f} days"
                        f" (from {_fmt(avg_a_val)} to {_fmt(avg_b_val)} days on average)"
                    )
            w()
        if most_worsened and most_worsened[0][3] > 0.01:
            w("  Repositories with the most worsened average time to second approval:")
            for name, avg_a_val, avg_b_val, delta in most_worsened:
                if delta > 0.01:
                    w(
                        f"    {name}: increased by {delta:.2f} days"
                        f" (from {_fmt(avg_a_val)} to {_fmt(avg_b_val)} days on average)"
                    )
            w()

    # --- Coverage changes ---
    if new_repos or dropped_repos:
        w("  DATA COVERAGE CHANGES")
        if new_repos:
            w(
                f"  The following {'repository' if len(new_repos) == 1 else 'repositories'}"
                f" appeared in Period B but had no data in Period A:"
            )
            for r in new_repos:
                w(f"    {r}")
        if dropped_repos:
            w(
                f"  The following {'repository' if len(dropped_repos) == 1 else 'repositories'}"
                f" had data in Period A but are absent from Period B:"
            )
            for r in dropped_repos:
                w(f"    {r}")
        w()

    # --- Story point complexity trends ---
    if all_sp:
        sp_deltas: list[tuple[str, float, float, float, int, int]] = []
        low_confidence_sp: list[str] = []
        for sp in all_sp:
            cnt_a = sp_a.get(sp, {}).get("count", 0)
            cnt_b = sp_b.get(sp, {}).get("count", 0)
            med_a = sp_a.get(sp, {}).get("median_days")
            med_b = sp_b.get(sp, {}).get("median_days")
            if med_a is not None and med_b is not None:
                if cnt_a < MIN_SP_COUNT or cnt_b < MIN_SP_COUNT:
                    low_confidence_sp.append(sp)
                else:
                    sp_deltas.append((sp, med_a, med_b, med_b - med_a, cnt_a, cnt_b))

        if sp_deltas:
            w("  STORY POINT COMPLEXITY TRENDS — MEDIAN DAYS TO SECOND APPROVAL")
            w()
            for sp, med_a_val, med_b_val, delta, cnt_a, cnt_b in sp_deltas:
                trend = _trend_word(delta)
                if trend == "held steady":
                    w(
                        f"  {sp}-point work: held steady at {_fmt(med_b_val)} days"
                        f" ({cnt_a} pull requests in Period A, {cnt_b} in Period B)"
                    )
                else:
                    direction = "reduced" if delta < 0 else "increased"
                    w(
                        f"  {sp}-point work: {trend} by {abs(delta):.2f} days,"
                        f" {direction} from {_fmt(med_a_val)} to {_fmt(med_b_val)} days"
                        f" ({cnt_a} pull requests in Period A, {cnt_b} in Period B)"
                    )
            w()

        if low_confidence_sp:
            w(
                f"  The following story point {'bucket' if len(low_confidence_sp) == 1 else 'buckets'}"
                f" had fewer than {MIN_SP_COUNT} pull requests in at least one period and"
                f" {'has' if len(low_confidence_sp) == 1 else 'have'} been excluded from the trend"
                f" narrative — a median from 1–{MIN_SP_COUNT - 1} data points reflects individual"
                f" outliers, not a genuine pattern:"
            )
            for sp in low_confidence_sp:
                cnt_a = sp_a.get(sp, {}).get("count", 0)
                cnt_b = sp_b.get(sp, {}).get("count", 0)
                med_a = sp_a.get(sp, {}).get("median_days")
                med_b = sp_b.get(sp, {}).get("median_days")
                w(
                    f"    {sp}-point work: {_fmt(med_a)} → {_fmt(med_b)} days"
                    f" (n={cnt_a} in Period A, n={cnt_b} in Period B)"
                )
            w()

    # --- Exclusion / data quality notes ---
    exc_no_jira_a = sma.get("excluded_no_jira", 0)
    exc_no_jira_b = smb.get("excluded_no_jira", 0)
    exc_no_sp_a = sma.get("excluded_no_sp", 0)
    exc_no_sp_b = smb.get("excluded_no_sp", 0)
    exc_lt2_a = sma.get("excluded_lt2", 0)
    exc_lt2_b = smb.get("excluded_lt2", 0)

    any_exclusions = any([exc_no_jira_a, exc_no_jira_b, exc_no_sp_a, exc_no_sp_b, exc_lt2_a, exc_lt2_b])
    if any_exclusions:
        w("  DATA QUALITY NOTES")
        if exc_lt2_a or exc_lt2_b:
            w(
                f"  Pull requests excluded for having fewer than two approvals:"
                f" {exc_lt2_a} in Period A, {exc_lt2_b} in Period B."
            )
        if exc_no_jira_a or exc_no_jira_b:
            w(
                f"  Pull requests excluded for missing a Jira ticket reference:"
                f" {exc_no_jira_a} in Period A, {exc_no_jira_b} in Period B."
            )
        if exc_no_sp_a or exc_no_sp_b:
            w(
                f"  Pull requests excluded for missing story point estimates:"
                f" {exc_no_sp_a} in Period A, {exc_no_sp_b} in Period B."
            )
        w()
    return "\n".join(out)

def render_comparison(a: dict, b: dict, ai_adoption: bool = False) -> str:
    out: list[str] = []
    def w(s: str = "") -> None:
        out.append(s)

    label_a, label_b = _period_labels(a, b, ai_adoption)
    col_a = "Baseline" if ai_adoption else "Period A"
    col_b = "Post-AI" if ai_adoption else "Period B"

    w()
    w("════════════════════════════════════════════════════════════════════════")
    w(f"  COMPARISON")
    w(f"  {'Baseline' if ai_adoption else 'Period A'} : {label_a}")
    w(f"  {'Post-AI ' if ai_adoption else 'Period B'} : {label_b}")
    w("════════════════════════════════════════════════════════════════════════")

    # --- Volume ---
    sma, smb = a["summary"], b["summary"]
    w()
    w("  VOLUME")
    w(f"  {'Metric':<26}  {col_a:>10}  {col_b:>10}  {'Change':>10}")
    w("  " + "─" * 62)
    for key, label in [
        ("total_examined", "PRs examined"),
        ("total_approved", "PRs w/ 2+ approvals"),
        ("excluded_lt2", "Excluded (<2 approvals)"),
        ("excluded_no_jira", "Excluded (no Jira key)"),
        ("excluded_no_sp", "Excluded (no story pts)"),
    ]:
        va, vb = sma.get(key, 0), smb.get(key, 0)
        w(f"  {label:<26}  {va:>10}  {vb:>10}  {_delta_int(va, vb):>10}")

    # --- Days to 2nd approval (with optional clean stats when raw_days available) ---
    sa, sb = a["stats"]["days"], b["stats"]["days"]
    raw_a: list[float] = a.get("raw_days", [])
    raw_b: list[float] = b.get("raw_days", [])
    clean_a, outliers_a = _detect_outliers(raw_a) if raw_a else ([], [])
    clean_b, outliers_b = _detect_outliers(raw_b) if raw_b else ([], [])
    has_outliers = bool(outliers_a or outliers_b)
    clean_stats_a = _stats_dict_from_vals(clean_a) if clean_a else None
    clean_stats_b = _stats_dict_from_vals(clean_b) if clean_b else None

    w()
    w("  TIME TO 2ND APPROVAL (days) — ALL PRs")
    w(f"  {'Metric':<10}  {col_a:>10}  {col_b:>10}  {'Change':>10}")
    w("  " + "─" * 46)
    for metric in ("median", "p75", "avg"):
        w(
            f"  {metric:<10}  {_fmt(sa.get(metric)):>10}"
            f"  {_fmt(sb.get(metric)):>10}  {_delta(sa.get(metric), sb.get(metric)):>10}"
        )

    if has_outliers and (clean_stats_a or clean_stats_b):
        n_out_a = len(outliers_a)
        n_out_b = len(outliers_b)
        w()
        w(f"  TIME TO 2ND APPROVAL (days) — OUTLIERS REMOVED")
        note_a = f"  (excl. {n_out_a} outlier{'s' if n_out_a != 1 else ''})" if n_out_a else ""
        note_b = f"  (excl. {n_out_b} outlier{'s' if n_out_b != 1 else ''})" if n_out_b else ""
        w(f"  {col_a}{note_a}")
        w(f"  {col_b}{note_b}")
        w(f"  {'Metric':<10}  {col_a:>10}  {col_b:>10}  {'Change':>10}")
        w("  " + "─" * 46)
        csa = clean_stats_a or sa
        csb = clean_stats_b or sb
        for metric in ("median", "p75", "avg"):
            w(
                f"  {metric:<10}  {_fmt(csa.get(metric)):>10}"
                f"  {_fmt(csb.get(metric)):>10}  {_delta(csa.get(metric), csb.get(metric)):>10}"
            )

    # --- Days per story point (only if at least one period has data) ---
    dpa, dpb = a["stats"]["days_per_sp"], b["stats"]["days_per_sp"]
    has_dsp = any(v is not None for v in list(dpa.values()) + list(dpb.values()))
    if has_dsp:
        w()
        w("  DAYS PER STORY POINT")
        w(f"  {'Metric':<10}  {col_a:>10}  {col_b:>10}  {'Change':>10}")
        w("  " + "─" * 46)
        for metric in ("median", "p75", "avg"):
            w(
                f"  {metric:<10}  {_fmt(dpa.get(metric)):>10}"
                f"  {_fmt(dpb.get(metric)):>10}  {_delta(dpa.get(metric), dpb.get(metric)):>10}"
            )

    # --- Outlier detail ---
    if has_outliers:
        w()
        w("  OUTLIERS  (detected via 3×IQR rule — excluded from clean stats above)")
        w("  ─────────────────────────────────────────────────────")
        if outliers_a:
            for v in sorted(outliers_a, reverse=True):
                w(f"  {col_a:<10}  {v:.2f} days")
        if outliers_b:
            for v in sorted(outliers_b, reverse=True):
                w(f"  {col_b:<10}  {v:.2f} days")
        w()
        w("  These PRs are long-running branches merged into the window.")
        w("  They remain in the full dataset above but skew avg significantly.")
        w("  Investigate these PRs to understand whether they represent process")
        w("  debt, blocked work, or branches held open across multiple sprints.")

    # --- Per-repo avg ---
    repos_a = {r["name"]: r for r in a.get("repos", [])}
    repos_b = {r["name"]: r for r in b.get("repos", [])}
    all_repos = sorted(set(repos_a) | set(repos_b))

    if all_repos:
        w()
        w("  PER-REPO AVG DAYS TO 2ND APPROVAL")
        w(f"  {'Repository':<45}  {col_a:>10}  {col_b:>10}  {'Change':>10}")
        w("  " + "─" * 74)
        # Compute per-repo outlier threshold: repos whose avg_days is an outlier
        # relative to all repo avgs (using same IQR rule). Only flag if we have
        # enough repos with data to make the detection meaningful.
        all_repo_avgs = [
            v for r in all_repos
            for v in [repos_a.get(r, {}).get("avg_days"), repos_b.get(r, {}).get("avg_days")]
            if v is not None
        ]
        _, repo_outlier_upper = _iqr_bounds(all_repo_avgs) if len(all_repo_avgs) >= 4 else (None, float("inf"))

        for repo in all_repos:
            avg_a = repos_a.get(repo, {}).get("avg_days")
            avg_b = repos_b.get(repo, {}).get("avg_days")
            is_outlier = (avg_a is not None and avg_a > repo_outlier_upper) or \
                         (avg_b is not None and avg_b > repo_outlier_upper)
            flag = "  ⚠ outlier" if is_outlier else ""
            w(
                f"  {repo:<45.45}  {_fmt(avg_a):>10}"
                f"  {_fmt(avg_b):>10}  {_delta(avg_a, avg_b):>10}{flag}"
            )

    # --- Story point groups ---
    sp_a = a.get("storypoint_groups", {})
    sp_b = b.get("storypoint_groups", {})
    all_sp = sorted(
        set(sp_a) | set(sp_b),
        key=lambda x: (0, float(x)) if x.replace(".", "", 1).isdigit() else (1, x),
    )
    if all_sp:
        # Only show range columns if at least one SP group in either snapshot has min/max data
        has_ranges = any(
            sp_a.get(sp, {}).get("min_days") is not None or sp_b.get(sp, {}).get("min_days") is not None
            for sp in all_sp
        )
        w()
        w("  STORY POINT GROUPS — MEDIAN DAYS")
        if has_ranges:
            w(f"  {'SP':<8}  {f'{col_a} (med [min–max])':>28}  {f'{col_b} (med [min–max])':>28}  {'Change':>10}  {'Count A':>8}  {'Count B':>8}  Note")
            w("  " + "─" * 104)
        else:
            w(f"  {'SP':<8}  {col_a:>10}  {col_b:>10}  {'Change':>10}  {'Count A':>8}  {'Count B':>8}  Note")
            w("  " + "─" * 80)
        for sp in all_sp:
            ga = sp_a.get(sp, {})
            gb = sp_b.get(sp, {})
            med_a = ga.get("median_days")
            med_b = gb.get("median_days")
            cnt_a = ga.get("count", 0)
            cnt_b = gb.get("count", 0)
            low = cnt_a < MIN_SP_COUNT or cnt_b < MIN_SP_COUNT
            note = f"⚠ low n ({cnt_a}/{cnt_b})" if low else ""
            if has_ranges:
                range_a = (
                    f" [{_fmt(ga.get('min_days'))}–{_fmt(ga.get('max_days'))}]"
                    if ga.get("min_days") is not None else ""
                )
                range_b = (
                    f" [{_fmt(gb.get('min_days'))}–{_fmt(gb.get('max_days'))}]"
                    if gb.get("min_days") is not None else ""
                )
                cell_a = f"{_fmt(med_a)}{range_a}"
                cell_b = f"{_fmt(med_b)}{range_b}"
                w(
                    f"  {sp:<8}  {cell_a:>28}  {cell_b:>28}"
                    f"  {_delta(med_a, med_b):>10}  {cnt_a:>8}  {cnt_b:>8}  {note}"
                )
            else:
                w(
                    f"  {sp:<8}  {_fmt(med_a):>10}  {_fmt(med_b):>10}"
                    f"  {_delta(med_a, med_b):>10}  {cnt_a:>8}  {cnt_b:>8}  {note}"
                )

    # --- Story point groups — days per SP ---
    has_dsp_groups = any(
        sp_a.get(sp, {}).get("median_dsp") is not None
        or sp_b.get(sp, {}).get("median_dsp") is not None
        for sp in all_sp
    )
    if all_sp and has_dsp_groups:
        w()
        w("  STORY POINT GROUPS — MEDIAN DAYS PER STORY POINT")
        w(f"  {'SP':<8}  {col_a:>10}  {col_b:>10}  {'Change':>10}  {'Count A':>8}  {'Count B':>8}  Note")
        w("  " + "─" * 80)
        for sp in all_sp:
            ga = sp_a.get(sp, {})
            gb = sp_b.get(sp, {})
            med_a = ga.get("median_dsp")
            med_b = gb.get("median_dsp")
            cnt_a = ga.get("count", 0)
            cnt_b = gb.get("count", 0)
            low = cnt_a < MIN_SP_COUNT or cnt_b < MIN_SP_COUNT
            note = f"⚠ low n ({cnt_a}/{cnt_b})" if low else ""
            w(
                f"  {sp:<8}  {_fmt(med_a):>10}  {_fmt(med_b):>10}"
                f"  {_delta(med_a, med_b):>10}  {cnt_a:>8}  {cnt_b:>8}  {note}"
            )

    w()
    return "\n".join(out)

def plot_comparison(a: dict, b: dict, output_dir: str, ai_adoption: bool = False) -> None:
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
        label_a = f"Baseline ({a['period']['from']} → {a['period']['to']})"
        label_b = f"Post-AI ({b['period']['from']} → {b['period']['to']})"
        main_title = "PR Time to 2nd Approval — Pre-AI Baseline vs Post-Copilot Adoption"
    else:
        label_a = f"{a['period']['from']} → {a['period']['to']}"
        label_b = f"{b['period']['from']} → {b['period']['to']}"
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
        for d in (a["stats"]["days_per_sp"], b["stats"]["days_per_sp"])
        for v in d.values()
    )
    active_stats = stat_keys if has_dsp else stat_keys[:1]

    fig, axes = plt.subplots(1, len(active_stats), figsize=(7 * len(active_stats), 5))
    if len(active_stats) == 1:
        axes = [axes]
    fig.suptitle(main_title, fontsize=14, fontweight="bold")

    for ax, (key, title) in zip(axes, active_stats):
        sa, sb = a["stats"][key], b["stats"][key]
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
    repos_a = {r["name"]: r.get("avg_days") for r in a.get("repos", [])}
    repos_b = {r["name"]: r.get("avg_days") for r in b.get("repos", [])}
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
    sp_a = a.get("storypoint_groups", {})
    sp_b = b.get("storypoint_groups", {})
    all_sp = sorted(
        set(sp_a) | set(sp_b),
        key=lambda x: (0, float(x)) if x.replace(".", "", 1).isdigit() else (1, x),
    )
    if all_sp:
        fig, ax = plt.subplots(figsize=(max(8, len(all_sp) * 1.4 + 2), 5))
        x = np.arange(len(all_sp))
        bars_a = ax.bar(x - width / 2, [sp_a.get(sp, {}).get("median_days") or 0 for sp in all_sp],
                        width, label=label_a, color=COLOR_A, alpha=0.85)
        bars_b = ax.bar(x + width / 2, [sp_b.get(sp, {}).get("median_days") or 0 for sp in all_sp],
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
        sp_a.get(sp, {}).get("median_dsp") is not None
        or sp_b.get(sp, {}).get("median_dsp") is not None
        for sp in all_sp
    ):
        fig, ax = plt.subplots(figsize=(max(8, len(all_sp) * 1.4 + 2), 5))
        x = np.arange(len(all_sp))
        bars_a = ax.bar(x - width / 2, [sp_a.get(sp, {}).get("median_dsp") or 0 for sp in all_sp],
                        width, label=label_a, color=COLOR_A, alpha=0.85)
        bars_b = ax.bar(x + width / 2, [sp_b.get(sp, {}).get("median_dsp") or 0 for sp in all_sp],
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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="pr_compare.py",
        description="Compare two pr_approval_time.sh snapshots and plot changes.",
    )
    parser.add_argument("snapshot_a", help="Earlier period snapshot JSON")
    parser.add_argument("snapshot_b", help="Later period snapshot JSON")
    parser.add_argument(
        "--output-dir", "-o",
        default="./pr_comparison_charts",
        help="Directory to write chart PNGs (default: ./pr_comparison_charts)",
    )
    parser.add_argument("--no-plot", action="store_true", help="Print table only, skip charts")
    parser.add_argument(
        "--ai-adoption",
        action="store_true",
        help=(
            "Frame the comparison as pre-AI baseline vs post-AI adoption. "
            "Adds a dedicated AI impact summary section and relabels all output "
            "accordingly. Use when snapshot_a is the human-only baseline and "
            "snapshot_b is the first period with Copilot reviewing every PR."
        ),
    )

    args = parser.parse_args(argv)

    a = load(args.snapshot_a)
    b = load(args.snapshot_b)

    if args.ai_adoption:
        print(render_ai_impact_summary(a, b))
    print(render_executive_summary(a, b, ai_adoption=args.ai_adoption))
    print(render_delivery_leads_summary(a, b, ai_adoption=args.ai_adoption))
    print(render_comparison(a, b, ai_adoption=args.ai_adoption))

    if not args.no_plot:
        print("════════════════════════════════════════════════════════════════════════")
        print("  CHARTS")
        print("════════════════════════════════════════════════════════════════════════")
        plot_comparison(a, b, args.output_dir, ai_adoption=args.ai_adoption)
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
