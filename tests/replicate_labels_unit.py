"""Replicate labels: non-integer codes are numbered, a blank cell is a named refusal.

  1. integer-like labels keep their number; codes are numbered 1..n in sorted order;
  2. a blank replicate cell raises a ModuleFailure naming the file, column and rows;
  3. no replicate column: every row is replicate 1.

    uv run python tests/replicate_labels_unit.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import FAILS, check  # noqa: E402

from octomod.connectors.local_files import LocalFilesConnector  # noqa: E402
from octomod.orchestration.run_context import ModuleFailure  # noqa: E402
from octomod.workflow_modules.data.engine import _execute_mappings  # noqa: E402


def _mapping(replicate_column):
    return {
        "mappings": [
            {
                "file": "t.csv",
                "observable_label": "pR_au",
                "time_column": "time_min",
                "value_column": "pR_au",
                "condition_columns": ["dose"],
                "condition_label_template": "dose={dose}",
                "replicate_column": replicate_column,
                "units": "arbitrary",
                "error_type": "replicates",
            }
        ]
    }


def _run(csv: str, replicate_column):
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "data"
        d.mkdir()
        (d / "t.csv").write_text(csv)
        conn = LocalFilesConnector(d)
        return _execute_mappings(_mapping(replicate_column), conn, conn.list_sources())


def test_integer_and_coded_labels() -> None:
    df, prov = _run(
        "dose,time_min,replicate,pR_au\n0.3,0,2,1.0\n0.3,0,1,1.1\n", "replicate"
    )
    check(
        "integer-like labels keep their own number",
        sorted(df["replicate"]) == [1, 2],
        str(list(df["replicate"])),
    )
    df, prov = _run(
        "dose,time_min,donor,pR_au\n0.3,0,BC59,1.0\n0.3,0,BC12,1.1\n0.3,1,BC59,0.9\n",
        "donor",
    )
    check(
        "donor codes are numbered 1..n in sorted order",
        list(df["replicate"]) == [2, 1, 2],
        str(list(df["replicate"])),
    )
    check(
        "the label->id table is recorded beside the provenance",
        prov[0].get("replicate_labels") == {"BC12": 1, "BC59": 2},
        str(prov[0].get("replicate_labels")),
    )


def test_a_blank_cell_is_a_named_refusal() -> None:
    csv = "dose,time_min,donor,pR_au\n0.3,0,BC59,1.0\n0.3,0,,1.1\n0.3,1,BC12,0.9\n"
    try:
        _run(csv, "donor")
        check("a blank replicate cell is refused", False, "no exception")
        return
    except ModuleFailure as e:
        msg = str(e)
        check(
            "the refusal is a ModuleFailure (what the S2 draft loop turns into a re-ask)",
            True,
        )
        check(
            "it names the file, the column and the file row",
            "t.csv" in msg
            and "'donor'" in msg
            and "[3]" in msg
            and "1 of 3 rows" in msg,
            msg[:200],
        )
        check(
            "and says what the agent may do instead of guessing a group",
            "replicate_column to null" in msg and "never guesses" in msg,
        )
    except Exception as e:  # noqa: BLE001
        check(
            "the refusal is a ModuleFailure, not a traceback",
            False,
            f"{type(e).__name__}: {e}",
        )


def test_no_replicate_column() -> None:
    df, _ = _run("dose,time_min,pR_au\n0.3,0,1.0\n0.3,1,0.9\n", None)
    check("no replicate column: every row is replicate 1", set(df["replicate"]) == {1})


def main() -> int:
    test_integer_and_coded_labels()
    test_a_blank_cell_is_a_named_refusal()
    test_no_replicate_column()
    if FAILS:
        print(f"\nREPLICATE LABELS FAILED — {len(FAILS)} check(s):")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print(
        "\nREPLICATE LABELS UNIT OK — codes are numbered, a blank cell is refused "
        "by file, column and row"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
