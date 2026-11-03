# 2. New rules compared with the previous model

Sources (unchanged copies in `data/optiflux_v2/source/rules/`):
`general_rules_assignment.txt`, `demand_changes.txt`,
`crew_master_data_changes.txt`.

"Previous model" means the prototype in `src/railway_rostering` as documented
in `docs/assumptions_and_open_questions.md` and `docs/db_schema.md`.

**Where enforced:**
- **Data**: applied to the tables in `data/optiflux_v2/` (see `03_data_changes.md`).
- **Roster gen**: enforced by `scripts/roster_making.py` (see `05_roster_generation.md`).
- **Recovery**: applies to phase 2 (remove ~10 %, refill). Not built yet.
- **Deferred**: postponed by request.

**Status (initial roster):** every Data and Roster gen rule below is met.
`scripts/check_roster.py` checks each one; results are in
`data/optiflux_v2/roster_checks.md` (34/34 pass). The table at the end of
`05_roster_generation.md` maps each rule to the check.

---

## A. The workflow

| ID | New rule | Previous model | Where enforced |
|---|---|---|---|
| G1 | Build roster rows for the users from the demand of each activity head, so every day has its total number of activity demands filled. | `roster_df` was an **input** that already covered most demand. The solver only filled *open demand* = demand − valid roster rows of regular crew. | Roster gen |
| G9 | Produce the **initial roster without any leave**. Random or greedy assignment is acceptable. More User Ids may be created if needed. | No roster construction existed; crew count was fixed by the data. | Roster gen |
| G10 | After the initial roster, remove **about 10 %** of it, then reassign Excess and Relief crew to those gaps. | This is what the current CP-SAT model does: cover uncovered duties with Relief/Excess crew, respecting rest, swings and location. | Recovery (reuse existing solver after the loader is adapted) |
| G2 | Add rows with **no activity**, needed later for overtime hours. | Not modelled. | **Deferred** ("not considered for now") |

## B. Crew categories and extras

| ID | New rule | Previous model | Where enforced |
|---|---|---|---|
| C1 | `Classification` holds **Residential** or **FIFO**. Person tables use `User Id` (no `CM Id`). | `Classification` held Permanent / Relief / Excess; Residential / FIFO / Line sat in `Position` and were informational. The briefing linked FIFO ↔ Relief (14/14) and Residential ↔ Excess (6/6). | Data |
| G5 | **Excess** = a person assigned to an activity when the demand needs fewer people than are assigned (surplus on an activity). | Excess was a crew type: rostered at a fixed time, ±1 h lift-up/layback, 6 on / 6 off. | Roster gen (`Assignment Type = Excess`: extra teams on ~10 % of lines, and Work Train return trips) |
| G6 | **Relief** = extra people not assigned to any activity; their roster rows have Activity Name = Activity Head = `Relief`. | Relief was a crew type (any start time, 14 on / 14 off) shown by `Relief Standby` rows (CRT-9001, head `Relief`). | Data (activity A90 `Relief`) + Roster gen (everyone not needed for Demand/Excess) |
| G7 | If an **Excess** person takes leave, no gap is created (they were surplus). | Absence of any optimised crew removed availability only. | Recovery (Excess leave is not a gap to fill) |
| G8 | Find Relief or Excess people who can be **reassigned** to gaps. | Same intent as the current model. | Recovery |

Consequence: Relief/Excess is no longer a property of the person. The same
person can be on an activity one day, Excess another day and Relief another.
The swing patterns (14/14, 6/6) are not restated by the new rules; they are
kept (Q3 in `04_open_questions.md`).

## C. FIFO and Residential rules

| ID | New rule | Previous model | Where enforced |
|---|---|---|---|
| F1 | FIFO crew have **travel_in** and **travel_out**: when exactly they arrive and leave. | No travel at all; positioning was switched off because the schema had no travel times. | Roster gen (new data, see below) |
| F2 | travel_in must be **before the first shift** and travel_out **after the last shift**. | — | Roster gen + validation |
| F3 | For now, set travel times **randomly** (within F2). | — | Roster gen |
| R1 | For **Residential** crew the **first shift must be a day shift**. | Day/night only mattered for the 23 h transition rest; a day shift was one starting 03:00–15:00 (an assumption). | Roster gen; needs the day-shift definition (Q4) |

Travel times depend on the generated shifts, so they are written with the
roster: two rows per FIFO swing, `Travel In` (ends 1–4 h before the first
shift) and `Travel Out` (starts 1–4 h after the last), each lasting 2–6 h.

## D. Demand (`activity_demand_df`)

