# gap_generation: put crew on leave and write roster_full.csv

Layer 0 of the gap-filling pipeline. The next layers are `option_generation/` and then `CP-SAT/`.
The rules are in `data/optiflux_v2/source/rules/gap_filling_rules.md`.

The script puts 15% of the crew on leave and writes the roster with the gaps that leave creates. The
input tables in `data/optiflux_v2` are only read.

```bash
python gap_generation/make_gaps.py                 # seed 2026, writes gap_generation/output/
python gap_generation/make_gaps.py --seed 7 --output-dir gap_generation/output_seed7
python scripts/run_pipeline.py                     # all layers + Excel workbook
```

## Leave mix (G2)

The shares come from `constraints_df.csv`. Each person gets one leave, and every leave falls inside one swing.

| Leave type | Share of crew (700) | People | Rows on leave |
|---|---|---|---|
| Full Swing | 5% | 35 | every shift of one swing (6 Residential, 14 FIFO). A FIFO person's travel rows for that swing are cancelled too |
| Day Shifts | 2% | 14 | the 3 day shifts of a 6-day Residential swing |
| Night Shifts | 3% | 21 | the 3 night shifts of a 6-day Residential swing |
| Random | 5% | 35 | a run of 1 or more consecutive shifts inside one swing |

## Output

| File | Content |
|---|---|
| `output/roster_full.csv` | `roster_df.csv` plus the columns below |
| `output/leave_plan.csv` | One row per leave: person, type, dates, number of gaps, number of locked gaps |

Columns added to `roster_full.csv`:

| Column | Meaning |
|---|---|
| `New User Id` | Right after `User Id`. Who works the row after leave. **Blank on leave rows** (G3) |
| `Optimised User Id` | **Always blank here.** CP-SAT fills it only after the whole pipeline has run (G4) |
| `Leave Type` | The leave type for rows on leave, else blank |
| `Is Gap` | True for a Demand row on leave: a seat now has nobody on it. Excess and Relief rows on leave are not gaps |
| `Is_locked_gap` | On gaps only. True before the solver start (6 Nov): those days have happened and are never filled (G1). False from 6 Nov on |

## Example run (seed 2026)

```text
Leave: 105 of 700 crew (Random 35, Full Swing 35, Day Shifts 14, Night Shifts 21)
Rows on leave: 704 (Demand 296, Excess 89, Relief 281, Travel In 19, Travel Out 19)
Gaps (Demand rows on leave): 296; locked (before 2026-11-06): 38; to fill: 258
```

## How it picks

1. It considers only swings that lie wholly inside the horizon (1–30 Nov).
2. It shuffles the people with the seed and hands out the leave types in this order: Day Shifts,
   Night Shifts, Full Swing, Random. The two types that need a 3 + 3 Residential swing go first, so
   they always find one.
3. For each person it picks one of their swings at random. For a Random leave it then picks the
   length and the start of the run at random.
