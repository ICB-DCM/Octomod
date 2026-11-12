"""A boundary species (`$E`, not consumed) is a model entity, not invisible.

  1. it is a model entity, yet stays out of the floating state (`species_ids`);
  2. its value resolves in a formula namespace, exactly as a parameter's does;
  3. a condition can override it, and the override reaches the simulation;
  4. an override target that names nothing in the model still raises.

    uv run python tests/boundary_species_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.workflow_modules.model.simwrap import RRModel, SimError  # noqa: E402

# `$E`: catalytic and not consumed, so a boundary species.
ANT = """
model catalyst_case
  species S, P;
  species $E;
  S = 10; P = 0; E = 1;
  k = 0.05;
  J0: S -> P; k * E * S;
end
"""


def _model() -> RRModel:
    import antimony

    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(ANT) >= 0, antimony.getLastError()
    return RRModel(antimony.getSBMLString(antimony.getMainModuleName()))


def test_it_is_an_entity_but_not_state():
    m = _model()
    assert "E" in m.boundary_ids, m.boundary_ids
    assert "E" in set(m.entity_ids), m.entity_ids
    assert "E" not in set(m.species_ids), (
        "a boundary species is a CONSTANT, not floating state — putting it in "
        "species_ids would hand it to the conservation and non-negativity screens"
    )
    assert {"S", "P"} <= set(m.species_ids)
    print("  entity        'E' is an entity and is NOT in the floating state")


def test_its_value_resolves_like_a_parameter():
    m = _model()
    vals = m.parameter_values()
    assert "E" in vals, f"a formula referring to E would be unresolved: {sorted(vals)}"
    assert vals["E"] == 1.0, vals["E"]
    assert "k" in vals, "parameters must still be there"
    print("  namespace     'E' resolves to 1.0 alongside the parameters")


def test_a_condition_can_override_it():
    m = _model()
    slow = m.simulate(20.0, n_points=5, overrides={"E": 1.0})["S"][-1]
    fast = m.simulate(20.0, n_points=5, overrides={"E": 4.0})["S"][-1]
    assert fast < slow, f"override ignored: S={fast} at 4x vs {slow} at 1x"
    # 4x catalyst on a first-order law is exp(-4kt) against exp(-kt)
    import math

    assert abs(fast - 10 * math.exp(-0.05 * 4 * 20)) < 1e-3, fast
    print(f"  override      4x catalyst leaves S={fast:.4f} against {slow:.4f} at 1x")


def test_an_unknown_target_still_fails_loudly():
    """An override target that is in no category still raises (a typo)."""
    m = _model()
    try:
        m.simulate(1.0, overrides={"not_in_the_model": 1.0})
    except SimError as e:
        assert "not_in_the_model" in str(e), e
        print("  unknown       a name that is in no category still raises")
        return
    raise AssertionError("an unknown override target was accepted")


if __name__ == "__main__":
    test_it_is_an_entity_but_not_state()
    test_its_value_resolves_like_a_parameter()
    test_a_condition_can_override_it()
    test_an_unknown_target_still_fails_loudly()
    print(
        "BOUNDARY SPECIES UNIT OK — a catalyst written `$E` is an entity, "
        "resolves in a formula, and a condition can set it"
    )
