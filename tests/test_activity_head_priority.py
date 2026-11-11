import sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "CP-SAT"))

from solver import solve  # noqa: E402
from utils.activity_head_priority import PRIORITY_WEIGHTS, load_activity_head_priorities  # noqa: E402
from utils.load_options import load_options  # noqa: E402

from option_generation.data import DEFAULT_DATA_DIR, read_csv  # noqa: E402
from option_generation.options import Costs, Option  # noqa: E402
from option_generation.rules import Rules  # noqa: E402


def write_priority_inputs(tmp_path: Path, demand_heads: str, priorities: str) -> tuple[Path, Path]:
    demand = tmp_path / "activity_demand_df.csv"
    priority = tmp_path / "activity_head_priority.csv"
    demand.write_text(f"Activity Head\n{demand_heads}", encoding="utf-8")
    priority.write_text(f"Activity Head,Priority\n{priorities}", encoding="utf-8")
    return demand, priority


def test_activity_head_priorities_load_for_every_demand_head(tmp_path: Path):
    demand, priority = write_priority_inputs(tmp_path, "High\nLow\n", "High,1\nLow,2\n")

    assert load_activity_head_priorities(demand, priority) == {"High": 1, "Low": 2}


def test_default_priority_config_covers_every_project_demand_head():
    priorities = load_activity_head_priorities(DEFAULT_DATA_DIR / "activity_demand_df.csv")

    assert len(priorities) == 14


def test_priority_weights_are_configured_centrally():
    assert PRIORITY_WEIGHTS == {priority: 15 - priority for priority in range(1, 15)}


def test_load_options_applies_configured_head_priorities(tmp_path: Path):
    (tmp_path / "seats.csv").write_text(
        "Seat Key,Date,Start,Activity ID,Activity Head,Demand,Fixed Occupants,Priority,Chain Level,Gap Assignment IDs\n"
        "high,2026-11-01,06:00,A1,High,1,0,99,0,\n"
        "low,2026-11-01,06:00,A2,Low,1,0,1,0,\n",
        encoding="utf-8",
    )
    (tmp_path / "swings.csv").write_text(
        "Swing Key,User Id,Home Depot,Classification,Earliest Start,Latest End,In Model,Rows,Droppable Rows,Status\n",
        encoding="utf-8",
    )
    (tmp_path / "options.csv").write_text(
        "Swing Key,Row Index,Kind,Start,End,Start Location,End Location,Activity ID,Demand ID,Seat Key,"
        "Excess Seat Key,Standby,Row Type,Offset Minutes,Cost,Chain Level,Unchanged\n",
        encoding="utf-8",
    )

    seats, swings = load_options(tmp_path, {"High": 1, "Low": 2})

    assert seats["high"].priority == 1
    assert seats["low"].priority == 2
    assert swings == []


def test_activity_head_priorities_reject_missing_demand_head(tmp_path: Path):
    demand, priority = write_priority_inputs(tmp_path, "High\nLow\n", "High,1\n")

    with pytest.raises(SystemExit, match="missing priorities for demand activity heads: Low"):
        load_activity_head_priorities(demand, priority)


def test_activity_head_priorities_reject_duplicate_entries(tmp_path: Path):
    demand, priority = write_priority_inputs(tmp_path, "High\n", "High,1\nHigh,2\n")

    with pytest.raises(SystemExit, match="duplicate activity-head priority entries: High"):
        load_activity_head_priorities(demand, priority)


@pytest.mark.parametrize("value", ["0", "-1", "15", "urgent", ""])
def test_activity_head_priorities_reject_invalid_values(tmp_path: Path, value: str):
    demand, priority = write_priority_inputs(tmp_path, "High\n", f"High,{value}\n")

    with pytest.raises(SystemExit, match="must be integers from 1 to 14"):
        load_activity_head_priorities(demand, priority)


