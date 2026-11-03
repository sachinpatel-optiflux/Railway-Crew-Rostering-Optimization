#!/usr/bin/env python3
"""Check the v2 roster against every rule, reading only the CSV tables (independent of roster_making.py).

Rule IDs refer to Progress/real_data_understanding/02_rules_vs_previous_model.md.

    python scripts/check_roster.py                 # print the results; exit code 1 if any rule fails
    python scripts/check_roster.py --write-report  # also write data/optiflux_v2/roster_checks.md
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "optiflux_v2"

CREW_TARGETS = {  # crew_master_data_changes.txt
    ("Haskett", "Residential"): 300,
    ("Haskett", "FIFO"): 100,
    ("Yarmouth", "FIFO"): 300,
    ("Nelaway", "Residential"): 200,
    ("Nelaway", "FIFO"): 100,
}
WORK = ("Demand", "Excess", "Relief")
TRAVEL = ("Travel In", "Travel Out")
SWING_BREAK = timedelta(hours=48)  # longer gap between two shifts = a new swing
MAX_EXAMPLES = 3


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def dt(d: str, t: str) -> datetime:
    return datetime.fromisoformat(f"{d}T{t}")


class Checks:
    def __init__(self) -> None:
        self.results: list[tuple[str, str, bool, str]] = []

    def add(self, rule: str, text: str, failures: list[str], extra: str = "") -> None:
        detail = "; ".join(failures[:MAX_EXAMPLES]) + (
            f" (+{len(failures) - MAX_EXAMPLES} more)" if len(failures) > MAX_EXAMPLES else ""
        )
        self.results.append((rule, text, not failures, detail or extra))

    @property
    def ok(self) -> bool:
        return all(r[2] for r in self.results)


def run(data_dir: Path) -> Checks:
    acts = {a["Activity ID"]: a for a in read_csv(data_dir / "activities_df.csv")}
    demand = [d for d in read_csv(data_dir / "activity_demand_df.csv") if d["Is Active"] == "Yes"]
    cons = {r["Constraint"]: (r["Value"], r["Status"]) for r in read_csv(data_dir / "constraints_df.csv")}
    crew = {c["User Id"]: c for c in read_csv(data_dir / "crew_master_data_df.csv")}
    roster = read_csv(data_dir / "roster_df.csv")
    comps = read_csv(data_dir / "crew_competencies_df.csv")
    curr = read_csv(data_dir / "crew_currency_df.csv")
    compliance = read_csv(data_dir / "compliance_matrix_df.csv")
    restrictions = read_csv(data_dir / "crew_restrictions.csv")

    start = date.fromisoformat(cons["Planning Horizon Start"][0])
    days = int(cons["Planning Horizon Days"][0])
    horizon = [start + timedelta(days=k) for k in range(days)]
    shift_h = int(cons["Shift Length Hours"][0])
    rest_h = float(cons["Ordinary Rest Hours"][0])
    trans_h = float(cons["Transition Rest Hours"][0])
    lo, hi = (int(t[:2]) * 60 + int(t[3:]) for t in cons["Day Shift Window"][0].split("-"))
    on_off = {c: tuple(int(x) for x in cons[f"{c} Work/Off Days"][0].split("/")) for c in ("FIFO", "Residential")}

    def is_day(t: datetime) -> bool:
        return lo <= t.hour * 60 + t.minute < hi

    for r in roster:
        r["_s"] = dt(r["Start Date"], r["Shift Start Time"])
        r["_e"] = dt(r["End Date"], r["Shift End Time"])
    work = [r for r in roster if r["Assignment Type"] in WORK]
    ck = Checks()

    # ---- data shape --------------------------------------------------------------------------------
    ids = [r["Assignment ID"] for r in roster]
    ck.add("—", "Assignment IDs are unique", [i for i, n in Counter(ids).items() if n > 1])
    ck.add("—", "Every row's activity exists; Assignment Type is known",
           [r["Assignment ID"] for r in roster if r["Activity ID"] not in acts or r["Assignment Type"] not in WORK + TRAVEL])  # fmt: skip
    ck.add("—", "`In Horizon` matches the start date",
           [r["Assignment ID"] for r in roster if (r["In Horizon"] == "Yes") != (start <= r["_s"].date() < start + timedelta(days=days))])  # fmt: skip
    ck.add("D1", "Demand `Shift` holds a start time only (HH:MM)",
           [d["Demand ID"] for d in demand if len(d["Shift"]) != 5 or d["Shift"][2] != ":"])  # fmt: skip
    ck.add("D3/D4", "NE Task and BY Shed are renamed (NE Crew, BY Ship)",
           [a["Activity Name"] for a in acts.values() if a["Activity Name"] in ("NE Task", "BY Shed")])  # fmt: skip

    # ---- coverage (G1), Excess (G5), Relief (G6) ----------------------------------------------------------
    by_slot = Counter(
        (r["Activity ID"], r["Start Date"], r["Shift Start Time"]) for r in work if r["Assignment Type"] == "Demand"
    )
    fails = []
    for d in demand:
        for day in horizon:
            got = by_slot[(d["Activity ID"], day.isoformat(), d["Shift"])]
            if got != int(d["Demand"]):
                fails.append(f"{d['Demand ID']} {d['Activity Name']} {day} {d['Shift']}: {got}/{d['Demand']}")
    total = sum(int(d["Demand"]) for d in demand)
    ck.add(
        "G1",
        f"Every demand slot on every horizon day has exactly its demand ({total} crew-shifts/day x {days} days)",
        fails,
    )
    dem_of = {(d["Activity ID"], d["Shift"]): d for d in demand}
    ck.add("G1", "Demand rows carry the Demand ID of their activity and start time",
           [r["Assignment ID"] for r in work if r["Assignment Type"] != "Relief"
            and dem_of.get((r["Activity ID"], r["Shift Start Time"]), {}).get("Demand ID") != r["Demand ID"]])  # fmt: skip
    over = [k for k, n in by_slot.items() if (k[0], k[2]) not in dem_of or n > int(dem_of[(k[0], k[2])]["Demand"])]
    ck.add("G1", "No slot (in or outside the horizon) has more Demand rows than its demand", [str(k) for k in over])
    ck.add("G5", "Excess rows are on work activities whose slot is already fully covered (surplus)",
           [r["Assignment ID"] for r in work if r["Assignment Type"] == "Excess" and r["In Horizon"] == "Yes"
            and by_slot[(r["Activity ID"], r["Start Date"], r["Shift Start Time"])] < int(dem_of[(r["Activity ID"], r["Shift Start Time"])]["Demand"])]
           + [r["Assignment ID"] for r in work if r["Assignment Type"] == "Excess" and acts[r["Activity ID"]]["Activity Type"] in ("Relief", "Travel")])  # fmt: skip
    ck.add("G6", "Relief rows: Activity Name = Activity Head = Relief, no Demand ID",
           [r["Assignment ID"] for r in work if r["Assignment Type"] == "Relief"
            and not (r["Activity Name"] == r["Activity Head"] == "Relief" and not r["Demand ID"])])  # fmt: skip
    ck.add("G6", "Only Relief rows use the Relief activity",
           [r["Assignment ID"] for r in roster if r["Activity Name"] == "Relief" and r["Assignment Type"] != "Relief"])  # fmt: skip
    ck.add("G9", "Initial roster has no leave (crew_restrictions empty, everyone Fit)",
           [r.get("Restriction ID", "?") for r in restrictions] + [u for u, c in crew.items() if c["Medical"] != "Fit"])  # fmt: skip
    ck.add("G2", "No 'no activity' rows yet (deferred)", [r["Assignment ID"] for r in roster if not r["Activity ID"]])
    ck.add("—", "Is Locked: Yes for Demand and Travel, No for Excess and Relief (free for the recovery step)",
           [r["Assignment ID"] for r in roster if (r["Is Locked"] == "Yes") != (r["Assignment Type"] in ("Demand",) + TRAVEL)])  # fmt: skip

    # ---- shift length (D2) ---------------------------------------------------------------------------------
    ck.add("D2", f"Every work row lasts {shift_h} h",
           [r["Assignment ID"] for r in work if r["_e"] - r["_s"] != timedelta(hours=shift_h)])  # fmt: skip

    # ---- crew list (M1-M5) -----------------------------------------------------------------------------------
    pools = Counter((c["Depot"], c["Classification"]) for c in crew.values())
    ck.add("M1-M4", "Crew per depot and classification meets the targets (more allowed)",
           [f"{k}: {pools[k]}/{v}" for k, v in CREW_TARGETS.items() if pools[k] < v]
           + [f"unexpected pool {k}" for k in pools if k not in CREW_TARGETS], extra=", ".join(f"{d}/{c} {pools[(d, c)]}" for d, c in CREW_TARGETS))  # fmt: skip
    ck.add(
        "M5", "Classification is Residential or FIFO", [u for u, c in crew.items() if c["Classification"] not in on_off]
    )
    users = {r["User Id"] for r in roster}
    ck.add("—", "Every roster user is in the crew list, and everyone in the crew list is rostered",
           sorted(users - set(crew)) + sorted(set(crew) - users))  # fmt: skip
    ck.add("C1", "No CM Id: per-person tables are keyed by User Id",
           [f for f in ("crew_master_data_df", "crew_competencies_df", "crew_currency_df", "crew_restrictions", "Crew_Onsite_App")
            if "CM Id" in (read_csv(data_dir / f"{f}.csv")[0] if read_csv(data_dir / f"{f}.csv") else open(data_dir / f"{f}.csv").readline())])  # fmt: skip

    # ---- per person: rest, swings, R1, location, travel -----------------------------------------------------
    per_user: dict[str, list[dict]] = defaultdict(list)
    travel_of: dict[str, list[dict]] = defaultdict(list)
    for r in sorted(roster, key=lambda r: r["_s"]):
        (per_user if r["Assignment Type"] in WORK else travel_of)[r["User Id"]].append(r)
    f_overlap, f_rest, f_trans, f_daily, f_swing_len, f_off, f_r1, f_loc, f_base, f_travel, f_res_travel = (
        [] for _ in range(11)
    )
    for uid, rows in per_user.items():
        c = crew.get(uid)
        if c is None:
            continue
        on, off = on_off[c["Classification"]]
        days_used = Counter(r["Start Date"] for r in rows)
        f_daily += [f"{uid} {d}" for d, n in days_used.items() if n > 1]
        swings: list[list[dict]] = [[rows[0]]]
        for prev, cur in zip(rows, rows[1:]):
            gap = cur["_s"] - prev["_e"]
            if gap < timedelta(0):
                f_overlap.append(f"{uid} {prev['Assignment ID']}/{cur['Assignment ID']}")
            elif gap < timedelta(hours=rest_h):
                f_rest.append(f"{uid} {cur['Assignment ID']} ({gap})")
            elif is_day(prev["_s"]) != is_day(cur["_s"]) and gap < timedelta(hours=trans_h):
                f_trans.append(f"{uid} {cur['Assignment ID']} ({gap})")
            if gap > SWING_BREAK:
                if gap < timedelta(days=off):
                    f_off.append(f"{uid} before {cur['Start Date']} ({gap})")
                swings.append([cur])
            else:
                swings[-1].append(cur)
                if cur["Start Location"] != prev["End Location"]:
                    f_loc.append(
                        f"{uid} {cur['Assignment ID']}: starts {cur['Start Location']}, was at {prev['End Location']}"
                    )
        for sw in swings:
            if len(sw) > on:
                f_swing_len.append(f"{uid} swing from {sw[0]['Start Date']}: {len(sw)} shifts")
            if c["Classification"] == "Residential" and not is_day(sw[0]["_s"]):
                f_r1.append(f"{uid} swing from {sw[0]['Start Date']} starts {sw[0]['Shift Start Time']}")
            if sw[0]["Start Location"] != c["Depot"] or sw[-1]["End Location"] != c["Depot"]:
                f_base.append(f"{uid} swing from {sw[0]['Start Date']}")
            for r in sw:
                a = acts[r["Activity ID"]]
                want = (a["Start Depot"], a["End Depot"]) if a["Start Depot"] else (c["Depot"], c["Depot"])
                if (r["Start Location"], r["End Location"]) != want:
                    f_loc.append(
                        f"{uid} {r['Assignment ID']}: {r['Start Location']}>{r['End Location']} on {a['Activity Name']}"
                    )
        trav = travel_of.get(uid, [])
        if c["Classification"] == "FIFO":
            ins = [t for t in trav if t["Assignment Type"] == "Travel In"]
            outs = [t for t in trav if t["Assignment Type"] == "Travel Out"]
            if len(ins) != len(swings) or len(outs) != len(swings):
                f_travel.append(f"{uid}: {len(swings)} swings, {len(ins)} in, {len(outs)} out")
                continue
            for sw, ti, to in zip(swings, ins, outs):
                if not (ti["_e"] <= sw[0]["_s"] and ti["End Location"] == sw[0]["Start Location"]):
                    f_travel.append(
                        f"{uid} Travel In {ti['Assignment ID']} not before first shift {sw[0]['Assignment ID']}"
                    )
                if not (to["_s"] >= sw[-1]["_e"] and to["Start Location"] == sw[-1]["End Location"]):
                    f_travel.append(
                        f"{uid} Travel Out {to['Assignment ID']} not after last shift {sw[-1]['Assignment ID']}"
                    )
                prev_end = [s for s in swings if s[-1]["_e"] < sw[0]["_s"]]
                if prev_end and ti["_s"] < prev_end[-1][-1]["_e"]:
                    f_travel.append(f"{uid} Travel In {ti['Assignment ID']} before the previous swing ended")
        elif trav:
            f_res_travel.append(uid)
    ck.add("F*", "No overlapping shifts", f_overlap)
    ck.add("F*", f"At least {rest_h:g} h rest between shifts", f_rest)
    ck.add("F*", f"At least {trans_h:g} h rest when switching day <-> night", f_trans)
    ck.add("F*", "At most one shift starting per person per day", f_daily)
    ck.add("F*", "Swing length: no more shifts in a swing than its work days (FIFO 14, Residential 6)", f_swing_len)
    ck.add("F*", "Off time between swings at least the off days (FIFO 14, Residential 6)", f_off)
    ck.add("R1", "Residential: the first shift of every swing is a day shift", f_r1)
    ck.add("F*", "Location continuity: each shift starts where the previous one ended, at the activity's depots", f_loc)
    ck.add("F*", "Every swing starts and ends at the person's home depot", f_base)
    ck.add(
        "F1-F3",
        "FIFO: one Travel In before the first shift and one Travel Out after the last shift of every swing",
        f_travel,
    )
    ck.add("F1", "Residential crew have no travel rows", f_res_travel)

    # ---- eligibility -------------------------------------------------------------------------------------------
    codes_of: dict[str, set[str]] = defaultdict(set)
    for r in compliance:
        codes_of[r["Activity ID"]].add(r["Competency LMS Code"])
    held: dict[str, dict[str, date]] = defaultdict(dict)
    for r in comps:
        if r["status"] == "Valid":
            held[r["User Id"]][r["Competency LMS Code"]] = date.fromisoformat(r["Expiry Date"])
    last_done: dict[tuple[str, str], date] = {
        (r["User Id"], r["Activity Head"]): date.fromisoformat(r["Last Performed Date"]) for r in curr
    }
    f_elig, f_role, f_comp, f_cur = [], [], [], []
    for r in sorted(work, key=lambda r: r["_s"]):
        if r["Assignment Type"] == "Relief":
            continue
        uid, a = r["User Id"], acts[r["Activity ID"]]
        c, day = crew[uid], r["_s"].date()
        if r["Activity ID"] not in c["Eligibility"].split(";"):
            f_elig.append(f"{uid} {r['Activity ID']}")
        if c["Role"] not in [x.strip() for x in a["Roles/Job"].split(";")]:
            f_role.append(f"{uid} {c['Role']} on {a['Activity Name']}")
        missing = [code for code in codes_of[r["Activity ID"]] if held[uid].get(code, date.min) < day]
        if missing:
            f_comp.append(f"{uid} {r['Activity ID']} {day}: {','.join(sorted(missing))}")
        if a["Currency Threshold"]:
            key = (uid, a["Activity Head"])
            last = last_done.get(key)
            if last is None or (day - last).days > int(a["Currency Threshold"]):
                f_cur.append(f"{uid} {a['Activity Head']} {day} (last {last})")
            last_done[key] = day
    ck.add("—", "Work rows only on activities in the person's Eligibility", f_elig)
    ck.add("—", "The person's Role is allowed by the activity's Roles/Job", f_role)
    ck.add("—", "The person holds every competency the activity needs, valid on the duty date", f_comp)
    ck.add("—", "Currency: the activity head was performed within its threshold before each duty", f_cur)
    return ck


def to_markdown(ck: Checks) -> str:
    lines = [
        "# Roster rule checks",
        "",
        "Generated by `python scripts/check_roster.py --write-report`; do not edit by hand.",
        "Rule IDs: `Progress/real_data_understanding/02_rules_vs_previous_model.md` (F* = rules carried over from the previous model).",
        "",
        f"**Result: {'all checks pass' if ck.ok else 'FAILURES'}** ({sum(r[2] for r in ck.results)}/{len(ck.results)})",
        "",
        "| Rule | Check | Result | Detail |",
        "|---|---|---|---|",
    ]
    for rule, text, ok, detail in ck.results:
        lines.append(f"| {rule} | {text} | {'PASS' if ok else 'FAIL'} | {detail.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data-dir", type=Path, default=DEFAULT_DIR)
    p.add_argument("--write-report", action="store_true", help="write roster_checks.md into the data folder")
    args = p.parse_args(argv)
    ck = run(args.data_dir)
    for rule, text, ok, detail in ck.results:
        print(f"{'PASS' if ok else 'FAIL'}  {rule:6s} {text}" + (f"  [{detail}]" if detail and not ok else ""))
    if args.write_report:
        (args.data_dir / "roster_checks.md").write_text(to_markdown(ck), encoding="utf-8")
    print("all checks pass" if ck.ok else "SOME CHECKS FAIL")
    return 0 if ck.ok else 1


if __name__ == "__main__":
    sys.exit(main())
