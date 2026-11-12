"""AMICI-safe observable formulas: `log2`/`log10` are rewritten via petab's parser,
unknown functions are named, and the T0 gate `assembly_formulas_compile_safe` refuses them.

    uv run python tests/formula_safe_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.workflow_modules.assembly.assembly_edit import (  # noqa: E402
    amici_safe_formula,
    unsupported_functions,
)


def main() -> int:
    assert unsupported_functions("log2(m_IRF1)") == ["log2"]
    assert unsupported_functions("log(m_IRF1)/log(2)") == []
    assert unsupported_functions("sigma_obs_x * exp(-k*t)") == []
    assert unsupported_functions("noiseParameter1_obs_x") == []
    out = amici_safe_formula("log2(m_IRF1)")
    assert "log2" not in out and "log(m_IRF1)" in out, out
    out10 = amici_safe_formula("log10(m_CXCL9 + off_obs)")
    assert "log10" not in out10 and "log(10)" in out10, out10
    same = "log(m_IRF1)/log(2)"
    assert (
        amici_safe_formula(same) == same
    ), "an already-safe formula is returned byte-identical"
    try:
        amici_safe_formula("mylog(m_IRF1)")
    except ValueError as e:
        assert "mylog" in str(e)
    else:
        raise AssertionError("unknown function must raise")
    # the gate, on a tables object with one bad row
    from octomod.gates.petab_gates import PetabTables, make_petab_gates  # noqa: E402
    from octomod.workflow_modules.assembly import petab_io

    petab_dir = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"
    # the problem as an in-memory object: libraries never read the run's files
    tables = PetabTables.from_input(petab_io.from_dir(petab_dir))
    tables.observables = pd.DataFrame(
        [
            {
                "observableId": "obs_a",
                "observableFormula": "log2(x)",
                "noiseFormula": "sigma_a",
            },
            {
                "observableId": "obs_b",
                "observableFormula": "log(x)/log(2)",
                "noiseFormula": "sigma_b",
            },
        ]
    )

    class _Spec:  # the gate list needs only .get(); tolerances default when absent
        def get(self, key, default=None):
            return default

    gates = make_petab_gates(tables, _Spec())
    g = next(g for g in gates if g.__name__ == "g_formulas")
    r = g()
    assert (
        r.passed is False and "obs_a.observableFormula calls ['log2']" in r.detail
    ), r.detail
    tables.observables.loc[0, "observableFormula"] = "log(x)/log(2)"
    assert g().passed is True
    print("formula_safe_unit: rewrite, refusal and gate all OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
