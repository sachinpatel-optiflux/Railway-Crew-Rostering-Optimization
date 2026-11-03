# 6. The data files in plain words

All files are in `data/optiflux_v2/`. Every table that is about a person uses
**`User Id`**. `CM Id` is not used: it was only a second name for the same
person.

Think of three groups: **what work exists**, **who the people are**, and
**the rules and the plan**.

## What work exists

| File | What it tells you | Example |
|---|---|---|
| `activities_df.csv` | The **list of jobs**: where each starts and ends, which roles may do it, whether a mentor is needed, and how recently someone must have done it (currency threshold). Also the non-work entries `Relief`, `Travel In`, `Travel Out` | A01 Haskett Mainline: Driver, Haskett → Yarmouth, done in the last 90 days |
| `activity_demand_df.csv` | **How many people each job needs, at which start time**, every day. Each shift lasts 12 h | Haskett Mainline, 05:00, 1 person |
| `compliance_matrix_df.csv` | **Which qualifications each job needs** | Haskett Mainline needs Safeworking Rules, Route Knowledge Haskett–Yarmouth, ... |
| `activity_priority.csv` | **Which jobs matter most**, 1 = highest. Used to order the roster lines | 1 = Madison Crew |
| `excluded_activities.csv` | Jobs to ignore. Empty | — |

## Who the people are

| File | What it tells you | Example |
|---|---|---|
| `crew_master_data_df.csv` | The **staff list**: home depot, Residential or FIFO, role, which jobs they may do (`Eligibility`), their roster line (`Position`) | U100001, Haskett, Residential, Driver, A06, L001 |
| `crew_competencies_df.csv` | **Each person's qualifications** and when they expire | U100001 holds Yard Operations until 2027-08-07 |
| `crew_currency_df.csv` | **When each person last did a job that has a currency limit** | U100233 last did Haskett Mainline on 2026-09-29 |
| `crew_restrictions.csv` | Leave or bans on certain work. Empty: the first roster has no leave | — |
| `Crew_Onsite_App.csv` | Daily check-ins (present, absent, sick). Empty for now | — |

## The rules and the plan

| File | What it tells you | Example |
|---|---|---|
| `constraints_df.csv` | **Settings**: planning dates, 12 h shifts, 11 h / 23 h rest, day-shift window, swing patterns (FIFO 14/14, Residential 6/6), travel times, Excess share, random seed | Ordinary Rest Hours = 11 |
| `roster_df.csv` | **The schedule**: who works which job, on which day, from when to when, from where to where | U100001 works Madison Crew on 1 Nov, 03:00–15:00 |
| `roster_lines.csv` | *Explanation, not a database table.* The **teams** behind the roster: which people rotate on which job and start times | L001: Madison Crew 03:00/15:00, U100001–U100004 |
| `roster_report.md` | *Generated summary.* Totals and pattern samples | — |
| `roster_checks.md` | *Generated.* Every rule check and its result | 34/34 pass |

## Columns of `roster_df.csv`

| Column | Meaning |
|---|---|
| `Assignment ID` | Row number |
| `User Id` | Who |
| `Start Date`, `Shift Start Time`, `End Date`, `Shift End Time` | When. Night shifts end the next day |
| `Activity ID`, `Activity Name`, `Activity Head`, `Activity Type`, `Activity Group` | Which job (copied from `activities_df`) |
| `Assignment Type` | **Demand**: fills a demand seat. **Excess**: extra person on a job that is already covered. **Relief**: spare, on standby. **Travel In** / **Travel Out**: a FIFO person arriving or leaving |
| `Demand ID` | The demand row being covered (blank for Relief and Travel) |
| `Start Location`, `End Location` | Where the shift starts and ends. Mainline shifts end at the other depot. Travel uses `Off Site` |
| `Is Locked` | `Yes` = keep as is (Demand, Travel). `No` = may be moved in the recovery step (Excess, Relief) |
| `Line ID` | The person's team (`roster_lines.csv`) |
| `Swing` | The person's 1st, 2nd, ... work period |
| `In Horizon` | `Yes` inside 1–28 Nov. `No` = part of a swing that started before or ends after the horizon |

## How they fit together

A person may be put on a shift only if all of these hold:

1. The job needs someone at that time (**demand**).
2. The job is in the person's **Eligibility**, and their **Role** is allowed
   (crew list vs activities).
3. They hold every qualification the job needs, and none has expired
   (**competencies** vs **compliance matrix**).
4. They did the job recently enough (**currency**).
5. They are not on leave or absent (**restrictions**, **check-ins**).
6. They had enough rest, are inside their work days, and start where their
   last shift ended (**constraints**).

`scripts/check_roster.py` checks each of these for every roster row.
