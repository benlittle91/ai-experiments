"""Tests for the shared stats module.

Run with:
    python3 -m pytest pr-approval-time/test_stats.py -v

Or, without pytest, as a plain script (the assertions still fire):
    python3 pr-approval-time/test_stats.py
"""

from __future__ import annotations

import math

from stats import iqr_bounds, percentile, split_outliers, summary_stats


# ---------- percentile ----------

def test_percentile_empty_returns_none():
    assert percentile([], 50) is None
    assert percentile([], 99) is None


def test_percentile_single_value_returns_that_value():
    assert percentile([7.0], 0) == 7.0
    assert percentile([7.0], 50) == 7.0
    assert percentile([7.0], 100) == 7.0


def test_percentile_matches_numpy_linear_method():
    # Reference values computed with numpy.percentile(data, p, method='linear').
    data = sorted([1.0, 2.0, 3.0, 4.0, 5.0])
    assert percentile(data, 0) == 1.0
    assert percentile(data, 25) == 2.0
    assert percentile(data, 50) == 3.0
    assert percentile(data, 75) == 4.0
    assert percentile(data, 100) == 5.0


def test_percentile_interpolates_between_ranks():
    # 4 points, p=50 falls between index 1 and 2 → mean of 2.0 and 3.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5


# ---------- summary_stats ----------

def test_summary_stats_empty_returns_none_dict():
    assert summary_stats([]) == {"avg": None, "median": None, "p75": None}


def test_summary_stats_basic():
    result = summary_stats([1.0, 2.0, 3.0, 4.0, 5.0])
    assert result["avg"] == 3.0
    assert result["median"] == 3.0
    assert result["p75"] == 4.0


def test_summary_stats_rounds_to_four_places():
    result = summary_stats([1.0, 2.0])  # avg = 1.5, median = 1.5, p75 = 1.75
    assert result["avg"] == 1.5
    assert result["median"] == 1.5
    assert result["p75"] == 1.75


def test_summary_stats_accepts_unsorted_input():
    a = summary_stats([5.0, 1.0, 3.0, 2.0, 4.0])
    b = summary_stats([1.0, 2.0, 3.0, 4.0, 5.0])
    assert a == b


# ---------- iqr_bounds ----------

def test_iqr_bounds_too_few_values_disables_fence():
    lower, upper = iqr_bounds([1.0, 2.0, 3.0])
    assert lower == float("-inf")
    assert upper == float("inf")


def test_iqr_bounds_fences_around_bulk_of_data():
    # Bulk 1..10 with one huge outlier. Upper fence should exclude 1000.
    _, upper = iqr_bounds([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 1000], k=3.0)
    assert upper < 1000
    assert upper > 10  # doesn't clip real values


# ---------- split_outliers ----------

def test_split_outliers_empty():
    clean, out = split_outliers([])
    assert clean == []
    assert out == []


def test_split_outliers_partitions_only_upper_tail():
    # Only the far-high value should be flagged; low values are never outliers.
    vals = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 1000.0]
    clean, out = split_outliers(vals)
    assert 1000.0 in out
    assert set(clean) == set(vals) - {1000.0}


def test_split_outliers_no_outliers_leaves_data_intact():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    clean, out = split_outliers(vals)
    assert out == []
    assert sorted(clean) == vals


if __name__ == "__main__":
    # Run every test_* function without needing pytest installed.
    import sys
    failures = 0
    tests = [
        (name, obj) for name, obj in globals().items()
        if name.startswith("test_") and callable(obj)
    ]
    for name, fn in tests:
        try:
            fn()
        except AssertionError as e:
            failures += 1
            print(f"FAIL: {name}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR: {name}: {type(e).__name__}: {e}")
        else:
            print(f"ok: {name}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
