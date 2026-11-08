# optiflux_v2: data and initial roster from the real-data rules

All 12 OptiFlux tables, plus explanation files. Every per-person table is
keyed by `User Id` (no `CM Id`). Don't edit the CSV files by hand. Change the
scripts and rebuild:

```bash
python scripts/build_optiflux_v2_data.py       # 1. fixed tables, from source/
python scripts/roster_making.py                # 2. roster -> crew list -> competencies, currency
python scripts/check_roster.py --write-report  # 3. check every rule -> roster_checks.md
python scripts/export_excel.py                 # 4. every CSV as one sheet -> optiflux_v2.xlsx
```

`tests/test_optiflux_v2_data.py` reruns all three and fails if a committed
file is stale or any rule check fails.

| File | Rows | Built by |
|---|---|---|
| `activities_df.csv` | 21 (17 work + Relief, Travel In, Travel Out, Off/RR) | 1 |
| `activity_demand_df.csv` | 150, i.e. 171 crew-shifts per day; `Shift` = start time, 12 h shifts | 1 |
| `activity_priority.csv` | 14 activity heads | 1 |
| `compliance_matrix_df.csv` | 60 | 1 |
| `constraints_df.csv` | 29 settings (horizon 1–30 Nov 2026, solver start 6 Nov, rest, swings, travel, leave mix, start-change limits, ...) | 1 |
| `excluded_activities.csv`, `crew_restrictions.csv`, `Crew_Onsite_App.csv` | header only | 1 |
| `roster_df.csv` | 24,814 (Demand, Excess, Relief, Travel and 10,220 `Off` rows for the off-blocks); `Is Locked` = False everywhere | 2 |
| `crew_master_data_df.csv` | 700 | 2 |
| `crew_competencies_df.csv` | 3,896 | 2 |
| `eligibility_matrix.csv` | 17: per activity (grouped by head), who holds every competency it needs. Gap filling reads this, not the two tables it comes from | 2 |
| `crew_currency_df.csv` | 600 | 2 |
| `roster_lines.csv` | 164 teams behind the roster (explanation) | 2 |
| `roster_report.md` | totals and pattern samples (generated) | 2 |
| `roster_checks.md` | rule check results (generated) | 3 |
| `optiflux_v2.xlsx` | every CSV above as one sheet (`python scripts/export_excel.py`); the CSVs stay the source | 4 |
| `source/` | uploaded tables, rule notes (incl. `rules/gap_filling_rules.md`), two reused old tables (unchanged) | — |

**Explanations:**
- How the roster is made: `Progress/real_data_understanding/05_roster_generation.md`.
- What each file and column means: `Progress/real_data_understanding/06_data_files_guide.md`.

The current solver (`load_instance`) can't read this folder yet, because the
schema changed: no `CM Id`, no `CRT Activity ID`, start-time shifts and
Residential/FIFO classification. Adapting it is the first part of the
recovery step.
