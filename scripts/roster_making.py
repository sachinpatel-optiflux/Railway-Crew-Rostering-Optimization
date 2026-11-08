#!/usr/bin/env python3
"""Make the initial OptiFlux roster, and the crew list it needs, from the v2 data tables.

Step 2 of 2 (step 1: ``scripts/build_optiflux_v2_data.py``).

Reads (data/optiflux_v2/):
    activities_df, activity_demand_df, activity_priority, compliance_matrix_df, constraints_df

Writes (data/optiflux_v2/):
    roster_df.csv             who works which job, when and where (Demand / Excess / Relief / Travel rows)
    crew_master_data_df.csv   one row per person the roster uses (700; more only if needed)
    crew_competencies_df.csv  competencies each person needs for the activities they are eligible for
    crew_currency_df.csv      last time each person performed each activity head with a currency threshold
    eligibility_matrix.csv    per activity (grouped by head): who holds every competency it needs
    roster_lines.csv          the shift lines (teams) behind the roster: explanation, not a DB table
    roster_report.md          generated summary with pattern samples

How the roster is built is explained in Progress/real_data_understanding/05_roster_generation.md.
``scripts/check_roster.py`` re-checks every rule independently.

    python scripts/roster_making.py
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "optiflux_v2"

# crew_master_data_changes.txt had 1,000 crew; gap_filling_rules.md R2 cuts that to 700, keeping the mix (70% of
# each pool). 280 Haskett = 210 Residential + 70 FIFO; 210 Yarmouth = 210 FIFO; 210 Nelaway = 140 Residential + 70 FIFO.
# general_rules_assignment.txt: "we can create more user ids if needed".
CREW_TARGETS: dict[tuple[str, str], int] = {
    ("Haskett", "Residential"): 210,
    ("Haskett", "FIFO"): 70,
    ("Yarmouth", "FIFO"): 210,
    ("Nelaway", "Residential"): 140,
    ("Nelaway", "FIFO"): 70,
}
DEPOT_ORDER = ["Haskett", "Yarmouth", "Nelaway"]
CLASS_ORDER = ["Residential", "FIFO"]
FIRST_USER_NUMBER = 100001  # same User Id format as the upload (U100001 ...)

RELIEF_ID, TRAVEL_IN_ID, TRAVEL_OUT_ID, OFF_ID = "A90", "A91", "A92", "A93"
RELIEF_ROLE = "Driver"  # every work activity accepts a Driver, so Relief can cover any gap
OFF_SITE = "Off Site"

ROSTER_HEADER = [
    "Assignment ID", "User Id", "Start Date", "End Date", "Shift Start Time", "Shift End Time",
    "Activity ID", "Activity Name", "Is Locked", "Activity Head", "Activity Type", "Activity Group",
    "Assignment Type", "Demand ID", "Start Location", "End Location", "Line ID", "Swing", "In Horizon",
]  # fmt: skip
CREW_HEADER = ["User Id", "Classification", "Eligibility", "Depot", "Role", "Is Mentor", "Medical", "Position"]
COMPETENCY_HEADER = ["User Id", "Competency", "Competency LMS Code", "Expiry Date", "status"]
CURRENCY_HEADER = ["Currency ID", "User Id", "Activity Head", "Last Performed Date", "Last Activity ID"]
ELIGIBILITY_HEADER = ["Activity Head", "Activity ID", "Activity Name", "Eligible Count", "Eligible User Ids"]
LINE_HEADER = [
    "Line ID", "Assignment Type", "Pattern", "Activity IDs", "Activity Names", "Day Start", "Night Start",
    "Classification", "Home Depots", "Role", "Members", "Shifts Per Day",
]  # fmt: skip

# Pattern kinds. "Pair" kinds cover one day start and one night start (12 h apart) of the same work;
# "single" kinds cover one start time. "Two-way" kinds alternate an outbound and a return activity
# (Haskett -> Yarmouth, Yarmouth -> Haskett) so the crew always starts where the last shift ended.
PAIR, SINGLE, TWOWAY_PAIR, TWOWAY_SINGLE, SHUTTLE = "pair", "single", "two-way pair", "two-way single", "shuttle"
PAIR_KINDS = (PAIR, TWOWAY_PAIR)
TWOWAY_KINDS = (TWOWAY_PAIR, TWOWAY_SINGLE, SHUTTLE)


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _range(value: str) -> tuple[float, float]:
    lo, hi = value.split("-")
    return float(lo), float(hi)


@dataclass(frozen=True)
class Settings:
    start: date
    days: int
    shift_hours: int
    day_window: tuple[int, int]  # minutes of the day, [lo, hi)
    on_off: dict[str, tuple[int, int]]
    travel_gap: tuple[float, float]
    travel_duration: tuple[float, float]
    excess_fraction: float
    seed: int

    @classmethod
    def from_rows(cls, rows: list[dict[str, str]]) -> Settings:
        c = {r["Constraint"]: r["Value"] for r in rows if r["Status"].strip().lower() == "active"}
        lo, hi = (int(t[:2]) * 60 + int(t[3:]) for t in c["Day Shift Window"].split("-"))
        on_off = {}
        for crew_class in CLASS_ORDER:
            on, off = (int(x) for x in c[f"{crew_class} Work/Off Days"].split("/"))
            if on != off or on % 2:
                raise SystemExit(f"{crew_class} Work/Off Days must be equal and even (got {on}/{off})")
            on_off[crew_class] = (on, off)
        return cls(
            start=date.fromisoformat(c["Planning Horizon Start"]),
            days=int(c["Planning Horizon Days"]),
            shift_hours=int(c["Shift Length Hours"]),
            day_window=(lo, hi),
            on_off=on_off,
            travel_gap=_range(c["Travel Gap Hours"]),
            travel_duration=_range(c["Travel Duration Hours"]),
            excess_fraction=float(c["Excess Line Fraction"]),
            seed=int(c["Random Seed"]),
        )

    def block(self, crew_class: str) -> int:
        """Days in one block: a swing is a day block followed by a night block."""
        return self.on_off[crew_class][0] // 2

    def is_day(self, hour: int) -> bool:
        lo, hi = self.day_window
        return lo <= hour * 60 < hi


# ---------------------------------------------------------------------------
# Lines (teams) and their patterns
# ---------------------------------------------------------------------------


@dataclass
class Line:
    kind: str
    assignment_type: str  # Demand | Excess | Relief
    activities: tuple[str, ...]  # one activity, or (outbound, return) for two-way kinds
    crew_class: str
    homes: tuple[str, ...]  # one home depot per member group
    priority: int
    family: str  # lines of the same work share a family (used for Excess and roles)
    day_hour: int | None = None
    night_hour: int | None = None
    hour: int | None = None
    team_size: int = 0  # members per home group; 0 = full team for the kind
    role: str = ""
    line_id: str = ""
    members: list[str] = field(default_factory=list)

    def offsets(self, b: int) -> list[int]:
        """Cycle position of each member on day 0 (cycle = 4 blocks = one swing on + one swing off).

        Pair kinds: 4 members whose day blocks follow each other, so every day exactly one member is
        on the day start and one on the night start. Member 0 starts on day shifts, member 1 is on
        nights. Single kinds: 2 members, each working a whole swing in turn.
        """
        if self.kind in PAIR_KINDS:
            late_night = self.night_hour < self.day_hour  # night start is after midnight
            offs = [0, 2 * b, 3 * b, b] if late_night else [0, b, 3 * b, 2 * b]
        else:
            offs = [0, 2 * b]
        return offs[: self.team_size or len(offs)]

    def position(self, b: int, p: int) -> tuple[int, int] | None:
        """(start hour, shift number within the swing) at cycle position ``p``, or None when off."""
        if self.kind in PAIR_KINDS:
            if p < b:
                return self.day_hour, p
            # Night block starts after at least 24 h rest (23 h needed for a day->night transition).
            night_from = b + (1 if self.night_hour < self.day_hour else 0)
            if night_from <= p < night_from + b:
                return self.night_hour, b + p - night_from
            return None
        return (self.hour, p) if p < 2 * b else None

    def shifts_per_day(self) -> int:
        groups = 1 if self.kind == SHUTTLE else len(self.homes)  # shuttle: one outbound per day per seat
        if self.kind in PAIR_KINDS:
            return 2 * groups if (self.team_size or 4) == 4 else 0
        return groups if (self.team_size or 2) == 2 else 0


def demand_seats(demand: list[dict[str, str]]) -> dict[str, Counter]:
    seats: dict[str, Counter] = defaultdict(Counter)
    for d in demand:
        if d["Is Active"].strip().lower() == "yes":
            seats[d["Activity ID"]][int(d["Shift"][:2])] += int(d["Demand"])
    return seats


def pair_hours(counter: Counter, s: Settings) -> tuple[list[tuple[int, int]], list[int]]:
    """Match each day start with the night start 12 h later. Returns (pairs, unmatched hours)."""
    left = Counter(counter)
    pairs = []
    for d in sorted(h for h in left if s.is_day(h)):
        n = (d + 12) % 24
        m = min(left[d], left.get(n, 0))
        pairs += [(d, n)] * m
        left[d] -= m
        left[n] -= m
    singles = sorted(h for h, c in left.items() for _ in range(c))
    return pairs, singles


def plan_demand_lines(acts, seats, priority, s: Settings) -> list[Line]:
    """One team per demand seat pattern, as described in 05_roster_generation.md."""
    hours_with_demand = {a: set(c) for a, c in seats.items()}
    seats = {a: Counter(c) for a, c in seats.items()}
    lines: list[Line] = []

    def prio(aid: str) -> int:
        return priority[acts[aid]["Activity Head"]]

    def has_class(depot: str, crew_class: str) -> bool:
        return CREW_TARGETS.get((depot, crew_class), 0) > 0

    # 1. Two-way work (start depot != end depot) with a matching reverse activity: alternate the two.
    moving = [a for a in sorted(seats) if acts[a]["Start Depot"] != acts[a]["End Depot"]]
    candidates = []
    for x in moving:
        for r in moving:
            if (
                x < r
                and acts[x]["Start Depot"] == acts[r]["End Depot"]
                and acts[x]["End Depot"] == acts[r]["Start Depot"]
            ):
                matched = sum(min(seats[x][h], seats[r][h]) for h in seats[x])
                candidates.append((-matched, x, r))
    for _, x, r in sorted(candidates):
        both = Counter({h: min(seats[x][h], seats[r][h]) for h in seats[x] if min(seats[x][h], seats[r][h]) > 0})
        if not both:
            continue
        seats[x] -= both
        seats[r] -= both
        homes = (acts[x]["Start Depot"], acts[x]["End Depot"])
        family = f"{x}+{r}"
        pairs, singles = pair_hours(both, s)
        for d, n in pairs:
            lines.append(Line(TWOWAY_PAIR, "Demand", (x, r), "FIFO", homes, min(prio(x), prio(r)), family, d, n))
        for h in singles:
            lines.append(Line(TWOWAY_SINGLE, "Demand", (x, r), "FIFO", homes, min(prio(x), prio(r)), family, hour=h))

    # 2. Remaining moving work: shuttle. Crew alternate the activity and the reverse trip at the same hour;
    #    the reverse trip is surplus on that activity, i.e. Excess.
    for x in moving:
        for h in sorted(seats[x].elements()):
            back = [r for r in sorted(acts) if acts[r]["Start Depot"] == acts[x]["End Depot"]
                    and acts[r]["End Depot"] == acts[x]["Start Depot"] and acts[r]["Activity Type"] not in ("Relief", "Travel", "Off")]  # fmt: skip
            back.sort(key=lambda r: (h not in hours_with_demand.get(r, set()), r))  # prefer a return with demand at h
            if not back:
                raise SystemExit(f"{x} ends away from its start depot and no activity returns from there")
            homes = (acts[x]["Start Depot"], acts[x]["End Depot"])
            lines.append(Line(SHUTTLE, "Demand", (x, back[0]), "FIFO", homes, prio(x), x, hour=h))
        seats[x].clear()

    # 3. Local work (start depot == end depot): day/night pairs, then single start times.
    for a in sorted(seats):
        if not seats[a]:
            continue
        depot = acts[a]["Start Depot"]
        pairs, singles = pair_hours(seats[a], s)
        local_class = "Residential" if has_class(depot, "Residential") else "FIFO"
        for d, n in pairs:
            lines.append(Line(PAIR, "Demand", (a,), local_class, (depot,), prio(a), a, d, n))
        for h in singles:
            # Residential crew must start each swing on a day shift, so a night-only start goes to FIFO.
            crew_class = local_class if s.is_day(h) or not has_class(depot, "FIFO") else "FIFO"
            if crew_class == "Residential" and not s.is_day(h):
                raise SystemExit(f"{a} {h:02d}:00 is night-only and {depot} has no FIFO crew")
            lines.append(Line(SINGLE, "Demand", (a,), crew_class, (depot,), prio(a), a, hour=h))
    return lines


def members_needed(line: Line) -> Counter:
    per_group = len(line.offsets(2))  # number of members does not depend on the block length
    return Counter({(home, line.crew_class): per_group for home in line.homes})


def plan_excess_lines(demand_lines: list[Line], fraction: float) -> list[Line]:
    """Add Excess teams to about ``fraction`` of each family's day/night pair lines, spread over the day."""
    by_family: dict[str, list[Line]] = defaultdict(list)
    for ln in demand_lines:
        if ln.kind in PAIR_KINDS:
            by_family[ln.family].append(ln)
    out = []
    for family, group in by_family.items():
        group.sort(key=lambda ln: ln.day_hour)
        n = len(group)
        k = math.ceil(fraction * n - 1e-9)
        for j in range(k):
            src = group[int((j + 0.5) * n / k)]
            out.append(Line(src.kind, "Excess", src.activities, src.crew_class, src.homes, src.priority, family,
                            src.day_hour, src.night_hour))  # fmt: skip
    return out


