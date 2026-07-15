"""Rendering helpers for pr_compare — pure text output, no matplotlib.

Every function returns a string; the caller decides when to print.
"""

from __future__ import annotations

from models import Snapshot, SpGroup
from stats import iqr_bounds, split_outliers, summary_stats

# SP buckets with fewer than this many PRs are flagged as low-confidence.
# A median/avg from 1-2 data points is statistically meaningless and can
# swing wildly between periods due to a single outlier PR.
MIN_SP_COUNT = 5


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


def _period_labels(a: Snapshot, b: Snapshot, ai_adoption: bool) -> tuple[str, str]:
    pa, pb = a.period, b.period
    if ai_adoption:
        return (
            f"{pa.from_} to {pa.to} (pre-AI baseline, human-only reviews)",
            f"{pb.from_} to {pb.to} (post-AI adoption, Copilot on every PR)",
        )
    return f"{pa.from_} to {pa.to}", f"{pb.from_} to {pb.to}"


def render_ai_impact_summary(a: Snapshot, b: Snapshot) -> str:
    """Render an AI adoption-specific impact narrative."""
    lines: list[str] = []
    label_a = f"{a.period.from_} to {a.period.to}"
    label_b = f"{b.period.from_} to {b.period.to}"

    med_a, med_b = a.days.median, b.days.median
    p75_a, p75_b = a.days.p75, b.days.p75
    avg_a, avg_b = a.days.avg, b.days.avg

    dsp_med_a, dsp_med_b = a.days_per_sp.median, b.days_per_sp.median

    vol_a, vol_b = a.summary.total_examined, b.summary.total_examined
    apr_a, apr_b = a.summary.total_approved, b.summary.total_approved

    lines.append("")
    lines.append("════════════════════════════════════════════════════════════════════════")
    lines.append("  AI ADOPTION IMPACT — COPILOT CODE REVIEW")
    lines.append("════════════════════════════════════════════════════════════════════════")
    lines.append("")
    lines.append("  METHODOLOGY")
    lines.append(f"  Baseline  : {label_a}  — human reviewers only")
    lines.append(f"  Post-AI   : {label_b}  — Copilot reviews every PR")
    lines.append("")
    lines.append("  This comparison uses a time-based cohort rather than per-PR detection.")
    lines.append("  All PRs in the post-AI period are assumed to have received a Copilot")
    lines.append("  review. This is a reasonable proxy when rollout is team-wide and")
    lines.append("  consistent, but note that other factors (team velocity, PR size,")
    lines.append("  holiday periods) may also influence the delta. One month of post-AI")
    lines.append("  data is early-signal only — treat trends with appropriate caution.")
    lines.append("")

    # Headline: median
    lines.append("  HEADLINE — MEDIAN TIME TO 2ND APPROVAL")
    if med_a is not None and med_b is not None:
        med_delta = med_b - med_a
        direction = "decreased" if med_delta < 0 else "increased"
        sign = "" if med_delta < 0 else "+"
        lines.append(
            f"  Median time to second approval {direction} from {med_a:.2f} days (baseline)"
            f" to {med_b:.2f} days (post-AI) — a change of {sign}{med_delta:.2f} days."
        )
        if abs(med_delta) < 0.1:
            lines.append("  This is a negligible shift; median performance is effectively unchanged.")
        elif med_delta < 0:
            lines.append("  The typical PR is moving through review faster after AI adoption.")
        else:
            lines.append("  The typical PR is taking longer to reach a second approval.")
            lines.append("  This does not necessarily indicate AI is slowing reviews — volume")
            lines.append("  changes, PR complexity, or reviewer availability may be contributing.")
    else:
        lines.append("  Insufficient data to compare median times.")
    lines.append("")

    # Tail: p75 (most actionable for slow PRs)
    lines.append("  TAIL PERFORMANCE — P75 (SLOWEST QUARTER OF PRS)")
    if p75_a is not None and p75_b is not None:
        p75_delta = p75_b - p75_a
        direction = "decreased" if p75_delta < 0 else "increased"
        sign = "" if p75_delta < 0 else "+"
        lines.append(
            f"  The 75th percentile {direction} from {p75_a:.2f} to {p75_b:.2f} days"
            f" ({sign}{p75_delta:.2f} days)."
        )
        lines.append(
            "  The p75 captures your slowest-moving quarter of PRs — often the ones"
            " most likely to benefit from an AI first-pass that surfaces issues early."
        )
        if p75_delta < -0.5:
            lines.append("  A meaningful drop here suggests AI is helping unblock complex or slow PRs.")
        elif p75_delta > 0.5:
            lines.append("  A rise here warrants monitoring — slow PRs are getting slower.")
    else:
        lines.append("  Insufficient data to compare p75 times.")
    lines.append("")

    # Effort-adjusted
    if dsp_med_a is not None and dsp_med_b is not None:
        dsp_delta = dsp_med_b - dsp_med_a
        direction = "decreased" if dsp_delta < 0 else "increased"
        sign = "" if dsp_delta < 0 else "+"
        lines.append("  EFFORT-ADJUSTED — MEDIAN DAYS PER STORY POINT")
        lines.append(
            f"  When normalised for ticket complexity, the median days per story point"
            f" {direction} from {dsp_med_a:.3f} to {dsp_med_b:.3f} ({sign}{dsp_delta:.3f} d/SP)."
        )
        lines.append(
            "  This accounts for whether the team is shipping larger or smaller tickets"
            " between periods, giving a fairer like-for-like comparison."
        )
        lines.append("")

    # Volume context
    lines.append("  VOLUME CONTEXT")
    vol_delta = vol_b - vol_a
    apr_delta = apr_b - apr_a
    vol_sign = "+" if vol_delta >= 0 else ""
    apr_sign = "+" if apr_delta >= 0 else ""
    lines.append(f"  PRs examined : {vol_a} (baseline) → {vol_b} (post-AI)  [{vol_sign}{vol_delta}]")
    lines.append(f"  PRs w/ 2+ approvals: {apr_a} → {apr_b}  [{apr_sign}{apr_delta}]")
    lines.append("")
    lines.append("  Note: a rising PR volume can inflate average and p75 times independently")
    lines.append("  of AI impact. Interpret deltas in the context of throughput changes.")
    lines.append("")

    # What to watch next
    lines.append("  WHAT TO WATCH")
    lines.append("  - Run this comparison monthly as more post-AI data accumulates.")
    lines.append("  - Watch the p75 trend — sustained improvement there is the strongest")
    lines.append("    signal that AI reviews are surfacing issues before human reviewers.")
    lines.append("  - If median days/SP improves while PR volume rises, that is a strong")
    lines.append("    positive signal that the team is delivering more with less review friction.")
    lines.append("")
    return "\n".join(lines)

