"""An axis patch may use Antimony's own vocabulary: `time` and the standard functions.

  1. `time`, `exp` and the math words are not undeclared; an unknown symbol is, by name;
  2. the patched model builds, simulates to finite values and switches off at neutral;
  3. both agent instructions still prefer a decaying state over a function of time.

    uv run python tests/time_forcing_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod.agents import ROLES  # noqa: E402
from octomod.gates.build_gates import antimony_to_sbml  # noqa: E402
from octomod.workflow_modules.assembly.assembly_edit import MATH_WORDS  # noqa: E402
from octomod.workflow_modules.model import model_space, supermodel  # noqa: E402
from octomod.workflow_modules.model.simwrap import RRModel  # noqa: E402

BASE = """model cell
  R1: A -> B; k1*A;
  A = 1; B = 0; k1 = 0.5;
end
"""


def _par(pid, nominal, neutral=None):
    p = {"id": pid, "lb": 0.0, "ub": 10.0, "nominal_value": nominal, "estimate": True}
    if neutral is not None:
        p["neutral_value"] = neutral
    return p


def main() -> int:
    pulse = {
        "id": "culture_pulse",
        "on_antimony_patch": {
            "replace_reaction": "R1",
            "with": "R1: A -> B; k1*A + a0*exp(-time/tau)",
        },
        "adds_parameters": [_par("a0", 0.2, neutral=0.0), _par("tau", 2.0)],
    }
    und = model_space.undeclared_symbols(BASE, pulse)
    check("`time` and `exp` are not undeclared symbols", und == [], str(und))
    check(
        "the whitelist is Antimony's vocabulary, shared with the noise-formula grammar",
        {"time", "exp", "log", "sqrt", "pow"} <= set(MATH_WORDS),
        str(sorted(MATH_WORDS)),
    )
    unknown = {
        **pulse,
        "on_antimony_patch": {
            "replace_reaction": "R1",
            "with": "R1: A -> B; k1*A + a0*exp(-time/tau) + zeta*A",
        },
    }
    check(
        "a genuinely unknown symbol is still refused, by name",
        model_space.undeclared_symbols(BASE, unknown) == ["zeta"],
        str(model_space.undeclared_symbols(BASE, unknown)),
    )
    ant, _added, applied = supermodel.apply_all(BASE, [pulse])
    sbml, err = antimony_to_sbml(ant)
    check("the patched model builds", applied and sbml is not None, str(err)[:120])
    if sbml:
        traj = RRModel(sbml).simulate(10.0)
        b = np.asarray(traj["B"], dtype=float)
        check(
            "…and simulates to finite values with the explicit time term active",
            bool(np.all(np.isfinite(b))) and float(b[-1]) > 0,
            f"B(10) = {float(b[-1]):.4g}",
        )
        off_traj = RRModel(sbml).simulate(10.0, overrides={"a0": 0.0})
        base_traj = RRModel(antimony_to_sbml(BASE)[0]).simulate(10.0)
        check(
            "with a0 at its neutral value the forcing vanishes (the axis is switchable)",
            np.allclose(off_traj["B"], base_traj["B"], rtol=1e-5, atol=1e-8),
        )
    for role in ("construction", "revision"):
        c = ROLES[role].contract
        check(
            f"{role} is told: accepted, but PREFER a state over a function of time",
            "PREFER" in c and "function of time" in c and "first-order decay" in c,
        )
    return finish(
        "\nTIME FORCING",
        "\ntime forcing: accepted by the grammar, a state still preferred",
    )


if __name__ == "__main__":
    sys.exit(main())
