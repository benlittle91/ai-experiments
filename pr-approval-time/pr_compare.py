#!/usr/bin/env python3
"""Compare two pr_approval_time.sh snapshots and print month-over-month changes.

Usage:
  python3 pr_compare.py snapshot_a.json snapshot_b.json
  python3 pr_compare.py snapshot_a.json snapshot_b.json --ai-adoption
"""

from __future__ import annotations

import argparse
import sys

from models import Snapshot
from report import (
    render_ai_impact_summary,
    render_comparison,
    render_delivery_leads_summary,
    render_executive_summary,
)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="pr_compare.py",
        description="Compare two pr_approval_time.sh snapshots and print period-over-period changes.",
    )
    parser.add_argument("snapshot_a", help="Earlier period snapshot JSON")
    parser.add_argument("snapshot_b", help="Later period snapshot JSON")
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

    a = Snapshot.load(args.snapshot_a)
    b = Snapshot.load(args.snapshot_b)

    if args.ai_adoption:
        print(render_ai_impact_summary(a, b))
    print(render_executive_summary(a, b, ai_adoption=args.ai_adoption))
    print(render_delivery_leads_summary(a, b, ai_adoption=args.ai_adoption))
    print(render_comparison(a, b, ai_adoption=args.ai_adoption))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
