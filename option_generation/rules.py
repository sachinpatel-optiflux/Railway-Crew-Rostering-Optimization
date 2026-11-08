"""Rule settings from constraints_df.csv, and the checks between two consecutive shifts of one person."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

SWING_BREAK = timedelta(hours=48)  # a longer gap starts a new swing (same as scripts/check_roster.py)


@dataclass(frozen=True)
class Rules:
    horizon_start: date
    horizon_days: int
    solver_start: date  # gap_filling_rules.md G1: nothing before this date changes
    shift_hours: int
    rest: timedelta
    transition_rest: timedelta
    day_from: int  # minutes after midnight
    day_to: int
    off_days: dict[str, int]  # Classification -> days off between swings
    excess_offsets: frozenset[int]  # allowed start changes for Excess, in minutes
    demand_offsets: frozenset[int]  # allowed start changes for Demand crew moving seat (F1: lift-up / layback)
    max_changes: int  # F3: start-time changes allowed per day/night block
    max_change_minutes: int  # F3: size of one change

    @classmethod
    def from_table(cls, rows: list[dict[str, str]]) -> "Rules":
        value = {r["Constraint"]: r["Value"] for r in rows if r["Status"] == "Active"}
        day_from, day_to = (int(t[:2]) * 60 + int(t[3:]) for t in value["Day Shift Window"].split("-"))
        if value["Relief Allowed Start Offsets"] != "ANY":
            raise SystemExit("error: only 'ANY' is supported for Relief Allowed Start Offsets")

        def offsets(name: str) -> frozenset[int]:
            return frozenset(int(x) for x in value[name].split(";"))

        return cls(
            horizon_start=date.fromisoformat(value["Planning Horizon Start"]),
            horizon_days=int(value["Planning Horizon Days"]),
            solver_start=date.fromisoformat(value["Solver Start Date"]),
            shift_hours=int(value["Shift Length Hours"]),
            rest=timedelta(hours=float(value["Ordinary Rest Hours"])),
            transition_rest=timedelta(hours=float(value["Transition Rest Hours"])),
            day_from=day_from,
            day_to=day_to,
            off_days={c: int(value[f"{c} Work/Off Days"].split("/")[1]) for c in ("FIFO", "Residential")},
            excess_offsets=offsets("Excess Allowed Start Offsets"),
            demand_offsets=offsets("Demand Allowed Start Offsets"),
            max_changes=int(value["Max Start Changes Per Block"]),
            max_change_minutes=int(value["Max Start Change Minutes"]),
        )

    @property
    def horizon_end(self) -> date:
        """First day after the horizon."""
        return self.horizon_start + timedelta(days=self.horizon_days)

    def is_day(self, start: datetime) -> bool:
        return self.day_from <= start.hour * 60 + start.minute < self.day_to

    def in_horizon(self, day: date) -> bool:
        return self.horizon_start <= day < self.horizon_end

    def solvable(self, day: date) -> bool:
        """May a row on this day change? From the solver start to the end of the horizon."""
        return self.solver_start <= day < self.horizon_end

    def block_minute(self, start: datetime) -> int:
        """Minutes since the start of its own window (day or night), so a night block never wraps midnight."""
        m = start.hour * 60 + start.minute
        return (m - (self.day_from if self.is_day(start) else self.day_to)) % 1440

    def can_follow(self, first, second) -> bool:
        """True if `second` may be the next shift after `first` in the same swing.

        Rest, day/night transition rest, one shift a day, location continuity, and (F3) no jump of more than
        the allowed change between two worked shifts of the same block. Relief standby rows (`standby`) have
        no real start time, so the F3 jump check skips them.
        """
        gap = second.start - first.end
        if gap < self.rest or gap > SWING_BREAK:
            return False
        if first.start.date() == second.start.date() or first.end_loc != second.start_loc:
            return False
        same_block = self.is_day(first.start) == self.is_day(second.start)
        if not same_block and gap < self.transition_rest:
            return False
        if same_block and not (first.standby or second.standby):
            step = abs(self.block_minute(first.start) - self.block_minute(second.start))
            if step > self.max_change_minutes:
                return False
        return True
