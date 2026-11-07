"""Work out what each crew swing could do: its rows, and each legal replacement for each row.

A swing is one person's run of shifts between two off periods. Each row of a swing gets a list of
options: keep it, or replace it with a gap (`fill`) or a trip home (`ride`). Options that can never
sit in a legal sequence are removed here, so the CP-SAT model stays small.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .data import TRAVEL_TYPES, WORK_TYPES, Problem
from .gaps import Slot, slot_times
from .rules import SWING_BREAK

FREE_TYPES = ("Excess", "Relief")
RETURN_RIDES = (("A03", "22:00"),)  # the Work Train return seat (Q12): Excess on Yarmouth Mainline 22:00


@dataclass(frozen=True)
class Option:
    row_index: int  # position of the row in its swing
    kind: str  # keep | fill | ride
    start: datetime
    end: datetime
    start_loc: str
    end_loc: str
    cost: int = 0
    activity_id: str = ""
    demand_id: str = ""
    slot_key: tuple[str, str] | None = None  # fill only


@dataclass
class Swing:
    user: str
    home: str
    classification: str
    rows: list[dict]
    earliest_start: datetime | None = None
    latest_end: datetime | None = None
    options: list[list[Option]] = field(default_factory=list)  # one list per row

    def droppable(self, index: int, allow: bool) -> bool:
        return allow and is_free(self.rows[index])


def is_free(row: dict) -> bool:
    """Only unlocked rows inside the horizon may change."""
    return row["Is Locked"] == "No" and row["Assignment Type"] in FREE_TYPES and row["In Horizon"] == "Yes"


def build_swings(problem: Problem) -> list[Swing]:
    """Split each person's work rows into swings, with the time limits set by off days and travel."""
    work, travel = defaultdict(list), defaultdict(list)
    for row in sorted(problem.roster, key=lambda r: r["_s"]):
        if row["User Id"] in problem.crew:
            if row["Assignment Type"] in WORK_TYPES:
                work[row["User Id"]].append(row)
            elif row["Assignment Type"] in TRAVEL_TYPES:
                travel[row["User Id"]].append(row)

    swings = []
    for user, rows in work.items():
        person = problem.crew[user]
        groups = [[rows[0]]]
        for previous, current in zip(rows, rows[1:]):
            if current["_s"] - previous["_e"] > SWING_BREAK:
                groups.append([current])
            else:
                groups[-1].append(current)
        off = timedelta(days=problem.rules.off_days[person["Classification"]])
        arrivals = [t for t in travel[user] if t["Assignment Type"] == "Travel In"]
        departures = [t for t in travel[user] if t["Assignment Type"] == "Travel Out"]
        for i, group in enumerate(groups):
            earliest = [groups[i - 1][-1]["_e"] + off] if i else []
            latest = [groups[i + 1][0]["_s"] - off] if i + 1 < len(groups) else []
            earliest += [t["_e"] for t in arrivals if t["_e"] <= group[0]["_s"]][-1:]
            latest += [t["_s"] for t in departures if t["_s"] >= group[-1]["_e"]][:1]
            swings.append(
                Swing(
                    user=user,
                    home=person["Depot"],
                    classification=person["Classification"],
                    rows=group,
                    earliest_start=max(earliest, default=None),
                    latest_end=min(latest, default=None),
                )
            )
    return swings


def can_work(problem: Problem, user: str, activity_id: str, day: date) -> bool:
    """Eligibility, role, medical, competencies and currency for one person on one duty."""
    person, activity = problem.crew[user], problem.activities[activity_id]
    if activity_id not in person["Eligibility"].split(";") or person["Medical"] != "Fit":
        return False
    if person["Role"] not in [r.strip() for r in activity["Roles/Job"].split(";")]:
        return False
    held = problem.held_codes.get(user, {})
    if any(held.get(code, date.min) < day for code in problem.required_codes[activity_id]):
        return False
    if activity["Currency Threshold"]:
        last = problem.last_done.get((user, activity["Activity Head"]))
        return last is not None and (day - last).days <= int(activity["Currency Threshold"])
    return True


def clock_hours_apart(a: datetime, b: datetime) -> float:
    """Distance between two times of day, in hours (0 to 12)."""
    minutes = abs((a.hour * 60 + a.minute) - (b.hour * 60 + b.minute))
    return min(minutes, 1440 - minutes) / 60


