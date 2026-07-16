# PR Approval Time

A command-line tool that measures how long merged pull requests take to reach **two approvals** across a set of GitHub repositories, and produces leadership-ready summary tables.

The tool is deliberately unopinionated about *what* the numbers mean — see [`METHODOLOGY.md`](./METHODOLOGY.md) for interpretation guidance, limitations, and comparison to alternative approaches (e.g. Jira column-time).

---

## What it produces

For a given date range, the tool:

1. Fetches merged PRs from each configured repository.
2. Deduplicates approvers per PR (a single reviewer approving twice counts once).
3. Keeps PRs with **two or more unique approvals** for the main metric.
4. Optionally enriches each PR with its Jira ticket's story-point value.
5. Prints a streaming per-repo view, a summary table, and a plain-English "leadership summary" paragraph you can paste directly into a report.
6. Optionally writes the run to a JSON snapshot for later comparison.

Output includes:

- **Time to 2nd approval** — median, p75, and average (in days).
- **Days per story point** — the same metrics, normalised by ticket effort (Jira mode only).
- **Per-repo breakdown** — average days for each repository.
- **Story-point breakdown** — median days grouped by SP size (1 / 2 / 3 / 5 / 8 / 13 …).
- **Excluded PRs, with reasons** — how many PRs were dropped and why (<2 approvals, no Jira ticket, no story points).

---

## Project structure

```text
pr-approval-time/
├── pr_approval_time.sh   # orchestrator: repo traversal, gh/jq/jira CLI calls
├── pr_metrics.py         # analytics engine + snapshot writer
├── pr_compare.py         # CLI that diffs two snapshots
├── report.py             # text rendering of comparison sections
├── models.py             # typed dataclasses describing the snapshot JSON
├── stats.py              # shared percentile / summary-stats helpers
├── test_stats.py         # unit tests for stats.py
├── README.md
└── METHODOLOGY.md        # what the metric measures, what it doesn't, and why
```

---

## Requirements

Required:

- `bash`, `gh`, `jq`, `python3`, `awk`

Optional (Jira story-point enrichment only):

- `jira` CLI (configured for your Jira instance)

---

## Setup

The tool discovers repositories to analyse by scanning a directory of git checkouts. By default it looks at `../../gam/*/` relative to the script — i.e. it expects to be run from inside a checkout that sits alongside a `gam/` directory containing your team's cloned repos.

To point it at a different directory, edit the top of `pr_approval_time.sh`:

```bash
REPOS_DIR="$(cd "$(dirname "$0")/../../gam" && pwd)"
```

No other configuration is required for a first run.

---

## Quick start

```bash
chmod +x pr_approval_time.sh pr_metrics.py

# Smallest possible run — no Jira, two repos, one month:
./pr_approval_time.sh --no-jira --from 2026-01-01 --to 2026-01-31 --max-repos 2
```

---

## Usage

```bash
./pr_approval_time.sh [weeks]

./pr_approval_time.sh --from YYYY-MM-DD --to YYYY-MM-DD \
  [--jira-sp-field customfield_12345] \
  [--jira-project-prefix POS] \
  [--no-jira] \
  [--group-by-story-points | --no-group-by-story-points] \
  [--max-repos N] \
  [--save-json FILE]
```

### Options

| Flag | Description |
|---|---|
| `[weeks]` | Positional. Analyse the last N weeks (default: 8). |
| `--from`, `--to` | Explicit date range. Both required together, in `YYYY-MM-DD`. Uses PR merged date. |
| `--jira-sp-field` | Custom Jira field ID that holds story points. Default: `customfield_10715`. |
| `--jira-project-prefix` | Jira project key prefix used to extract ticket IDs from PR titles / branch names / bodies. Default: `POS`. |
| `--no-jira` | Skip Jira enrichment entirely. Faster; no story-point breakdown. |
| `--group-by-story-points` / `--no-group-by-story-points` | Toggle the "grouped by exact story points" table. Default: enabled. |
| `--max-repos N` | Only analyse the first N discovered repos. Useful while iterating. |
| `--save-json FILE` | Also write the run to a JSON snapshot for later comparison with `pr_compare.py`. |

### Examples

```bash
# Last 12 weeks with Jira enrichment
./pr_approval_time.sh 12

# Explicit range, no Jira, limited repos
./pr_approval_time.sh --from 2026-02-01 --to 2026-02-28 --no-jira --max-repos 3

# Save a snapshot for later diffing
./pr_approval_time.sh --from 2026-04-01 --to 2026-04-30 --save-json april2026.json

# Different Jira project prefix (e.g. GAM instead of POS)
./pr_approval_time.sh --from 2026-06-01 --to 2026-06-30 --jira-project-prefix GAM
```

---

## Comparing periods (`pr_compare.py`)

Once you have two snapshots produced with `--save-json`, diff them:

```bash
# Generic period-over-period comparison
python3 pr_compare.py april2026.json may2026.json

# AI-adoption framing — snapshot A is the pre-AI baseline,
# snapshot B is the first period with AI reviewing every PR
python3 pr_compare.py april2026.json may2026.json --ai-adoption
```

The `--ai-adoption` flag:

- Adds a dedicated **AI Adoption Impact** section at the top with methodology notes and caveats.
- Relabels all tables as "Baseline" vs "Post-AI" instead of "Period A/B".
- Highlights p75 (the tail) as the key signal for AI review benefit.
- Provides "what to watch" guidance for subsequent months.

---

## Testing

```bash
python3 test_stats.py
```

13 unit tests covering the shared percentile / summary-stats / outlier helpers.

---

## Architecture

- **Bash** handles orchestration: repo traversal, `gh` / `jq` / `jira` CLI calls, output formatting.
- **Python** handles all deterministic analytics: datetime math, divisions, percentiles, IQR-based outlier detection, grouped stats, snapshot IO.

This split keeps shell scripting simple and keeps numeric logic maintainable and testable.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ERROR: Missing dependency 'X'` | Install the missing CLI and re-run. |
| `jira CLI not found...` | Either install/configure the `jira` CLI, or run with `--no-jira`. |
| `--from and --to must be used together` | Provide both, in `YYYY-MM-DD` format. |
| Empty stats (`—`) | No PRs met the metric criteria in that window — usually means no PRs had two or more approvals. Check the excluded-PRs summary. |
| `WARN: gh pr list failed for <repo>` | The gh CLI could not query that repo (typically auth or repo-name mismatch). The run continues; the repo is reported with zero PRs. |

---

## Reading the output

See [`METHODOLOGY.md`](./METHODOLOGY.md) for:

- What "time to 2nd approval" precisely measures.
- What this tool deliberately *does not* measure.
- How outliers are detected and displayed.
- How small-sample buckets are flagged.
- Why we use PR events rather than Jira column transitions.
- How to interpret month-over-month changes without over-reading.
