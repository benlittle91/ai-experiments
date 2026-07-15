# Copilot Instructions — pr-approval-time

A bash+Python tool for measuring PR time-to-2-approvals across GitHub repos, producing leadership-ready stats.

---

## Running the tool

```bash
# From the pr-approval-time/ directory:
chmod +x pr_approval_time.sh pr_metrics.py

# Minimal run (no Jira):
./pr_approval_time.sh --no-jira --from 2026-01-01 --to 2026-01-31

# Limit repos while iterating:
./pr_approval_time.sh --no-jira --from 2026-01-01 --to 2026-01-31 --max-repos 3

# With Jira story-point enrichment:
./pr_approval_time.sh --from 2026-01-01 --to 2026-01-31 --jira-sp-field customfield_12345

# Save a snapshot for later comparison:
./pr_approval_time.sh --no-jira --from 2026-01-01 --to 2026-01-31 --save-json jan2026.json

# Compare two snapshots (prints comparison tables):
python3 pr_compare.py jan2026.json feb2026.json
```

---

## Architecture

- `pr_approval_time.sh` — orchestration: repo traversal, `gh`/`jq`/`jira` CLI calls, output formatting.
- `pr_metrics.py` — analytics engine and snapshot writer: datetime math, percentiles, grouped stats, and `--save-json` output.
- `stats.py` — shared percentile / summary-stats helpers imported by both Python modules. Unit-tested in `test_stats.py`.
- `models.py` — typed dataclasses (`Snapshot`, `Period`, `StatBundle`, `RepoStat`, `SpGroup`) describing the on-disk snapshot JSON contract.
- `pr_compare.py` — thin CLI: loads two snapshots via `Snapshot.load()` and delegates rendering to `report.py`.
- `report.py` — text rendering of executive / delivery-leads / detailed comparison sections.

This split is intentional: keep shell scripting simple, keep numeric logic maintainable and testable in Python.

---

## Configuration required before first use

`pr_approval_time.sh` auto-discovers repos by looking one directory up in `../../gam/*/` (relative to the script) for anything that is a git checkout. Adjust `REPOS_DIR` at the top of the script if your layout differs.

---

## Dependencies

Required: `bash`, `gh`, `jq`, `python3`, `awk`.
Optional: `jira` CLI (story-point enrichment only).

---

## Running the tests

```bash
python3 pr-approval-time/test_stats.py
```
