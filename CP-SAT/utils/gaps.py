"""Find the gaps left by the removed crew: Demand seats in the horizon with nobody on them."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from .data import Problem


@dataclass(frozen=True)
class Slot:
    """One activity at one start time on one day. `seats` is how many people it is short of."""

    activity_id: str
    start: datetime
    seats: int
    demand_id: str

    @property
    def key(self) -> tuple[str, str]:
        return self.activity_id, self.start.isoformat(timespec="minutes")


def slot_times(problem: Problem, activity_id: str, start: datetime) -> tuple[datetime, str, str]:
    """End time and start/end depots of a duty on this activity."""
    activity = problem.activities[activity_id]
    return start + timedelta(hours=problem.rules.shift_hours), activity["Start Depot"], activity["End Depot"]


def find_gaps(problem: Problem) -> list[Slot]:
    """Compare demand with the Demand rows of the remaining crew, slot by slot.

    Counting against demand (not just listing the removed rows) means Excess and Relief rows of
    removed crew never become gaps (rule G7), and a slot is never opened twice.
    """
    rules = problem.rules
    filled = Counter(
        (r["Activity ID"], r["_s"])
        for r in problem.roster
        if r["Assignment Type"] == "Demand" and r["User Id"] not in problem.removed
    )
    slots = []
    for offset in range(rules.horizon_days):
        day = rules.horizon_start + timedelta(days=offset)
        for (activity_id, shift), row in problem.demand.items():
            start = datetime.fromisoformat(f"{day.isoformat()}T{shift}")
            short = int(row["Demand"]) - filled[(activity_id, start)]
            if short > 0:
                slots.append(Slot(activity_id, start, short, row["Demand ID"]))
    return slots
