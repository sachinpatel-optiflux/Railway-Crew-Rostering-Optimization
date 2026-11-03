# 5. How the initial roster is made

`scripts/roster_making.py` builds the starting roster (`roster_df.csv`) from
the demand, then builds the crew list (`crew_master_data_df.csv`) from the
people the roster uses. `scripts/check_roster.py` re-checks every rule
afterwards, reading only the CSV files.

```bash
python scripts/build_optiflux_v2_data.py       # 1. fixed tables (activities, demand, rules, ...)
python scripts/roster_making.py                # 2. roster + crew list + per-person tables
python scripts/check_roster.py --write-report  # 3. rule checks -> data/optiflux_v2/roster_checks.md
```

The roster is **greedy and pattern-based**, which the rules allow ("we can use
random or greedy assignments"). There is no optimiser in this step. Each slot
of demand gets a small fixed **team** that rotates through a regular pattern.
The teams are called **lines** (`roster_lines.csv`). Every rule holds by
construction, and the checker confirms it.

## Result

| Item | Value |
|---|---|
| Horizon | 1–28 Nov 2026 (one full FIFO cycle; set in `constraints_df`) |
| Demand covered | 171 crew-shifts every day, every slot exactly (4,788 in the horizon) |
| People | 1,000, exactly the split in the rules; none had to be added |
| Lines | 238: 76 Demand, 15 Excess, 147 Relief |
| Rows per day (horizon) | 171 Demand, 36 Excess, 293 Relief, about 15 Travel In and 15 Travel Out |
| Rule checks | 34 / 34 pass (`data/optiflux_v2/roster_checks.md`) |

Details and pattern samples: `data/optiflux_v2/roster_report.md`.

## The basic pattern: a team of four on one day start and one night start

Most demand comes in pairs of start times 12 hours apart: a **day** start
(starting 03:00–14:59) and a **night** start 12 hours later. Examples:
Madison Crew 03:00 and 15:00, CAM LOT 06:00 and 18:00. One team of four
people covers both, every day:

```
Residential (6 on / 6 off)    day: 01 02 03 04 05 06 07 08 09 10 11 12 | 13 ...
  member 1 (U100001)               D  D  D  N  N  N  .  .  .  .  .  .  | D
  member 2 (U100002)               N  N  N  .  .  .  .  .  .  D  D  D  | N
  member 3 (U100003)               .  .  .  D  D  D  N  N  N  .  .  .  | .
  member 4 (U100004)               .  .  .  .  .  .  D  D  D  N  N  N  | .
```

- Each person works one **swing**: half day shifts, then half night shifts,
  then the same number of days off. Residential crew work 3 days and 3
  nights, then have 6 days off. FIFO crew work 7 days and 7 nights, then have
  14 days off.
- Every day exactly one member is on the day start and one on the night
  start. So user 1 works the job's day shift and user 2 works the same job's
  night shift on the same day, which is the pattern asked for.
- **Rest:** within a block a person starts at the same time every day, which
  gives 12 h rest (11 h needed). Between the last day shift and the first
  night shift there are 24 h (23 h needed for a day-to-night switch).
- **Night starts after midnight** (00:00–02:00, paired with day starts
  12:00–14:00). One empty day sits between the day block and the night block,
  so the switch still gets 24 h rest.
- **First shift is a day shift.** Every swing starts with the day block, so
  Residential crew start each swing on a day shift (rule R1).

Lines are numbered in **priority order** (`activity_priority.csv`). User Ids
follow the line order, so U100001–U100004 are the team on the priority-1 job
(Madison Crew 03:00/15:00), U100005–U100008 the next one, and so on.

## Other line types

| Pattern | Used for | Team | How it works |
|---|---|---|---|
| **pair** | Local work (starts and ends at the same depot) with a day and a night start | 4 | As above |
| **single** | A start time with no partner 12 h away: Fuel Train 10:00, Fuel Return 10:00, Haskett Mainline CO 17:00 | 2 | Each person works a whole swing on that start, then the other takes over |
| **two-way pair** | Haskett Mainline (Haskett→Yarmouth) together with Yarmouth Mainline (Yarmouth→Haskett) | 4 Haskett + 4 Yarmouth FIFO | Each person alternates the two directions, so every shift starts where the last one ended. A swing has 14 shifts, an even number, so it ends back at home. One Haskett-based and one Yarmouth-based member are on each start, going opposite ways, so both directions are covered |
| **shuttle** | Work Train (Haskett→Yarmouth, 22:00, 2 people) | 2 Haskett + 2 Yarmouth FIFO per seat | Work Train has no return duty, so a driver works it one night and returns the next night on Yarmouth Mainline 22:00. That return seat is already covered, so the trip back is marked **Excess** (rule G5). Two drivers alternate, so Work Train is covered every night |

Mainline sample (FIFO, `H>Y` = Haskett to Yarmouth):

```
day:        01      02      03   ...  07      08      09   ...  14      15
U100233   D H>Y   D Y>H   D H>Y  ...  D H>Y   N Y>H   N H>Y  ...  N Y>H   .
U100237   D Y>H   D H>Y   D Y>H  ...  D Y>H   N H>Y   N Y>H  ...  N H>Y   .
```

## Which crew does which work

| Work | Crew | Why |
|---|---|---|
| Local work at Haskett and Nelaway | Residential at that depot | Local crew. Their day-first swings satisfy R1 |
| Local work at Yarmouth (CAM LOT, Yarmouth Mainline CO) | Yarmouth FIFO | Yarmouth has only FIFO crew |
| Night-only start (Haskett Mainline CO 17:00) | FIFO | A Residential person on it would start a swing on a night shift (R1) |
| Mainline and Work Train | FIFO at both ends | Both ends need the same swing length; Yarmouth has only FIFO |

## Excess and Relief

The rules define both as **roster states**, not types of person (G5, G6).

- **Excess** (`Assignment Type = Excess`): more people on an activity than its
  demand. About 10 % of each activity's day/night lines get one extra team on
  the same start times (`Excess Line Fraction = 0.10`). That makes 15 Excess
  lines, spread over the day. The Work Train return trips are Excess too.
  Excess rows are `Is Locked = No`, so the recovery step can move them.
- **Relief** (`Assignment Type = Relief`, Activity Name = Activity Head =
  `Relief`): everyone not needed for Demand or Excess. They are on standby at
  their home depot in the same day/night team pattern. Their start times are
  spread over all 12 day starts, so some Relief is near every gap. Relief rows
  are `Is Locked = No`.

**Crew capacity.** The rules ask for 1,000 people. Covering the demand needs
346 of them (Demand lines), and Excess uses another 68. That leaves **586
people as Relief**, about 293 on standby every day. Haskett is the tightest
depot (105 of the 171 daily shifts); Yarmouth and Nelaway have the most spare.
See `04_open_questions.md`, Q14.

## FIFO travel (F1–F3)

Every FIFO swing gets two rows:

- `Travel In` ends 1–4 h before the first shift (random, in 15-minute steps)
  and lasts 2–6 h. It goes from `Off Site` to the depot of the first shift.
- `Travel Out` starts 1–4 h after the last shift ends and lasts 2–6 h. It goes
  to `Off Site`.

The ranges are `Travel Gap Hours` and `Travel Duration Hours` in
`constraints_df`. The random seed is fixed (`Random Seed = 2026`), so the
output is the same on every run. Residential crew have no travel rows.

## Complete swings

The horizon starts in the middle of some swings. For example, U100002 is on
night shifts on 1 Nov, so their swing began on 29 Oct. The roster includes
the **whole swing** of anyone working in the horizon, with `In Horizon = No`
on the rows outside it. That way every swing shows its first shift (R1) and
both travel rows (F2). Coverage is guaranteed only inside the horizon.

## The crew list comes from the roster

Each person in `crew_master_data_df.csv` exists because a line needs them:

| Column | Value |
|---|---|
| `User Id` | In line order (priority order). U100001… |
| `Classification` | Residential / FIFO, from the line |
| `Depot` | The person's home depot (for two-way lines: their end of the line) |
| `Role` | One of the activity's `Roles/Job`, rotating between the activity's teams. Relief: Driver (every activity accepts a Driver) |
| `Eligibility` | Activity IDs the person may work: their line's activities. Relief: every activity starting or ending at their depot |
| `Is Mentor` / `Medical` | `No` / `Fit` (no data given; Q6) |
| `Position` | The person's line (`roster_lines.csv`) |

The per-person tables are then built to match, all keyed by **User Id**:

- `crew_competencies_df`: every competency the compliance matrix lists for the
  person's eligible activities. Valid, expiring 6–30 months after the horizon.
- `crew_currency_df`: for activity heads with a currency threshold (the
  mainlines 90 days, the fuel trains 60 days). The last-performed date is
  random but recent enough that the person stays current for the whole
  horizon.
- `crew_restrictions`, `Crew_Onsite_App`: empty. The initial roster has no
  leave (G9).

If a line needed more people than a depot/classification has, the script
would add users (allowed by G9) and list them in `roster_report.md`. With the
current data none are needed.

## Rule → how it is met → check

| Rule | Met by | Check in `check_roster.py` |
|---|---|---|
| G1 rows for users from the demand of each activity, every day | One line per demand slot | Every slot, every horizon day: Demand rows = demand; no slot over-filled |
| G2 no-activity rows for overtime | Deferred | No such rows |
| G5 Excess = more assigned than demand | Excess lines and shuttle return trips | Excess only where the slot is already full |
| G6 Relief = extras, name and head `Relief` | Relief lines on activity A90 | Name = Head = Relief, no Demand ID |
| G9 initial roster without leave, more users allowed | No restrictions; users added if a pool runs out | Restrictions empty, all Fit |
| G10 remove ~10 % and reassign | Next step. Excess/Relief rows are unlocked; `Recovery Removal Fraction = 0.10` | — |
| F1–F3 FIFO travel in/out, random | Travel rows per swing | One in before the first shift and one out after the last, per swing |
| R1 Residential first shift is a day shift | Day block first in every swing | First shift of every Residential swing is in the day window |
| D1–D2 start-time shifts, 12 h | Demand table; shift length from constraints | Every work row is 12 h |
| M1–M5 1,000 crew, the depot/classification split | Pools fixed in `roster_making.py` | Counts per pool |
| Rest 11 h / 23 h, one duty a day, swings 14/14 and 6/6, location, return to base | The line patterns | One check each |
| Eligibility: role, competencies, currency | Crew tables built from the roster | One check each |

## Limits and next steps

- **No optimisation.** The patterns are regular by design. All teams change
  over on the same days (every 3 days for Residential, every 7 for FIFO), so
  FIFO travel is bunched. Staggering the teams is a small change if wanted.
- **The solver can't read v2 yet.** The current solver
  (`src/railway_rostering`) cannot load v2: it expects `CM Id` and
  `CRT Activity ID`, and `HH:MM-HH:MM` shifts. Adapting the loader is the
  first part of the recovery step (G10).
- **Mentor and TEA rules unused.** Nothing is filled in for them yet (Q6, Q8).
