"""A spreadsheet in data/ is named, not silently skipped.

  1. a lone workbook is named, and still not read;
  2. a workbook beside a csv is named, so a partial run cannot happen quietly;
  3. every spreadsheet flavour (xlsx, xlsm, xls, ods) counts;
  4. notes, dotfiles and scripts are still skipped silently;
  5. a missing directory returns [], leaving the real error to S2.

    uv run python tests/data_dir_guard_unit.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.connectors.local_files import (  # noqa: E402
    LocalFilesConnector,
    unreadable_spreadsheets,
)

CSV = "dose,time_min,replicate,pR_au\n0.3,0,1,1.0\n"


def _dir(names: dict[str, str]) -> Path:
    d = Path(tempfile.mkdtemp())
    for name, text in names.items():
        (d / name).write_text(text)
    return d


def test_a_lone_workbook_is_named() -> None:
    d = _dir({"measurements.xlsx": "not really a workbook"})
    assert unreadable_spreadsheets(d) == ["measurements.xlsx"]
    assert LocalFilesConnector(d).list_sources() == []
    print("  lone workbook   named, and still not read")


def test_a_workbook_beside_a_csv_is_named() -> None:
    """A workbook beside a csv is named, so a partial run cannot happen quietly."""
    d = _dir({"measurements.xlsx": "x", "timecourse.csv": CSV})
    assert unreadable_spreadsheets(d) == ["measurements.xlsx"]
    assert [r.meta["filename"] for r in LocalFilesConnector(d).list_sources()] == [
        "timecourse.csv"
    ]
    print("  workbook + csv  named, so the partial run cannot happen quietly")


def test_every_spreadsheet_flavour_counts() -> None:
    d = _dir({f"b.{s}": "x" for s in ("xlsx", "xlsm", "xls", "ods")})
    assert unreadable_spreadsheets(d) == ["b.ods", "b.xls", "b.xlsm", "b.xlsx"]
    print("  xlsx/xlsm/xls/ods  all named")


def test_it_stays_quiet_about_everything_else() -> None:
    """Not a blocklist of 'not csv' — a stray note must not stop a run."""
    d = _dir({"README.md": "notes", ".DS_Store": "", "make_data.py": "", "t.csv": CSV})
    assert unreadable_spreadsheets(d) == []
    assert [r.meta["filename"] for r in LocalFilesConnector(d).list_sources()] == [
        "t.csv"
    ]
    print("  notes/dotfiles  still skipped silently, as before")


def test_a_missing_directory_does_not_raise() -> None:
    assert unreadable_spreadsheets(Path(tempfile.mkdtemp()) / "nope") == []
    print("  missing dir     returns [], leaving the real error to S2")


if __name__ == "__main__":
    test_a_lone_workbook_is_named()
    test_a_workbook_beside_a_csv_is_named()
    test_every_spreadsheet_flavour_counts()
    test_it_stays_quiet_about_everything_else()
    test_a_missing_directory_does_not_raise()
    print(
        "DATA DIR GUARD OK — a workbook in data/ is named in the error, "
        "whether or not a csv sits next to it"
    )
