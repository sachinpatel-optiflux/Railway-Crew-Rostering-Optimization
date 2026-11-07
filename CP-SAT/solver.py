"""CP-SAT model: put Excess and Relief crew on the gaps.

Each swing that could help gets one AddCircuit. A path through the circuit is the sequence of shifts
the person really works, so rest, day/night switches, location, the first-shift rule and return to
base are enforced on consecutive shifts. Rows of everyone else stay as they are.

The solve has two stages. Stage 1 fills as many seats as possible, breaking ties by activity
priority. Stage 2 holds that result and makes the smallest change to the roster.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from utils.gaps import Slot
from utils.options import Option, Swing, can_close, can_open, skippable

SEAT_VALUE = 10_000  # one seat always beats any priority tie-break
LOWEST_PRIORITY = 15


@dataclass(frozen=True)
class Costs:
    """Stage 2 penalties. Lower is preferred."""

    excess_same_slot: int = 0  # an Excess person already on this slot takes the seat
    relief_fill: int = 10  # plus 1 per hour between the standby time and the duty
    excess_moved: int = 20  # plus 1 per hour of start change
    ride: int = 30
    drop_relief: int = 15  # a standby row removed to make room
    drop_excess: int = 25


@dataclass
class Result:
    status: str  # stage 1
    disruption_status: str  # stage 2
    seats_open: int
    seats_filled: int
    bound: float
    disruption: int | None
    disruption_bound: float | None
    seconds: float
    chosen: list[tuple[Swing, list[Option]]] = field(default_factory=list)  # changed swings only


def solve(problem, swings: list[Swing], slots: list[Slot], costs: Costs, allow_drop: bool,
          time_limit: float, workers: int, seed: int, log: bool = False) -> Result:  # fmt: skip
    model = cp_model.CpModel()
    tracked: list = []  # every variable, so stage 1's answer can seed stage 2
    picks: list[tuple[Swing, list[tuple[Option, object]]]] = []
    by_slot: dict[tuple[str, str], list] = {s.key: [] for s in slots}
    disruption: list = []
    rules = problem.rules

    def new_bool(name: str):
        var = model.new_bool_var(name)
        tracked.append(var)
        return var

    for number, swing in enumerate(swings):
        if not any(o.kind != "keep" for options in swing.options for o in options):
            continue
        nodes: list[tuple[Option, object]] = []
        arcs: list[tuple[int, int, object]] = []
        for index, options in enumerate(swing.options):
            literals = []
            droppable = swing.droppable(index, allow_drop)
            for option in options:
                literal = new_bool(f"s{number}_r{index}_{option.kind}{len(nodes)}")
                nodes.append((option, literal))
                literals.append(literal)
                arcs.append((len(nodes), len(nodes), literal.Not()))
                disruption.append((option.cost, literal))
                if option.slot_key:
                    by_slot[option.slot_key].append(literal)
            if droppable:
                dropped = new_bool(f"s{number}_r{index}_drop")
                model.add_exactly_one(literals + [dropped])
                is_relief = swing.rows[index]["Assignment Type"] == "Relief"
                disruption.append((costs.drop_relief if is_relief else costs.drop_excess, dropped))
            else:
                model.add_exactly_one(literals)

        last = len(swing.options)
        for a, (first, _) in enumerate(nodes, start=1):
            if skippable(swing, -1, first.row_index, allow_drop) and can_open(problem, swing, first):
                arcs.append((0, a, new_bool(f"s{number}_open{a}")))
            if skippable(swing, first.row_index, last, allow_drop) and can_close(swing, first):
                arcs.append((a, 0, new_bool(f"s{number}_close{a}")))
            for b, (second, _) in enumerate(nodes, start=1):
                if (
                    first.row_index < second.row_index
                    and skippable(swing, first.row_index, second.row_index, allow_drop)
                    and rules.can_follow(first, second)
                ):
                    arcs.append((a, b, new_bool(f"s{number}_{a}_{b}")))
        model.add_circuit(arcs)
        picks.append((swing, nodes))

    # Seats per slot, and the G5 rule: an Excess row may only stay on a slot that is fully covered.
    filled_terms = []
    for slot in slots:
        taken = by_slot[slot.key]
        model.add(sum(taken) <= slot.seats)
        head = problem.activities[slot.activity_id]["Activity Head"]
        weight = SEAT_VALUE + LOWEST_PRIORITY - problem.priority.get(head, LOWEST_PRIORITY)
        filled_terms += [(weight, t) for t in taken]
    slot_at = {(s.activity_id, s.start): s for s in slots}
    for swing, nodes in picks:
        for option, literal in nodes:
            row = swing.rows[option.row_index]
            slot = slot_at.get((row["Activity ID"], row["_s"]))
            if option.kind == "keep" and row["Assignment Type"] == "Excess" and slot:
                model.add(sum(by_slot[slot.key]) >= slot.seats).only_enforce_if(literal)

    def run(limit: float):
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = limit
        solver.parameters.num_workers = workers
        solver.parameters.random_seed = seed
        solver.parameters.log_search_progress = log
        return solver, solver.solve(model)

    print(f"Model: {len(picks)} swings, {len(tracked)} variables")
    coverage = sum(w * t for w, t in filled_terms)
    model.maximize(coverage)
    stage1, status1 = run(time_limit)
    seats_open = sum(s.seats for s in slots)
    if status1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Result(stage1.status_name(status1), "NOT RUN", seats_open, 0, 0, None, None, stage1.wall_time)
    best = round(stage1.objective_value)
    print(f"Stage 1 ({stage1.status_name(status1)}): {best // SEAT_VALUE} of {seats_open} seats, "
          f"{stage1.wall_time:.1f}s")  # fmt: skip

    model.clear_objective()
    model.clear_hints()
    for var in tracked:
        model.add_hint(var, stage1.value(var))
    model.add(coverage >= best)
    model.minimize(sum(c * v for c, v in disruption))
    stage2, status2 = run(time_limit)
    final, status = (stage2, status2) if status2 in (cp_model.OPTIMAL, cp_model.FEASIBLE) else (stage1, status1)
    print(f"Stage 2 ({stage2.status_name(status2)}): disruption {stage2.objective_value:.0f}, "
          f"{stage2.wall_time:.1f}s")  # fmt: skip

    chosen = []
    for swing, nodes in picks:
        active = [option for option, literal in nodes if final.value(literal)]
        if len(active) != len(swing.rows) or any(o.kind != "keep" for o in active):
            chosen.append((swing, active))
    return Result(
        status=stage1.status_name(status1),
        disruption_status=stage2.status_name(status2),
        seats_open=seats_open,
        seats_filled=best // SEAT_VALUE,
        bound=stage1.best_objective_bound / SEAT_VALUE,
        disruption=round(stage2.objective_value) if final is stage2 else None,
        disruption_bound=stage2.best_objective_bound if final is stage2 else None,
        seconds=stage1.wall_time + stage2.wall_time,
        chosen=chosen,
    )
