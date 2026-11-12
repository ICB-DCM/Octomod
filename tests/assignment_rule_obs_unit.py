"""An observable that is not a species must still be a time course.

  1. two identical calls agree exactly, with no dependence on call history;
  2. the assignment-rule quantity varies over time rather than being frozen;
  3. its values are the ones the rule defines, checked against its species.

    uv run python tests/assignment_rule_obs_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.gates.petab_gates import PetabTables  # noqa: E402
from octomod.workflow_modules.model.simwrap import RRModel  # noqa: E402

# `total` is an assignment rule on a PARAMETER, not a species: the shape PySB
# emits for every observable, which the species-based fixtures never exercise.
ANT = """
model assignment_rule_case
  species A, B;
  A = 10; B = 0;
  k = 0.05;
  total := A + 2*B;
  J0: A -> B; k*A;
end
"""


def _tables() -> tuple[PetabTables, np.ndarray]:
    import antimony

    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(ANT) >= 0, antimony.getLastError()
    sbml = antimony.getSBMLString(antimony.getMainModuleName())
    obs = pd.DataFrame(
        [
            {
                "observableId": "o_total",
                "observableFormula": "total",
                "noiseFormula": "0.1",
                "noiseDistribution": "normal",
            }
        ]
    )
    cond = pd.DataFrame([{"conditionId": "c1"}])
    meas = pd.DataFrame(
        [
            {
                "observableId": "o_total",
                "simulationConditionId": "c1",
                "time": 0.0,
                "measurement": 10.0,
            }
        ]
    )
    par = pd.DataFrame(
        [
            {
                "parameterId": "k",
                "parameterScale": "lin",
                "lowerBound": 1e-3,
                "upperBound": 1e3,
                "nominalValue": 0.05,
                "estimate": 1,
            }
        ]
    )
    return PetabTables(obs, cond, meas, par, sbml), np.linspace(0.0, 40.0, 21)


def test_the_model_lists_the_assignment_target():
    import antimony

    antimony.clearPreviousLoads()
    antimony.loadAntimonyString(ANT)
    sbml = antimony.getSBMLString(antimony.getMainModuleName())
    m = RRModel(sbml)
    assert "total" in m.assignment_ids, m.assignment_ids
    assert "total" not in m.species_ids
    assert set(m.dynamic_ids) == set(m.species_ids) | {"total"}
    print("  discovery     'total' found as an assignment target, not a species")


def test_identical_calls_agree_exactly():
    """Identical calls agree exactly, whatever ran before them."""
    tables, times = _tables()
    runs = [tables.simulate_observables("c1", times)["o_total"] for _ in range(4)]
    spread = max(float(np.max(np.abs(r - runs[0]))) for r in runs)
    assert spread == 0.0, f"calls disagree by {spread}"
    # and interleaving a different parameter value must not contaminate it
    tables.simulate_observables("c1", times, param_override={"k": 0.5})
    again = tables.simulate_observables("c1", times)["o_total"]
    assert float(np.max(np.abs(again - runs[0]))) == 0.0, "call history leaked in"
    print("  repeatable    4 identical calls agree to 0.0, and survive an interleave")


def test_it_is_a_time_course_with_the_right_values():
    tables, times = _tables()
    got = tables.simulate_observables("c1", times)["o_total"]
    assert float(np.ptp(got)) > 1.0, f"still frozen: {got[:3]}"
    # total = A + 2B with A + B = 10 conserved, so total = 10 + B, and
    # B(t) = 10 * (1 - exp(-k t))
    want = 10.0 + 10.0 * (1.0 - np.exp(-0.05 * times))
    err = float(np.max(np.abs(got - want)))
    assert err < 1e-3, f"values wrong by {err}"
    assert abs(got[0] - 10.0) < 1e-9, got[0]
    print(f"  values        matches 10 + B(t) analytically to {err:.2e}")


if __name__ == "__main__":
    test_the_model_lists_the_assignment_target()
    test_identical_calls_agree_exactly()
    test_it_is_a_time_course_with_the_right_values()
    print(
        "ASSIGNMENT RULE OBS UNIT OK — a non-species observable is discovered, "
        "resolved over time, and does not depend on what ran before it"
    )
