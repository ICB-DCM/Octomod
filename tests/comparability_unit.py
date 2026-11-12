"""Likelihoods over differently transformed data are corrected before AIC compares them.

  1. each observable's transformation is read from the table; an absent one is lin;
  2. the change-of-variables correction is SUM log y, with the log10 base term;
  3. a non-positive measurement is counted as unusable, not dropped;
  4. a shared transformation is detected and each disagreement is named;
  5. the gate refuses an uncorrected comparison and passes a corrected or shared one;
  6. the correction runs before the criterion arithmetic, so a reversed ranking holds.

    uv run python tests/comparability_unit.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.workflow_modules.evaluation.selection import (  # noqa: E402
    comparable,
    jacobian_correction,
    transformations,
)


def _obs(kind: str) -> pd.DataFrame:
    return pd.DataFrame({"observableId": ["o1"], "observableTransformation": [kind]})


MEAS = pd.DataFrame(
    {"observableId": ["o1"] * 4, "measurement": [1.0, 10.0, 100.0, 0.5]}
)


def test_transformations_default_to_lin() -> None:
    assert transformations(_obs("log10")) == {"o1": "log10"}
    assert transformations(_obs("LOG")) == {"o1": "log"}, "case-insensitive"
    bare = pd.DataFrame({"observableId": ["o1", "o2"]})
    assert transformations(bare) == {
        "o1": "lin",
        "o2": "lin",
    }, "an absent column means lin, not a crash"
    assert transformations(_obs("")) == {"o1": "lin"}


def test_the_change_of_variables_term_is_the_textbook_one() -> None:
    """nllh_measurement = nllh_transformed + SUM log y, base-corrected."""
    lin, _ = jacobian_correction(_obs("lin"), MEAS)
    assert lin == 0.0, "a linear observable needs no correction"

    nat, detail = jacobian_correction(_obs("log"), MEAS)
    expected = sum(math.log(v) for v in (1.0, 10.0, 100.0, 0.5))
    assert abs(nat - expected) < 1e-9, (nat, expected)
    assert detail["o1"]["n"] == 4 and detail["o1"]["n_unusable"] == 0

    ten, _ = jacobian_correction(_obs("log10"), MEAS)
    assert abs(ten - (expected + 4 * math.log(math.log(10)))) < 1e-9, ten
    assert ten > nat, "log10 carries the extra base term"


def test_a_non_positive_measurement_is_reported_not_skipped() -> None:
    meas = pd.DataFrame({"observableId": ["o1"] * 3, "measurement": [1.0, 0.0, -2.0]})
    total, detail = jacobian_correction(_obs("log"), meas)
    assert total == 0.0, "only the usable point contributes, and log(1) is 0"
    assert detail["o1"]["n"] == 3 and detail["o1"]["n_unusable"] == 2, (
        "a value that cannot be log-transformed must be counted, not silently "
        "dropped"
    )


def test_sharing_is_detected_and_disagreement_is_named() -> None:
    ok, why = comparable({"a": {"o1": "lin"}, "b": {"o1": "lin"}})
    assert ok and "same transformation" in why

    ok, why = comparable({"a": {"o1": "lin", "o2": "lin"}, "b": {"o1": "log"}})
    assert not ok
    assert "o1: lin vs log" in why, why
    assert "o2" not in why, "only the observables that actually differ"

    ok, why = comparable({})
    assert ok, "no candidates, nothing to compare"


def test_the_gate_refuses_an_uncorrected_comparison() -> None:
    """Without the correction the gate refuses; corrected or shared, it passes."""
    from octomod.workflow_modules.evaluation.engine import _comparability_gate

    refused = _comparability_gate(
        {
            "shared_transformation": False,
            "correction_applied": False,
            "detail": "candidates disagree on the observable transformation",
            "per_candidate": {},
        }
    )()
    assert refused.passed is False, "an uncorrected comparison must be refused"
    assert (
        refused.tier == "T1" and refused.blocking is not False
    ), "blocking for a selection round"

    corrected = _comparability_gate(
        {
            "shared_transformation": False,
            "correction_applied": True,
            "detail": "candidates disagree on the observable transformation",
            "per_candidate": {"a": {"correction": 6.2146}, "b": {"correction": 0.0}},
        }
    )()
    assert corrected.passed is True
    assert "6.2146" in str(
        corrected.detail
    ), "the correction VALUE must be visible in the gate record"
    shared = _comparability_gate(
        {
            "shared_transformation": True,
            "correction_applied": False,
            "detail": "every candidate uses the same transformation",
            "per_candidate": {},
        }
    )()
    assert shared.passed is True and "same transformation" in str(shared.detail)


def test_the_correction_runs_before_anything_is_compared() -> None:
    """A correction that reverses the ranking is followed by the selection."""
    from octomod.workflow_modules.evaluation.selection import apply_correction
    from octomod.workflow_modules.model import model_space

    rows = [
        {"id": "lin_model", "n_est": 2, "n_data": 20, "nllh": 10.0, "aic": 24.0},
        {"id": "log_model", "n_est": 2, "n_data": 20, "nllh": 8.0, "aic": 20.0},
    ]
    transforms = {"lin_model": {"o1": "lin"}, "log_model": {"o1": "log10"}}
    # a large positive term on the log candidate: in MEASUREMENT space it is
    # the worse model, though its transformed likelihood looked better
    corrections = {"lin_model": 0.0, "log_model": 9.0}

    uncorrected_best = min(rows, key=lambda r: r["aic"])["id"]
    shared, rec = apply_correction(rows, transforms, corrections)
    assert not shared and rec["correction_applied"], rec
    by_id = {r["id"] for r in rows}
    log_row = next(r for r in rows if r["id"] == "log_model")
    assert log_row["nllh_transformed"] == 8.0, "the raw value must be kept"
    assert log_row["nllh"] == 17.0, log_row["nllh"]
    assert log_row["aic"] == 2 * 2 + 2 * 17.0, log_row["aic"]
    corrected_best = min(rows, key=lambda r: r["aic"])["id"]
    assert uncorrected_best == "log_model" and corrected_best == "lin_model", (
        "the fixture must actually reverse the ranking, or this test proves "
        f"nothing: {uncorrected_best} -> {corrected_best}"
    )
    picked = model_space.select(
        [
            {
                "model_id": r["id"],
                "axes_on": [],
                "n_estimated": r["n_est"],
                "nllh": r["nllh"],
                "n_data": r["n_data"],
            }
            for r in rows
        ],
        "AIC",
        2.0,
        0.7,
    )
    assert picked["winner"] == "lin_model", (
        f"selecting after the correction must pick the measurement-space "
        f"winner, got {picked['winner']}"
    )
    assert by_id == {"lin_model", "log_model"}

    # a shared set is left alone
    single = [{"id": "a", "n_est": 1, "n_data": 5, "nllh": 1.0, "aic": 3.0}]
    shared2, rec2 = apply_correction(single, {"a": {"o1": "lin"}}, {"a": 0.0})
    assert shared2 and not rec2["correction_applied"], rec2
    assert "nllh_transformed" not in single[0], "nothing to correct, nothing touched"

    # and the ENGINE calls it in that order
    s7 = (
        REPO / "octomod" / "workflow_modules" / "evaluation" / "engine.py"
    ).read_text()
    i_corr = s7.find("_selection.apply_correction")
    i_aics = s7.find("aics = np.array")
    i_sel = s7.find("local = model_space.select")
    assert 0 < i_corr < i_aics < i_sel, (
        "the engine must correct BEFORE the delta/weight arithmetic and before "
        f"select(): apply_correction@{i_corr} aics@{i_aics} select@{i_sel}"
    )
    assert '"comparability": comparability,' in s7, "and record it in the report"
    assert "_comparability_gate(comparability)" in s7
    print(
        "  ORDER         corrected before compared — a reversed ranking follows "
        "the corrected numbers"
    )


if __name__ == "__main__":
    test_transformations_default_to_lin()
    print("  transforms    read from the table, absent means lin")
    test_the_change_of_variables_term_is_the_textbook_one()
    print("  correction    SUM log y, with the log10 base term")
    test_a_non_positive_measurement_is_reported_not_skipped()
    print("  unusable      a non-positive measurement is counted, not dropped")
    test_sharing_is_detected_and_disagreement_is_named()
    print("  comparison    sharing detected, disagreement named per observable")
    test_the_gate_refuses_an_uncorrected_comparison()
    print("  gate          refuses uncorrected, passes corrected or shared")
    test_the_correction_runs_before_anything_is_compared()
    print("COMPARABILITY UNIT OK — a search cannot win by transforming the data")
