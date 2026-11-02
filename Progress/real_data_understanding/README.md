# Understanding the real OptiFlux data

This folder records how our understanding of the real OptiFlux data has
changed, and what we have done about it. Each file covers one step.

The model built so far (package `src/railway_rostering`, data in
`data/generated/` and `data/sample/`) assumed that a **roster already exists**
and that we only fill its gaps with Relief and Excess crew. The new rules say
something different: we must first **build the initial roster ourselves**
from demand, and only then run the gap-filling (recovery) step. The data has
been updated for this; the roster itself has not been built yet.

## Files

| # | File | What it covers |
|---|---|---|
| 1 | [`01_data_comparison.md`](01_data_comparison.md) | The four uploaded tables compared with the tables in the repo |
| 2 | [`02_rules_vs_previous_model.md`](02_rules_vs_previous_model.md) | **Every new rule**, numbered, next to how the previous model handled it, and where it will be enforced |
| 3 | [`03_data_changes.md`](03_data_changes.md) | The changes made to the data files, why, and a capacity check |
| 4 | [`04_open_questions.md`](04_open_questions.md) | Gaps and contradictions to confirm before or during roster generation |

Source material, unchanged: `data/optiflux_v2/source/` (the four uploaded
CSV files and the three rule notes).

## Progress

| Step | Status | Where |
|---|---|---|
| Compare uploaded tables with the repo | Done | `01_data_comparison.md` |
| Structure the new rules against the previous model | Done | `02_rules_vs_previous_model.md` |
| Apply every rule that can be applied to the data | Done | `data/optiflux_v2/`, `scripts/build_optiflux_v2_data.py`, `03_data_changes.md` |
| Automated checks on the new data | Done | `tests/test_optiflux_v2_data.py` |
| Confirm open questions | **Pending** | `04_open_questions.md` |
| Generate the initial roster (greedy/random, no leave) | **Next step**, not started | — |
| Remove ~10 % of the roster and reassign Relief/Excess to the gaps | Later | likely reuses the existing CP-SAT recovery model |
| "No activity" rows for overtime | Deferred by request | — |

## Main shifts in understanding

1. **Two phases, not one.** Phase 1 builds an initial roster from demand.
   Phase 2 removes about 10 % of it and refills the gaps with Relief and
   Excess crew. The existing solver already does phase 2; phase 1 is new.
2. **Relief and Excess are roster states, not crew types.** Crew are now
   classified as **Residential** or **FIFO**. *Excess* means a person
   assigned to an activity beyond its demand; *Relief* means a spare person
   not on any activity (activity name and head both `Relief`).
3. **Demand is given per start hour.** Each demand row is a start time; every
   shift lasts 12 hours. The main lines need a crew start every hour.
4. **Scale.** 1,000 crew at three depots (Haskett, Yarmouth, Nelaway) against
   171 crew-shifts a day. Madison and Bethway are no longer crew depots; their
   activities start at Haskett.
5. **FIFO travel.** FIFO crew need a travel-in before the first shift and a
   travel-out after the last shift of each swing (random for now).
