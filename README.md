# ai-experiments

Small, self-contained tools that came out of ideas worth exploring.

## What's here

### [`pr-approval-time/`](./pr-approval-time)

A command-line tool that measures how long merged pull requests take to reach two approvals across a set of GitHub repositories. Produces leadership-ready summary tables, per-repo breakdowns, and — when Jira is available — review time normalised by story-point size (1 / 2 / 3 / 5 / 8 / 13). Supports saving snapshots and diffing periods (e.g. April → June) to spot trends.

See [`pr-approval-time/README.md`](./pr-approval-time/README.md) for setup and usage, and [`pr-approval-time/METHODOLOGY.md`](./pr-approval-time/METHODOLOGY.md) for what the metric measures, what it deliberately doesn't, and how to interpret the numbers.
