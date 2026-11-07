"""Turn the solver's choices into the recovered roster and the report files."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from .data import Problem
from .gaps import Slot

TIME = "%H:%M"
DAY = "%Y-%m-%d"


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def rewrite_row(problem: Problem, row: dict, option) -> dict:
    """The roster row after a move. It keeps its Assignment ID, Line ID and Swing."""
    activity = problem.activities[option.activity_id]
    new = dict(row)
    new.update({
        "Start Date": option.start.strftime(DAY),
        "End Date": option.end.strftime(DAY),
        "Shift Start Time": option.start.strftime(TIME),
        "Shift End Time": option.end.strftime(TIME),
        "Activity ID": option.activity_id,
        "Activity Name": activity["Activity Name"],
        "Activity Head": activity["Activity Head"],
        "Activity Type": activity["Activity Type"],
        "Activity Group": activity["Activity Group"],
        "Assignment Type": "Demand" if option.kind == "fill" else "Excess",
        "Is Locked": "Yes" if option.kind == "fill" else "No",
        "Demand ID": option.demand_id,
        "Start Location": option.start_loc,
        "End Location": option.end_loc,
        "In Horizon": "Yes" if problem.rules.in_horizon(option.start.date()) else "No",
    })  # fmt: skip
    new["_s"], new["_e"] = option.start, option.end
    return new


def apply_solution(problem: Problem, chosen) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Return the new roster, the fills, the trips home and the dropped rows."""
    replaced: dict[str, dict] = {}
    dropped_ids: set[str] = set()
    fills, rides, dropped = [], [], []
    for swing, active in chosen:
        by_row = {option.row_index: option for option in active}
        for index, row in enumerate(swing.rows):
            option = by_row.get(index)
            if option is None:
                dropped_ids.add(row["Assignment ID"])
                dropped.append({**row, "Reason": "Stood down to give rest around a reassigned duty"})
            elif option.kind != "keep":
                replaced[row["Assignment ID"]] = rewrite_row(problem, row, option)
                record = {
                    "Date": option.start.strftime(DAY),
                    "Start": option.start.strftime(TIME),
                    "Activity ID": option.activity_id,
                    "Activity Name": problem.activities[option.activity_id]["Activity Name"],
                    "Demand ID": option.demand_id,
                    "User Id": swing.user,
                    "Classification": swing.classification,
                    "Home Depot": swing.home,
                    "Previous Type": row["Assignment Type"],
                    "Previous Activity": row["Activity Name"],
                    "Previous Date": row["Start Date"],
                    "Previous Start": row["Shift Start Time"],
                    "Assignment ID": row["Assignment ID"],
                }
                (fills if option.kind == "fill" else rides).append(record)
    roster = [
        replaced.get(row["Assignment ID"], row)
        for row in problem.roster
        if row["User Id"] not in problem.removed and row["Assignment ID"] not in dropped_ids
    ]
    key = lambda r: (r["Date"], r["Start"], r["Activity ID"], r["User Id"])  # noqa: E731
    return roster, sorted(fills, key=key), sorted(rides, key=key), dropped


def unfilled_seats(problem: Problem, slots: list[Slot], fills: list[dict]) -> list[dict]:
    taken = Counter((f["Activity ID"], f["Date"], f["Start"]) for f in fills)
    rows = []
    for slot in slots:
        key = (slot.activity_id, slot.start.strftime(DAY), slot.start.strftime(TIME))
        if slot.seats > taken[key]:
            rows.append({
                "Date": key[1], "Start": key[2], "Activity ID": slot.activity_id,
                "Activity Name": problem.activities[slot.activity_id]["Activity Name"],
                "Demand ID": slot.demand_id, "Seats Open": slot.seats - taken[key],
            })  # fmt: skip
    return rows


def write_summary(path: Path, problem, slots, result, fills, rides, dropped, unfilled, validation, args) -> None:
    open_by = Counter()
    for slot in slots:
        open_by[problem.activities[slot.activity_id]["Activity Name"]] += slot.seats
    filled_by = Counter(f["Activity Name"] for f in fills)
    source = Counter(f["Previous Type"] for f in fills)
    same_slot = sum(
        f["Previous Type"] == "Excess" and f["Previous Activity"] == f["Activity Name"]
        and (f["Previous Date"], f["Previous Start"]) == (f["Date"], f["Start"])
        for f in fills
    )  # fmt: skip
    lines = [
        "# CP-SAT gap filling result",
        "",
        "Generated by `python CP-SAT/run_gap_filling.py`; do not edit by hand.",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Crew file | `{args.crew.name}` |",
        f"| Crew available / removed | {len(problem.crew)} / {len(problem.removed)} |",
        f"| Seats open in the horizon | {result.seats_open} |",
        f"| Seats filled | **{result.seats_filled}** ({100 * result.seats_filled / max(result.seats_open, 1):.1f}%) |",
        f"| Seats left open | {sum(u['Seats Open'] for u in unfilled)} |",
        f"| Stage 1, coverage | {result.status} (upper bound {result.bound:.0f} seats) |",
        f"| Stage 2, roster changes | {result.disruption_status} (cost {result.disruption}, lower bound {result.disruption_bound:.0f}) |",
        f"| Filled by Excess / Relief | {source['Excess']} / {source['Relief']} |",
        f"| Excess already on the same slot | {same_slot} |",
        f"| People moved | {len({f['User Id'] for f in fills + rides})} |",
        f"| Trips across the line as Excess | {len(rides)} |",
        f"| Standby or Excess rows stood down | {len(dropped)} |",
        f"| Solve time | {result.seconds:.1f} s |",
        f"| Rule check | {validation['headline']} |",
        "",
        "## By activity",
        "",
        "| Activity | Open | Filled |",
        "|---|---|---|",
    ]
    lines += [f"| {name} | {seats} | {filled_by[name]} |" for name, seats in sorted(open_by.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
