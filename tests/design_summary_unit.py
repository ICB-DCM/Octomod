"""The design summary names what a 25-row data preview cannot show.

  1. the abcd fixture's absent cell (u=0.25, bx11=1) is named in the summary and card;
  2. no measurement value reaches the payload;
  3. a balanced design reports no absent cells;
  4. column roles are guesses, and the payload says so;
  5. row order does not change the summary;
  6. only data_extraction and condition receive it; construction is excluded.

    uv run python tests/design_summary_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.workflow_modules.data import design_summary as ds  # noqa: E402


def test_it_names_the_absent_cell_in_abcd():
    """The 80-row fixture lacks exactly (u=0.25, bx11=1); the cell is named."""
    df = pd.read_csv(REPO / "testcase" / "abcd_blind" / "data" / "synmod4_ms.csv")
    s = ds.compute({"synmod4_ms.csv": df})
    f = s["per_file"]["synmod4_ms.csv"]["factorial"]
    assert f["available"] and not f["balanced"], f
    assert f["n_full_factorial"] == 6 and f["n_present"] == 5, f
    assert f["absent_cells"] == [{"u": 0.25, "bx11": 1}], f["absent_cells"]
    # and it survives into the prompt card, which is what the agent reads
    card = "\n".join(ds.card_lines(s))
    assert "ABSENT: u=0.25, bx11=1" in card, card
    print("  abcd          names the absent cell: u=0.25, bx11=1")


def test_no_measurement_value_is_ever_in_the_payload():
    """No measured number from the file appears in the rendered payload or card."""
    import json

    df = pd.read_csv(REPO / "testcase" / "abcd_blind" / "data" / "synmod4_ms.csv")
    s = ds.compute({"synmod4_ms.csv": df})
    blob = json.dumps(s) + "\n".join(ds.card_lines(s))
    leaked = []
    for col in ("KinA_p_uM", "RegB_p_uM", "ProD_uM"):
        rec = s["per_file"]["synmod4_ms.csv"]["columns"][col]
        assert rec["role"] == "measurement", rec
        assert "levels" not in rec, f"{col} carries its values: {rec}"
        for v in df[col].head(40):
            # 12 significant digits: a full float from the file, not a count
            if f"{v:.12g}" in blob and len(f"{v:.12g}") > 8:
                leaked.append((col, v))
    assert not leaked, f"measurement values reached the payload: {leaked[:3]}"
    print("  no values     measurement columns give dtype and cardinality only")


def test_a_balanced_design_says_so():
    df = pd.DataFrame(
        {
            "dose": [1, 1, 2, 2] * 2,
            "drug": ["a", "b"] * 4,
            "time": [0, 0, 0, 0, 10, 10, 10, 10],
            "y": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
        }
    )
    f = ds.compute({"x.csv": df})["per_file"]["x.csv"]["factorial"]
    assert f["balanced"] and f["n_absent"] == 0 and f["absent_cells"] == [], f
    print("  balanced      a complete factorial reports absent_cells == []")


def test_roles_are_guesses_and_the_payload_says_so():
    """Roles are inferred from name and cardinality and labelled as guesses."""
    df = pd.DataFrame(
        {
            "time_min": [0, 1] * 3,
            "replicate": [1, 2] * 3,
            "u": [1, 1, 2, 2, 3, 3],
            "sig": [0.11, 0.22, 0.33, 0.44, 0.55, 0.66],
        }
    )
    s = ds.compute({"x.csv": df})
    cols = s["per_file"]["x.csv"]["columns"]
    assert cols["time_min"]["role"] == "time", cols["time_min"]
    assert cols["replicate"]["role"] == "replicate", cols["replicate"]
    assert cols["u"]["role"] == "design", cols["u"]
    assert "GUESS" in s["how_to_read_this"], s["how_to_read_this"]
    print("  roles         name+cardinality guess, declared as a guess")


def test_it_is_deterministic():
    df = pd.read_csv(REPO / "testcase" / "abcd_blind" / "data" / "synmod4_ms.csv")
    import json

    a = json.dumps(ds.compute({"f.csv": df}), sort_keys=True)
    b = json.dumps(
        ds.compute({"f.csv": df.sample(frac=1.0, random_state=3)}), sort_keys=True
    )
    assert a == b, "row order changed the design summary"
    print("  determinism   row order does not change the summary")


def test_the_two_granted_roles_and_no_others():
    """Routed to data_extraction and condition; construction is excluded."""
    from octomod.agents import routing

    for role in ("data_extraction", "condition"):
        assert "design_summary" in routing.allowed(role), role
    assert "design_summary" not in routing.allowed("construction")
    assert any(
        "design_summary" in n for n in routing.ROUTING["construction"]["never"]
    ), "construction's exclusion must be recorded, not merely absent"
    print("  routing       granted to 2 roles; construction's absence is stated")


if __name__ == "__main__":
    test_it_names_the_absent_cell_in_abcd()
    test_no_measurement_value_is_ever_in_the_payload()
    test_a_balanced_design_says_so()
    test_roles_are_guesses_and_the_payload_says_so()
    test_it_is_deterministic()
    test_the_two_granted_roles_and_no_others()
    print(
        "DESIGN SUMMARY UNIT OK — the absent cell is named, and no measurement "
        "value is in the payload"
    )