def fill_cost(row: dict, slot: Slot, costs, excess_offsets: frozenset[int]) -> int | None:
    """Cost of moving `row` onto `slot`, or None if the move is not allowed for this row type."""
    offset = int((slot.start - row["_s"]).total_seconds() // 60)
    if row["Assignment Type"] == "Excess":
        if offset not in excess_offsets:
            return None
        if offset == 0 and row["Activity ID"] == slot.activity_id:
            return costs.excess_same_slot
        return costs.excess_moved + abs(offset) // 60
    if row["_s"].date() != slot.start.date():
        return None
    return costs.relief_fill + round(clock_hours_apart(row["_s"], slot.start))


def add_options(problem: Problem, swings: list[Swing], slots: list[Slot], costs, allow_drop: bool, allow_rides: bool):
    """Fill in `Swing.options`, then remove the options no legal sequence can use."""
    rules = problem.rules
    by_day: dict[date, list[Slot]] = defaultdict(list)
    for slot in slots:
        by_day[slot.start.date()].append(slot)
    open_slots = {(s.activity_id, s.start) for s in slots}

    for swing in swings:
        swing.options = []
        for index, row in enumerate(swing.rows):
            options = [
                Option(index, "keep", row["_s"], row["_e"], row["Start Location"], row["End Location"],
                       activity_id=row["Activity ID"], demand_id=row["Demand ID"])
            ]  # fmt: skip
            if is_free(row):
                days = {row["_s"].date()}
                if row["Assignment Type"] == "Excess":  # a one-hour move can cross midnight
                    days |= {(row["_s"] + timedelta(minutes=m)).date() for m in rules.excess_offsets}
                for day in days:
                    for slot in by_day[day]:
                        cost = fill_cost(row, slot, costs, rules.excess_offsets)
                        if cost is None or not can_work(problem, swing.user, slot.activity_id, slot.start.date()):
                            continue
                        end, start_loc, end_loc = slot_times(problem, slot.activity_id, slot.start)
                        options.append(
                            Option(index, "fill", slot.start, end, start_loc, end_loc, cost,
                                   slot.activity_id, slot.demand_id, slot.key)
                        )  # fmt: skip
                if allow_rides:
                    options += ride_options(problem, swing, row, index, open_slots, costs)
            swing.options.append(options)
        prune(problem, swing, allow_drop)


def ride_options(problem: Problem, swing: Swing, row: dict, index: int, open_slots: set, costs) -> list[Option]:
    """A trip across the line as Excess on a seat that is already covered, to get home or into position."""
    rides = []
    for activity_id, shift in RETURN_RIDES:
        start = datetime.fromisoformat(f"{row['_s'].date().isoformat()}T{shift}")
        if (activity_id, start) in open_slots or not can_work(problem, swing.user, activity_id, start.date()):
            continue
        end, start_loc, end_loc = slot_times(problem, activity_id, start)
        demand_id = problem.demand[(activity_id, shift)]["Demand ID"]
        rides.append(Option(index, "ride", start, end, start_loc, end_loc, costs.ride, activity_id, demand_id))
    return rides


def can_open(problem: Problem, swing: Swing, option: Option) -> bool:
    """May this option be the first shift of the swing?"""
    if option.start_loc != swing.home or (swing.earliest_start and option.start < swing.earliest_start):
        return False
    return swing.classification != "Residential" or problem.rules.is_day(option.start)


def can_close(swing: Swing, option: Option) -> bool:
    """May this option be the last shift of the swing?"""
    return option.end_loc == swing.home and not (swing.latest_end and option.end > swing.latest_end)


def skippable(swing: Swing, first: int, last: int, allow_drop: bool) -> bool:
    """True if every row strictly between positions `first` and `last` may be dropped."""
    return all(swing.droppable(i, allow_drop) for i in range(first + 1, last))


def prune(problem: Problem, swing: Swing, allow_drop: bool) -> None:
    """Keep only options on some complete legal path through the swing."""
    rules, count = problem.rules, len(swing.options)
    reach_from_start: set[Option] = set()
    for i, options in enumerate(swing.options):
        for option in options:
            if skippable(swing, -1, i, allow_drop) and can_open(problem, swing, option):
                reach_from_start.add(option)
                continue
            for j in range(i):
                if skippable(swing, j, i, allow_drop) and any(
                    p in reach_from_start and rules.can_follow(p, option) for p in swing.options[j]
                ):
                    reach_from_start.add(option)
                    break
    reach_end: set[Option] = set()
    for i in range(count - 1, -1, -1):
        for option in swing.options[i]:
            if skippable(swing, i, count, allow_drop) and can_close(swing, option):
                reach_end.add(option)
                continue
            for j in range(i + 1, count):
                if skippable(swing, i, j, allow_drop) and any(
                    n in reach_end and rules.can_follow(option, n) for n in swing.options[j]
                ):
                    reach_end.add(option)
                    break
    swing.options = [[o for o in options if o in reach_from_start and o in reach_end] for options in swing.options]
