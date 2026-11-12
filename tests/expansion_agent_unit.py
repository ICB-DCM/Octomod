"""Candidates as declared differences from one tested base.

  1. every candidate carries the base's FULL parameter list, with its declared changes;
  2. a switch changes the table AND the model's value line, even on a shared line;
  3. an unknown parameter, reaction or undeclared symbol is refused, candidate named;
  4. two candidates that come out identical are a problem of the set;
  5. the card's difference lines are exactly what was declared.

    uv run python tests/expansion_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.workflow_modules.model import expansion as V  # noqa: E402

BASE = {
    "antimony": (
        "model base\n"
        "  compartment cell; cell = 1;\n"
        "  species S in cell, P in cell;\n"
        "  S = 10; P = 0;\n"
        "  Q := 1 + comp*w*S;\n"
        "  Jp: S -> P; cell*k*S/Q;\n"
        "  Jd: P -> S; cell*kd*f*P;\n"
        "  k = 0.1; kd = 0.05;\n"
        "  w = 0.01; comp = 0; f = 1;\n"
        "end\n"
    ),
    "parameters": [
        {"id": "k", "nominal_value": 0.1, "estimate": True, "lb": 1e-3, "ub": 10},
        {"id": "kd", "nominal_value": 0.05, "estimate": True, "lb": 1e-3, "ub": 1},
        {"id": "w", "nominal_value": 0.01, "estimate": True, "lb": 1e-4, "ub": 1},
        {"id": "comp", "nominal_value": 0, "estimate": False, "lb": 0, "ub": 1},
        {"id": "f", "nominal_value": 1, "estimate": False, "lb": 0.02, "ub": 50},
    ],
}


def test_every_candidate_carries_the_full_parameter_list():
    cands, problems = V.materialize_all(
        BASE,
        [
            {"id": "M1_base"},
            {"id": "M3_comp", "set_parameters": [{"id": "comp", "nominal_value": 1}]},
            {"id": "M2_f", "set_parameters": [{"id": "f", "estimate": True}]},
        ],
    )
    assert not problems, problems
    base_ids = [p["id"] for p in BASE["parameters"]]
    for c in cands:
        assert [
            p["id"] for p in c["parameters"]
        ] == base_ids, (
            f"{c['id']} lost base parameters: {[p['id'] for p in c['parameters']]}"
        )
    m2 = next(c for c in cands if c["id"] == "M2_f")
    f = next(p for p in m2["parameters"] if p["id"] == "f")
    assert f["estimate"] is True and f["lb"] == 0.02 and f["ub"] == 50, f
    # the base object is never mutated by a candidate's changes
    assert next(p for p in BASE["parameters"] if p["id"] == "f")["estimate"] is False
    print(
        f"  full list     {len(cands)} candidates, each with all {len(base_ids)} base parameters"
    )


def test_a_switch_changes_the_table_and_the_model_line():
    (m3,), problems = V.materialize_all(
        BASE, [{"id": "M3", "set_parameters": [{"id": "comp", "nominal_value": 1}]}]
    )
    assert not problems, problems
    assert "comp = 1;" in m3["antimony"], m3["antimony"]
    # the other assignment on the same line is untouched
    assert "w = 0.01; comp = 1; f = 1;" in m3["antimony"], m3["antimony"]
    # and the rule that USES comp is not mistaken for its value line
    assert "Q := 1 + comp*w*S;" in m3["antimony"], m3["antimony"]
    comp = next(p for p in m3["parameters"] if p["id"] == "comp")
    assert comp["nominal_value"] == 1, comp
    print("  switch        table and model line agree; neighbours and rules untouched")


def test_problems_name_the_candidate_and_the_symbol():
    _, problems = V.materialize_all(
        BASE,
        [
            {"id": "Mx", "set_parameters": [{"id": "kcat", "nominal_value": 1}]},
            {
                "id": "My",
                "on_antimony_patch": {
                    "replace_reaction": "J_nope",
                    "with": "J_nope: S -> P; k*S;",
                },
            },
            {
                "id": "Mz",
                "on_antimony_patch": {
                    "replace_reaction": "Jd",
                    "with": "Jd: P -> S; cell*kd2*P;",
                },
            },
            {"id": "Mw", "set_parameters": [{"id": "k", "varies_by": ["population"]}]},
        ],
    )
    text = "\n".join(problems)
    assert "Mx" in text and "'kcat'" in text and "adds_parameters" in text, text
    assert "My" in text and "J_nope" in text, text
    assert "Mz" in text and "kd2" in text, text
    assert "Mw" in text and "varies_by" in text, text
    # the same patch with its new symbol declared is fine
    (mz,), ok = V.materialize_all(
        BASE,
        [
            {
                "id": "Mz",
                "on_antimony_patch": {
                    "replace_reaction": "Jd",
                    "with": "Jd: P -> S; cell*kd2*P;",
                },
                "adds_parameters": [
                    {
                        "id": "kd2",
                        "nominal_value": 0.1,
                        "estimate": True,
                        "lb": 1e-3,
                        "ub": 1,
                    }
                ],
            }
        ],
    )
    assert not ok, ok
    assert (
        "Jd: P -> S; cell*kd2*P;" in mz["antimony"] and "kd2 = 0.1;" in mz["antimony"]
    )
    assert [p["id"] for p in mz["parameters"]][-1] == "kd2"
    print(
        f"  refusals      {len(problems)} problem(s), each naming candidate and symbol"
    )


def test_identical_candidates_are_a_problem_of_the_set():
    _, problems = V.materialize_all(
        BASE,
        [
            {"id": "A"},
            {"id": "B", "set_parameters": [{"id": "comp", "nominal_value": 0}]},
        ],
    )
    assert any("B is identical to A" in p for p in problems), problems
    print("  identity      a difference that changes nothing is refused")


def test_the_card_lines_are_the_declared_difference():
    cands, problems = V.materialize_all(
        BASE,
        [
            {"id": "M1"},
            {
                "id": "M4",
                "set_parameters": [
                    {"id": "comp", "nominal_value": 1},
                    {"id": "f", "estimate": True, "lb": 0.02, "ub": 50},
                ],
            },
        ],
    )
    assert not problems, problems
    lines = {c["id"]: V.difference_lines(c) for c in cands}
    assert lines["M1"] == ["(the base itself)"], lines
    assert lines["M4"] == ["comp = 1", "f estimated [0.02, 50]"], lines
    print(f"  card          M4: {'; '.join(lines['M4'])}")


if __name__ == "__main__":
    test_every_candidate_carries_the_full_parameter_list()
    test_a_switch_changes_the_table_and_the_model_line()
    test_problems_name_the_candidate_and_the_symbol()
    test_identical_candidates_are_a_problem_of_the_set()
    test_the_card_lines_are_the_declared_difference()
    print("\nVARIATIONS UNIT OK")
