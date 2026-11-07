#!/usr/bin/env python3
"""Make a percentage of the crew unavailable, writing a reduced copy of the crew master data.

The original file is only read. See gap_generation/README.md for the full explanation.

    python gap_generation/make_gaps.py --percent 5
    python gap_generation/make_gaps.py --percent 10 --seed 7
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_INPUT = HERE.parent / "data" / "optiflux_v2" / "crew_master_data_df.csv"
DEFAULT_OUTPUT = HERE / "crew_with_gaps.csv"
REMOVED_NAME = "removed_crew.csv"
ROSTER_NAME = "roster_df.csv"  # looked for next to the input file
DEFAULT_SEED = 2026  # same as "Random Seed" in data/optiflux_v2/constraints_df.csv
ID_COLUMN = "User Id"


def parse_percent(text: str) -> float:
    """Accept 5, 7.5 or 5%. Must leave at least some crew and remove at least some."""
    try:
        value = float(text.strip().rstrip("%"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from None
    if not 0 < value < 100:
        raise argparse.ArgumentTypeError(f"{text!r} must be above 0 and below 100")
    return value


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def pick_removed(user_ids: list[str], percent: float, seed: int) -> set[str]:
    """Pick round(N * percent / 100) people at random, but always at least 1.

    Sorting first makes the result independent of the file's row order. Taking the front of
    one shuffled list means that, for the same seed, the 5% group is inside the 10% group.
    """
    count = max(1, round(len(user_ids) * percent / 100))
    shuffled = sorted(user_ids)
    random.Random(seed).shuffle(shuffled)
    return set(shuffled[:count])


def open_shifts(roster_path: Path, removed: set[str]) -> Counter[str]:
    """Count the removed people's shifts inside the horizon, by Assignment Type."""
    _, rows = read_csv(roster_path)
    return Counter(r["Assignment Type"] for r in rows if r["User Id"] in removed and r["In Horizon"] == "Yes")


def print_summary(crew: list[dict[str, str]], removed_rows: list[dict[str, str]], percent: float, seed: int) -> None:
    print(f"Crew: {len(crew)} -> {len(crew) - len(removed_rows)} ({len(removed_rows)} removed, {percent:g}%, seed {seed})")
    for column in ("Depot", "Classification", "Role"):
        before = Counter(r[column] for r in crew)
        after = Counter(r[column] for r in removed_rows)
        print(f"  {column}: " + ", ".join(f"{k} -{after[k]}/{before[k]}" for k in sorted(before)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove a percentage of crew from the crew master data.")
    parser.add_argument("--percent", required=True, type=parse_percent, help="share of crew to remove, e.g. 5 or 10")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"random seed (default {DEFAULT_SEED})")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="crew master CSV to read")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="reduced crew CSV to write")
    args = parser.parse_args(argv)

    removed_path = args.output.parent / REMOVED_NAME
    if args.input.resolve() in (args.output.resolve(), removed_path.resolve()):
        print("error: an output path is the same as --input; the original file must stay unchanged", file=sys.stderr)
        return 2

    header, crew = read_csv(args.input)
    if ID_COLUMN not in header:
        print(f"error: {args.input} has no {ID_COLUMN!r} column", file=sys.stderr)
        return 2
    user_ids = [r[ID_COLUMN] for r in crew]
    if len(set(user_ids)) != len(user_ids):
        print(f"error: {args.input} has duplicate {ID_COLUMN} values", file=sys.stderr)
        return 2

    removed = pick_removed(user_ids, args.percent, args.seed)
    kept_rows = [r for r in crew if r[ID_COLUMN] not in removed]
    removed_rows = [r for r in crew if r[ID_COLUMN] in removed]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.output, header, kept_rows)
    write_csv(removed_path, header, removed_rows)

    print_summary(crew, removed_rows, args.percent, args.seed)
    roster_path = args.input.parent / ROSTER_NAME
    if roster_path.exists():
        shifts = open_shifts(roster_path, removed)
        detail = ", ".join(f"{k} {v}" for k, v in sorted(shifts.items()))
        print(f"Their shifts in the horizon: {sum(shifts.values())} ({detail})")
    print(f"Wrote {args.output}")
    print(f"Wrote {removed_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
