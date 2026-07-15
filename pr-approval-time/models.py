"""Typed model of a pr_approval_time snapshot.

Wrapping the on-disk JSON shape in dataclasses eliminates chains like
`a["stats"]["days"].get("median")` and makes the contract between the
snapshot writer (pr_metrics.py::cmd_save_snapshot) and the comparator
(pr_compare.py) explicit and greppable.

Every field is Optional-friendly so this loader tolerates older snapshots
missing fields introduced later (e.g. raw_days, min_days, max_days).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Period:
    from_: str
    to: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Period:
        return cls(from_=d["from"], to=d["to"])


@dataclass(frozen=True)
class Summary:
    total_examined: int = 0
    total_approved: int = 0
    excluded_lt2: int = 0
    excluded_no_jira: int = 0
    excluded_no_sp: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Summary:
        return cls(
            total_examined=int(d.get("total_examined", 0)),
            total_approved=int(d.get("total_approved", 0)),
            excluded_lt2=int(d.get("excluded_lt2", 0)),
            excluded_no_jira=int(d.get("excluded_no_jira", 0)),
            excluded_no_sp=int(d.get("excluded_no_sp", 0)),
        )


@dataclass(frozen=True)
class StatBundle:
    """The avg/median/p75 triple used for both raw days and days-per-SP."""

    avg: float | None = None
    median: float | None = None
    p75: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> StatBundle:
        d = d or {}
        return cls(avg=d.get("avg"), median=d.get("median"), p75=d.get("p75"))

    def as_dict(self) -> dict[str, float | None]:
        return {"avg": self.avg, "median": self.median, "p75": self.p75}


@dataclass(frozen=True)
class RepoStat:
    name: str
    total: int = 0
    approved: int = 0
    excluded_lt2: int = 0
    excluded_no_jira: int = 0
    excluded_no_sp: int = 0
    avg_days: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RepoStat:
        return cls(
            name=d["name"],
            total=int(d.get("total", 0)),
            approved=int(d.get("approved", 0)),
            excluded_lt2=int(d.get("excluded_lt2", 0)),
            excluded_no_jira=int(d.get("excluded_no_jira", 0)),
            excluded_no_sp=int(d.get("excluded_no_sp", 0)),
            avg_days=d.get("avg_days"),
        )


@dataclass(frozen=True)
class SpGroup:
    """Stats for one story-point bucket (e.g. all 3-point tickets)."""

    count: int = 0
    median_days: float | None = None
    p75_days: float | None = None
    avg_days: float | None = None
    min_days: float | None = None
    max_days: float | None = None
    median_dsp: float | None = None
    p75_dsp: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SpGroup:
        return cls(
            count=int(d.get("count", 0)),
            median_days=d.get("median_days"),
            p75_days=d.get("p75_days"),
            avg_days=d.get("avg_days"),
            min_days=d.get("min_days"),
            max_days=d.get("max_days"),
            median_dsp=d.get("median_dsp"),
            p75_dsp=d.get("p75_dsp"),
        )


@dataclass(frozen=True)
class Snapshot:
    """One period's data as produced by pr_metrics.py::cmd_save_snapshot."""

    period: Period
    summary: Summary
    days: StatBundle
    days_per_sp: StatBundle
    raw_days: list[float] = field(default_factory=list)
    repos: list[RepoStat] = field(default_factory=list)
    storypoint_groups: dict[str, SpGroup] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Snapshot:
        stats = d.get("stats", {})
        return cls(
            period=Period.from_dict(d["period"]),
            summary=Summary.from_dict(d.get("summary", {})),
            days=StatBundle.from_dict(stats.get("days")),
            days_per_sp=StatBundle.from_dict(stats.get("days_per_sp")),
            raw_days=list(d.get("raw_days") or []),
            repos=[RepoStat.from_dict(r) for r in d.get("repos", [])],
            storypoint_groups={
                sp: SpGroup.from_dict(g)
                for sp, g in (d.get("storypoint_groups") or {}).items()
            },
        )

    @classmethod
    def load(cls, path: str) -> Snapshot:
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def sp_group(self, key: str) -> SpGroup:
        """Return the SpGroup for `key`, or an empty default if absent.

        Lets callers write `snap.sp_group(sp).median_days` without repeatedly
        guarding on `sp in snap.storypoint_groups`.
        """
        return self.storypoint_groups.get(key, SpGroup())

    def repo(self, name: str) -> RepoStat | None:
        """Look up a repo by name, or None if not in this snapshot."""
        for r in self.repos:
            if r.name == name:
                return r
        return None
