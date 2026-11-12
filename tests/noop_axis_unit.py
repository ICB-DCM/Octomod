"""An axis whose patch reproduces the base is a no-op on that base and is not searched.

Enumerating it would double the lattice with exact duplicates.

    uv run python tests/noop_axis_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.workflow_modules.model import model_space, supermodel  # noqa: E402

BASE = """model amplified
  compartment cell = 1;
  species A in cell, B in cell;
  A = 0; B = 0;
  J_A_syn: -> A; cell * k_A * u * (1 + k_amp * A / (K_amp + A));
  J_A_deg: A -> ; cell * k_A * A;
  J_B: -> B; cell * g * A;
  k_A = 2; u = 1; k_amp = 2; K_amp = 0.1; g = 1;
end"""
BASE_PAR = [
    {"id": "k_A", "lb": 0.001, "ub": 50, "nominal_value": 2, "estimate": True},
    {"id": "k_amp", "lb": 0.01, "ub": 100, "nominal_value": 2, "estimate": True},
    {"id": "g", "lb": 0.01, "ub": 100, "nominal_value": 1, "estimate": True},
]
AMP = {
    "id": "amp_drive",
    "on_antimony_patch": {
        "replace_reaction": "J_A_syn",
        "with": "J_A_syn: -> A; cell * k_A * u * (1 + k_amp * A / (K_amp + A));",
    },
    "adds_parameters": [
        {
            "id": "k_amp",
            "lb": 0.01,
            "ub": 100,
            "nominal_value": 2,
            "estimate": True,
            "neutral_value": 0,
        },
        {"id": "K_amp", "lb": 0.1, "ub": 0.1, "nominal_value": 0.1, "estimate": False},
    ],
}
REAL = {
    "id": "integrator",
    "on_antimony_patch": {
        "append": "species H in cell;\nH = 0;\nJ_H: -> H; cell * eta * A;\nJ_fb: A -> ; cell * H * A;"
    },
    "adds_parameters": [
        {
            "id": "eta",
            "lb": 0,
            "ub": 10,
            "nominal_value": 0.05,
            "estimate": True,
            "neutral_value": 0,
        }
    ],
}


def main() -> int:
    noop = supermodel.noop_axes(BASE, [AMP, REAL])
    assert [n["id"] for n in noop] == ["amp_drive"], noop
    part = supermodel.verified_partition(BASE, [AMP, REAL], 10.0)
    assert [n["id"] for n in part["noop"]] == ["amp_drive"]
    assert "amp_drive" not in {a["id"] for a in part["neutral"] + part["separate"]}
    assert part["verification"]["per_axis"]["amp_drive"]["noop"] is True
    enc = model_space.enumerate_with_encoding(
        BASE, BASE_PAR, [AMP, REAL], 8, t_end=10.0
    )
    ids = sorted(m["model_id"] for m in enc["models"])
    assert ids == ["base", "integrator"], ids
    assert [n["id"] for n in enc["encoding"]["noop_axes"]] == ["amp_drive"]
    # the same patch on a base WITHOUT amplification is a real axis
    plain = BASE.replace(" * (1 + k_amp * A / (K_amp + A))", "").replace(
        "k_amp = 2; K_amp = 0.1; ", ""
    )
    assert supermodel.noop_axes(plain, [AMP]) == []
    print(
        "NOOP AXIS UNIT OK — an axis the base already carries is dropped by name, not enumerated twice"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