| ID | New rule | Previous model | Where enforced |
|---|---|---|---|
| D1 | `Shift` holds the **start time only** (e.g. `05:00`, not `05:00-17:00`). | `HH:MM-HH:MM` windows, mostly 05–17 / 17–05. | Data |
| D2 | Every shift lasts **12 hours** (end = start + 12 h). | End time given in the window (also 12 h in practice). | Data (implicit) + Roster gen |
| D3 | Rename **NE Task → NE Crew**. | — | Data |
| D4 | Rename **BY Shed → BY Ship**; its demand is like NE Ship. | — | Data |

Demand per activity, previous vs new (crew-shifts per day):

| Activity | Previous demand | New rule | New starts | Per day |
|---|---|---|---|---|
| A01 Haskett Mainline | 05–17 ×1, 17–05 ×1 (2) | 1 person per hour | every hour 00:00–23:00 | 24 |
| A03 Yarmouth Mainline | 05–17 ×1, 17–05 ×1 (2) | 1 person per hour | every hour | 24 |
| A05 CAM LOT | 05–17, 17–05 (2) | 1 per 3 h from 00:00 | 00, 03, 06, … 21 | 8 |
| A06 Madison Crew | 05–17 ×2, 17–05 ×1 (3) | 1 person per hour | every hour | 24 |
| A07 Madison Yard | 06–18 ×2, 18–06 ×1 (3) | 1 per 3 h from 01:00 | 01, 04, 07, … 22 | 8 |
| A08 Work Train | 07–19 ×1 (1) | 2 people at 22:00 | 22:00 ×2 | 2 |
| A09 Fuel Train | 17–05 ×1 (1) | 1 person at 10:00 | 10:00 | 1 |
| A10 Fuel Return | 05–17 ×1 (1) | 1 person at 10:00 | 10:00 | 1 |
| A11 Bethway Join/FI Crew | 05–17, 17–05 (2) | 1 per 3 h from 04:00 | 04, 07, … 22, 01 | 8 |
| A12 BY Ship (was BY Shed) | 05–17 ×1 (1); 17–05 inactive | similar to NE Ship | 04, 09, 16, 21 | 4 |
| A13 Nelaway Driver | 05–17, 17–05 (2) | 1 person per hour | every hour | 24 |
| A14 Nelaway Shuttle Driver | 05–17 ×1 (1) | 1 per 3 h from 01:00 | 01, 04, … 22 | 8 |
| A15 NE Ship | 05–17 ×1 (1) | 04, 16, 09, 21, 1 person each | 04, 09, 16, 21 | 4 |
| A16 NE Crew (was NE Task) | 05–17, 17–05 (2) | 4 people at 04, 16, 07, 19, 09, 21; 2 at 00, 12 | 6 × 4 + 2 × 2 | 28 |
| A02 Haskett Mainline CO | 17–05 ×1 (1) | *not mentioned*, kept | 17:00 | 1 |
| A04 Yarmouth Mainline CO | 05–17, 17–05 (2) | *not mentioned*, kept | 05:00, 17:00 | 2 |
| A17 Route Learning | 05–17 ×1 (1) | *activity removed* | dropped | 0 |
| **Total** | **28** | | | **171** |

Demand rises about six-fold. Because the main lines start a crew every hour,
duty start times are spread across the whole day rather than the two shift
times (05:00 / 17:00) the previous model mostly had.

## E. Crew master data (`crew_master_data_df`)

| ID | New rule | Previous model (`data/generated/small`) | Where enforced |
|---|---|---|---|
| M1 | **1,000** crew members | 74 (small) to 1,540 (xlarge) synthetic crew | Roster gen (crew list built from the roster; checked) |
| M2 | Haskett 400 = 300 Residential + 100 FIFO | Haskett 6 + some reserve | Data |
| M3 | Yarmouth 300 = 300 FIFO | Yarmouth 12 + some reserve | Data |
| M4 | Nelaway 300 = 200 Residential + 100 FIFO | Nelaway 12 + some reserve | Data |
| M5 | Residential / FIFO are values of `Classification` | see C1 | Data |
| — | Madison and Bethway are no longer crew depots | Madison 16 + Bethway 8 crew | Data (follows from M1–M4) |

## F. Rules from the previous model not restated

The new rules do not mention these. They stay in the plan unless told
otherwise, and the generator should respect them:

| Rule | Previous setting |
|---|---|
| Ordinary rest between shifts | 11 h |
| Rest on a day↔night transition | 23 h |
| One duty per calendar day | yes (12 h shift + 11 h rest = 23 h) |
| Location continuity | a crew member starts a duty where the last one ended (relevant for Haskett ↔ Yarmouth mainline duties) |
| Return to base | at swing end and on transition days |
| Swing patterns | FIFO 14 on / 14 off, Residential 6 on / 6 off (briefing §4) |
| Eligibility: role, competencies, currency, medical, mentor | role, competencies, currency and medical are set from the roster and checked; mentor not used yet (Q6) |
