# optiflux_v2 — data built from the real-data rules

Built by `python scripts/build_optiflux_v2_data.py` from `source/` (the
uploaded tables and rule notes, unchanged). Do not edit the built CSV files by
hand: change the script and rebuild. `tests/test_optiflux_v2_data.py` checks
that the files are current.

| File | Rows |
|---|---|
| `activities_df.csv` | 18 activities (incl. A90 `Relief`) |
| `activity_demand_df.csv` | 150 rows, 171 crew-shifts per day; `Shift` = start time, every shift is 12 h |
| `crew_master_data_df.csv` | 1,000 crew: Haskett 300 Residential + 100 FIFO, Yarmouth 300 FIFO, Nelaway 200 Residential + 100 FIFO |
| `roster_df.csv` | header only; the initial roster is generated in a later step |

This folder does **not** load with the current solver (`load_instance`) yet:
the schema changed (no `CM Id`, no `CRT Activity ID`, start-time shifts,
Residential/FIFO classification). See
[`Progress/real_data_understanding/`](../../Progress/real_data_understanding/README.md).
