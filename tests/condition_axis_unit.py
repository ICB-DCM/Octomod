"""An observation axis gives one condition its own estimated copy of a parameter.

  1. `apply_patch` keeps an id an id; validation refuses undeclared or measured ids;
  2. the enumerator tags the copy `layer: assembly` and keeps it out of the model;
  3. S3 renders the copy's own row and refuses a partial split of an estimated one;
  4. it compiles, and a seeded fit moves the copy to the planted value (3.0).

    uv run python tests/condition_axis_unit.py
"""

from __future__ import annotations

import logging
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.WARNING)

from _harness import check, finish  # noqa: E402
from _record import rnd, temp_record, work  # noqa: E402

from octomod.gates.build_gates import antimony_to_sbml  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.orchestration.run_context import ModuleFailure  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import assembly_edit, petab_io  # noqa: E402
from octomod.workflow_modules.assembly import engine as assembly_module  # noqa: E402
from octomod.workflow_modules.estimation import problem as estimation  # noqa: E402
from octomod.workflow_modules.model import supermodel  # noqa: E402

K, MU_B, SD = 0.3, 3.0, 0.02  # the planted truth: condition b runs 3x faster

ANT = """model m
  compartment cell = 1;
  species A in cell = 1;
  species B in cell = 0;
  u = 1;
  kcat = 0.3;
  mu = 1;
  J0: A -> B; kcat*mu*u*A;
end
"""
PARAMS = [
    {"id": "kcat", "nominal_value": 0.3, "lb": 1e-3, "ub": 10.0, "estimate": True},
    {"id": "mu", "nominal_value": 1.0, "lb": 0.05, "ub": 20.0, "estimate": False},
]
AXIS = {
    "id": "b_own_rate",
    "kind": "observation",
    "default": "off",
    "on_assembly_patch": {
        "change_condition": {
            "condition_id": "c_b",
            "overrides": {"mu": "mu_b"},
        }
    },
    "adds_parameters": [
        {
            "id": "mu_b",
            "nominal_value": 1.0,
            "lb": 0.05,
            "ub": 20.0,
            "estimate": True,
            "neutral_value": 1.0,
        }
    ],
}
ASSEMBLY = {
    "observables": [
        {
            "observable_id": "obs_b",
            "maps_to_label": "b",
            "formula": "B",
            "transformation": "lin",
            "rationale": "unit fixture",
        }
    ],
    "noise": [
        {
            "observable_id": "obs_b",
            "distribution": "normal",
            "formula": "sigma_obs_b",
            "estimate_sigma": True,
        }
    ],
    "scaling": [{"observable_id": "obs_b", "mode": "none"}],
    "conditions": [
        {"condition_id": "c_a", "maps_to_label": "lig=a", "overrides": {"u": 1.0}},
        {"condition_id": "c_b", "maps_to_label": "lig=b", "overrides": {"u": 1.0}},
    ],
}


