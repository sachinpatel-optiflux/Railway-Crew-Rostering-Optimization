"""Check the recovered roster with scripts/check_roster.py, which shares no code with the solver.

check_roster.py was written for the full roster, so one result is expected to differ: the crew
counts in M1-M4 fall short because people were removed on purpose. G1 fails if any seat is unfilled.
A few recovery-only checks are added on top.
"""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
from pathlib import Path

from .data import ROOT, Problem
from .output import write_csv

EXPECTED_FAILS = {"M1-M4"}
COPIED_TABLES = (
    "activities_df.csv", "activity_demand_df.csv", "activity_priority.csv", "compliance_matrix_df.csv",
    "constraints_df.csv", "crew_competencies_df.csv", "crew_currency_df.csv", "crew_restrictions.csv",
    "Crew_Onsite_App.csv", "excluded_activities.csv",
)  # fmt: skip


def load_checker():
    spec = importlib.util.spec_from_file_location("check_roster", ROOT / "scripts" / "check_roster.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def recovery_checks(problem: Problem, roster: list[dict], fills: list[dict]) -> list[tuple[str, str, bool, str]]:
    columns = problem.roster_columns
    original = {r["Assignment ID"]: r for r in problem.roster}
    new_rows = {r["Assignment ID"]: r for r in roster}

    def changed(row: dict) -> bool:
        new = new_rows.get(row["Assignment ID"])
        return new is None or any(row[c] != new[c] for c in columns)

    frozen = [
        r["Assignment ID"]
        for r in problem.roster
        if r["User Id"] not in problem.removed and (r["Is Locked"] == "Yes" or r["In Horizon"] == "No") and changed(r)
    ]
    from_locked = [f["Assignment ID"] for f in fills if original[f["Assignment ID"]]["Is Locked"] != "No"]
    return [
        ("R1", "Removed crew have no rows in the recovered roster",
         not [r for r in roster if r["User Id"] in problem.removed], ""),
        ("R2", "Locked rows and rows outside the horizon are unchanged", not frozen, ", ".join(frozen[:3])),
        ("R3", "Every reassigned row was an unlocked Excess or Relief row", not from_locked, ", ".join(from_locked[:3])),
        ("R4", "No row appears twice", len(new_rows) == len(roster), ""),
    ]  # fmt: skip


def validate(problem: Problem, data_dir: Path, crew_path: Path, roster: list[dict], fills, seats_left: int, out: Path) -> dict:
    checker = load_checker()
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp)
        for table in COPIED_TABLES:
            shutil.copy(data_dir / table, staged / table)
        shutil.copy(crew_path, staged / "crew_master_data_df.csv")
        write_csv(staged / "roster_df.csv", problem.roster_columns, roster)
        results = checker.run(staged).results
    results = results + recovery_checks(problem, roster, fills)

    allowed = set(EXPECTED_FAILS) | ({"G1"} if seats_left else set())
    failures = [r for r in results if not r[2]]
    unexpected = [r for r in failures if r[0] not in allowed]
    lines = [
        "# Rule check of the recovered roster",
        "",
        "`scripts/check_roster.py` on the recovered roster, plus recovery checks R1-R4.",
        f"Expected failures: {', '.join(sorted(allowed))} (see `CP-SAT/README.md`).",
        "",
        f"**{len(results) - len(failures)} of {len(results)} pass; {len(unexpected)} unexpected failure(s).**",
        "",
        "| Rule | Check | Result | Detail |",
        "|---|---|---|---|",
    ]
    for rule, text, ok, detail in results:
        label = "PASS" if ok else ("expected" if rule in allowed else "FAIL")
        lines.append(f"| {rule} | {text} | {label} | {detail.replace('|', '/')} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    headline = f"{len(results) - len(failures)}/{len(results)} pass, {len(unexpected)} unexpected failure(s)"
    return {"headline": headline, "unexpected": unexpected, "failures": failures}