def render_executive_summary(a: Snapshot, b: Snapshot, ai_adoption: bool = False) -> str:
    """Render a concise executive and leadership summary in plain prose."""
    lines: list[str] = []
    label_a, label_b = _period_labels(a, b, ai_adoption)

    med_a, med_b = a.days.median, b.days.median
    avg_a, avg_b = a.days.avg, b.days.avg
    p75_a, p75_b = a.days.p75, b.days.p75

    med_delta = (med_b - med_a) if med_a is not None and med_b is not None else None
    avg_delta = (avg_b - avg_a) if avg_a is not None and avg_b is not None else None
    p75_delta = (p75_b - p75_a) if p75_a is not None and p75_b is not None else None

    vol_a = a.summary.total_examined
    vol_b = b.summary.total_examined
    apr_a = a.summary.total_approved
    apr_b = b.summary.total_approved
    vol_delta = vol_b - vol_a

    lines.append("")
    lines.append("════════════════════════════════════════════════════════════════════════")
    lines.append("  EXECUTIVE SUMMARY")
    lines.append("════════════════════════════════════════════════════════════════════════")
    lines.append("")
    lines.append("  This report compares pull request review performance across two periods:")
    lines.append(f"    Period A : {label_a}")
    lines.append(f"               {vol_a} pull requests examined, {apr_a} with two or more approvals")
    lines.append(f"    Period B : {label_b}")
    lines.append(f"               {vol_b} pull requests examined, {apr_b} with two or more approvals")
    lines.append("")

    # Headline metric
    lines.append("  HEADLINE METRIC — MEDIAN TIME TO SECOND APPROVAL")
    if med_a is not None and med_b is not None:
        trend = _trend_word(med_delta)
        if trend == "held steady":
            lines.append(f"  The median time for a pull request to receive a second approval held steady")
            lines.append(f"  at {_fmt(med_b)} days across both periods.")
        else:
            direction = "reduced" if med_delta < 0 else "increased"
            lines.append(
                f"  The median time for a pull request to receive a second approval {trend} by"
                f" {abs(med_delta):.2f} days,"
            )
            lines.append(
                f"  {direction} from {_fmt(med_a)} days in Period A to {_fmt(med_b)} days in Period B."
            )
    else:
        lines.append("  Insufficient data to calculate median time to second approval.")
    lines.append("")

    # Supporting metrics
    lines.append("  SUPPORTING METRICS")
    if avg_a is not None and avg_b is not None:
        trend = _trend_word(avg_delta)
        if trend == "held steady":
            lines.append(f"  The average time to second approval held steady at {_fmt(avg_b)} days.")
        else:
            direction = "reduced" if avg_delta < 0 else "increased"
            lines.append(
                f"  The average time to second approval {trend} by {abs(avg_delta):.2f} days,"
                f" {direction} from {_fmt(avg_a)} to {_fmt(avg_b)} days."
            )
    if p75_a is not None and p75_b is not None:
        trend = _trend_word(p75_delta)
        if trend == "held steady":
            lines.append(f"  The 75th percentile time to second approval held steady at {_fmt(p75_b)} days.")
        else:
            direction = "reduced" if p75_delta < 0 else "increased"
            lines.append(
                f"  The 75th percentile time to second approval (the slowest quarter of pull requests)"
                f" {trend} by {abs(p75_delta):.2f} days,"
            )
            lines.append(f"  {direction} from {_fmt(p75_a)} to {_fmt(p75_b)} days.")
    if vol_delta == 0:
        lines.append(f"  Pull request volume remained unchanged at {vol_b} examined.")
    elif vol_delta > 0:
        lines.append(
            f"  Pull request volume increased by {vol_delta} pull requests,"
            f" from {vol_a} to {vol_b} examined."
        )
    else:
        lines.append(
            f"  Pull request volume decreased by {abs(vol_delta)} pull requests,"
            f" from {vol_a} to {vol_b} examined."
        )

    # Effort-adjusted metric
    dsp_med_a, dsp_med_b = a.days_per_sp.median, b.days_per_sp.median
    if dsp_med_a is not None and dsp_med_b is not None:
        dsp_delta = dsp_med_b - dsp_med_a
        trend = _trend_word(dsp_delta)
        lines.append("")
        lines.append("  EFFORT-ADJUSTED PERFORMANCE — DAYS PER STORY POINT")
        if trend == "held steady":
            lines.append(
                f"  When accounting for work complexity, the median days per story point held steady"
                f" at {_fmt(dsp_med_b)} days per story point."
            )
        else:
            direction = "reduced" if dsp_delta < 0 else "increased"
            lines.append(
                f"  When accounting for work complexity, the median days per story point {trend} by"
                f" {abs(dsp_delta):.2f} days,"
            )
            lines.append(
                f"  {direction} from {_fmt(dsp_med_a)} to {_fmt(dsp_med_b)} days per story point."
            )
    lines.append("")
    return "\n".join(lines)

