# Methodology

How this tool measures PR approval time, what the numbers do and do not tell you, and how to interpret them without over-reading.

---

## What the metric measures

**Time to second approval** is defined as:

> The elapsed time between a pull request's `createdAt` timestamp and the `submittedAt` timestamp of the second unique reviewer to leave an approving review.

Both timestamps come from GitHub's immutable API. "Unique" means a single reviewer approving twice is counted once — we take the earliest approval per reviewer, sort chronologically, and take the second entry.

Elapsed time is calendar time, not working time (see *Limitations* below).

---

## What the metric does not measure

- **PR cycle time** (open → merge). A PR that is approved on day 1 but merges on day 4 has a 1-day *review time* and a 4-day *cycle time*. This tool measures the first.
- **Code quality of the review** — approval count is a proxy for "review happened", not "review was thorough". A reviewer who rubber-stamps in 30 seconds counts identically to one who spent an hour.
- **Reviewer effort** — approving three PRs in one sitting counts the same as approving one at a time.
- **Blocked or waiting states** — if a PR is opened Friday and approved Monday, the two calendar days over the weekend are counted in full. See *Working-time normalisation* below.

---

## Why PR events and not Jira column transitions

Both approaches are valid, but they answer different questions.

**Jira column time** measures workflow hygiene: how long a card sat in a column that someone was expected to drag it into and out of. Its accuracy depends entirely on how disciplined the team is at moving cards.

**PR time-to-2-approvals** measures the review event itself: the immutable GitHub timestamps of when the PR was opened and when reviewers approved. There is no human step between the event and the measurement.

The trade-off:

|  | Jira column time | PR time-to-2-approvals |
|---|---|---|
| Human step to capture | Someone drags a card | None — API timestamps |
| Definition ambiguity | "Exited Review" = approved / merged / QA'd / mis-dragged / bulk-moved | Exactly one: 2nd `Approve` click |
| Coverage | Silently drops PRs whose ticket wasn't tracked (hotfixes, dependabot, release-please) | Every merged PR accounted for; exclusions are counted with reasons |
| Auditable to | The Jira changelog, subjective interpretation | A specific PR, reviewer, and timestamp |
| Answers | "Is our workflow discipline healthy?" | "How long do reviewers actually take?" |

If the question is "are cards moving through the board correctly?", Jira column time is the right tool. If the question is "how long is code sitting waiting for review?", this tool is the right tool.

---

## The story-point breakdown

Because each PR is joined to its Jira ticket to fetch story points, review time can be sliced by ticket size (1 / 2 / 3 / 5 / 8 / 13). This matters because a single "average review time" number can move for two very different reasons:

1. Reviewers got slower.
2. The mix of work shipped got heavier (or lighter).

A blended average cannot distinguish these. The SP breakdown can. If 1-point tickets are quietly stalling while 5-point tickets speed up, the story-point view surfaces that immediately; a headline number would hide it.

This turns "reviews are slower this month" (unactionable) into "our smallest tickets are stalling" (a conversation the team can have).

---

## Outliers and small samples

### Outlier detection

We use the **3 × IQR rule** on the days-to-approval distribution. Any PR whose duration falls above `Q3 + 3 × (Q3 − Q1)` is flagged as an outlier. When outliers exist in a period, the comparison output shows two versions of the same table side-by-side: *ALL PRs* and *OUTLIERS REMOVED*. Neither is hidden; the reader sees the impact of the outlier without having to trust that we removed the right one.

Outlier PRs typically fall into one of three categories:

1. Long-lived feature branches merged into the window.
2. PRs held open across sprints while waiting for external input.
3. Reverts, hotfixes, or release-please PRs where branch protection was overridden after the substantive review already happened.

We prefer investigating outliers to deleting them — they usually indicate process debt worth surfacing.

### Small samples

Any story-point bucket with fewer than **5 PRs in either period** is flagged with `⚠ low n (X/Y)`. Low-n buckets are excluded from the delivery-leads narrative entirely, because a median from 1–4 data points reflects individual PRs rather than a pattern.

Per-repo averages that fall above the population's IQR upper bound are similarly flagged with `⚠ outlier`.

---

## What good practice looks like when quoting these numbers

**Do:**

- Lead with the median, not the average. The median is robust to a single runaway PR.
- Quote the sample size alongside every stat (`n = 33`, `n = 5`, etc.).
- Publish your exclusion rules once, up front, and apply them uniformly.
- Investigate outlier PRs by URL before deciding whether they're process debt or genuinely one-off.
- Use rolling three-month windows for trend claims. Two data points can only ever tell you "different", not "trending".

**Don't:**

- Trim outliers case-by-case to make a chart prettier. The metric's credibility comes from having one exclusion rule.
- Quote a single average with no context. Every number should carry its denominator and its spread.
- Hide the `<2 approvals` bucket. It is often several times larger than the included bucket; any story you tell must acknowledge which fraction of PRs the metric covers.
- Conflate review time with cycle time.
- Silently exclude any category of PR (bot PRs, AI-reviewer approvals, etc.) without documenting the rule.

---

## Known limitations

- **Calendar time, not working time.** A PR opened Friday afternoon and approved Monday morning has ~2.5 days of "elapsed review time" that is really ~4 working hours. Weekend and holiday PRs will look artificially slow.
- **Two approvals is a policy assumption.** If your branch protection requires a different number, the "2+ approvals" cohort will need adjusting.
- **`POS-<digits>` Jira ticket format is assumed by default.** Configurable via `--jira-project-prefix`. If your team uses multiple prefixes, only one is currently supported per run.
- **Repo discovery is filesystem-based.** The tool expects local git checkouts under `REPOS_DIR`. It does not query the GitHub API for repo lists.
- **Jira story-point field is a single hard-coded default** (`customfield_10715`). Override with `--jira-sp-field` if your instance uses a different ID.

---

## Reproducibility

Every run can be captured to JSON with `--save-json`, and the resulting file is versionable and comparable via `pr_compare.py`. Every number in an output table is derivable from the snapshot, and every snapshot is derivable from a specific date range against the current state of the repos and Jira.

Snapshots contain no PR contents, but do contain PR numbers, Jira ticket keys, and PR titles — treat them as internal team data and do not check them into public repositories.
