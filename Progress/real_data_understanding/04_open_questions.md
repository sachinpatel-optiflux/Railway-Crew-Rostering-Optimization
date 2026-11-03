# 4. Open questions

Each question lists the assumption the data and roster use now. All of them
can be changed in `scripts/build_optiflux_v2_data.py` (data, settings) or
`scripts/roster_making.py` (crew pools); then rerun the scripts.

## Settled

| # | Question | Decision |
|---|---|---|
| Q7 | Activities have no `CRT Activity ID`. What should the roster reference? | `Activity ID`, directly |
| — | `CM Id` vs `User Id` | `User Id` only (mentor's instruction). `CM Id` is not used in v2 |
| Q10 | How is Excess shown in the roster? | `Assignment Type = Excess` on the row |
| Q5 | How is FIFO travel stored? | Two roster rows per swing, `Travel In` / `Travel Out`; random gap of 1–4 h, duration 2–6 h |
| Q11 | Planning horizon? | 1–28 Nov 2026 (one full FIFO cycle). Set in `constraints_df` |
| Q12 | Work Train ends at Yarmouth with no return duty | The driver comes back the next night on Yarmouth Mainline 22:00, as Excess |

## Still open

| # | Question | Current assumption |
|---|---|---|
| Q1 | The rules do not mention **Haskett Mainline CO**, **Yarmouth Mainline CO** or **Work Train CO**. Do they still have demand? | CO demand kept from the old table (A02 17:00 ×1; A04 05:00 and 17:00 ×1). Work Train CO has no demand |
| Q2 | **NE Ship, NE Crew** (and the Madison, Bethway and BY activities) start at **Haskett** in the uploaded activities. "NE" was Nelaway before. Correct? | Haskett, as uploaded. Haskett carries 105 of the 171 daily shifts |
| Q3 | Do the **swing patterns** apply: FIFO 14 on / 14 off, Residential 6 on / 6 off? | Yes (briefing). Inside a swing: half day shifts, then half night shifts |
| Q4 | What counts as a **day shift** for "Residential first shift is a day shift"? | Starts between 03:00 and 14:59 (previous model's window) |
| Q6 | **Role, Eligibility, Is Mentor, Medical** were blank. | Role and Eligibility are set from the roster; Is Mentor = No; Medical = Fit. Work Train's `Mentor Required = Yes` is not used yet |
| Q8 | `TEA Required` and `Can Be Moved` are blank. Meaning? | Not used. Locking comes from `Is Locked` on the roster row |
| Q9 | Does the 12 h length apply to every activity? | Yes |
| Q13 | Bethway Join is every 3 h "starting at 04:00": 04, 07, …, 22, 01? | Yes (8 per day) |
| Q14 | **1,000 crew is far more than needed.** Covering the demand needs 346 people; 586 end up as Relief (about 293 on standby a day). Keep 1,000, or reduce? | Keep 1,000, as the rules say |
| Q15 | All teams change over on the same days, so FIFO travel is bunched (e.g. many arrivals on 1 and 8 Nov). Should teams be staggered? | Not staggered, so the patterns stay easy to read |
| Q16 | Should Relief crew have a fixed standby time, or be "on call" for the whole day? | Fixed 12 h standby shifts, spread over all day starts, in the same day/night pattern |
