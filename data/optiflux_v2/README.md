# optiflux_v2: data and initial roster from the real-data rules

All 12 OptiFlux tables, plus explanation files. Every per-person table is
keyed by `User Id` (no `CM Id`). Don't edit the CSV files by hand. Change the
scripts and rebuild:

```bash
python scripts/build_optiflux_v2_data.py       # 1. fixed tables, from source/
python scripts/roster_making.py                # 2. roster -> crew list -> competencies, currency
python scripts/check_roster.py --write-report  # 3. check every rule -> roster_checks.md
```

`tests/test_optiflux_v2_data.py` reruns all three and fails if a committed
file is stale or any rule check fails.

| File | Rows | Built by |
|---|---|---|
| `activities_df.csv` | 20 (17 work + Relief, Travel In, Travel Out) | 1 |
| `activity_demand_df.csv` | 150, i.e. 171 crew-shifts per day; `Shift` = start time, 12 h shifts | 1 |
| `activity_priority.csv` | 14 activity heads | 1 |
| `compliance_matrix_df.csv` | 60 | 1 |
| `constraints_df.csv` | 21 settings (horizon 1–28 Nov 2026, rest, swings, travel, ...) | 1 |
| `excluded_activities.csv`, `crew_restrictions.csv`, `Crew_Onsite_App.csv` | header only | 1 |
| `roster_df.csv` | 18,838 (14,862 in the horizon) | 2 |
| `crew_master_data_df.csv` | 1,000 | 2 |
| `crew_competencies_df.csv` | 7,676 | 2 |
| `crew_currency_df.csv` | 1,260 | 2 |
| `roster_lines.csv` | 238 teams behind the roster (explanation) | 2 |
| `roster_report.md` | totals and pattern samples (generated) | 2 |
| `roster_checks.md` | rule check results (generated) | 3 |
| `source/` | uploaded tables, rule notes, two reused old tables (unchanged) | — |

**Explanations:**
- How the roster is made: `Progress/real_data_understanding/05_roster_generation.md`.
- What each file and column means: `Progress/real_data_understanding/06_data_files_guide.md`.

The current solver (`load_instance`) can't read this folder yet, because the
schema changed: no `CM Id`, no `CRT Activity ID`, start-time shifts and
Residential/FIFO classification. Adapting it is the first part of the
recovery step.
