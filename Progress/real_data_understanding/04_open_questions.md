# 4. Open questions

Each question names the assumption currently used in `data/optiflux_v2/` or
planned for the roster generator. All can be changed in
`scripts/build_optiflux_v2_data.py` and rebuilt.

| # | Question | Current assumption |
|---|---|---|
| Q1 | The demand rules do not mention **Haskett Mainline CO**, **Yarmouth Mainline CO** or **Work Train CO**. Do they still have demand? | CO demand kept from the old table (A02 17:00 ×1, A04 05:00 and 17:00 ×1); Work Train CO has no demand, as before. |
| Q2 | **NE Ship** and **NE Crew** (and Madison, Bethway, BY activities) start at **Haskett** in the uploaded activities. "NE" was Nelaway before. Is Haskett correct? Nelaway has 300 crew but only 32 shifts a day. | Haskett, as uploaded. |
| Q3 | Do the **swing patterns** still apply: FIFO 14 on / 14 off, Residential 6 on / 6 off? | Yes, carried over from the briefing. |
| Q4 | What counts as a **day shift** for "Residential first shift is a day shift"? | Start between 03:00 and 15:00 (previous model's window). |
| Q5 | How should **travel_in / travel_out** be stored, and how far before/after the shift? | Proposal: two roster rows per FIFO swing (`Travel In`, `Travel Out`); random gap of a few hours before the first and after the last shift. |
| Q6 | **Role**, **Eligibility**, **Is Mentor** and **Medical** are blank for all crew. Activities need Driver / Conductor / Shunter roles and Work Train needs a mentor. How are these filled? | Blank. Until filled, the generator ignores role, mentor and medical checks. |
| Q7 | Activities have no `CRT Activity ID`. Should the new roster reference `Activity ID` directly? | Yes. |
| Q8 | `TEA Required` and `Can Be Moved` are blank. Meaning? | Not used for the initial roster. Blank `Can Be Moved` must not be read as "No" (current loader does). |
| Q9 | Does the **12 h** shift length apply to every activity, including Work Train, Fuel Train and CO activities? | Yes. |
| Q10 | "Excess" in the roster: should a surplus assignment be its own row status (e.g. a column `Assignment Status` = Demand / Excess / Relief)? | Planned as a status on the roster row. |
| Q11 | Which **planning horizon** should the initial roster cover (start date, number of days)? It must be at least one full FIFO cycle (28 days) for the swings to show. | To decide. |
| Q12 | Work Train runs Haskett → Yarmouth with no return duty. Is the crew expected to travel back, or end at Yarmouth? | To decide (affects location continuity). |
| Q13 | Bethway Join demand is every 3 h "starting at 04:00"; read as 04, 07, …, 22, 01 (8 per day). Correct? | Yes. |
