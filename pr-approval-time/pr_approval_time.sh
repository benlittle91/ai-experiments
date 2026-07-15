#!/bin/bash
# Multi-repo: PR time-to-2-approvals for all GAM repos
#
# Usage:
#   ./pr_approval_time.sh
#   ./pr_approval_time.sh 12
#   ./pr_approval_time.sh --from 2026-02-01 --to 2026-02-28
#   ./pr_approval_time.sh --group-by-story-points --jira-sp-field customfield_12345

set -euo pipefail

SINCE_DATE=""
UNTIL_DATE=""
WEEKS_BACK=""
JIRA_SP_FIELD="customfield_10715"
NO_JIRA=0
GROUP_BY_STORY_POINTS=1
MAX_REPOS=""
SAVE_JSON=""

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
REPOS_DIR="$(cd "$(dirname "$0")/../../gam" && pwd)"
METRICS_PY="$BASE_DIR/pr_metrics.py"

REPOS=()
for _repo_dir in "$REPOS_DIR"/*/; do
  [[ -d "${_repo_dir}.git" ]] && REPOS+=("$(basename "$_repo_dir")")
done
unset _repo_dir

die() {
  echo "ERROR: $*" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Usage:
  ./pr_approval_time.sh [weeks]
  ./pr_approval_time.sh --from YYYY-MM-DD --to YYYY-MM-DD [--jira-sp-field customfield_12345] [--no-jira] [--group-by-story-points|--no-group-by-story-points] [--max-repos N] [--save-json FILE]

Notes:
  - Date filtering uses merged PR dates.
  - Jira story point field defaults to customfield_10715.
USAGE
}

require_option_value() {
  local option_name="$1"
  local option_value="${2-}"
  if [[ -z "$option_value" || "$option_value" == --* ]]; then
    die "$option_name requires a value"
  fi
}

check_dependency() {
  local dep="$1"
  command -v "$dep" >/dev/null 2>&1 || die "Missing dependency '$dep'"
}

date_weeks_ago() {
  local weeks="$1"
  if date -v-1w +%Y-%m-%d >/dev/null 2>&1; then
    date -v-"${weeks}"w +%Y-%m-%d
  else
    date -d "-${weeks} weeks" +%Y-%m-%d
  fi
}

calc_duration() {
  python3 "$METRICS_PY" calc-duration "$1" "$2"
}

float_add() {
  awk -v a="$1" -v b="$2" 'BEGIN { printf "%.10f", (a + b) }'
}

num_div() {
  python3 "$METRICS_PY" num-div "$1" "$2"
}

file_stats() {
  python3 "$METRICS_PY" file-stats "$1"
}

extract_jira_key() {
  printf "%s\n%s\n%s\n" "$1" "$2" "$3" | grep -Eo 'POS-[0-9]+' | head -1 || true
}

setup_temp_files() {
  JIRA_CACHE_FILE=$(mktemp "$BASE_DIR/.pr_approval_jira_cache.XXXXXX")
  ALL_DAYS_FILE=$(mktemp "$BASE_DIR/.pr_approval_days.XXXXXX")
  ALL_DAYS_PER_SP_FILE=$(mktemp "$BASE_DIR/.pr_approval_days_per_sp.XXXXXX")
  STORYPOINT_TABLE_FILE=$(mktemp "$BASE_DIR/.pr_approval_storypoint_rows.XXXXXX")
  PER_REPO_FILE=$(mktemp "$BASE_DIR/.pr_approval_per_repo.XXXXXX")

  : > "$JIRA_CACHE_FILE"
  : > "$ALL_DAYS_FILE"
  : > "$ALL_DAYS_PER_SP_FILE"
  : > "$STORYPOINT_TABLE_FILE"
  : > "$PER_REPO_FILE"

  trap 'rm -f "$JIRA_CACHE_FILE" "$ALL_DAYS_FILE" "$ALL_DAYS_PER_SP_FILE" "$STORYPOINT_TABLE_FILE" "$PER_REPO_FILE"' EXIT
}

get_jira_metadata() {
  local issue_key="$1"
  local cached_line
  cached_line=$(grep -E "^${issue_key}[[:space:]]" "$JIRA_CACHE_FILE" | head -1 || true)
  if [[ -n "$cached_line" ]]; then
    echo "$cached_line" | cut -f2
    return 0
  fi

  local raw sp
  raw=$(jira issue view "$issue_key" --raw 2>/dev/null || true)
  if [[ -z "$raw" ]]; then
    printf "%s\t\n" "$issue_key" >> "$JIRA_CACHE_FILE"
    echo ""
    return 0
  fi

  sp=$(echo "$raw" | jq -r --arg field "$JIRA_SP_FIELD" '.fields[$field] // empty' 2>/dev/null || true)
  if [[ "$sp" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    printf "%s\t%s\n" "$issue_key" "$sp" >> "$JIRA_CACHE_FILE"
    printf "%s\n" "$sp"
  else
    printf "%s\t\n" "$issue_key" >> "$JIRA_CACHE_FILE"
    echo ""
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --from)
        require_option_value "$1" "${2-}"
        SINCE_DATE="$2"; shift 2 ;;
      --to)
        require_option_value "$1" "${2-}"
        UNTIL_DATE="$2"; shift 2 ;;
      --jira-sp-field)
        require_option_value "$1" "${2-}"
        JIRA_SP_FIELD="$2"; shift 2 ;;
      --no-jira)
        NO_JIRA=1; shift ;;
      --group-by-story-points)
        GROUP_BY_STORY_POINTS=1; shift ;;
      --no-group-by-story-points)
        GROUP_BY_STORY_POINTS=0; shift ;;
      --max-repos)
        require_option_value "$1" "${2-}"
        MAX_REPOS="$2"; shift 2 ;;
      --save-json)
        require_option_value "$1" "${2-}"
        SAVE_JSON="$2"; shift 2 ;;
      --help|-h)
        usage; exit 0 ;;
      --*)
        usage
        die "Unknown option: $1" ;;
      *)
        if [[ -n "$WEEKS_BACK" ]]; then
          die "Only one positional [weeks] argument is supported"
        fi
        WEEKS_BACK="$1"; shift ;;
    esac
  done
}

resolve_period() {
  if [[ -n "$SINCE_DATE" || -n "$UNTIL_DATE" ]]; then
    if [[ -z "$SINCE_DATE" || -z "$UNTIL_DATE" ]]; then
      die "--from and --to must be used together (YYYY-MM-DD)"
    fi
    PERIOD_LABEL="$SINCE_DATE → $UNTIL_DATE"
  else
    WEEKS_BACK="${WEEKS_BACK:-8}"
    SINCE_DATE=$(date_weeks_ago "$WEEKS_BACK")
    UNTIL_DATE=$(date +%Y-%m-%d)
    PERIOD_LABEL="$SINCE_DATE → $UNTIL_DATE (last $WEEKS_BACK weeks)"
  fi
}

validate_config() {
  for dep in gh jq python3 awk; do
    check_dependency "$dep"
  done

  if [[ ! -f "$METRICS_PY" ]]; then
    die "Missing helper script: $METRICS_PY"
  fi

  if [[ "$NO_JIRA" -eq 0 ]]; then
    command -v jira >/dev/null 2>&1 || die "jira CLI not found. Install/configure jira CLI or pass --no-jira"
  fi

  if [[ -n "$MAX_REPOS" && ! "$MAX_REPOS" =~ ^[0-9]+$ ]]; then
    die "--max-repos must be a non-negative integer"
  fi
}

print_header() {
  echo ""
  echo "════════════════════════════════════════════════════════════════"
  echo " GAM PR Time-to-2-Approvals (all repos)"
  echo " Period: $PERIOD_LABEL"
  echo " Filter: merged date"
  if [[ -n "$MAX_REPOS" && "$MAX_REPOS" -gt 0 ]]; then
    echo " Repos : ${PROCESSED_REPOS} of ${TOTAL_REPOS} (limited by --max-repos)"
  else
    echo " Repos : ${TOTAL_REPOS}"
  fi
  if [[ "$NO_JIRA" -eq 0 ]]; then
    echo " Jira  : story point field = $JIRA_SP_FIELD"
    if [[ "$GROUP_BY_STORY_POINTS" -eq 1 ]]; then
      echo " Group : exact story points = enabled"
    else
      echo " Group : exact story points = disabled"
    fi
  else
    echo " Jira  : disabled (--no-jira)"
  fi
  echo "════════════════════════════════════════════════════════════════"
}

process_repo() {
  local repo="$1"
  local repo_dir="$REPOS_DIR/$repo"

  if [[ ! -d "$repo_dir" ]]; then
    echo ""
    echo "  ── $repo (directory not found, skipping)"
    return
  fi

  pushd "$repo_dir" >/dev/null

  local pr_json
  pr_json=$(gh pr list \
    --state merged \
    --search "merged:>=$SINCE_DATE merged:<=$UNTIL_DATE" \
    --json number,createdAt,mergedAt,title,url,headRefName,body \
    --limit 500 2>/dev/null || echo "[]")

  local pr_count
  pr_count=$(echo "$pr_json" | jq 'length')

  if [[ "$pr_count" -eq 0 ]]; then
    popd >/dev/null
    summary_rows+=("$(printf "  %-55s  %4d  %4d  %4d  %4d  %4d  %s" "$repo" 0 0 0 0 0 "—")")
    printf "%s\t%d\t%d\t%d\t%d\t%d\t%s\n" "$repo" 0 0 0 0 0 "—" >> "$PER_REPO_FILE"
    return
  fi

  echo ""
  echo "  ── $repo  ($pr_count merged PR(s))"

  local repo_approved=0
  local repo_excluded_lt2=0
  local repo_excluded_no_jira=0
  local repo_excluded_no_sp=0
  local repo_days_sum=0.0

  while IFS= read -r pr_obj; do
    [[ -z "$pr_obj" ]] && continue

    local pr_num created_at pr_title head_ref pr_body jira_key story_points
    local second_approval duration hours days days_per_sp reviews_json unique_approvals

    pr_num=$(echo "$pr_obj" | jq -r '.number')
    created_at=$(echo "$pr_obj" | jq -r '.createdAt')
    pr_title=$(echo "$pr_obj" | jq -r '.title // ""')
    head_ref=$(echo "$pr_obj" | jq -r '.headRefName // ""')
    pr_body=$(echo "$pr_obj" | jq -r '.body // ""')

    jira_key=""
    story_points=""
    if [[ "$NO_JIRA" -eq 0 ]]; then
      jira_key=$(extract_jira_key "$pr_title" "$head_ref" "$pr_body")
      if [[ -n "$jira_key" ]]; then
        story_points=$(get_jira_metadata "$jira_key")
      fi
    fi

    reviews_json=$(gh pr view "$pr_num" --json reviews 2>/dev/null \
      | jq '[.reviews[] | select(.state == "APPROVED" and .author.login != null) | {author: .author.login, submittedAt: .submittedAt}] | sort_by(.submittedAt) | unique_by(.author)' 2>/dev/null \
      || echo '[]')

    unique_approvals=$(echo "$reviews_json" | jq 'length')

    if [[ "$unique_approvals" -lt 2 ]]; then
      repo_excluded_lt2=$((repo_excluded_lt2 + 1))
      printf "     PR #%-5s  [%s unique approval(s) — excluded]  %s\n" \
        "$pr_num" "$unique_approvals" "$(echo "$pr_title" | cut -c1-50)"
      continue
    fi

    repo_approved=$((repo_approved + 1))
    second_approval=$(echo "$reviews_json" | jq -r '.[1].submittedAt')

    duration=$(calc_duration "$created_at" "$second_approval")
    hours=$(echo "$duration" | cut -f1)
    days=$(echo "$duration" | cut -f2)

    repo_days_sum=$(float_add "$repo_days_sum" "$days")
    echo "$days" >> "$ALL_DAYS_FILE"

    days_per_sp=""
    if [[ "$NO_JIRA" -eq 0 ]]; then
      if [[ -z "$jira_key" ]]; then
        repo_excluded_no_jira=$((repo_excluded_no_jira + 1))
      elif [[ -z "$story_points" ]]; then
        repo_excluded_no_sp=$((repo_excluded_no_sp + 1))
      else
        days_per_sp=$(num_div "$days" "$story_points")
        if [[ -n "$days_per_sp" ]]; then
          echo "$days_per_sp" >> "$ALL_DAYS_PER_SP_FILE"
          printf "%s\t#%s\t%s\t%s\t%s\t%s\t%s\n" \
            "$repo" "$pr_num" "$jira_key" "$story_points" "$days" "$days_per_sp" "$pr_title" >> "$STORYPOINT_TABLE_FILE"
        fi
      fi
    fi

    if [[ -n "$days_per_sp" ]]; then
      printf "     PR #%-5s  %5.1f days  (%6.1f h)  %s  [%s SP, %.3f d/SP]\n" \
        "$pr_num" "$days" "$hours" "$(echo "$pr_title" | cut -c1-40)" "$story_points" "$days_per_sp"
    else
      printf "     PR #%-5s  %5.1f days  (%6.1f h)  %s\n" \
        "$pr_num" "$days" "$hours" "$(echo "$pr_title" | cut -c1-50)"
    fi

  done < <(echo "$pr_json" | jq -c '.[]')

  total_examined=$((total_examined + pr_count))
  total_approved=$((total_approved + repo_approved))
  total_excluded_lt2=$((total_excluded_lt2 + repo_excluded_lt2))
  total_excluded_no_jira=$((total_excluded_no_jira + repo_excluded_no_jira))
  total_excluded_no_sp=$((total_excluded_no_sp + repo_excluded_no_sp))

  local repo_avg
  if [[ "$repo_approved" -gt 0 ]]; then
    repo_avg=$(awk -v sum="$repo_days_sum" -v count="$repo_approved" 'BEGIN { printf "%.1f", (sum / count) }')
  else
    repo_avg="—"
  fi

  summary_rows+=("$(printf "  %-55s  %4d  %4d  %4d  %4d  %4d  %s" \
    "$repo" "$pr_count" "$repo_approved" "$repo_excluded_lt2" "$repo_excluded_no_jira" "$repo_excluded_no_sp" "${repo_avg} days")")

  printf "%s\t%d\t%d\t%d\t%d\t%d\t%s\n" \
    "$repo" "$pr_count" "$repo_approved" "$repo_excluded_lt2" \
    "$repo_excluded_no_jira" "$repo_excluded_no_sp" "$repo_avg" >> "$PER_REPO_FILE"

  popd >/dev/null
}

main() {
  parse_args "$@"
  resolve_period
  validate_config

  TOTAL_REPOS="${#REPOS[@]}"
  PROCESS_REPOS=("${REPOS[@]}")
  if [[ -n "$MAX_REPOS" && "$MAX_REPOS" -gt 0 ]]; then
    PROCESS_REPOS=("${REPOS[@]:0:$MAX_REPOS}")
  fi
  PROCESSED_REPOS="${#PROCESS_REPOS[@]}"

  setup_temp_files
  print_header

  total_examined=0
  total_approved=0
  total_excluded_lt2=0
  total_excluded_no_jira=0
  total_excluded_no_sp=0

  summary_rows=()

  for REPO in "${PROCESS_REPOS[@]}"; do
    process_repo "$REPO"
  done

  raw_stats=$(file_stats "$ALL_DAYS_FILE")
  raw_avg=$(echo "$raw_stats" | cut -f1)
  raw_median=$(echo "$raw_stats" | cut -f2)
  raw_p75=$(echo "$raw_stats" | cut -f3)

  sp_stats=$(file_stats "$ALL_DAYS_PER_SP_FILE")
  sp_avg=$(echo "$sp_stats" | cut -f1)
  sp_median=$(echo "$sp_stats" | cut -f2)
  sp_p75=$(echo "$sp_stats" | cut -f3)

  echo ""
  echo ""
  if [[ "$NO_JIRA" -eq 0 ]]; then
    echo "════════════════════════════════════════════════════════════════"
    echo " STORY-POINT METRIC COHORT (included rows)"
    echo "════════════════════════════════════════════════════════════════"
    if [[ -s "$STORYPOINT_TABLE_FILE" ]]; then
      printf "  %-36s  %-8s  %-12s  %6s  %6s  %8s  %s\n" "Repo" "PR" "Jira key" "SP" "Days" "Days/SP" "Title"
      echo "  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────"
      while IFS=$'\t' read -r repo pr jira_key sp days days_per_sp title; do
        printf "  %-36.36s  %-8s  %-12s  %6s  %6s  %8s  %.60s\n" \
          "$repo" "$pr" "$jira_key" "$sp" "$days" "$days_per_sp" "$title"
      done < "$STORYPOINT_TABLE_FILE"
    else
      echo "  (No PRs met story-point cohort criteria in this period)"
    fi
    echo ""
  fi

  echo "════════════════════════════════════════════════════════════════"
  echo " SUMMARY TABLE"
  echo "════════════════════════════════════════════════════════════════"
  printf "  %-55s  %4s  %4s  %4s  %4s  %4s  %s\n" "Repository" "Ttl" "2+" "<2" "NoJ" "NoSP" "Avg time"
  echo "  ────────────────────────────────────────────────────────────────────────────────────"
  for row in "${summary_rows[@]+"${summary_rows[@]}"}"; do
    echo "$row"
  done
  echo "  ────────────────────────────────────────────────────────────────────────────────────"
  printf "  %-55s  %4d  %4d  %4d  %4d  %4d  %s\n" \
    "TOTAL" "$total_examined" "$total_approved" "$total_excluded_lt2" "$total_excluded_no_jira" "$total_excluded_no_sp" "${raw_avg} days"
  echo "════════════════════════════════════════════════════════════════"

  echo ""
  echo " Primary (time to 2nd approval): median=${raw_median}, p75=${raw_p75}"
  echo " Secondary (time to 2nd approval): avg=${raw_avg}"
  if [[ "$NO_JIRA" -eq 0 ]]; then
    echo " Primary (days per story point): median=${sp_median}, p75=${sp_p75}"
    echo " Secondary (days per story point): avg=${sp_avg}"
  fi

  if [[ "$NO_JIRA" -eq 0 && "$GROUP_BY_STORY_POINTS" -eq 1 ]]; then
    echo ""
    echo "════════════════════════════════════════════════════════════════"
    echo " GROUPED BY EXACT STORY POINTS"
    echo "════════════════════════════════════════════════════════════════"
    if [[ -s "$STORYPOINT_TABLE_FILE" ]]; then
      python3 "$METRICS_PY" grouped-storypoints "$STORYPOINT_TABLE_FILE"
    else
      echo "  (No story-point grouped data available in this period)"
    fi
  fi

  echo ""
  echo "════════════════════════════════════════════════════════════════"
  echo " LEADERSHIP SUMMARY"
  echo "════════════════════════════════════════════════════════════════"
  eligible_count=$(wc -l < "$ALL_DAYS_PER_SP_FILE" | tr -d ' ')
  if [[ "$total_approved" -gt 0 ]]; then
    coverage_pct=$(python3 "$METRICS_PY" coverage "$eligible_count" "$total_approved")
  else
    coverage_pct="0.0"
  fi
  echo " Period: $SINCE_DATE to $UNTIL_DATE"
  echo " We reviewed $total_examined merged PRs in this period; $total_approved reached at least two approvals."
  echo " How long it typically takes to get two approvals: median is ${raw_median} days (a typical PR), and p75 is ${raw_p75} days (about 3 in 4 are at or below this)."
  echo " How this changes when adjusted for ticket effort (story points): median is ${sp_median} days per point, and p75 is ${sp_p75} days per point."
  echo " How much of the dataset has Jira story-point coverage: ${eligible_count}/${total_approved} PRs (${coverage_pct}%)."

  echo ""
  echo "  Note: PRs with <2 approvals are excluded from the avg time."
  echo "  These are typically: automated release-please PRs, emergency"
  echo "  reverts, or snapshot-removal commits where branch protection"
  echo "  was overridden after the substantive change was already reviewed."
  echo ""

  if [[ -n "$SAVE_JSON" ]]; then
    python3 "$METRICS_PY" save-snapshot \
      --from "$SINCE_DATE" \
      --to "$UNTIL_DATE" \
      --total-examined "$total_examined" \
      --total-approved "$total_approved" \
      --excluded-lt2 "$total_excluded_lt2" \
      --excluded-no-jira "$total_excluded_no_jira" \
      --excluded-no-sp "$total_excluded_no_sp" \
      --days-file "$ALL_DAYS_FILE" \
      --dsp-file "$ALL_DAYS_PER_SP_FILE" \
      --sp-table "$STORYPOINT_TABLE_FILE" \
      --repo-file "$PER_REPO_FILE" \
      --output "$SAVE_JSON"
    echo " Snapshot saved: $SAVE_JSON"
  fi
}

main "$@"
