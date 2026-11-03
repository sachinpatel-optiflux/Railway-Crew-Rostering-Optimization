# Understanding the real OptiFlux data

This folder records how our understanding of the real OptiFlux data has
changed, and what we have done about it. Each file covers one step.

The model built so far (package `src/railway_rostering`, data in
`data/generated/` and `data/sample/`) assumed that a **roster already exists**
and that we only fill its gaps with Relief and Excess crew. The new rules say
something different: we first **build the initial roster ourselves** from
demand, and then run the gap-filling (recovery) step. The initial roster now
exists (`data/optiflux_v2/roster_df.csv`) and passes every rule check.

## Files

| # | File | What it covers |
|---|---|---|
| 1 | [`01_data_comparison.md`](01_data_comparison.md) | The four uploaded tables compared with the tables in the repo |
| 2 | [`02_rules_vs_previous_model.md`](02_rules_vs_previous_model.md) | **Every new rule**, numbered, next to how the previous model handled it, and where it is enforced |
| 3 | [`03_data_changes.md`](03_data_changes.md) | The changes made to the data files, and why |
| 4 | [`04_open_questions.md`](04_open_questions.md) | Gaps and contradictions to confirm, with the assumption used for each |
| 5 | [`05_roster_generation.md`](05_roster_generation.md) | **How the initial roster is made**: team patterns, Excess and Relief, FIFO travel, the crew list, rule-by-rule compliance |
| 6 | [`06_data_files_guide.md`](06_data_files_guide.md) | Every data file and roster column in plain words |

Source material, unchanged: `data/optiflux_v2/source/`.

## How to rebuild everything

```bash
python scripts/build_optiflux_v2_data.py       # fixed tables
python scripts/roster_making.py                # roster, crew list, per-person tables
python scripts/check_roster.py --write-report  # rule checks
```

## Progress

| Step | Status | Where |
|---|---|---|
| Compare uploaded tables with the repo | Done | `01_data_comparison.md` |
| Structure the new rules against the previous model | Done | `02_rules_vs_previous_model.md` |
| Apply the rules to the uploaded tables | Done | `scripts/build_optiflux_v2_data.py`, `03_data_changes.md` |
| Add the remaining 8 tables, keyed by `User Id` (no `CM Id`) | Done | `03_data_changes.md` |
| **Generate the initial roster** (patterned, no leave) | **Done** | `scripts/roster_making.py`, `05_roster_generation.md` |
| Build the crew list from the roster (1,000 people) | Done | `crew_master_data_df.csv` |
| Independent check of every rule | Done: 34/34 pass | `scripts/check_roster.py`, `data/optiflux_v2/roster_checks.md` |
| Automated tests | Done | `tests/test_optiflux_v2_data.py` |
| Confirm open questions | **Pending** | `04_open_questions.md` |
| Remove ~10 % of the roster and reassign Relief/Excess to the gaps | **Next** | adapt the solver loader to v2, then reuse the CP-SAT recovery model |
| "No activity" rows for overtime | Deferred by request | — |

## Main shifts in understanding

1. **Two phases, not one.** Phase 1 builds an initial roster from demand.
   Phase 2 removes about 10 % of it and refills the gaps with Relief and
   Excess crew. The existing solver already does phase 2.
2. **Relief and Excess are roster states, not crew types.** Crew are
   **Residential** or **FIFO**. *Excess* = a person on a job beyond its
   demand. *Relief* = a spare person on no job (name and head `Relief`).
3. **Demand is given per start hour.** Each demand row is a start time, and
   every shift lasts 12 h. The main lines need a crew start every hour.
4. **The crew list follows the roster.** People are created for the roster's
   teams, in priority order. The 1,000 required are more than enough: 346
   cover the demand, 68 are Excess, and 586 are Relief.
5. **User Id is the only person key.** `CM Id` is not used anywhere in v2.
6. **FIFO travel** rows sit around each FIFO swing: in before the first
   shift, out after the last.