def test_cp_sat_prefers_higher_priority_head_when_demand_cannot_all_be_filled():
    rules = Rules.from_table(read_csv(DEFAULT_DATA_DIR / "constraints_df.csv"))
    rules = replace(
        rules,
        rest=timedelta(hours=8),
        transition_rest=timedelta(hours=8),
        day_from=6 * 60,
        day_to=18 * 60,
    )
    start = datetime(2026, 11, 1, 6)
    high = Option(
        0, "fill", start, start + timedelta(hours=8), "A", "A", "high",
        seat="high-seat",
    )
    low = Option(
        0, "fill", start, start + timedelta(hours=8), "A", "A", "low",
        seat="low-seat",
    )
    swing = SimpleNamespace(
        key="U1|priority",
        user="U1",
        home="A",
        classification="FIFO",
        earliest_start=None,
        latest_end=None,
        row_ids=["R1"],
        droppable=[False],
        options=[[high, low]],
    )
    seats = {
        "high-seat": SimpleNamespace(capacity=1, priority=1),
        "low-seat": SimpleNamespace(capacity=1, priority=2),
    }

    result = solve(rules, seats, [swing], Costs(), 5, 1, 0)

    assert result.chosen[swing.key][0] == high
    assert result.places_filled == 1


def test_cp_sat_uses_weight_sum_not_lexicographic_priority():
    rules = Rules.from_table(read_csv(DEFAULT_DATA_DIR / "constraints_df.csv"))
    rules = replace(
        rules,
        rest=timedelta(0),
        transition_rest=timedelta(0),
        day_from=6 * 60,
        day_to=18 * 60,
        max_change_minutes=600,
    )
    first_day = datetime(2026, 11, 1, 6)
    second_day = datetime(2026, 11, 2, 10)
    high = Option(
        0, "fill", first_day, second_day + timedelta(hours=2), "A", "A", "high",
        seat="high-seat",
    )
    low_first = Option(
        0, "fill", first_day, first_day + timedelta(hours=2), "A", "A", "low-first",
        seat="low-first-seat",
    )
    low_second = Option(
        1, "fill", second_day, second_day + timedelta(hours=2), "A", "A", "low-second",
        seat="low-second-seat",
    )
    swing = SimpleNamespace(
        key="U1|weighted-priority",
        user="U1",
        home="A",
        classification="FIFO",
        earliest_start=None,
        latest_end=None,
        row_ids=["R1", "R2"],
        droppable=[False, True],
        options=[[high, low_first], [low_second]],
    )
    seats = {
        "high-seat": SimpleNamespace(capacity=1, priority=1),
        "low-first-seat": SimpleNamespace(capacity=1, priority=2),
        "low-second-seat": SimpleNamespace(capacity=1, priority=2),
    }

    result = solve(rules, seats, [swing], Costs(), 5, 1, 0)

    assert result.chosen[swing.key] == [low_first, low_second]
    assert result.places_filled == 2


@pytest.mark.parametrize(("capacity", "expected_filled"), [(1, 1), (2, 2)])
def test_cp_sat_counts_demand_positions_up_to_seat_capacity(capacity: int, expected_filled: int):
    rules = Rules.from_table(read_csv(DEFAULT_DATA_DIR / "constraints_df.csv"))
    rules = replace(
        rules,
        rest=timedelta(hours=8),
        transition_rest=timedelta(hours=8),
        day_from=6 * 60,
        day_to=18 * 60,
    )
    first_start = datetime(2026, 11, 1, 6)
    second_start = datetime(2026, 11, 2, 6)
    first_option = Option(
        0, "fill", first_start, first_start + timedelta(hours=8), "A", "A", "demand",
        seat="shared-seat",
    )
    second_option = Option(
        1, "fill", second_start, second_start + timedelta(hours=8), "A", "A", "demand",
        seat="shared-seat",
    )
    swing = SimpleNamespace(
        key="U1|capacity",
        user="U1",
        home="A",
        classification="FIFO",
        earliest_start=None,
        latest_end=None,
        row_ids=["R1", "R2"],
        droppable=[True, True],
        options=[[first_option], [second_option]],
    )
    seats = {"shared-seat": SimpleNamespace(capacity=capacity, priority=1)}

    result = solve(rules, seats, [swing], Costs(), 5, 1, 0)

    assert result.places_filled == expected_filled
    assert sum(selected is not None for selected in result.chosen[swing.key]) == expected_filled
