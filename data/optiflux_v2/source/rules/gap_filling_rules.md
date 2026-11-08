# Gap-filling rules (round 2)

This is a clean version of `gap_creation-optiflux.txt`, with the answers given when the change list
was reviewed. Where the two differ, this file wins.

## Data

| # | Rule |
|---|---|
| R1 | Rest days get their own roster rows: **Activity Name = `Off`, Activity Head = `RR`**. They are only written for the off-block between two swings (for example the 6 days off after a 6-day Residential swing, or the 14 days off after a FIFO swing). The short rest inside a swing gets no row, and neither do leave days or gaps. |
| R2 | **Crew = 700** instead of 1000. Each depot/classification pool shrinks by the same 70%. |
| R3 | The roster covers the **full month**: 1–30 Nov 2026 (30 days). |
| R4 | **`Is Locked` = `False` on every row.** Only a user locks rows, through the application, and that is not built yet. |
| R5 | **`eligibility_matrix.csv`** combines `crew_competencies_df.csv` and `compliance_matrix_df.csv`. For every activity it lists the people who hold all of that activity's competencies, grouped by Activity Head. Gap filling reads this file only, not the two tables it was built from. Role, medical fitness and currency are still checked from their own tables. |
| R6 | **One Excel workbook** has every CSV as its own sheet. The individual CSV files are kept too. |

## Gaps

| # | Rule |
|---|---|
| G1 | The roster started on 1 Nov; **the solver starts on 6 Nov**. A gap dated before 6 Nov has `Is_locked_gap = True` and is never filled. A gap dated 6 Nov or later has `Is_locked_gap = False`. |
| G2 | Leave mix, as a share of the 700 crew (15% in total). **Full swing 5%**: every shift of one swing. **Day shifts only 2%**: the day block of one 6-day swing. **Night shifts only 3%**: the night block of one 6-day swing. **Random 5%**: any run of days inside one swing. |
| G3 | A gap is one roster row whose person is on leave. Their id is removed from `New User Id`, so the cell is blank. The solver later writes its choice in `Optimised User Id`. |
| G4 | `roster_full.csv` puts three columns side by side: `User Id` (original), `New User Id` (after leave) and `Optimised User Id`. **`Optimised User Id` stays empty until the whole gap-generation, option-generation and CP-SAT pipeline has run.** |

## Who may fill a gap

| # | Rule |
|---|---|
| F1 | Sources are **Excess**, **Relief**, and **Demand crew from other assignments**. A Demand person must be eligible and can move at most ±1 h (lift-up / layback). |
| F2 | If a Demand person moves, **their old seat becomes a gap**, and the same process fills it. All other constraints still apply: rest, day/night transition, one duty a day, location, base return and travel. |
| F3 | **Swing start-time pattern:** inside one block (the day block or the night block of a swing), the start time changes at most **once**, by at most **1 h**. Allowed: `03 03 03 / 16 16 16`, `03 03 03 / 14 14 14`, `03 04 04 / 16 16 16`. Not allowed: `03 04 03` (two changes) or `03 05 05` (2 h). |
| F4 | Anyone whose swing had **already started before 6 Nov** keeps that swing as it is (only a ±1 h change of their own shift is allowed, and the solver has no reason to use it). They are not candidates for other gaps during that swing. Their later swings, after their next off-block, can change. |

## Pipeline

1. `gap_generation/` writes `roster_full.csv` with the leave applied.
2. `option_generation/` rejects every impossible (person, gap) pair and writes the legal options.
3. `CP-SAT/` chooses from those options only and fills `Optimised User Id`.
