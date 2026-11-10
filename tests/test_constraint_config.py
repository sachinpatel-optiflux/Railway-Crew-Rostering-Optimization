from pathlib import Path

from option_generation.data import DEFAULT_DATA_DIR, read_csv
from option_generation.rules import Rules


def test_constraint_switches_load_from_yaml(tmp_path: Path):
    config = tmp_path / "config.yml"
    config.write_text(
        "constraints:\n"
        "  residential_start_restriction: false\n"
        "  relief_only_day_night_transition: false\n",
        encoding="utf-8",
    )

    rules = Rules.from_table(read_csv(DEFAULT_DATA_DIR / "constraints_df.csv"), config)

    assert rules.residential_start_restriction is False
    assert rules.relief_only_day_night_transition is False
