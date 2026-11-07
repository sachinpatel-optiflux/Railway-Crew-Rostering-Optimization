"""Rule settings from constraints_df.csv, and the checks between two shifts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

SWING_BREAK = timedelta(hours=48)  # a longer gap starts a new swing (same as scripts/check_roster.py)


@dataclass(frozen=True)
class Rules:
    horizon_start: date
    horizon_days: int
    shift_hours: int
    rest: timedelta
    transition_rest: timedelta
    day_from: int  # minutes after midnight
    day_to: int
    off_days: dict[str, int]  # Classification -> days off between swings
    excess_offsets: frozenset[int]  # allowed start changes for Excess, in minutes

    @classmethod
    def from_table(cls, rows: list[dict[str, str]]) -> "Rules":
        value = {r["Constraint"]: r["Value"] for r in rows}
        day_from, day_to = (int(t[:2]) * 60 + int(t[3:]) for t in value["Day Shift Window"].split("-"))
        if value["Relief Allowed Start Offsets"] != "ANY":
            raise SystemExit("error: only 'ANY' is supported for Relief Allowed Start Offsets")
        return cls(
            horizon_start=date.fromisoformat(value["Planning Horizon Start"]),
            horizon_days=int(value["Planning Horizon Days"]),
            shift_hours=int(value["Shift Length Hours"]),
            rest=timedelta(hours=float(value["Ordinary Rest Hours"])),
            transition_rest=timedelta(hours=float(value["Transition Rest Hours"])),
            day_from=day_from,
            day_to=day_to,
            off_days={c: int(value[f"{c} Work/Off Days"].split("/")[1]) for c in ("FIFO", "Residential")},
            excess_offsets=frozenset(int(x) for x in value["Excess Allowed Start Offsets"].split(";")),
        )

    def is_day(self, start: datetime) -> bool:
        return self.day_from <= start.hour * 60 + start.minute < self.day_to

    def in_horizon(self, day: date) -> bool:
        return 0 <= (day - self.horizon_start).days < self.horizon_days

    def can_follow(self, first, second) -> bool:
        """True if `second` may be the next shift after `first` in the same swing."""
        gap = second.start - first.end
        if gap < self.rest or gap > SWING_BREAK:
            return False
        if first.start.date() == second.start.date() or first.end_loc != second.start_loc:
            return False
        return self.is_day(first.start) == self.is_day(second.start) or gap >= self.transition_rest
