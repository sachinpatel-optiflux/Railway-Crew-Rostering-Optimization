# gap_generation: make some crew unavailable

This folder creates a test scenario for the recovery step: a chosen percentage
of crew becomes unavailable, which leaves gaps in the roster.

The script picks those people at random and writes a reduced copy of the crew
list. **The original `data/optiflux_v2/crew_master_data_df.csv` is only read,
never changed.**

## How to run

Run from the repository root. Only standard Python is needed, no extra packages.

```bash
python gap_generation/make_gaps.py --percent 5     # remove 5% of crew
python gap_generation/make_gaps.py --percent 10    # remove 10% of crew
```

| Option | Required | Default | Meaning |
|---|---|---|---|
| `--percent` | yes | none | Share of crew to remove, above 0 and below 100. `5`, `7.5` and `5%` all work |
| `--seed` | no | `2026` | Random seed. Change it to get a different group of people |
| `--input` | no | `data/optiflux_v2/crew_master_data_df.csv` | Crew file to read |
| `--output` | no | `gap_generation/crew_with_gaps.csv` | Reduced crew file to write |

## What it creates

| File | Content |
|---|---|
| `crew_with_gaps.csv` | The crew who are still available. Same columns and row order as the original |
| `removed_crew.csv` | The crew who were removed, with the same columns. Always written next to `crew_with_gaps.csv` |

Every run **overwrites** these two files. To keep several scenarios, give each
its own folder:

```bash
python gap_generation/make_gaps.py --percent 5  --output gap_generation/gaps_05/crew_with_gaps.csv
python gap_generation/make_gaps.py --percent 10 --output gap_generation/gaps_10/crew_with_gaps.csv
```

## Example output

```text
$ python gap_generation/make_gaps.py --percent 10
Crew: 1000 -> 900 (100 removed, 10%, seed 2026)
  Depot: Haskett -45/400, Nelaway -31/300, Yarmouth -24/300
  Classification: FIFO -44/500, Residential -56/500
  Role: Conductor -5/60, Driver -88/880, Shunter -7/60
Their shifts in the horizon: 1450 (Demand 414, Excess 85, Relief 879, Travel In 39, Travel Out 33)
```

- `Haskett -45/400` means 45 of the 400 Haskett crew were removed.
- The last line counts the removed people's shifts inside the planning horizon
  (`In Horizon = Yes` in `roster_df.csv`), by `Assignment Type`.
- **Demand** shifts are the real gaps, because each one is a required seat that
  now has nobody on it. Here that is 414 of the 4,788 Demand shifts in the
  horizon.
- This line is only shown when `roster_df.csv` sits next to the input file.

| Percent (seed 2026) | Crew left | Demand shifts left open |
|---|---|---|
| 5% | 950 | 191 |
| 10% | 900 | 414 |

## How the code works

Everything is in `make_gaps.py`, and it runs these steps in order:

1. **Check the inputs.** `parse_percent` rejects anything that isn't a number
   above 0 and below 100. `main` stops if an output path is the same as the
   input, if `User Id` is missing, or if a `User Id` appears twice.
2. **Read the crew file** (`read_csv`). One row is one person.
3. **Work out how many to remove.** `pick_removed` uses
   `round(crew count × percent / 100)`, and always removes at least 1.
   With 1,000 crew, 5% is 50 people.
4. **Pick the people.** `pick_removed` sorts the `User Id`s, shuffles them with
   the seed, and takes that many from the front.
5. **Split the rows.** Each row goes to either the kept list or the removed
   list. Both keep the original row order.
6. **Write the two files** (`write_csv`).
7. **Print the summary** (`print_summary`, `open_shifts`). This step only reads
   data, and changes neither output file.

### Why the selection works this way

- **Everyone has the same chance.** The pick is plain random across all crew,
  so nobody is protected and it doesn't balance depots or roles. A depot can
  lose slightly more than its share: at 5%, Haskett lost 24 and Yarmouth 9. A
  small group, such as a four-person roster line, can also lose several people.
- **Same inputs, same result.** The same percent, seed and input always give
  identical files, so a scenario can be repeated exactly.
- **Bigger percentages add to smaller ones.** With the same seed, everyone in
  the 5% group is also in the 10% group. Comparing 5% with 10% therefore shows
  the effect of more absences, not of a different random group.

## Limits

- **Only the crew list changes.** `roster_df.csv`, `crew_competencies_df.csv`
  and `crew_currency_df.csv` still contain the removed people. Use
  `removed_crew.csv` to find their rows.
- **The solver can't use this output yet.** `load_instance` can't read the
  `optiflux_v2` format (see `data/optiflux_v2/README.md`), and it also expects
  the file name `crew_master_data_df.csv`, not `crew_with_gaps.csv`.
- **Absence covers the whole period.** A removed person is gone for all of it,
  not for a few days.