def render_delivery_leads_summary(a: Snapshot, b: Snapshot, ai_adoption: bool = False) -> str:
    """Render an operational summary for delivery leads: per-repository movements,
    story point trends, and data coverage observations."""
    lines: list[str] = []
    label_a, label_b = _period_labels(a, b, ai_adoption)

    repos_a = {r.name: r for r in a.repos}
    repos_b = {r.name: r for r in b.repos}
    all_repos = sorted(set(repos_a) | set(repos_b))

    # Repositories that gained or lost data between periods
    new_repos = sorted(set(repos_b) - set(repos_a))
    dropped_repos = sorted(set(repos_a) - set(repos_b))

    # Compute per-repository deltas where both periods have data
    repo_deltas: list[tuple[str, float, float, float]] = []  # (name, avg_a, avg_b, delta)
    for repo in all_repos:
        avg_a = repos_a[repo].avg_days if repo in repos_a else None
        avg_b = repos_b[repo].avg_days if repo in repos_b else None
        if avg_a is not None and avg_b is not None:
            repo_deltas.append((repo, avg_a, avg_b, avg_b - avg_a))

    most_improved = sorted(repo_deltas, key=lambda x: x[3])[:3]
    most_worsened = sorted(repo_deltas, key=lambda x: x[3], reverse=True)[:3]

    sp_a = a.storypoint_groups
    sp_b = b.storypoint_groups
    all_sp = sorted(
        set(sp_a) | set(sp_b),
        key=lambda x: (0, float(x)) if x.replace(".", "", 1).isdigit() else (1, x),
    )

    lines.append("════════════════════════════════════════════════════════════════════════")
    lines.append("  DELIVERY LEADS SUMMARY")
    lines.append("════════════════════════════════════════════════════════════════════════")
    lines.append("")
    lines.append(f"  Comparing Period A ({label_a}) against Period B ({label_b}).")
    lines.append("")

    # --- Per-repository movements ---
    if repo_deltas:
        lines.append("  REPOSITORY PERFORMANCE MOVEMENTS")
        lines.append("")
        if most_improved and most_improved[0][3] < -0.01:
            lines.append("  Repositories with the most improved average time to second approval:")
            for name, avg_a_val, avg_b_val, delta in most_improved:
                if delta < -0.01:
                    lines.append(
                        f"    {name}: reduced by {abs(delta):.2f} days"
                        f" (from {_fmt(avg_a_val)} to {_fmt(avg_b_val)} days on average)"
                    )
            lines.append("")
        if most_worsened and most_worsened[0][3] > 0.01:
            lines.append("  Repositories with the most worsened average time to second approval:")
            for name, avg_a_val, avg_b_val, delta in most_worsened:
                if delta > 0.01:
                    lines.append(
                        f"    {name}: increased by {delta:.2f} days"
                        f" (from {_fmt(avg_a_val)} to {_fmt(avg_b_val)} days on average)"
                    )
            lines.append("")

    # --- Coverage changes ---
    if new_repos or dropped_repos:
        lines.append("  DATA COVERAGE CHANGES")
        if new_repos:
            lines.append(
                f"  The following {'repository' if len(new_repos) == 1 else 'repositories'}"
                f" appeared in Period B but had no data in Period A:"
            )
            for r in new_repos:
                lines.append(f"    {r}")
        if dropped_repos:
            lines.append(
                f"  The following {'repository' if len(dropped_repos) == 1 else 'repositories'}"
                f" had data in Period A but are absent from Period B:"
            )
            for r in dropped_repos:
                lines.append(f"    {r}")
        lines.append("")

    # --- Story point complexity trends ---
    if all_sp:
        sp_deltas: list[tuple[str, float, float, float, int, int]] = []
        low_confidence_sp: list[str] = []
        for sp in all_sp:
            cnt_a = sp_a.get(sp, SpGroup()).count
            cnt_b = sp_b.get(sp, SpGroup()).count
            med_a = sp_a.get(sp, SpGroup()).median_days
            med_b = sp_b.get(sp, SpGroup()).median_days
            if med_a is not None and med_b is not None:
                if cnt_a < MIN_SP_COUNT or cnt_b < MIN_SP_COUNT:
                    low_confidence_sp.append(sp)
                else:
                    sp_deltas.append((sp, med_a, med_b, med_b - med_a, cnt_a, cnt_b))

        if sp_deltas:
            lines.append("  STORY POINT COMPLEXITY TRENDS — MEDIAN DAYS TO SECOND APPROVAL")
            lines.append("")
            for sp, med_a_val, med_b_val, delta, cnt_a, cnt_b in sp_deltas:
                trend = _trend_word(delta)
                if trend == "held steady":
                    lines.append(
                        f"  {sp}-point work: held steady at {_fmt(med_b_val)} days"
                        f" ({cnt_a} pull requests in Period A, {cnt_b} in Period B)"
                    )
                else:
                    direction = "reduced" if delta < 0 else "increased"
                    lines.append(
                        f"  {sp}-point work: {trend} by {abs(delta):.2f} days,"
                        f" {direction} from {_fmt(med_a_val)} to {_fmt(med_b_val)} days"
                        f" ({cnt_a} pull requests in Period A, {cnt_b} in Period B)"
                    )
            lines.append("")

        if low_confidence_sp:
            lines.append(
                f"  The following story point {'bucket' if len(low_confidence_sp) == 1 else 'buckets'}"
                f" had fewer than {MIN_SP_COUNT} pull requests in at least one period and"
                f" {'has' if len(low_confidence_sp) == 1 else 'have'} been excluded from the trend"
                f" narrative — a median from 1–{MIN_SP_COUNT - 1} data points reflects individual"
                f" outliers, not a genuine pattern:"
            )
            for sp in low_confidence_sp:
                cnt_a = sp_a.get(sp, SpGroup()).count
                cnt_b = sp_b.get(sp, SpGroup()).count
                med_a = sp_a.get(sp, SpGroup()).median_days
                med_b = sp_b.get(sp, SpGroup()).median_days
                lines.append(
                    f"    {sp}-point work: {_fmt(med_a)} → {_fmt(med_b)} days"
                    f" (n={cnt_a} in Period A, n={cnt_b} in Period B)"
                )
            lines.append("")

    # --- Exclusion / data quality notes ---
    exc_no_jira_a = a.summary.excluded_no_jira
    exc_no_jira_b = b.summary.excluded_no_jira
    exc_no_sp_a = a.summary.excluded_no_sp
    exc_no_sp_b = b.summary.excluded_no_sp
    exc_lt2_a = a.summary.excluded_lt2
    exc_lt2_b = b.summary.excluded_lt2

    any_exclusions = any([exc_no_jira_a, exc_no_jira_b, exc_no_sp_a, exc_no_sp_b, exc_lt2_a, exc_lt2_b])
    if any_exclusions:
        lines.append("  DATA QUALITY NOTES")
        if exc_lt2_a or exc_lt2_b:
            lines.append(
                f"  Pull requests excluded for having fewer than two approvals:"
                f" {exc_lt2_a} in Period A, {exc_lt2_b} in Period B."
            )
        if exc_no_jira_a or exc_no_jira_b:
            lines.append(
                f"  Pull requests excluded for missing a Jira ticket reference:"
                f" {exc_no_jira_a} in Period A, {exc_no_jira_b} in Period B."
            )
        if exc_no_sp_a or exc_no_sp_b:
            lines.append(
                f"  Pull requests excluded for missing story point estimates:"
                f" {exc_no_sp_a} in Period A, {exc_no_sp_b} in Period B."
            )
        lines.append("")
    return "\n".join(lines)