def plan_relief_lines(remaining: Counter) -> list[Line]:
    """Every person left in a pool becomes Relief, in day/night teams at spread-out start times."""
    out = []
    for depot in DEPOT_ORDER:
        for crew_class in CLASS_ORDER:
            r = remaining.get((depot, crew_class), 0)
            i = 0
            fam = f"Relief {depot} {crew_class}"
            while r > 0:
                day = 3 + (i * 5) % 12  # 03, 08, 13, 06, 11, 04, ... : every day start in turn
                if r >= 4:
                    ln = Line(PAIR, "Relief", (RELIEF_ID,), crew_class, (depot,), 999, fam, day, (day + 12) % 24)
                    r -= 4
                else:
                    size = 2 if r >= 2 else 1
                    ln = Line(SINGLE, "Relief", (RELIEF_ID,), crew_class, (depot,), 999, fam, hour=day, team_size=size)
                    r -= size
                out.append(ln)
                i += 1
    return out


# ---------------------------------------------------------------------------
# Roster rows
# ---------------------------------------------------------------------------


@dataclass
class Shift:
    user: str
    start: datetime
    end: datetime
    activity: str
    assignment_type: str
    demand_id: str
    start_loc: str
    end_loc: str
    line: str
    swing: int


def member_shifts(line: Line, home: str, p0: int, acts, demand_ids, s: Settings) -> dict[int, list[Shift]]:
    """All shifts of one member, grouped by swing; only complete swings that touch the horizon."""
    b = s.block(line.crew_class)
    cycle = 4 * b
    by_swing: dict[int, list[Shift]] = defaultdict(list)
    loc = home
    for k in range(-cycle - 1, s.days + cycle + 1):
        pos = line.position(b, (p0 + k) % cycle)
        if pos is None:
            continue
        hour, idx = pos
        swing = (p0 + k) // cycle
        if idx == 0:
            loc = home  # a swing always starts at the home depot
        if line.kind in TWOWAY_KINDS:
            aid = next(a for a in line.activities if acts[a]["Start Depot"] == loc)
        else:
            aid = line.activities[0]
        start = datetime.combine(s.start + timedelta(days=k), datetime.min.time()) + timedelta(hours=hour)
        end_loc = acts[aid]["End Depot"] or loc
        rtype = line.assignment_type
        if line.kind == SHUTTLE and aid != line.activities[0]:
            rtype = "Excess"  # the trip back is surplus on the return activity
        by_swing[swing].append(
            Shift(line.members[0], start, start + timedelta(hours=s.shift_hours), aid, rtype,
                  demand_ids.get((aid, hour), "") if rtype != "Relief" else "", loc, end_loc, line.line_id, swing)
        )  # fmt: skip
        loc = end_loc
    kept = {}
    for swing, shifts in by_swing.items():
        complete = shifts[0].start.date() > s.start + timedelta(days=-cycle - 1)
        touches = any(0 <= (sh.start.date() - s.start).days < s.days for sh in shifts)
        if complete and touches:
            if shifts[-1].end_loc != home:
                raise SystemExit(f"{line.line_id}: swing ends away from {home}")
            kept[swing] = shifts
    return kept


