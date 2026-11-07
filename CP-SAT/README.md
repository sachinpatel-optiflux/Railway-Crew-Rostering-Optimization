# CP-SAT: fill the roster gaps with Excess and Relief crew

This folder is the recovery step (rule G10). It takes the reduced crew list from
`gap_generation/`, finds the Demand seats nobody is on, and uses OR-Tools CP-SAT to move Excess and
Relief crew onto them.

## How to run

Run from the repository root, after `pip install -r requirements.txt`.

```bash
python CP-SAT/run_gap_filling.py
python CP-SAT/run_gap_filling.py --crew gap_generation/gaps_10/crew_with_gaps.csv
```

| Option | Default | Meaning |
|---|---|---|
| `--crew` | `gap_generation/crew_with_gaps.csv` | Reduced crew list. Anyone missing from it counts as removed |
| `--data-dir` | `data/optiflux_v2` | The other tables. Only read, never changed |
| `--output-dir` | `CP-SAT/outputs/<crew file name>` | Where results go. A rerun overwrites them |
| `--time-limit` | `300` | Seconds per stage. The run stops early once a stage is proven optimal |
| `--workers` | `8` | CP-SAT threads |
| `--allow-stand-down` | off | Let the solver remove standby or Excess rows. See the assumptions below |
| `--no-return-rides` | off | Turn off trips across the line as Excess |
| `--log` | off | Print the CP-SAT search log |

With several workers, two runs can give different assignments of equal cost.

## Files

| File | Purpose |
|---|---|
| `run_gap_filling.py` | Command line entry point |
| `solver.py` | The CP-SAT model, the two solve stages and the stage 2 costs (`Costs`) |
| `utils/data.py` | Loads the tables |
| `utils/rules.py` | Reads `constraints_df.csv`; the rest, location and day/night check between two shifts |
| `utils/gaps.py` | Finds the open seats |
| `utils/options.py` | Eligibility, swings, and the legal replacements for each row |
| `utils/output.py` | Builds the recovered roster and the report files |
| `utils/validate.py` | Runs `scripts/check_roster.py` on the result, plus checks R1-R4 |
| `outputs/` | Results. Ignored by git (the `outputs/` rule in `.gitignore`) |

## Output files

| File | Content |
|---|---|
| `summary.md` | The headline numbers |
| `recovered_roster_df.csv` | The new roster, in the `roster_df.csv` format. Removed crew are gone |
| `reassignments.csv` | One row per filled seat: who took it, and what they were doing before |
| `return_trips.csv` | Trips across the line as Excess |
| `unfilled_gaps.csv` | Seats still open |
| `stood_down_rows.csv` | Rows removed. Empty unless `--allow-stand-down` is on |
| `validation.md` | Every rule check and its result |

## How the model works

**Gaps.** For each activity, start time and horizon day, a gap is demand minus the Demand rows of the
remaining crew. Excess and Relief rows of removed crew are not gaps (rule G7).

**Decisions.** Each unlocked Excess or Relief row inside the horizon can stay as it is, or be replaced
by a gap. Everything else is fixed: Demand rows, travel rows and rows outside the horizon. Every
replacement uses one existing row, so swing lengths never grow and nobody is called in on a day off.

| Row type | Which gaps it can take |
|---|---|
| Relief | Any start time on the same date (`Relief Allowed Start Offsets = ANY`) |
| Excess | Start time changed by -60, 0 or +60 minutes (`Excess Allowed Start Offsets`) |

**Hard rules.** A person is a candidate only if eligibility, role, medical, competencies and currency
all pass. Each swing that could help gets one `AddCircuit`, and a path through it is the sequence of
shifts the person works. That enforces, on consecutive shifts:

- 11 h rest, 23 h on a day/night switch, and one shift per day
- starting each shift where the last one ended
- starting and ending the swing at home
- a Residential swing starting on a day shift (R1)
- staying between Travel In and Travel Out, and keeping the full off days between swings

An Excess row can only stay on a slot that is fully covered (G5).

**Two stages.**

1. Fill as many seats as possible. Activity priority only breaks ties.
2. Keep that number of seats and change the roster as little as possible.

Stage 2 prefers, in order: an Excess person already on that slot, then the Relief person with the
closest standby time, then moving an Excess person. The penalties are in `Costs` in `solver.py`.

## Assumptions to confirm

- **Trips across the line as Excess.** Work Train ends at Yarmouth and has no return duty, so a
  replacement can ride Yarmouth Mainline 22:00 as Excess, as the initial roster does (Q12). Crew based
  at Yarmouth can also use this seat to reach Haskett first. It is the only seat allowed, and only on
  a slot that is already full. Without these trips, the 14 Work Train seats stay open.
- **Residential crew on mainline work.** The initial roster uses FIFO crew for the mainlines, but
  `Eligibility` also lists Residential drivers at Haskett, so the solver may use them.
- **Standby rows stay.** By default nobody loses a standby row. `--allow-stand-down` gives a much
  larger model that did not reach the optimum in 5 minutes, and it was not needed for full coverage.
- **Mentors are not enforced.** Work Train has `Mentor Required = Yes`, but nobody is a mentor yet (Q6).
- **Rows outside the horizon are not refilled.** Removed crew also leave Demand rows before 1 Nov and
  after 28 Nov. Those seats are not gaps here, and they are not in the recovered roster.

## The expected rule failure

`scripts/check_roster.py` always fails M1-M4, because removing people puts the crew counts below the
targets. `validation.md` marks it as expected. If seats stay open, G1 fails too and is marked the same
way. The run exits with an error for any other failure.
