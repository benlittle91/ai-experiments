#!/usr/bin/env python3
"""PR analytics helper for pr_approval_time.sh.

Keeps numeric/time/stat logic in one place so shell script remains orchestration.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime
from math import ceil, floor


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def pct(sorted_vals: list[float], percentile: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (percentile / 100.0)
    f = floor(k)
    c = ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def fmt_num(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def cmd_calc_duration(args: argparse.Namespace) -> int:
    opened = parse_iso(args.opened)
    approved = parse_iso(args.approved)
    secs = (approved - opened).total_seconds()
    hours = secs / 3600
    days = hours / 24
    print(f"{hours:.2f}\t{days:.2f}")
    return 0


def cmd_num_div(args: argparse.Namespace) -> int:
    num = float(args.num)
    den = float(args.den)
    if den <= 0:
        print("")
    else:
        print(f"{(num / den):.4f}")
    return 0


def cmd_file_stats(args: argparse.Namespace) -> int:
    vals: list[float] = []
    with open(args.path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                vals.append(float(line))

    if not vals:
        print("—\t—\t—")
        return 0

    vals.sort()
    avg = sum(vals) / len(vals)
    med = pct(vals, 50)
    p75 = pct(vals, 75)
    print(f"{avg:.2f}\t{med:.2f}\t{p75:.2f}")
    return 0


def cmd_grouped_storypoints(args: argparse.Namespace) -> int:
    groups: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"days": [], "dsp": []})

    with open(args.path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 6:
                continue

            sp = parts[3].strip()
            days = parts[4].strip()
            dsp = parts[5].strip()

            if not sp:
                continue

            try:
                groups[sp]["days"].append(float(days))
            except ValueError:
                pass

            if dsp:
                try:
                    groups[sp]["dsp"].append(float(dsp))
                except ValueError:
                    pass

    def sort_key(sp: str) -> tuple[int, float | str, str]:
        try:
            return (0, float(sp), sp)
        except ValueError:
            return (1, sp.lower(), sp)

    print(f"  {'SP':<8}  {'Count':>5}  {'Median days':>11}  {'P75 days':>8}  {'Median d/SP':>11}  {'P75 d/SP':>9}")
    print("  ─────────────────────────────────────────────────────────────────────────────")

    for sp in sorted(groups.keys(), key=sort_key):
        days_vals = sorted(groups[sp]["days"])
        dsp_vals = sorted(groups[sp]["dsp"])
        med_days = pct(days_vals, 50)
        p75_days = pct(days_vals, 75)
        med_dsp = pct(dsp_vals, 50)
        p75_dsp = pct(dsp_vals, 75)
        print(
            f"  {sp:<8}  {len(days_vals):>5}  {fmt_num(med_days):>11}  {fmt_num(p75_days):>8}  "
            f"{fmt_num(med_dsp):>11}  {fmt_num(p75_dsp):>9}"
        )

    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    eligible = int(args.eligible)
    approved = int(args.approved)
    if approved <= 0:
        print("0.0")
    else:
        print(f"{(eligible / approved) * 100:.1f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pr_metrics.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("calc-duration")
    p.add_argument("opened")
    p.add_argument("approved")
    p.set_defaults(func=cmd_calc_duration)

    p = sub.add_parser("num-div")
    p.add_argument("num")
    p.add_argument("den")
    p.set_defaults(func=cmd_num_div)

    p = sub.add_parser("file-stats")
    p.add_argument("path")
    p.set_defaults(func=cmd_file_stats)

    p = sub.add_parser("grouped-storypoints")
    p.add_argument("path")
    p.set_defaults(func=cmd_grouped_storypoints)

    p = sub.add_parser("coverage")
    p.add_argument("eligible")
    p.add_argument("approved")
    p.set_defaults(func=cmd_coverage)

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
