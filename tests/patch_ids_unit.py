"""A `replace_reaction` id names a base reaction; a unique respelling of one counts.

  1. `resolve_reaction_id` tells exact, respelt (case/underscores), missing, ambiguous;
  2. `apply_patch` applies a respelt patch under the base's own reaction id;
  3. `validate_axes` drops an axis naming no reaction; a respelt one is kept, ledgered.

    uv run python tests/patch_ids_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import RecordingLedger  # noqa: E402
from _record import rnd, temp_record  # noqa: E402

from octomod.workflow_modules.model import model_space as ms  # noqa: E402

BASE = """model m
  compartment cyt; cyt = 1;
  species S1 in cyt, S1p in cyt;
  S1 = 10; S1p = 0;
  Jphos1: S1 -> S1p; cyt*kp*S1;
  Jdeph1: S1p -> S1; cyt*kd*S1p;
  den := 1 + c*S1;
  kp = 0.1; kd = 0.05; c = 0.01;
end
"""


class Ctx:
    """The round is a group of the run record (`root`)."""

    def __init__(self, root):
        self.ledger = RecordingLedger()
        self.round_idx = 1
        self.root = root

    @property
    def round(self):
        return rnd(self.root, self.round_idx)


def test_resolution():
    assert ms.resolve_reaction_id(BASE, "Jdeph1") == ("Jdeph1", "exact")
    assert ms.resolve_reaction_id(BASE, "Jdeph_1") == ("Jdeph1", "respelt")
    assert ms.resolve_reaction_id(BASE, "JDEPH_1") == ("Jdeph1", "respelt")
    assert ms.resolve_reaction_id(BASE, "Jdeph_9") == (None, "missing")
    amb = BASE.replace(
        "  den := 1 + c*S1;\n",
        "  den := 1 + c*S1;\n  J_deph1: S1p -> S1; cyt*kd*S1p;\n",
    )
    assert ms.resolve_reaction_id(amb, "jdeph_1") == (
        None,
        "ambiguous",
    ), ms.resolve_reaction_id(amb, "jdeph_1")
    print(
        "  resolution    exact, respelt (unique), missing and ambiguous are told apart"
    )


def test_apply_keeps_the_base_id():
    patch = {
        "replace_reaction": "Jdeph_1",
        "with": "Jdeph_1: S1p -> S1; cyt*kd*S1p/(1 + kprot);",
    }
    ant, ok = ms.apply_patch(BASE, patch)
    assert ok, "a unique respelling must apply"
    assert "Jdeph1: S1p -> S1; cyt*kd*S1p/(1 + kprot);" in ant, ant
    assert "Jdeph_1" not in ant, "the base's reaction id must be kept"
    ant2, ok2 = ms.apply_patch(
        BASE, {"replace_reaction": "Jdeph_9", "with": "Jdeph_9: S1p -> S1; kd*S1p;"}
    )
    assert not ok2 and ant2 == BASE
    print(
        "  apply         a respelt patch applies under the base's own id; a missing one does not"
    )


def test_validation_drops_before_the_gate():
    with temp_record() as root:
        _validation_drops_before_the_gate(Ctx(root))


def _validation_drops_before_the_gate(ctx: Ctx) -> None:
    axes = [
        {
            "id": "respelt_axis",
            "on_antimony_patch": {
                "replace_reaction": "Jdeph_1",
                "with": "Jdeph_1: S1p -> S1; cyt*kd*S1p/(1 + kprot);",
            },
            "adds_parameters": [
                {
                    "id": "kprot",
                    "nominal_value": 0.0,
                    "estimate": True,
                    "lb": 0.0,
                    "ub": 10.0,
                }
            ],
        },
        {
            "id": "missing_axis",
            "on_antimony_patch": {
                "replace_reaction": "Jdeph_9",
                "with": "Jdeph_9: S1p -> S1; cyt*kd*S1p;",
            },
        },
    ]
    kept, dropped = ms.validate_axes(ctx, axes, BASE, {"kp", "kd", "c"}, "revision")
    assert [a["id"] for a in kept] == ["respelt_axis"], kept
    assert [d["id"] for d in dropped] == ["missing_axis"], dropped
    assert (
        "Jdeph1" in dropped[0]["reason"] and "Jphos1" in dropped[0]["reason"]
    ), dropped[0]["reason"]
    assert any(
        "respelt_axis" in str(r.get("note")) and "'Jdeph1'" in str(r.get("note"))
        for r in ctx.ledger.rows
    ), ctx.ledger.rows
    print(f"  validation    dropped before the gate: {dropped[0]['reason'][:70]}…")


if __name__ == "__main__":
    test_resolution()
    test_apply_keeps_the_base_id()
    test_validation_drops_before_the_gate()
    print("\nPATCH IDS UNIT OK")
