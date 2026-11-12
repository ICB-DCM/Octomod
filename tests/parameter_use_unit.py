"""An estimated parameter the model never reads is refused at S1.

  1. a shared constant left estimated beside its specific copies (`kdeph`) is refused;
  2. a parameter read only by an initial value or by a readout assignment rule is used;
  3. an unused parameter that is fixed is not this check's business;
  4. the gate is wired into the S1 ladder, before any simulation.

    uv run python tests/parameter_use_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.gates.build_gates import (  # noqa: E402
    antimony_to_sbml,
    estimated_but_unused,
    make_parameter_use_gates,
)

MODEL = """
model m
  compartment cell; cell = 1;
  species R in cell, S in cell, P in cell;
  R = Rtot; S = 10; P = 0;
  count := bg + P;
  Jp: S -> P; cell*k*R*S;
  Jd: P -> S; cell*kdeph_S1*P;
  Rtot = 1; bg = 2; k = 0.1; kdeph_S1 = 0.05; kdeph = 0.05; spare = 1;
end
"""


def _par(pid, est=True):
    return {"id": pid, "nominal_value": 1.0, "estimate": est, "lb": 1e-3, "ub": 10}


def _sbml():
    sbml, err = antimony_to_sbml(MODEL)
    assert sbml, err
    return sbml


def test_the_redraft_pattern_is_refused():
    params = [_par(p) for p in ("Rtot", "bg", "k", "kdeph_S1", "kdeph")]
    assert estimated_but_unused(_sbml(), params) == ["kdeph"]
    (g,) = make_parameter_use_gates(_sbml(), params)
    res = g()
    assert not res.passed and res.blocking and "'kdeph'" in res.detail, res
    print(f"  refused       {res.detail[:88]}…")


def test_initial_values_and_rules_are_uses():
    params = [_par("Rtot"), _par("bg")]
    assert estimated_but_unused(_sbml(), params) == [], (
        "Rtot (read by R's initial value) and bg (read by an assignment rule "
        "only the observation model uses) are uses"
    )
    print("  uses          initial value and a readout rule count as reads")


def test_a_fixed_unused_parameter_is_not_its_business():
    assert estimated_but_unused(_sbml(), [_par("spare", est=False)]) == []
    (g,) = make_parameter_use_gates(_sbml(), [_par("k"), _par("spare", est=False)])
    assert g().passed
    print("  fixed         an unused FIXED parameter passes")


def test_an_observation_axis_parameter_is_exempt():
    """A parameter tagged `layer="assembly"` (read by the PEtab tables) is exempt."""
    params = [_par("k"), dict(_par("mu_bc_term_il3"), layer="assembly")]
    assert (
        estimated_but_unused(_sbml(), params) == []
    ), "an observation-layer parameter was refused"
    # an untagged unused parameter is still refused
    assert estimated_but_unused(_sbml(), [_par("k"), _par("mu_bc_term_il3")]) == [
        "mu_bc_term_il3"
    ]
    print(
        "  layer         an observation axis's parameter is exempt; an untagged one is not"
    )


def test_it_is_wired_into_the_ladder_first():
    src = (REPO / "octomod" / "workflow_modules" / "model" / "engine.py").read_text()
    i = src.index("def _run_ladder(")
    body = src[i : i + 1800]
    assert 'make_parameter_use_gates(holder["sbml"], parameters)' in body, body[:400]
    assert body.index("make_parameter_use_gates(") < body.index(
        "make_sim_gates("
    ), "the cheap check must run before the simulations"
    print("  wired         in the S1 ladder, before the simulation gates")


if __name__ == "__main__":
    test_the_redraft_pattern_is_refused()
    test_initial_values_and_rules_are_uses()
    test_a_fixed_unused_parameter_is_not_its_business()
    test_an_observation_axis_parameter_is_exempt()
    test_it_is_wired_into_the_ladder_first()
    print("\nPARAMETER USE UNIT OK")