def build(data_dir: Path) -> dict:
    acts = {a["Activity ID"]: a for a in read_csv(data_dir / "activities_df.csv")}
    demand = read_csv(data_dir / "activity_demand_df.csv")
    priority = {r["Activity Head"]: int(r["Priority"]) for r in read_csv(data_dir / "activity_priority.csv")}
    compliance = read_csv(data_dir / "compliance_matrix_df.csv")
    s = Settings.from_rows(read_csv(data_dir / "constraints_df.csv"))
    rng = random.Random(s.seed)

    seats = demand_seats(demand)
    demand_ids = {(d["Activity ID"], int(d["Shift"][:2])): d["Demand ID"] for d in demand}

    # --- plan: demand lines first (may add people), then Excess and Relief from what is left --------
    demand_lines = plan_demand_lines(acts, seats, priority, s)
    need = Counter()
    for ln in demand_lines:
        need += members_needed(ln)
    added = {k: v - CREW_TARGETS.get(k, 0) for k, v in need.items() if v > CREW_TARGETS.get(k, 0)}
    remaining = Counter({k: max(0, v - need.get(k, 0)) for k, v in CREW_TARGETS.items()})
    excess_lines, skipped_excess = [], []
    for ln in sorted(plan_excess_lines(demand_lines, s.excess_fraction), key=lambda ln: (ln.priority, ln.family)):
        req = members_needed(ln)
        if all(remaining[k] >= v for k, v in req.items()):
            remaining -= req
            excess_lines.append(ln)
        else:
            skipped_excess.append(ln)
    relief_lines = plan_relief_lines(remaining)

    # --- order lines by priority (Excess right after its work), then number lines and people -----------
    def order(ln: Line):
        kind_rank = {TWOWAY_PAIR: 0, PAIR: 0, TWOWAY_SINGLE: 1, SHUTTLE: 1, SINGLE: 1}[ln.kind]
        type_rank = {"Demand": 0, "Excess": 1, "Relief": 2}[ln.assignment_type]
        hour = ln.day_hour if ln.day_hour is not None else ln.hour
        return (ln.priority, ln.family, type_rank, kind_rank, hour)

    lines = sorted(demand_lines + excess_lines, key=order) + relief_lines
    team_no: Counter = Counter()
    next_user = FIRST_USER_NUMBER
    crew: list[dict[str, str]] = []
    member_of: dict[str, tuple[Line, str, int]] = {}
    for i, ln in enumerate(lines, start=1):
        ln.line_id = f"L{i:03d}"
        if ln.assignment_type == "Relief":
            ln.role = RELIEF_ROLE
        else:
            roles = [r.strip() for r in acts[ln.activities[0]]["Roles/Job"].split(";") if r.strip()]
            ln.role = roles[team_no[ln.family] % len(roles)]
            team_no[ln.family] += 1
        for home in ln.homes:
            for p0 in ln.offsets(s.block(ln.crew_class)):
                uid = f"U{next_user}"
                next_user += 1
                ln.members.append(uid)
                member_of[uid] = (ln, home, p0)

    # --- shifts --------------------------------------------------------------------------------------------
    shifts: list[Shift] = []
    swings_of: dict[str, list[list[Shift]]] = {}
    for uid, (ln, home, p0) in member_of.items():
        orig = ln.members
        ln.members = [uid]  # member_shifts stamps members[0] on each shift
        swings = member_shifts(ln, home, p0, acts, demand_ids, s)
        ln.members = orig
        swings_of[uid] = [swings[k] for k in sorted(swings)]
        for sw in swings_of[uid]:
            shifts.extend(sw)

    # --- travel rows for FIFO: in before the first shift of each swing, out after the last -------------
    def hours(rng_range: tuple[float, float]) -> timedelta:
        lo, hi = rng_range
        return timedelta(minutes=15 * rng.randint(int(lo * 4), int(hi * 4)))

    travel: list[Shift] = []
    for uid, (ln, _home, _) in member_of.items():
        if ln.crew_class != "FIFO":
            continue
        for sw in swings_of[uid]:
            arrive = sw[0].start - hours(s.travel_gap)
            travel.append(Shift(uid, arrive - hours(s.travel_duration), arrive, TRAVEL_IN_ID, "Travel In", "",
                                OFF_SITE, sw[0].start_loc, ln.line_id, sw[0].swing))  # fmt: skip
            leave = sw[-1].end + hours(s.travel_gap)
            travel.append(Shift(uid, leave, leave + hours(s.travel_duration), TRAVEL_OUT_ID, "Travel Out", "",
                                sw[-1].end_loc, OFF_SITE, ln.line_id, sw[-1].swing))  # fmt: skip

    # --- Off rows (gap_filling_rules.md R1): every horizon day of the off-block between swings ---------------
    # A day is off when no swing of the person covers it (first to last shift start date). The short rest
    # inside a swing (e.g. between a day block and a late-night block) is not an off-block and gets no row.
    off: list[Shift] = []
    horizon_end = s.start + timedelta(days=s.days)
    for uid, (ln, home, _) in member_of.items():
        covered = set()
        for sw in swings_of[uid]:
            d0, d1 = sw[0].start.date(), sw[-1].start.date()
            covered |= {d0 + timedelta(days=k) for k in range((d1 - d0).days + 1)}
        where = home if ln.crew_class == "Residential" else OFF_SITE  # FIFO crew go home off site
        for k in range(s.days):
            d = s.start + timedelta(days=k)
            if d not in covered:
                t0 = datetime.combine(d, datetime.min.time())
                off.append(Shift(uid, t0, t0 + timedelta(hours=23, minutes=59), OFF_ID, "Off", "", where, where,
                                 ln.line_id, -1))  # fmt: skip

    # --- roster rows ---------------------------------------------------------------------------------------
    swing_no = {}
    for uid, sws in swings_of.items():
        for n, sw in enumerate(sws, start=1):
            swing_no[(uid, sw[0].swing)] = n
    roster = []
    for sh in sorted(shifts + travel + off, key=lambda x: (x.user, x.start)):
        a = acts[sh.activity]
        roster.append({
            "Assignment ID": f"AS{len(roster) + 1:07d}", "User Id": sh.user,
            "Start Date": sh.start.date().isoformat(), "End Date": sh.end.date().isoformat(),
            "Shift Start Time": sh.start.strftime("%H:%M"), "Shift End Time": sh.end.strftime("%H:%M"),
            "Activity ID": sh.activity, "Activity Name": a["Activity Name"],
            "Is Locked": "False",  # gap_filling_rules.md R4: nothing is locked until a user locks it in the app
            "Activity Head": a["Activity Head"], "Activity Type": a["Activity Type"], "Activity Group": a["Activity Group"],
            "Assignment Type": sh.assignment_type, "Demand ID": sh.demand_id,
            "Start Location": sh.start_loc, "End Location": sh.end_loc, "Line ID": sh.line,
            "Swing": str(swing_no[(sh.user, sh.swing)]) if sh.swing >= 0 else "",
            "In Horizon": "Yes" if s.start <= sh.start.date() < horizon_end else "No",
        })  # fmt: skip

    # --- crew master, competencies, currency ----------------------------------------------------------------
    work_ids = sorted(a for a in acts if a in seats)
    codes_of: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in compliance:
        codes_of[r["Activity ID"]].append((r["Competency LMS Code"], r["Competency"]))
    first_date = {}
    for r in roster:
        if r["Assignment Type"] not in ("Travel In", "Travel Out", "Off"):
            first_date.setdefault(r["User Id"], date.fromisoformat(r["Start Date"]))
    competencies, currency = [], []
    for uid, (ln, home, _) in member_of.items():
        if ln.assignment_type == "Relief":
            # Relief can be sent to any work starting or ending at their depot.
            elig = [a for a in work_ids if home in (acts[a]["Start Depot"], acts[a]["End Depot"])]
        else:
            elig = sorted(ln.activities)
        crew.append({
            "User Id": uid, "Classification": ln.crew_class, "Eligibility": ";".join(elig), "Depot": home,
            "Role": ln.role, "Is Mentor": "No", "Medical": "Fit", "Position": ln.line_id,
        })  # fmt: skip
        seen = set()
        for a in elig:
            for code, name in codes_of[a]:
                if code not in seen:
                    seen.add(code)
                    expiry = horizon_end + timedelta(days=rng.randint(180, 900))
                    competencies.append({"User Id": uid, "Competency": name, "Competency LMS Code": code,
                                         "Expiry Date": expiry.isoformat(), "status": "Valid"})  # fmt: skip
        heads_done = set()
        for a in elig:
            head, thr = acts[a]["Activity Head"], acts[a]["Currency Threshold"]
            if not thr or head in heads_done:
                continue
            heads_done.add(head)
            # Current for the whole horizon even without doing the work, and before the first roster row.
            lo = horizon_end - timedelta(days=int(thr) - 1)
            hi = first_date[uid] - timedelta(days=1)
            last = lo + timedelta(days=rng.randint(0, max(0, (hi - lo).days)))
            currency.append({"Currency ID": f"CU{len(currency) + 1:06d}", "User Id": uid, "Activity Head": head,
                             "Last Performed Date": last.isoformat(), "Last Activity ID": a})  # fmt: skip

    eligibility = build_eligibility(acts, compliance, competencies, horizon_end - timedelta(days=1))

    line_rows = []
    for ln in lines:
        line_rows.append({
            "Line ID": ln.line_id, "Assignment Type": ln.assignment_type, "Pattern": ln.kind,
            "Activity IDs": ";".join(ln.activities),
            "Activity Names": ";".join(acts[a]["Activity Name"] for a in ln.activities),
            "Day Start": f"{ln.day_hour:02d}:00" if ln.day_hour is not None else (
                f"{ln.hour:02d}:00" if ln.hour is not None and s.is_day(ln.hour) else ""),
            "Night Start": f"{ln.night_hour:02d}:00" if ln.night_hour is not None else (
                f"{ln.hour:02d}:00" if ln.hour is not None and not s.is_day(ln.hour) else ""),
            "Classification": ln.crew_class, "Home Depots": ";".join(ln.homes), "Role": ln.role,
            "Members": ";".join(ln.members), "Shifts Per Day": str(ln.shifts_per_day()),
        })  # fmt: skip

    return {
        "settings": s, "acts": acts, "demand": demand, "lines": lines, "roster": roster, "crew": crew,
        "competencies": competencies, "currency": currency, "line_rows": line_rows, "added": added,
        "eligibility": eligibility,
        "skipped_excess": skipped_excess,
    }  # fmt: skip


