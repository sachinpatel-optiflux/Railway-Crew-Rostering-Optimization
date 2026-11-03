# 3. Changes made to the data

Everything is in `data/optiflux_v2/`. Existing data (`data/generated/`,
`data/sample/`) and the tests built on it are unchanged. Every table that is
about a person is keyed by **`User Id`**. `CM Id` is not used.

## Files and where they come from

| File | Built by | Content |
|---|---|---|
| `source/*.csv`, `source/rules/*.txt` | — | The uploaded tables and rule notes, unchanged |
| `source/from_generated_small/*.csv` | — | Compliance matrix and priority list of the old data (`data/generated/small`), reused below |
| `activities_df.csv` | `build_optiflux_v2_data.py` | 20 activities: 17 work + Relief, Travel In, Travel Out |
| `activity_demand_df.csv` | `build_optiflux_v2_data.py` | 150 rows, 171 crew-shifts per day |
| `activity_priority.csv` | `build_optiflux_v2_data.py` | 14 activity heads in priority order |
| `compliance_matrix_df.csv` | `build_optiflux_v2_data.py` | 60 rows: competencies per activity |
| `excluded_activities.csv` | `build_optiflux_v2_data.py` | Empty |
| `constraints_df.csv` | `build_optiflux_v2_data.py` | 21 settings |
| `crew_restrictions.csv`, `Crew_Onsite_App.csv` | `build_optiflux_v2_data.py` | Header only (no leave, no check-ins) |
| `roster_df.csv` | `roster_making.py` | The initial roster |
| `crew_master_data_df.csv` | `roster_making.py` | 1,000 people, built from the roster |
| `crew_competencies_df.csv`, `crew_currency_df.csv` | `roster_making.py` | Matching the people and their work |
| `roster_lines.csv`, `roster_report.md` | `roster_making.py` | Explanation of the roster |
| `roster_checks.md` | `check_roster.py --write-report` | Rule check results |

`tests/test_optiflux_v2_data.py` rebuilds every file from `source/` and fails
if a committed file differs, or if any rule check fails.

## `activities_df.csv`

| Change | Rule | Why |
|---|---|---|
| A16 `NE Task` → `NE Crew` (name and head) | D3 | demand_changes.txt |
| A12 `BY Shed` → `BY Ship` (name and head) | D4 | demand_changes.txt |
| `Work Train CO` ID A08 → **A17** | — | The upload gave it the same ID as Work Train. Activity ID is a key, so it got the next free ID (A17 was Route Learning in the old data, which the upload removed) |
| Added A90 `Relief` (Group Reserve, Head `Relief`) | G6 | Relief rows need an activity whose name and head are both `Relief` |
| Added A91 `Travel In`, A92 `Travel Out` (Group/Head `Travel`) | F1 | FIFO travel rows in the roster |
| Everything else | — | As uploaded: no `CRT Activity ID` or `Location` column; `TEA Required` and `Can Be Moved` blank; depots and groups as supplied |

No `Excess` activity: Excess means extra people on a real activity (G5), so it
is shown by `Assignment Type = Excess` on the roster row.

## `activity_demand_df.csv`

One row per (activity, start time); `Shift` = start time `HH:MM`; every shift
lasts 12 h. The table of start times per activity is in section D of
`02_rules_vs_previous_model.md`.

Kept from the uploaded demand table, because the rules do not mention them:
A02 Haskett Mainline CO (17:00 ×1) and A04 Yarmouth Mainline CO (05:00 ×1,
17:00 ×1). Dropped: DM026 Route Learning (activity removed) and DM027 BY Shed
17–05 (was inactive; replaced by the BY Ship rule).

## The other tables

| Table | Made from | Changes |
|---|---|---|
| `activity_priority` | old priority list | NE Task → NE Crew, BY Shed → BY Ship. The order is unchanged. Work Train CO shares the head `Work Train`, so it needs no entry of its own |
| `compliance_matrix_df` | old compliance matrix | Renames applied. Old A17 (Route Learning) rows dropped. New A17 Work Train CO copies Work Train's competencies (own sign-off `AC-A17`) |
| `excluded_activities` | — | Empty: Route Learning, the only old exclusion, no longer exists. Copying the old file would have excluded the new A17 (Work Train CO) by mistake |
| `constraints_df` | old constraints + new rules | Horizon 1–28 Nov 2026; `Shift Length Hours` 12; `FIFO Work/Off Days` 14/14 and `Residential Work/Off Days` 6/6 replace the old Relief/Excess rows; new rows for R1, FIFO travel, Excess share, recovery share, random seed. Rest rules unchanged |
| `crew_restrictions`, `Crew_Onsite_App` | — | `User Id` instead of `CM Id`. Empty: no leave in the initial roster (G9) |
| `crew_competencies_df`, `crew_currency_df` | built from the roster | `User Id` instead of `CM Id`. Currency's `Last CRT Activity ID` is now `Last Activity ID` (activities have no CRT ID) |

## `crew_master_data_df.csv`

The crew list is now **made from the roster** (`05_roster_generation.md`), not
written out in advance:

| Depot | Classification | People | Demand lines | Excess lines | Relief |
|---|---|---|---|---|---|
| Haskett | Residential | 300 | 156 | 32 | 112 |
| Haskett | FIFO | 100 | 54 | 8 | 38 |
| Yarmouth | FIFO | 300 | 72 | 16 | 212 |
| Nelaway | Residential | 200 | 64 | 12 | 124 |
| Nelaway | FIFO | 100 | 0 | 0 | 100 |
| **Total** | | **1,000** | **346** | **68** | **586** |

User Ids follow the roster lines in priority order, so they are no longer
grouped by depot. `Role`, `Eligibility` and `Position` are now filled in from
the roster. `Is Mentor` = No and `Medical` = Fit, because no data was given
(Q6).

## Capacity

At most one 12 h shift per person per day. With 6/6 and 14/14 swings, half of
the crew work on any day. Demand by the depot where the work starts:

| Depot | Crew | Demand per day | Working per day | Spare per day |
|---|---|---|---|---|
| Haskett | 400 | 105 | ≈200 | ≈95 |
| Yarmouth | 300 | 34 | ≈150 | ≈116 |
| Nelaway | 300 | 32 | ≈150 | ≈118 |
| **Total** | **1,000** | **171** | **≈500** | **≈329** |

The mainlines are staffed half from Haskett and half from Yarmouth, which
moves some Haskett-start work to Yarmouth crew. Nelaway FIFO crew have no
line work: all 100 are Relief.
