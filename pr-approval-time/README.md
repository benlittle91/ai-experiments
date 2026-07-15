# PR Approval Time (GAM Repos)

A no-nonsense reporting script that measures how long merged PRs take to reach **2 approvals** across GAM repositories.

It gives you leadership-ready stats for:

- time to second approval (days/hours)
- optional days-per-story-point normalisation
- per-repo and overall summaries

---

## What this does

For each configured repo, the tool:

1. fetches merged PRs in a date range
2. finds unique approvers (deduped by reviewer)
3. keeps PRs with **2+ approvals** for the main metric
4. optionally enriches with Jira story points
5. outputs summary tables + median/p75 + leadership summary text

---

## Project structure

```text
pr-approval-time/
├── pr_approval_time.sh              # orchestrator (gh/jq/jira + reporting)
├── pr_metrics.py                    # time/math/stat engine
└── README.md
```

---

## Requirements

Required:

- `bash`
- `gh`
- `jq`
- `python3`
- `awk`

Optional (only when Jira enrichment is enabled):

- `jira` CLI

---

## Quick start

From the `pr-approval-time` directory:

```bash
chmod +x pr_approval_time.sh pr_metrics.py
./pr_approval_time.sh --no-jira --from 2026-01-01 --to 2026-01-31 --max-repos 5
```

> Important: the repo list is currently hardcoded for my team. You must replace it with your own repos before using this outside our setup.

## Configure your repo list (required)

Edit `pr_approval_time.sh` and update the `REPOS=(...)` array to your org/team repositories.

```bash
# pr_approval_time.sh
REPOS=(
  your-repo-1
  your-repo-2
  your-repo-3
)
```

Tips:

- Keep repo directory names aligned with where this script expects to run from (`$BASE_DIR/<repo-name>`).
- Start with 2-3 repos and run with `--max-repos` while validating output.

---

## Usage

```bash
./pr_approval_time.sh [weeks]
./pr_approval_time.sh --from YYYY-MM-DD --to YYYY-MM-DD \
  [--jira-sp-field customfield_12345] \
  [--no-jira] \
  [--group-by-story-points | --no-group-by-story-points] \
  [--max-repos N]
```

### Examples

```bash
# Last 8 weeks (default), with Jira enrichment
./pr_approval_time.sh

# Last 12 weeks
./pr_approval_time.sh 12

# Explicit date range, no Jira
./pr_approval_time.sh --from 2026-02-01 --to 2026-02-28 --no-jira

# Date range + custom Jira SP field
./pr_approval_time.sh --from 2026-02-01 --to 2026-02-28 \
  --jira-sp-field customfield_10715

# Limit repos while iterating locally
./pr_approval_time.sh --from 2026-02-01 --to 2026-02-28 --max-repos 3
```

---

## Output (at a glance)

The script prints:

- repo-by-repo PR processing lines
- story-point cohort table (if Jira enabled)
- summary table (`Ttl`, `2+`, `<2`, `NoJ`, `NoSP`, average days)
- primary/secondary metrics:
  - time to 2nd approval: median, p75, avg
  - days/SP: median, p75, avg (if Jira enabled)
- grouped-by-story-points table (if enabled)
- leadership summary paragraph you can paste directly

## Comparing periods (month-over-month)

Use `pr_compare.py` to diff two snapshots produced with `--save-json`:

```bash
# Generic period comparison
python3 pr_compare.py april2026.json may2026.json

# AI adoption framing — use when snapshot_a is the pre-AI baseline
# and snapshot_b is the first period with Copilot reviewing every PR
python3 pr_compare.py april2026.json may2026.json --ai-adoption
```

The `--ai-adoption` flag:
- Adds a dedicated **AI Adoption Impact** section at the top with methodology notes and caveats
- Relabels all tables as "Baseline" vs "Post-AI" instead of "Period A/B"
- Highlights the p75 (tail) trend as the key signal for AI review benefit
- Provides "what to watch" guidance for subsequent months

---



- **Bash** handles orchestration (repo traversal, CLI calls, formatting).
- **Python** handles deterministic analytics (`pr_metrics.py`): datetime math, divisions, percentiles, grouped stats.

This split keeps shell scripting simple and keeps numeric logic maintainable.

---

## Troubleshooting

- `ERROR: Missing dependency 'X'`
  Install the missing CLI and re-run.

- `jira CLI not found...`
  Either install/configure `jira` CLI or run with `--no-jira`.

- `--from and --to must be used together`
  Provide both values in `YYYY-MM-DD` format.

- Empty-looking stats (`—`)
  Usually means no PRs met the metric criteria in that window (for example, no PRs with 2+ approvals).

---

## Practical tips

- Start with `--max-repos` when tuning date windows.
- Run `--no-jira` first to baseline raw approval timing.
- Use Jira mode once SP field quality is confirmed.
