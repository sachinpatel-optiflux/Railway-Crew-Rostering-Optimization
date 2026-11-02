# 1. Uploaded tables vs the repo

Four tables were supplied: `roster_df`, `activities_df`,
`crew_master_data_df`, `activity_demand_df`. They are kept unchanged in
`data/optiflux_v2/source/`. The closest table set in the repo is
`data/generated/small/` (same depot and activity names, same User Id format).
`data/sample/briefing_abc/` uses the older Howrah/Yajpur example and is not
comparable.

## Summary

| Table | vs `data/generated/small/` |
|---|---|
| `roster_df` | **Identical** (273 rows) |
| `activity_demand_df` | **Identical** apart from Windows line endings (27 rows) |
| `activities_df` | **Changed**: columns, rows, depots and groups |
| `crew_master_data_df` | **Changed**: columns removed, values blanked |

## `activities_df`

| Change | Detail |
|---|---|
| Columns removed | `CRT Activity ID`, `Location` |
| Rows removed | A17 Route Learning (still referenced by demand DM026); A90 Relief Standby and A91 Excess Standby (used by about 150 roster rows) |
| Row added | `Work Train CO`, **with the same ID A08 as Work Train** (duplicate key) |
| `TEA Required`, `Can Be Moved` | Blank for every activity (were Yes/No) |
| Start/End Depot moved to Haskett | Madison Crew, Madison Yard, Work Train (now ends at Yarmouth), Fuel Train and Fuel Return (were Madison↔Bethway), Bethway Join/FI Crew, BY Shed, NE Ship, NE Task |
| Activity Group | Local / Freight / Shed → Yard; Work Train Infrastructure → Mainline |
| Unchanged | Roles/Job, Mentor Required, Currency Threshold (90 / 60), Activity Type |

## `crew_master_data_df`

| Change | Detail |
|---|---|
| Columns removed | `CM Id`, `Email`, `First Name`, `Last Name`, `Mentor Id` |
| Column added | `Eligibility` (empty) |
| Blanked | `Classification`, `Role`, `Is Mentor`, `Medical`, `Position` (were Permanent/Relief/Excess, Driver/Shunter/Conductor, 14 mentors, 1 Unfit, Line/Residential/FIFO) |
| Unchanged | User Ids U100001–U100074 and their depots |

## Consequences for the current loader (`src/railway_rostering/db_schema.py`)

These are **not fixed yet**. The code will be adapted when the roster
generator is written, once the open questions are settled.

1. The roster is linked to activities by `CRT Activity ID`, which is gone.
2. Optimised crew are found by `Classification ∈ {Relief, Excess}`; the new
   values are Residential / FIFO.
3. Competencies, currency, onsite and restrictions are keyed by `CM Id`,
   which is gone. `User Id` is now the only crew key.
4. A blank `Can Be Moved` is read as "No", which would lock every assignment.
5. The demand `Shift` column is parsed as `HH:MM-HH:MM`; the new rules give
   only a start time.
6. The supplied `roster_df` still uses the old activity groups, the standby
   activities and the 74 old users. It is superseded: the new roster will be
   generated (rule G1 in `02_rules_vs_previous_model.md`).
