#!/usr/bin/env python3
"""Build the OptiFlux v2 data tables from the uploaded files and the new rules.

Inputs (kept unchanged, for traceability):
    data/optiflux_v2/source/*.csv          the four tables as supplied
    data/optiflux_v2/source/rules/*.txt    the rule notes as supplied

Outputs (overwritten):
    data/optiflux_v2/activities_df.csv
    data/optiflux_v2/activity_demand_df.csv
    data/optiflux_v2/crew_master_data_df.csv
    data/optiflux_v2/roster_df.csv          header only: the roster is built in a later step

Every change is explained in Progress/real_data_understanding/03_data_changes.md.
The script uses only the standard library and is deterministic.

    python scripts/build_optiflux_v2_data.py
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "optiflux_v2"

SHIFT_HOURS = 12  # every shift lasts 12 h; the demand table stores only the start time

# ---------------------------------------------------------------------------
# Rules: activities_df
# ---------------------------------------------------------------------------

# Renames from demand_changes.txt: "NE task = replace by NE Crew", "replace By Shed with By Ship".
RENAMES = {
    "A12": {"Activity Name": "BY Ship", "Activity Head": "BY Ship"},
    "A16": {"Activity Name": "NE Crew", "Activity Head": "NE Crew"},
}

# The upload has two rows with Activity ID A08 (Work Train, Work Train CO).
# Activity ID is a key, so Work Train CO gets the next free ID.
DUPLICATE_ID_FIX = {("A08", "Work Train CO"): "A17"}

# general_rules_assignment.txt: "relief: extra relief that we have, activity name and head would be
# both relief, not assigned to any activity, just kept as extras".
RELIEF_ACTIVITY = {
    "Activity ID": "A90",
    "Activity Name": "Relief",
    "Activity Group": "Reserve",
    "Activity Head": "Relief",
    "Activity Type": "Relief",
    "TEA Required": "",
    "Can Be Moved": "",
    "Start Depot": "",
    "End Depot": "",
    "Mentor Required": "No",
    "Roles/Job": "",
    "Currency Threshold": "",
}

# ---------------------------------------------------------------------------
# Rules: activity_demand_df  (demand_changes.txt)
# ---------------------------------------------------------------------------


def every(step_h: int, first_h: int) -> list[int]:
    """Start hours every ``step_h`` hours over a day, beginning at ``first_h``."""
    return sorted((first_h + k * step_h) % 24 for k in range(24 // step_h))


HOURLY = every(1, 0)

# Activity ID -> list of (start hour, people). One row per start time.
DEMAND_RULES: dict[str, list[tuple[int, int]]] = {
    "A01": [(h, 1) for h in HOURLY],  # Haskett Mainline: 1 person per hour
    "A03": [(h, 1) for h in HOURLY],  # Yarmouth Mainline: 1 person per hour
    "A05": [(h, 1) for h in every(3, 0)],  # CAM LOT: 1 per 3 h from 00:00
    "A06": [(h, 1) for h in HOURLY],  # Madison Crew: 1 person per hour
    "A07": [(h, 1) for h in every(3, 1)],  # Madison Yard: 1 per 3 h from 01:00
    "A08": [(22, 2)],  # Work Train: 2 people at 22:00
    "A09": [(10, 1)],  # Fuel Train: 1 person at 10:00
    "A10": [(10, 1)],  # Fuel Return: 1 person at 10:00
    "A11": [(h, 1) for h in every(3, 4)],  # Bethway Join/FI Crew: 1 per 3 h from 04:00
    "A12": [(h, 1) for h in (4, 9, 16, 21)],  # BY Ship: "similar to NE Ship"
    "A13": [(h, 1) for h in HOURLY],  # Nelaway Driver: 1 person per hour
    "A14": [(h, 1) for h in every(3, 1)],  # Nelaway Shuttle Driver: 1 per 3 h from 01:00
    "A15": [(h, 1) for h in (4, 9, 16, 21)],  # NE Ship: 04:00, 09:00, 16:00, 21:00, 1 each
    # NE Crew: 4 people at 04, 07, 09, 16, 19, 21; 2 people at 00 and 12.
    "A16": sorted([(h, 4) for h in (4, 7, 9, 16, 19, 21)] + [(h, 2) for h in (0, 12)]),
    # Not in the new rules: kept from the uploaded demand table, start time only (open question Q1).
    "A02": [(17, 1)],  # Haskett Mainline CO
    "A04": [(5, 1), (17, 1)],  # Yarmouth Mainline CO
}

# ---------------------------------------------------------------------------
# Rules: crew_master_data_df  (crew_master_data_changes.txt)
# ---------------------------------------------------------------------------

# (Depot, Classification, count), in User Id order.
CREW_PLAN = [
    ("Haskett", "Residential", 300),
    ("Haskett", "FIFO", 100),
    ("Yarmouth", "FIFO", 300),
    ("Nelaway", "Residential", 200),
    ("Nelaway", "FIFO", 100),
]
FIRST_USER_NUMBER = 100001  # same User Id format as the upload (U100001 ...)

# ---------------------------------------------------------------------------


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_activities(source: Path) -> tuple[list[str], list[dict[str, str]]]:
    header, rows = read_csv(source / "activities_df.csv")
    out = []
    for r in rows:
        r = dict(r)
        new_id = DUPLICATE_ID_FIX.get((r["Activity ID"], r["Activity Name"]))
        if new_id:
            r["Activity ID"] = new_id
        r.update(RENAMES.get(r["Activity ID"], {}))
        out.append(r)
    out.append(dict(RELIEF_ACTIVITY))
    ids = [r["Activity ID"] for r in out]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    if dupes:
        raise SystemExit(f"duplicate Activity ID after fixes: {dupes}")
    return header, out


def build_demand(activities: list[dict[str, str]]) -> tuple[list[str], list[dict[str, str]]]:
    by_id = {a["Activity ID"]: a for a in activities}
    missing = sorted(set(DEMAND_RULES) - set(by_id))
    if missing:
        raise SystemExit(f"demand rules refer to unknown activities: {missing}")
    header = ["Demand ID", "Shift", "Demand", "Is Active", "Activity ID", "Activity Name", "Activity Head"]
    rows = []
    for aid in sorted(DEMAND_RULES):
        for hour, people in sorted(DEMAND_RULES[aid]):
            a = by_id[aid]
            rows.append(
                {
                    "Demand ID": f"DM{len(rows) + 1:03d}",
                    "Shift": f"{hour:02d}:00",
                    "Demand": str(people),
                    "Is Active": "Yes",
                    "Activity ID": aid,
                    "Activity Name": a["Activity Name"],
                    "Activity Head": a["Activity Head"],
                }
            )
    return header, rows


def build_crew(source: Path) -> tuple[list[str], list[dict[str, str]]]:
    header, _ = read_csv(source / "crew_master_data_df.csv")
    rows = []
    n = FIRST_USER_NUMBER
    for depot, classification, count in CREW_PLAN:
        for _ in range(count):
            row = {col: "" for col in header}
            row.update({"User Id": f"U{n}", "Classification": classification, "Depot": depot})
            rows.append(row)
            n += 1
    return header, rows


def summarise(activities, demand, crew) -> str:
    lines = []
    depot_of = {a["Activity ID"]: a["Start Depot"] for a in activities}
    per_act: dict[str, int] = defaultdict(int)
    per_depot: dict[str, int] = defaultdict(int)
    for d in demand:
        per_act[f"{d['Activity ID']} {d['Activity Name']}"] += int(d["Demand"])
        per_depot[depot_of[d["Activity ID"]]] += int(d["Demand"])
    lines.append(f"activities: {len(activities)} rows")
    lines.append(f"demand: {len(demand)} rows, {sum(per_act.values())} crew-shifts per day")
    for k, v in per_act.items():
        lines.append(f"  {k:32s} {v:3d}")
    lines.append("demand per day by start depot: " + ", ".join(f"{k}={v}" for k, v in sorted(per_depot.items())))
    crew_count = Counter((c["Depot"], c["Classification"]) for c in crew)
    lines.append(f"crew: {len(crew)} rows " + ", ".join(f"{d}/{c}={n}" for (d, c), n in crew_count.items()))
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data-dir", type=Path, default=DEFAULT_DIR, help="folder holding source/ (default: %(default)s)")
    args = p.parse_args()
    source = args.data_dir / "source"

    act_header, activities = build_activities(source)
    dem_header, demand = build_demand(activities)
    crew_header, crew = build_crew(source)
    roster_header, _ = read_csv(source / "roster_df.csv")

    write_csv(args.data_dir / "activities_df.csv", act_header, activities)
    write_csv(args.data_dir / "activity_demand_df.csv", dem_header, demand)
    write_csv(args.data_dir / "crew_master_data_df.csv", crew_header, crew)
    write_csv(args.data_dir / "roster_df.csv", roster_header, [])
    print(summarise(activities, demand, crew))


if __name__ == "__main__":
    main()
