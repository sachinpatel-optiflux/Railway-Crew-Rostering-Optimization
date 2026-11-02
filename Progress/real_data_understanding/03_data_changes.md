# 3. Changes made to the data

New folder: `data/optiflux_v2/`. Existing data (`data/generated/`,
`data/sample/`) and the tests built on it are unchanged.

| File | Content |
|---|---|
| `source/*.csv` | The four uploaded tables, unchanged (line endings normalised) |
| `source/rules/*.txt` | The three rule notes, unchanged |
| `activities_df.csv` | Built: 18 activities |
| `activity_demand_df.csv` | Built: 150 rows, 171 crew-shifts per day |
| `crew_master_data_df.csv` | Built: 1,000 crew |
| `roster_df.csv` | **Header only**: the roster is generated in the next step |

All four built files come from one deterministic script:

```bash
python scripts/build_optiflux_v2_data.py
```

`tests/test_optiflux_v2_data.py` rebuilds them and fails if the committed files
differ, and checks each rule (counts, start times, renames, unique IDs).

## `activities_df.csv`

| Change | Rule | Why |
|---|---|---|
| A16 `NE Task` → `NE Crew` (name and head) | D3 | demand_changes.txt |
| A12 `BY Shed` → `BY Ship` (name and head) | D4 | demand_changes.txt |
| `Work Train CO` ID A08 → **A17** | — | The upload gave it the same ID as Work Train. Activity ID is a key, so it got the next free ID. A17 was Route Learning in the old data, which the upload removed. |
| Added A90 `Relief` (Group Reserve, Head `Relief`, Type `Relief`) | G6 | Relief rows need an activity with name and head `Relief` |
| Everything else | — | As uploaded: no `CRT Activity ID` or `Location` column; `TEA Required` and `Can Be Moved` blank; depots and groups as supplied |

No `Excess` activity was added: Excess means extra people on a real activity
(G5), so it is a property of the roster row, not an activity.

## `activity_demand_df.csv`

Rebuilt from the rules in section D of `02_rules_vs_previous_model.md`:
one row per (activity, start time), `Shift` = start time `HH:MM`, all rows
active, Demand IDs DM001–DM150 in activity then time order. Shift length is
12 h for every row and is not stored.

Kept from the uploaded demand table, because the rules do not mention them:
A02 Haskett Mainline CO (17:00 ×1) and A04 Yarmouth Mainline CO (05:00 ×1,
17:00 ×1). Dropped: DM026 Route Learning (activity no longer exists) and DM027
BY Shed 17–05 (was inactive and is replaced by the BY Ship rule).

## `crew_master_data_df.csv`

| User Ids | Depot | Classification | Count |
|---|---|---|---|
| U100001–U100300 | Haskett | Residential | 300 |
| U100301–U100400 | Haskett | FIFO | 100 |
| U100401–U100700 | Yarmouth | FIFO | 300 |
| U100701–U100900 | Nelaway | Residential | 200 |
| U100901–U101000 | Nelaway | FIFO | 100 |

Columns are those of the upload (`User Id, Classification, Eligibility, Depot,
Role, Is Mentor, Medical, Position`). `Eligibility`, `Role`, `Is Mentor`,
`Medical` and `Position` stay **blank**, as uploaded: the rules give no values
(Q6). The 74 old users are replaced; the old User Ids now point to new people.

## Capacity check

At most one 12 h shift per person per day (12 h + 11 h rest = 23 h). Demand
by the depot where the duty starts:

| Depot | Crew | Demand per day | Crew needed per day if half are on swing | Spare per day |
|---|---|---|---|---|
| Haskett | 400 | 105 | ≈200 working | ≈95 |
| Yarmouth | 300 | 34 | ≈150 working | ≈116 |
| Nelaway | 300 | 32 | ≈150 working | ≈118 |
| **Total** | **1,000** | **171** | **≈500 working** | **≈329** |

"Half on swing" assumes the briefing's 14/14 and 6/6 patterns. With those
patterns there is ample crew in total: about 330 people a day would be Relief
or Excess. The spare is concentrated at Yarmouth and Nelaway, while Haskett
carries 105 of the 171 daily shifts, including NE Ship and NE Crew, which the
upload places at Haskett (Q2).

The main lines move crew between depots: Haskett Mainline runs Haskett →
Yarmouth and Yarmouth Mainline runs Yarmouth → Haskett, 24 starts a day each,
so the flows balance over a day. Work Train ends at Yarmouth with no matching
return demand.