def render_comparison(a: Snapshot, b: Snapshot, ai_adoption: bool = False) -> str:
    lines: list[str] = []
    label_a, label_b = _period_labels(a, b, ai_adoption)
    col_a = "Baseline" if ai_adoption else "Period A"
    col_b = "Post-AI" if ai_adoption else "Period B"

    lines.append("")
    lines.append("════════════════════════════════════════════════════════════════════════")
    lines.append(f"  COMPARISON")
    lines.append(f"  {'Baseline' if ai_adoption else 'Period A'} : {label_a}")
    lines.append(f"  {'Post-AI ' if ai_adoption else 'Period B'} : {label_b}")
    lines.append("════════════════════════════════════════════════════════════════════════")

    # --- Volume ---
    lines.append("")
    lines.append("  VOLUME")
    lines.append(f"  {'Metric':<26}  {col_a:>10}  {col_b:>10}  {'Change':>10}")
    lines.append("  " + "─" * 62)
    for attr, label in [
        ("total_examined", "PRs examined"),
        ("total_approved", "PRs w/ 2+ approvals"),
        ("excluded_lt2", "Excluded (<2 approvals)"),
        ("excluded_no_jira", "Excluded (no Jira key)"),
        ("excluded_no_sp", "Excluded (no story pts)"),
    ]:
        va, vb = getattr(a.summary, attr), getattr(b.summary, attr)
        lines.append(f"  {label:<26}  {va:>10}  {vb:>10}  {_delta_int(va, vb):>10}")

    # --- Days to 2nd approval (with optional clean stats when raw_days available) ---
    raw_a: list[float] = a.raw_days
    raw_b: list[float] = b.raw_days
    clean_a, outliers_a = split_outliers(raw_a) if raw_a else ([], [])
    clean_b, outliers_b = split_outliers(raw_b) if raw_b else ([], [])
    has_outliers = bool(outliers_a or outliers_b)
    clean_stats_a = summary_stats(clean_a) if clean_a else None
    clean_stats_b = summary_stats(clean_b) if clean_b else None

    sa, sb = a.days.as_dict(), b.days.as_dict()
    lines.append("")
    lines.append("  TIME TO 2ND APPROVAL (days) — ALL PRs")
    lines.append(f"  {'Metric':<10}  {col_a:>10}  {col_b:>10}  {'Change':>10}")
    lines.append("  " + "─" * 46)
    for metric in ("median", "p75", "avg"):
        lines.append(
            f"  {metric:<10}  {_fmt(sa.get(metric)):>10}"
            f"  {_fmt(sb.get(metric)):>10}  {_delta(sa.get(metric), sb.get(metric)):>10}"
        )

    if has_outliers and (clean_stats_a or clean_stats_b):
        n_out_a = len(outliers_a)
        n_out_b = len(outliers_b)
        lines.append("")
        lines.append(f"  TIME TO 2ND APPROVAL (days) — OUTLIERS REMOVED")
        note_a = f"  (excl. {n_out_a} outlier{'s' if n_out_a != 1 else ''})" if n_out_a else ""
        note_b = f"  (excl. {n_out_b} outlier{'s' if n_out_b != 1 else ''})" if n_out_b else ""
        lines.append(f"  {col_a}{note_a}")
        lines.append(f"  {col_b}{note_b}")
        lines.append(f"  {'Metric':<10}  {col_a:>10}  {col_b:>10}  {'Change':>10}")
        lines.append("  " + "─" * 46)
        csa = clean_stats_a or sa
        csb = clean_stats_b or sb
        for metric in ("median", "p75", "avg"):
            lines.append(
                f"  {metric:<10}  {_fmt(csa.get(metric)):>10}"
                f"  {_fmt(csb.get(metric)):>10}  {_delta(csa.get(metric), csb.get(metric)):>10}"
            )

    # --- Days per story point (only if at least one period has data) ---
    dpa, dpb = a.days_per_sp.as_dict(), b.days_per_sp.as_dict()
    has_dsp = any(v is not None for v in list(dpa.values()) + list(dpb.values()))
    if has_dsp:
        lines.append("")
        lines.append("  DAYS PER STORY POINT")
        lines.append(f"  {'Metric':<10}  {col_a:>10}  {col_b:>10}  {'Change':>10}")
        lines.append("  " + "─" * 46)
        for metric in ("median", "p75", "avg"):
            lines.append(
                f"  {metric:<10}  {_fmt(dpa.get(metric)):>10}"
                f"  {_fmt(dpb.get(metric)):>10}  {_delta(dpa.get(metric), dpb.get(metric)):>10}"
            )

    # --- Outlier detail ---
    if has_outliers:
        lines.append("")
        lines.append("  OUTLIERS  (detected via 3×IQR rule — excluded from clean stats above)")
        lines.append("  ─────────────────────────────────────────────────────")
        if outliers_a:
            for v in sorted(outliers_a, reverse=True):
                lines.append(f"  {col_a:<10}  {v:.2f} days")
        if outliers_b:
            for v in sorted(outliers_b, reverse=True):
                lines.append(f"  {col_b:<10}  {v:.2f} days")
        lines.append("")
        lines.append("  These PRs are long-running branches merged into the window.")
        lines.append("  They remain in the full dataset above but skew avg significantly.")
        lines.append("  Investigate these PRs to understand whether they represent process")
        lines.append("  debt, blocked work, or branches held open across multiple sprints.")

    # --- Per-repo avg ---
    repos_a = {r.name: r for r in a.repos}
    repos_b = {r.name: r for r in b.repos}
    all_repos = sorted(set(repos_a) | set(repos_b))

    if all_repos:
        lines.append("")
        lines.append("  PER-REPO AVG DAYS TO 2ND APPROVAL")
        lines.append(f"  {'Repository':<45}  {col_a:>10}  {col_b:>10}  {'Change':>10}")
        lines.append("  " + "─" * 74)
        # Compute per-repo outlier threshold: repos whose avg_days is an outlier
        # relative to all repo avgs (using same IQR rule). Only flag if we have
        # enough repos with data to make the detection meaningful.
        all_repo_avgs = [
            v for r in all_repos
            for v in [
                repos_a[r].avg_days if r in repos_a else None,
                repos_b[r].avg_days if r in repos_b else None,
            ]
            if v is not None
        ]
        _, repo_outlier_upper = iqr_bounds(all_repo_avgs) if len(all_repo_avgs) >= 4 else (None, float("inf"))

        for repo in all_repos:
            avg_a = repos_a[repo].avg_days if repo in repos_a else None
            avg_b = repos_b[repo].avg_days if repo in repos_b else None
            is_outlier = (avg_a is not None and avg_a > repo_outlier_upper) or \
                         (avg_b is not None and avg_b > repo_outlier_upper)
            flag = "  ⚠ outlier" if is_outlier else ""
            lines.append(
                f"  {repo:<45.45}  {_fmt(avg_a):>10}"
                f"  {_fmt(avg_b):>10}  {_delta(avg_a, avg_b):>10}{flag}"
            )

    # --- Story point groups ---
    sp_a = a.storypoint_groups
    sp_b = b.storypoint_groups
    all_sp = sorted(
        set(sp_a) | set(sp_b),
        key=lambda x: (0, float(x)) if x.replace(".", "", 1).isdigit() else (1, x),
    )
    if all_sp:
        # Only show range columns if at least one SP group in either snapshot has min/max data
        has_ranges = any(
            sp_a.get(sp, SpGroup()).min_days is not None or sp_b.get(sp, SpGroup()).min_days is not None
            for sp in all_sp
        )
        lines.append("")
        lines.append("  STORY POINT GROUPS — MEDIAN DAYS")
        if has_ranges:
            lines.append(f"  {'SP':<8}  {f'{col_a} (med [min–max])':>28}  {f'{col_b} (med [min–max])':>28}  {'Change':>10}  {'Count A':>8}  {'Count B':>8}  Note")
            lines.append("  " + "─" * 104)
        else:
            lines.append(f"  {'SP':<8}  {col_a:>10}  {col_b:>10}  {'Change':>10}  {'Count A':>8}  {'Count B':>8}  Note")
            lines.append("  " + "─" * 80)
        for sp in all_sp:
            ga = sp_a.get(sp, SpGroup())
            gb = sp_b.get(sp, SpGroup())
            med_a = ga.median_days
            med_b = gb.median_days
            cnt_a = ga.count
            cnt_b = gb.count
            low = cnt_a < MIN_SP_COUNT or cnt_b < MIN_SP_COUNT
            note = f"⚠ low n ({cnt_a}/{cnt_b})" if low else ""
            if has_ranges:
                range_a = (
                    f" [{_fmt(ga.get('min_days'))}–{_fmt(ga.get('max_days'))}]"
                    if ga.min_days is not None else ""
                )
                range_b = (
                    f" [{_fmt(gb.get('min_days'))}–{_fmt(gb.get('max_days'))}]"
                    if gb.min_days is not None else ""
                )
                cell_a = f"{_fmt(med_a)}{range_a}"
                cell_b = f"{_fmt(med_b)}{range_b}"
                lines.append(
                    f"  {sp:<8}  {cell_a:>28}  {cell_b:>28}"
                    f"  {_delta(med_a, med_b):>10}  {cnt_a:>8}  {cnt_b:>8}  {note}"
                )
            else:
                lines.append(
                    f"  {sp:<8}  {_fmt(med_a):>10}  {_fmt(med_b):>10}"
                    f"  {_delta(med_a, med_b):>10}  {cnt_a:>8}  {cnt_b:>8}  {note}"
                )

    # --- Story point groups — days per SP ---
    has_dsp_groups = any(
        sp_a.get(sp, SpGroup()).median_dsp is not None
        or sp_b.get(sp, SpGroup()).median_dsp is not None
        for sp in all_sp
    )
    if all_sp and has_dsp_groups:
        lines.append("")
        lines.append("  STORY POINT GROUPS — MEDIAN DAYS PER STORY POINT")
        lines.append(f"  {'SP':<8}  {col_a:>10}  {col_b:>10}  {'Change':>10}  {'Count A':>8}  {'Count B':>8}  Note")
        lines.append("  " + "─" * 80)
        for sp in all_sp:
            ga = sp_a.get(sp, SpGroup())
            gb = sp_b.get(sp, SpGroup())
            med_a = ga.median_dsp
            med_b = gb.median_dsp
            cnt_a = ga.count
            cnt_b = gb.count
            low = cnt_a < MIN_SP_COUNT or cnt_b < MIN_SP_COUNT
            note = f"⚠ low n ({cnt_a}/{cnt_b})" if low else ""
            lines.append(
                f"  {sp:<8}  {_fmt(med_a):>10}  {_fmt(med_b):>10}"
                f"  {_delta(med_a, med_b):>10}  {cnt_a:>8}  {cnt_b:>8}  {note}"
            )

    lines.append("")
    return "\n".join(lines)

