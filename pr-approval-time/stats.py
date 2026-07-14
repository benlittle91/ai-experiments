"""Shared statistics helpers for the PR-approval-time tool.

Kept intentionally dependency-free (stdlib only) so it is trivially importable
from both the snapshot builder (pr_metrics.py) and the comparator (pr_compare.py),
and testable in isolation without touching disk or the network.
"""

from __future__ import annotations

from math import ceil, floor


def percentile(sorted_vals: list[float], p: float) -> float | None:
    """Linear-interpolated percentile p (0–100) of a pre-sorted list.

    Returns None for an empty list. Matches numpy's default 'linear' method
    and Python 3.13 statistics.quantiles(method='inclusive') for n=100.
    """
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f, c = floor(k), ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def summary_stats(vals: list[float]) -> dict[str, float | None]:
    """Compute avg / median / p75 for a list of numbers.

    Returns a dict with None values when the input is empty, so callers can
    serialise the result to JSON without branching on emptiness.
    """
    if not vals:
        return {"avg": None, "median": None, "p75": None}
    s = sorted(vals)
    return {
        "avg": round(sum(s) / len(s), 4),
        "median": round(percentile(s, 50), 4),
        "p75": round(percentile(s, 75), 4),
    }


def iqr_bounds(vals: list[float], k: float = 3.0) -> tuple[float, float]:
    """Return (lower, upper) outlier fences using the k * IQR rule.

    Falls back to (-inf, +inf) — i.e. no fence — when there are too few
    values (<4) for quartiles to be meaningful.
    """
    if len(vals) < 4:
        return (float("-inf"), float("inf"))
    s = sorted(vals)
    n = len(s)
    q1 = s[n // 4]
    q3 = s[(3 * n) // 4]
    iqr = q3 - q1
    return (q1 - k * iqr, q3 + k * iqr)


def split_outliers(
    vals: list[float], k: float = 3.0
) -> tuple[list[float], list[float]]:
    """Partition vals into (within-fence, above-upper-fence) using k * IQR.

    Only the upper fence is used because in PR-time-to-approval data, unusually
    fast reviews are not the outliers we care about — long-running branches are.
    """
    if not vals:
        return [], []
    _, upper = iqr_bounds(vals, k)
    clean = [v for v in vals if v <= upper]
    outliers = [v for v in vals if v > upper]
    return clean, outliers
