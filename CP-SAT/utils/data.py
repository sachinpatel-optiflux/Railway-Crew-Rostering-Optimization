"""Load the optiflux_v2 tables and the reduced crew list."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .rules import Rules

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = ROOT / "data" / "optiflux_v2"
DEFAULT_CREW = ROOT / "gap_generation" / "crew_with_gaps.csv"

WORK_TYPES = ("Demand", "Excess", "Relief")
TRAVEL_TYPES = ("Travel In", "Travel Out")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def parse_dt(day: str, time: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{time}")


@dataclass
class Problem:
    """Everything the run needs. `roster` is the full initial roster, including removed crew."""

    rules: Rules
    activities: dict[str, dict[str, str]]
    demand: dict[tuple[str, str], dict[str, str]]  # (Activity ID, start time) -> demand row
    crew: dict[str, dict[str, str]]  # crew who are still available
    removed: set[str]
    roster: list[dict]
    roster_columns: list[str]
    required_codes: dict[str, set[str]]  # Activity ID -> competency codes
    held_codes: dict[str, dict[str, date]]  # User Id -> code -> expiry date
    last_done: dict[tuple[str, str], date]  # (User Id, Activity Head) -> last performed
    priority: dict[str, int]  # Activity Head -> priority, 1 = highest


def load_problem(data_dir: Path, crew_path: Path) -> Problem:
    for table in ("crew_restrictions.csv", "Crew_Onsite_App.csv", "excluded_activities.csv"):
        if read_csv(data_dir / table):
            raise SystemExit(f"error: {table} has rows, but this run does not model them yet")

    all_crew = {c["User Id"]: c for c in read_csv(data_dir / "crew_master_data_df.csv")}
    crew = {c["User Id"]: c for c in read_csv(crew_path)}
    unknown = sorted(set(crew) - set(all_crew))
    if unknown:
        raise SystemExit(f"error: {crew_path} has people missing from the crew master, e.g. {unknown[:3]}")

    roster = read_csv(data_dir / "roster_df.csv")
    columns = list(roster[0])
    for row in roster:
        row["_s"] = parse_dt(row["Start Date"], row["Shift Start Time"])
        row["_e"] = parse_dt(row["End Date"], row["Shift End Time"])

    required: dict[str, set[str]] = defaultdict(set)
    for row in read_csv(data_dir / "compliance_matrix_df.csv"):
        required[row["Activity ID"]].add(row["Competency LMS Code"])
    held: dict[str, dict[str, date]] = defaultdict(dict)
    for row in read_csv(data_dir / "crew_competencies_df.csv"):
        if row["status"] == "Valid":
            held[row["User Id"]][row["Competency LMS Code"]] = date.fromisoformat(row["Expiry Date"])
    last_done = {
        (r["User Id"], r["Activity Head"]): date.fromisoformat(r["Last Performed Date"])
        for r in read_csv(data_dir / "crew_currency_df.csv")
    }
    return Problem(
        rules=Rules.from_table(read_csv(data_dir / "constraints_df.csv")),
        activities={a["Activity ID"]: a for a in read_csv(data_dir / "activities_df.csv")},
        demand={
            (d["Activity ID"], d["Shift"]): d
            for d in read_csv(data_dir / "activity_demand_df.csv")
            if d["Is Active"] == "Yes"
        },
        crew=crew,
        removed=set(all_crew) - set(crew),
        roster=roster,
        roster_columns=columns,
        required_codes=required,
        held_codes=held,
        last_done=last_done,
        priority={r["Activity Head"]: int(r["Priority"]) for r in read_csv(data_dir / "activity_priority.csv")},
    )
