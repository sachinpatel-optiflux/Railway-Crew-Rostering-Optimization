"""Checks on data/optiflux_v2: the committed tables follow the rules and match the build script."""

import csv
import importlib.util
import shutil
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "optiflux_v2"
TABLES = ["activities_df.csv", "activity_demand_df.csv", "crew_master_data_df.csv", "roster_df.csv"]


def _rows(name):
    with (DATA / name).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_v2", ROOT / "scripts" / "build_optiflux_v2_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_committed_tables_match_build_script(tmp_path, monkeypatch):
    shutil.copytree(DATA / "source", tmp_path / "source")
    builder = _load_builder()
    monkeypatch.setattr("sys.argv", ["build", "--data-dir", str(tmp_path)])
    builder.main()
    for name in TABLES:
        assert (tmp_path / name).read_text() == (DATA / name).read_text(), f"{name} is stale: rerun the build script"


def test_activity_ids_unique_and_renamed():
    acts = _rows("activities_df.csv")
    ids = [a["Activity ID"] for a in acts]
    assert len(ids) == len(set(ids))
    names = {a["Activity Name"] for a in acts}
    assert {"NE Crew", "BY Ship", "Relief"} <= names
    assert not {"NE Task", "BY Shed"} & names
    relief = next(a for a in acts if a["Activity ID"] == "A90")
    assert relief["Activity Name"] == relief["Activity Head"] == "Relief"


def test_demand_rules():
    demand = _rows("activity_demand_df.csv")
    acts = {a["Activity ID"] for a in _rows("activities_df.csv")}
    assert all(d["Activity ID"] in acts for d in demand)
    assert all(len(d["Shift"]) == 5 and d["Shift"][2] == ":" for d in demand), "Shift holds the start time only"

    def starts(name):
        return {d["Shift"]: int(d["Demand"]) for d in demand if d["Activity Name"] == name}

    for name in ("Haskett Mainline", "Yarmouth Mainline", "Madison Crew", "Nelaway Driver"):
        assert starts(name) == {f"{h:02d}:00": 1 for h in range(24)}
    assert starts("CAM LOT") == {f"{h:02d}:00": 1 for h in range(0, 24, 3)}
    assert starts("Madison Yard") == {f"{h:02d}:00": 1 for h in range(1, 24, 3)}
    assert starts("Nelaway Shuttle Driver") == {f"{h:02d}:00": 1 for h in range(1, 24, 3)}
    assert starts("Bethway Join/FI Crew") == {f"{h:02d}:00": 1 for h in (1, 4, 7, 10, 13, 16, 19, 22)}
    assert starts("Work Train") == {"22:00": 2}
    assert starts("Fuel Train") == {"10:00": 1}
    assert starts("Fuel Return") == {"10:00": 1}
    assert starts("NE Ship") == starts("BY Ship") == {"04:00": 1, "09:00": 1, "16:00": 1, "21:00": 1}
    ne_crew = starts("NE Crew")
    assert ne_crew == {**{f"{h:02d}:00": 4 for h in (4, 7, 9, 16, 19, 21)}, "00:00": 2, "12:00": 2}
    assert sum(int(d["Demand"]) for d in demand) == 171


@pytest.mark.parametrize(
    "depot, classification, n",
    [("Haskett", "Residential", 300), ("Haskett", "FIFO", 100), ("Yarmouth", "FIFO", 300),
     ("Nelaway", "Residential", 200), ("Nelaway", "FIFO", 100)],
)  # fmt: skip
def test_crew_counts(depot, classification, n):
    crew = _rows("crew_master_data_df.csv")
    assert len(crew) == 1000
    assert len({c["User Id"] for c in crew}) == 1000
    assert Counter((c["Depot"], c["Classification"]) for c in crew)[(depot, classification)] == n
