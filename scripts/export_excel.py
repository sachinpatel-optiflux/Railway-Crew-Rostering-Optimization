#!/usr/bin/env python3
"""Put CSV files into one Excel workbook, one sheet per file (gap_filling_rules.md R6).

The CSV files are only read, never changed or removed: the workbook is an extra copy for people who
want everything in one place. Values are written as text, so dates and ids look exactly as in the CSVs.
Columns are sized to their content, so Excel shows dates in full rather than as ########.

    python scripts/export_excel.py                                  # data/optiflux_v2 -> optiflux_v2.xlsx
    python scripts/export_excel.py --dirs data/optiflux_v2 gap_generation/output CP-SAT/outputs/roster_full \
        --output outputs/optiflux_full.xlsx
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data" / "optiflux_v2"
MAX_SHEET_NAME = 31  # Excel limit
MAX_WIDTH = 60


def sheet_name(path: Path, used: set[str], prefix: str = "") -> str:
    base = (f"{prefix}.{path.stem}" if prefix else path.stem)[:MAX_SHEET_NAME]
    name, n = base, 2
    while name.lower() in used:
        suffix = f"_{n}"
        name = base[: MAX_SHEET_NAME - len(suffix)] + suffix
        n += 1
    used.add(name.lower())
    return name


def export(csv_files: list[Path], output: Path, prefixes: dict[Path, str] | None = None) -> list[tuple[str, Path, int]]:
    """One sheet per CSV. `prefixes` (folder -> short label) names sheets whose file name repeats across folders."""
    wb = Workbook(write_only=True)
    used: set[str] = set()
    stems = [f.stem for f in csv_files]
    written = []
    bold = Font(bold=True)
    for path in csv_files:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh))
        prefix = (prefixes or {}).get(path.parent, path.parent.name) if stems.count(path.stem) > 1 else ""
        name = sheet_name(path, used, prefix)
        ws = wb.create_sheet(name)
        widths: list[int] = []
        for row in rows[:2000]:  # sample enough rows to size the columns
            for i, value in enumerate(row):
                if i >= len(widths):
                    widths.append(0)
                widths[i] = max(widths[i], len(value))
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = min(MAX_WIDTH, w + 2)
        ws.freeze_panes = "A2"
        for n, row in enumerate(rows):
            if n == 0:
                header = []
                for value in row:
                    cell = WriteOnlyCell(ws, value=value)
                    cell.font = bold
                    header.append(cell)
                ws.append(header)
            else:
                ws.append(row)
        written.append((name, path, max(0, len(rows) - 1)))
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    return written


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dirs", type=Path, nargs="+", default=[DEFAULT_DIR], help="folders whose *.csv files to include")
    p.add_argument("--output", type=Path, help="workbook to write (default: <first folder>/<its name>.xlsx)")
    args = p.parse_args(argv)
    files = [f for d in args.dirs for f in sorted(d.glob("*.csv"))]
    if not files:
        raise SystemExit(f"no CSV files in {', '.join(map(str, args.dirs))}")
    output = args.output or args.dirs[0] / f"{args.dirs[0].name}.xlsx"
    for name, path, n in export(files, output):
        print(f"  {name:31s} {n:>7,} rows  <- {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