def build_eligibility(acts, compliance, competencies, last_day: date) -> list[dict[str, str]]:
    """eligibility_matrix.csv (gap_filling_rules.md R5): crew_competencies_df joined with compliance_matrix_df.

    One row per work activity, sorted by Activity Head. A person is eligible when they hold every competency
    the activity needs, each Valid and not expiring before the last horizon day. Role, medical and currency
    are separate checks and are not folded in here.
    """
    needs: dict[str, set[str]] = defaultdict(set)
    for r in compliance:
        needs[r["Activity ID"]].add(r["Competency LMS Code"])
    held: dict[str, set[str]] = defaultdict(set)
    for r in competencies:
        if r["status"] == "Valid" and date.fromisoformat(r["Expiry Date"]) >= last_day:
            held[r["User Id"]].add(r["Competency LMS Code"])
    rows = []
    for aid in sorted(needs, key=lambda a: (acts[a]["Activity Head"], a)):
        users = sorted(u for u, codes in held.items() if needs[aid] <= codes)
        rows.append({
            "Activity Head": acts[aid]["Activity Head"], "Activity ID": aid,
            "Activity Name": acts[aid]["Activity Name"], "Eligible Count": str(len(users)),
            "Eligible User Ids": ";".join(users),
        })  # fmt: skip
    return rows


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def pattern_grid(result: dict, line: Line, days: int) -> list[str]:
    """Markdown table: one row per member, one column per day. D/N = day/night shift, R = Relief, . = off."""
    s: Settings = result["settings"]
    cells: dict[tuple[str, int], str] = {}
    for r in result["roster"]:
        if r["Line ID"] != line.line_id or r["Assignment Type"] in ("Travel In", "Travel Out", "Off"):
            continue
        k = (date.fromisoformat(r["Start Date"]) - s.start).days
        if 0 <= k < days:
            dn = "D" if s.is_day(int(r["Shift Start Time"][:2])) else "N"
            mark = dn
            if line.kind in TWOWAY_KINDS:
                mark = f"{dn} {r['Start Location'][0]}>{r['End Location'][0]}"
                if r["Assignment Type"] == "Excess":
                    mark += "*"
            cells[(r["User Id"], k)] = mark
    head = "| User | " + " | ".join((s.start + timedelta(days=k)).strftime("%d") for k in range(days)) + " |"
    out = [head, "|" + "---|" * (days + 1)]
    for uid in line.members:
        out.append(f"| {uid} | " + " | ".join(cells.get((uid, k), ".") for k in range(days)) + " |")
    return out


