"""An `append` axis that adds a new state passes the undeclared-symbol check and builds.

    uv run python tests/append_species_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.gates.build_gates import antimony_to_sbml  # noqa: E402
from octomod.workflow_modules.model import model_space, supermodel  # noqa: E402

BASE = """model base
  compartment cell = 1;
  species A in cell, B in cell;
  A = 1; B = 0;
  R1: A -> B; cell * k1 * A;
  k1 = 0.5;
end"""

LOOP = {
    "id": "integrator_inhibitor",
    "on_antimony_patch": {
        "append": "species H_int in cell;\nH_int = 0;\n"
        "J_Hint_syn: -> H_int; cell * eta_int * A;\n"
        "J_A_fbI: A -> ; cell * H_int * A;"
    },
    "adds_parameters": [
        {
            "id": "eta_int",
            "lb": 0.0,
            "ub": 10.0,
            "nominal_value": 0.05,
            "estimate": True,
            "neutral_value": 0,
        }
    ],
}


def main() -> int:
    und = model_space.undeclared_symbols(BASE, LOOP)
    assert und == [], f"append-declared species flagged as undeclared: {und}"
    # a comma list with compartments, and $-prefixed boundary species
    multi = {
        **LOOP,
        "on_antimony_patch": {
            "append": "species P9 in cell, $E_in in cell;\nP9 = 0; E_in = 1;\nJ_open: -> P9; cell * eta_int * A * (1 - P9) * E_in;"
        },
    }
    assert model_space.undeclared_symbols(BASE, multi) == []
    # a genuinely unknown symbol in the appended kinetics is still caught
    bad = {
        **LOOP,
        "on_antimony_patch": {
            "append": "species H_int in cell;\nH_int = 0;\nJ_x: -> H_int; cell * zeta * A;"
        },
    }
    assert model_space.undeclared_symbols(BASE, bad) == ["zeta"]
    ant, _added, applied = supermodel.apply_all(BASE, [LOOP])
    assert applied and "H_int" in ant
    sbml, err = antimony_to_sbml(ant)
    assert sbml is not None, err
    print(
        "APPEND SPECIES UNIT OK — a new state declared in an append block is a declaration, not an undeclared symbol"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