def _long_df(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for lig, mu in (("a", 1.0), ("b", MU_B)):
        for t in (0.25, 0.5, 1.0, 2.0, 4.0, 8.0):
            for rep in (1, 2):
                rows.append(
                    {
                        "observable_label": "b",
                        "condition_label": f"lig={lig}",
                        "condition_key": f"lig={lig}",
                        "time": t,
                        "value": 1.0 - math.exp(-K * mu * t) + rng.normal(0.0, SD),
                        "replicate": rep,
                    }
                )
    return pd.DataFrame(rows)


class _Ctx:
    """Just the surface `_merge_to_petab` touches, over a record."""

    def __init__(self, root, spec):
        self.root, self.spec, self.ledger = root, spec, Ledger(root)
        self.round_idx, self.candidate = 0, None
        self.testcase = {"holdout": {"condition_labels": []}}

    @property
    def round(self):
        return rnd(self.root, 0)

    @property
    def work(self):
        return work(self.root, 0)

    @property
    def model(self):
        return self.round / "model"


def test_patch_and_validation() -> None:
    ents, pars = {"A", "B", "u", "kcat", "mu", "cell"}, {"kcat", "mu", "mu_b"}
    ok = assembly_edit.validate_patch(
        AXIS["on_assembly_patch"],
        model_entities=ents,
        parameter_ids=pars,
        adds={"mu_b"},
        assembly=ASSEMBLY,
    )
    check("a declared per-condition copy is a valid condition axis", ok == [], str(ok))
    ghost = assembly_edit.validate_patch(
        {
            "change_condition": {
                "condition_id": "c_b",
                "overrides": {"mu": "mu_x"},
            }
        },
        model_entities=ents,
        parameter_ids={"kcat", "mu"},
        adds=set(),
        assembly=ASSEMBLY,
    )
    check(
        "an undeclared copy is refused by name",
        any("'mu_x'" in p and "nobody declares" in p for p in ghost),
        str(ghost),
    )
    measured = assembly_edit.validate_patch(
        {
            "change_condition": {
                "condition_id": "c_b",
                "overrides": {"u": "u_b"},
            }
        },
        model_entities=ents,
        parameter_ids=pars | {"u_b"},
        adds={"u_b"},
        assembly=ASSEMBLY,
    )
    check(
        "turning a measured factor into a parameter is still refused",
        any("reinterprets" in p for p in measured),
        str(measured),
    )
    out = assembly_edit.apply_patch(ASSEMBLY, AXIS["on_assembly_patch"])
    c_b = next(c for c in out["conditions"] if c["condition_id"] == "c_b")
    check(
        "apply_patch keeps the id an id (it cast it to float)",
        c_b["overrides"] == {"u": 1.0, "mu": "mu_b"},
        str(c_b["overrides"]),
    )


def _axis_model() -> dict:
    grouped = supermodel.enumerate_grouped(
        ANT, PARAMS, [AXIS], 8, t_end=10.0, keep_base=True, one_at_a_time=True
    )
    return next(m for m in grouped["models"] if m["axes_on"] == ["b_own_rate"])


def test_enumeration() -> None:
    m = _axis_model()
    row = next(p for p in m["parameters"] if p["id"] == "mu_b")
    check(
        "the copy is tagged layer: assembly", row.get("layer") == "assembly", str(row)
    )
    check(
        "the copy is NOT declared into the model",
        "mu_b" not in m["antimony"] and m["antimony"].strip() == ANT.strip(),
        m["antimony"][-120:],
    )
    src = (REPO / "octomod" / "workflow_modules" / "model" / "engine.py").read_text()
    i = src.index("est_bounds = {")
    check(
        "S1's box gate is not handed an observation-layer parameter",
        'p.get("layer") != "assembly"' in src[i : i + 500],
    )


def _render(root, params: list[dict], antimony: str, overlay: list):
    spec = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
    ctx = _Ctx(root, spec)
    (ctx.model / "parameters").put(params)
    sbml, err = antimony_to_sbml(antimony)
    assert sbml, err
    petab_dir = ctx.work / "petab"
    merged = assembly_edit.apply_overlay(ASSEMBLY, overlay)
    assembly_module._merge_to_petab(ctx, merged, sbml, _long_df(), petab_dir)
    return ctx, petab_dir


def test_render_and_fit() -> None:
    m = _axis_model()
    with temp_record() as root:
        ctx, petab_dir = _render(
            root, m["parameters"], m["antimony"], m["assembly_overlay"]
        )
        par = (petab_dir / "parameters").table().set_index("parameterId")
        cond = (petab_dir / "conditions").table().set_index("conditionId")
        check(
            "the copy has the AXIS's row: estimated, bounds [0.05, 20]",
            "mu_b" in par.index
            and int(par.loc["mu_b", "estimate"]) == 1
            and float(par.loc["mu_b", "lowerBound"]) == 0.05
            and float(par.loc["mu_b", "upperBound"]) == 20.0,
            (
                str(par.loc["mu_b"].to_dict())
                if "mu_b" in par.index
                else str(sorted(par.index))
            ),
        )
        check(
            "the overridden fixed parameter left the parameter table (PEtab rule)",
            "mu" not in par.index,
            str(sorted(par.index)),
        )
        check(
            "c_b reads the copy, c_a the fixed value written out (not a blank)",
            str(cond.loc["c_b", "mu"]) == "mu_b"
            and float(cond.loc["c_a", "mu"]) == 1.0,
            str(cond["mu"].to_dict()),
        )
        notes = [
            r
            for r in ctx.ledger.entries()
            if "declared by an observation axis" in str(r.get("note"))
        ]
        check("the assembly ledgers the declared copy", len(notes) == 1, str(notes[:1]))

        inp = petab_io.from_work(ctx.work, ctx.model)
        prob, _pp, _ = estimation.build_problem(inp, {}, ctx.spec)
        names = list(prob.x_names)
        check(
            "the copy is a FREE parameter of the built problem",
            "mu_b" in {names[i] for i in prob.x_free_indices},
            f"free={[names[i] for i in prob.x_free_indices]}",
        )
        result = estimation.run_multistart(prob, 4, 20260914, ctx.spec)
        best = result.optimize_result.list[0]
        x_full = prob.get_full_vector(best.x, prob.x_fixed_vals)
        un = estimation.x_to_unscaled_dict(
            np.asarray(x_full, float), names, estimation.parameter_scales(inp)
        )
        check(
            f"the fit moves the copy to the planted {MU_B} (kcat {K})",
            abs(un["mu_b"] - MU_B) < 0.3 and abs(un["kcat"] - K) < 0.03,
            f"mu_b {un['mu_b']:.3f} kcat {un['kcat']:.4f} fval {float(best.fval):.2f}",
        )


def test_estimated_partial_split_refused() -> None:
    params = [dict(p, estimate=True) if p["id"] == "mu" else p for p in PARAMS]
    params = params + [dict(AXIS["adds_parameters"][0], layer="assembly")]
    with temp_record() as root:
        try:
            _render(root, params, ANT, [AXIS["on_assembly_patch"]])
            check(
                "a partial split of an ESTIMATED parameter is refused",
                False,
                "rendered",
            )
        except ModuleFailure as e:
            check(
                "a partial split of an ESTIMATED parameter is refused by name",
                "'mu'" in str(e) and "ESTIMATED" in str(e) and "c_a" in str(e),
                str(e)[:160],
            )


def main() -> int:
    test_patch_and_validation()
    test_enumeration()
    test_render_and_fit()
    test_estimated_partial_split_refused()
    return finish(
        "\nCONDITION AXIS",
        "\nCONDITION AXIS UNIT OK — a per-condition copy is declared, rendered, compiled and moved",
    )


if __name__ == "__main__":
    sys.exit(main())