def write_report(result: dict, path: Path) -> None:
    s: Settings = result["settings"]
    roster, crew, lines, acts = result["roster"], result["crew"], result["lines"], result["acts"]
    inh = [r for r in roster if r["In Horizon"] == "Yes"]
    by_type = Counter(r["Assignment Type"] for r in inh)
    daily_demand = sum(int(d["Demand"]) for d in result["demand"] if d["Is Active"] == "Yes")
    pools = Counter((c["Depot"], c["Classification"]) for c in crew)
    L = [
        "# Initial roster report",
        "",
        "Generated by `scripts/roster_making.py`; do not edit by hand. How the roster is built:",
        "`Progress/real_data_understanding/05_roster_generation.md`. Rule checks: `python scripts/check_roster.py`.",
        "",
        f"Planning horizon: **{s.start} to {s.start + timedelta(days=s.days - 1)}** ({s.days} days). "
        f"Rows outside it (`In Horizon = No`) complete swings that overlap it.",
        "",
        "## Totals",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Roster rows | {len(roster):,} ({len(inh):,} in the horizon) |",
        f"| People | {len(crew):,} |",
        f"| Shift lines (teams) | {len(lines)} ({sum(ln.assignment_type == 'Demand' for ln in lines)} Demand, "
        f"{sum(ln.assignment_type == 'Excess' for ln in lines)} Excess, "
        f"{sum(ln.assignment_type == 'Relief' for ln in lines)} Relief) |",
        f"| Demand per day | {daily_demand} crew-shifts |",
    ]
    for t in ("Demand", "Excess", "Relief", "Travel In", "Travel Out", "Off"):
        L.append(f"| {t} rows per day (horizon average) | {by_type[t] / s.days:.1f} |")
    L += ["", "## Crew by depot and classification", "", "| Depot | Classification | Target | In crew list | Demand lines | Excess lines | Relief |", "|---|---|---|---|---|---|---|"]  # fmt: skip
    role_count: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for ln in lines:
        for home in ln.homes:
            n = len(ln.members) // len(ln.homes)
            role_count[(home, ln.crew_class)][ln.assignment_type] += n
    for key in CREW_TARGETS:
        rc = role_count[key]
        L.append(f"| {key[0]} | {key[1]} | {CREW_TARGETS[key]} | {pools[key]} | {rc['Demand']} | {rc['Excess']} | {rc['Relief']} |")  # fmt: skip
    if result["added"]:
        L += ["", "People added beyond the targets: " + ", ".join(f"{d}/{c} +{n}" for (d, c), n in result["added"].items())]  # fmt: skip
    else:
        L += ["", f"No people had to be added beyond the {sum(CREW_TARGETS.values()):,} in the rules."]
    if result["skipped_excess"]:
        L += [f"Excess lines skipped for lack of people: {len(result['skipped_excess'])}."]

    L += ["", "## Lines per activity", "", "| Priority | Activity | Demand / day | Demand lines | Excess lines | Pattern | Crew |", "|---|---|---|---|---|---|---|"]  # fmt: skip
    fam_lines: dict[str, list[Line]] = defaultdict(list)
    for ln in lines:
        if ln.assignment_type != "Relief":
            fam_lines[ln.family].append(ln)
    per_day = Counter()
    for d in result["demand"]:
        per_day[d["Activity ID"]] += int(d["Demand"])
    for group in sorted(fam_lines.values(), key=lambda g: g[0].priority):
        aids = group[0].activities if group[0].kind != SHUTTLE else group[0].activities[:1]
        names = " + ".join(f"{a} {acts[a]['Activity Name']}" for a in aids)
        kinds = ", ".join(sorted({ln.kind for ln in group}))
        classes = ", ".join(sorted({f"{ln.crew_class} ({'/'.join(ln.homes)})" for ln in group}))
        L.append(f"| {group[0].priority} | {names} | {sum(per_day[a] for a in aids)} | "
                 f"{sum(ln.assignment_type == 'Demand' for ln in group)} | {sum(ln.assignment_type == 'Excess' for ln in group)} | {kinds} | {classes} |")  # fmt: skip

    def sample(title: str, pick, days: int, note: str):
        ln = next((x for x in lines if pick(x)), None)
        if ln is None:
            return
        L.extend(["", f"### {title}: line {ln.line_id}", "", note, ""])
        L.extend(pattern_grid(result, ln, days))

    L += ["", "## Pattern samples (first days of the horizon)", "",
          "`D` = day shift, `N` = night shift, `.` = off. For two-way lines the cell also shows the trip "
          "(`H>Y` = Haskett to Yarmouth); `*` = Excess (surplus trip back)."]  # fmt: skip
    sample("Priority 1, Residential day/night team", lambda x: x.assignment_type == "Demand" and x.kind == PAIR,
           14, "Four people rotate: 3 day shifts, then 3 night shifts, then 6 days off. Every day one is on the day start and one on the night start.")  # fmt: skip
    sample("Mainline, FIFO two-way team", lambda x: x.kind == TWOWAY_PAIR, 15,
           "Four Haskett and four Yarmouth FIFO crew. Each alternates Haskett>Yarmouth and Yarmouth>Haskett, so every shift starts where the last ended and each 14-shift swing ends at home.")  # fmt: skip
    sample("Work Train, shuttle seat", lambda x: x.kind == SHUTTLE, 15,
           "Work Train runs Haskett to Yarmouth only. Each driver works it every other night and comes back on Yarmouth Mainline at the same hour as Excess.")  # fmt: skip
    sample("Relief team", lambda x: x.assignment_type == "Relief" and x.kind == PAIR, 14,
           "Spare people, on standby at their depot (Activity Name and Head = Relief), in the same day/night rotation.")  # fmt: skip
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data-dir", type=Path, default=DEFAULT_DIR, help="v2 data folder (default: %(default)s)")
    args = p.parse_args(argv)
    out = args.data_dir
    result = build(out)
    write_csv(out / "roster_df.csv", ROSTER_HEADER, result["roster"])
    write_csv(out / "crew_master_data_df.csv", CREW_HEADER, result["crew"])
    write_csv(out / "crew_competencies_df.csv", COMPETENCY_HEADER, result["competencies"])
    write_csv(out / "crew_currency_df.csv", CURRENCY_HEADER, result["currency"])
    write_csv(out / "roster_lines.csv", LINE_HEADER, result["line_rows"])
    write_csv(out / "eligibility_matrix.csv", ELIGIBILITY_HEADER, result["eligibility"])
    write_report(result, out / "roster_report.md")
    types = Counter(r["Assignment Type"] for r in result["roster"])
    print(f"roster: {len(result['roster'])} rows {dict(types)}")
    print(f"crew: {len(result['crew'])} people, lines: {len(result['lines'])}, added: {result['added'] or 'none'}")


if __name__ == "__main__":
    main()
