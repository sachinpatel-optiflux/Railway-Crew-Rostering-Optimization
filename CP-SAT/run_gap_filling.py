#!/usr/bin/env python3
"""Reassign Excess and Relief crew to the gaps left by removed crew. See CP-SAT/README.md.

    python CP-SAT/run_gap_filling.py
    python CP-SAT/run_gap_filling.py --crew gap_generation/gaps_10/crew_with_gaps.csv --time-limit 300
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from solver import Costs, solve
from utils.data import DEFAULT_CREW, DEFAULT_DATA_DIR, load_problem
from utils.gaps import find_gaps
from utils.options import add_options, build_swings
from utils.output import apply_solution, unfilled_seats, write_csv, write_summary
from utils.validate import validate

HERE = Path(__file__).resolve().parent
FILL_COLUMNS = [
    "Date", "Start", "Activity ID", "Activity Name", "Demand ID", "User Id", "Classification", "Home Depot",
    "Previous Type", "Previous Activity", "Previous Date", "Previous Start", "Assignment ID",
]  # fmt: skip
UNFILLED_COLUMNS = ["Date", "Start", "Activity ID", "Activity Name", "Demand ID", "Seats Open"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill roster gaps with Excess and Relief crew using CP-SAT.")
    parser.add_argument("--crew", type=Path, default=DEFAULT_CREW, help="reduced crew CSV")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="folder with the optiflux_v2 tables")
    parser.add_argument("--output-dir", type=Path, help="default: CP-SAT/outputs/<crew file's name>")
    parser.add_argument("--time-limit", type=float, default=300, help="seconds per stage (default 300)")
    parser.add_argument("--workers", type=int, default=8, help="CP-SAT threads (default 8)")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--allow-stand-down", action="store_true", help="let the solver remove standby or Excess rows")
    parser.add_argument("--no-return-rides", action="store_true", help="no trips home as Excess")
    parser.add_argument("--log", action="store_true", help="print the CP-SAT search log")
    args = parser.parse_args(argv)
    out = args.output_dir or HERE / "outputs" / args.crew.stem
    out.mkdir(parents=True, exist_ok=True)

    problem = load_problem(args.data_dir, args.crew)
    slots = find_gaps(problem)
    print(f"Crew {len(problem.crew)}, removed {len(problem.removed)}, open seats {sum(s.seats for s in slots)}")

    costs = Costs()
    allow_drop = args.allow_stand_down
    swings = build_swings(problem)
    add_options(problem, swings, slots, costs, allow_drop, not args.no_return_rides)
    result = solve(problem, swings, slots, costs, allow_drop, args.time_limit, args.workers, args.seed, args.log)
    if not result.chosen and result.seats_open:
        print(f"error: no solution ({result.status})", file=sys.stderr)
        return 1

    roster, fills, rides, dropped = apply_solution(problem, result.chosen)
    unfilled = unfilled_seats(problem, slots, fills)
    seats_left = sum(u["Seats Open"] for u in unfilled)

    write_csv(out / "recovered_roster_df.csv", problem.roster_columns, roster)
    write_csv(out / "reassignments.csv", FILL_COLUMNS, fills)
    write_csv(out / "return_trips.csv", FILL_COLUMNS, rides)
    write_csv(out / "stood_down_rows.csv", problem.roster_columns + ["Reason"], dropped)
    write_csv(out / "unfilled_gaps.csv", UNFILLED_COLUMNS, unfilled)
    validation = validate(problem, args.data_dir, args.crew, roster, fills, seats_left, out / "validation.md")
    write_summary(out / "summary.md", problem, slots, result, fills, rides, dropped, unfilled, validation, args)

    print(f"Filled {len(fills)} of {result.seats_open} seats ({result.status}); {seats_left} left open")
    print(f"Rule check: {validation['headline']}")
    for rule, text, _, detail in validation["unexpected"]:
        print(f"  FAIL {rule} {text} [{detail}]")
    print(f"Wrote {out}")
    return 1 if validation["unexpected"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
