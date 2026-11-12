"""One parameter, one copy per population: the `split_parameter` axis.

Fixture: A -> B at rate kcat*u, two populations (p1, p2) x two ligand doses
(u = 1, 2); the truth runs 3x faster in p2 (kcat 0.3 vs 0.9).

  1. each condition's attributes come from the data's condition key, not a label;
  2. `resolve_split` puts a copy per population in every condition, or refuses by name;
  3. `validate_axes` resolves the two-key patch given the data, and drops it without;
  4. a resolved split that misses a condition is refused before any merge;
  5. the copies are tagged `layer: assembly`; the model is untouched, the ladder passes;
  6. the merge estimates both copies, and a fit moves them to the planted 0.3 and 0.9.

    uv run python tests/split_parameter_unit.py
"""

from __future__ import annotations

import copy
import logging
import math
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.WARNING)

from _harness import check_detail_on_fail as check  # noqa: E402
from _harness import finish  # noqa: E402
from _record import record_at  # noqa: E402

from octomod.gates.build_gates import antimony_to_sbml  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import assembly_edit, petab_io  # noqa: E402
from octomod.workflow_modules.assembly import engine as assembly_module  # noqa: E402
from octomod.workflow_modules.estimation import problem as estimation  # noqa: E402
from octomod.workflow_modules.model import model_space, supermodel  # noqa: E402

TRUE = {"p1": 0.3, "p2": 0.9}
SD = 0.02

ANT = """model m
  compartment cell = 1;
  species A in cell = 1;
  species B in cell = 0;
  u = 1;
  kcat = 0.3;
  J0: A -> B; kcat*u*A;
end
"""
PARAMS = [
    {
        "id": "kcat",
        "nominal_value": 0.3,
        "lb": 1e-3,
        "ub": 10.0,
        "estimate": True,
        "unit": "1/min",
        "evidence_tier": "to_be_estimated",
    },
    {"id": "u", "nominal_value": 1.0, "lb": 0.1, "ub": 10.0, "estimate": False},
]
CONDS = [("p1", "a", 1.0), ("p1", "b", 2.0), ("p2", "a", 1.0), ("p2", "b", 2.0)]
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
    # the labels are styled on purpose so nothing can parse them: the key is
    # the data's own (lig=…|pop=…)
    "conditions": [
        {
            "condition_id": f"c_{p}_{lig}",
            "maps_to_label": f"{p.upper()} cells, ligand {lig}",
            "overrides": {"u": u},
        }
        for p, lig, u in CONDS
    ],
}
KEY_BY_LABEL = {
    f"{p.upper()} cells, ligand {lig}": f"lig={lig}|pop={p}" for p, lig, _u in CONDS
}
AXIS = {
    "id": "kcat_per_population",
    "question": "Is the conversion rate the same in both populations?",
    "default": "off",
    "on_assembly_patch": {"split_parameter": {"parameter_id": "kcat", "by": "pop"}},
    "adds_parameters": [],
    "priority": 1,
}


def _values() -> dict:
    return assembly_edit.condition_attributes(ASSEMBLY, KEY_BY_LABEL)


def _long_df(seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for p, lig, u in CONDS:
        for t in (0.25, 0.5, 1.0, 2.0, 4.0, 8.0):
            for rep in (1, 2):
                rows.append(
                    {
                        "observable_label": "b",
                        "condition_label": f"{p.upper()} cells, ligand {lig}",
                        "condition_key": f"lig={lig}|pop={p}",
                        "time": t,
                        "value": 1.0 - math.exp(-TRUE[p] * u * t) + rng.normal(0.0, SD),
                        "replicate": rep,
                    }
                )
    return pd.DataFrame(rows)


class _Ctx:
    """Just the surface `_merge_to_petab` and `validate_axes` touch: a
    throwaway record (the run is one file) in `tmp`, round 0, single model."""

    def __init__(self, tmp: Path, spec=None):
        root = record_at(tmp / "run")
        root.store.create()
        self.root, self.store = root, root.store
        self.spec, self.ledger = spec, Ledger(root)
        self.round_idx, self.candidate = 0, None
        self.testcase = {"holdout": {"condition_labels": []}}

    @property
    def round(self):
        return tree.round_node(self.root, self.round_idx)

    @property
    def work(self):
        return tree.work_node(self.round, self.candidate)

    @property
    def model(self):
        return tree.model_node(self.round, self.candidate)


def _by(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """A PEtab table indexed by its id column (the record keeps it a column)."""
    return df.set_index(column) if column in df.columns else df


def test_attributes_and_resolution() -> dict:
    vals = _values()
    check(
        "attributes come from the data's key, not the styled label",
        vals.get("c_p2_b") == {"lig": "b", "pop": "p2"} and len(vals) == 4,
        str(vals),
    )
    resolved, problems = assembly_edit.resolve_split(
        {"parameter_id": "kcat", "by": "pop"}, ASSEMBLY, vals, PARAMS
    )
    check("the split resolves", resolved is not None and not problems, str(problems))
    copies = resolved["on_assembly_patch"]["split_parameter"]["copies_by_condition"]
    check(
        "one copy per population, in every condition",
        copies
        == {
            "c_p1_a": "kcat_p1",
            "c_p1_b": "kcat_p1",
            "c_p2_a": "kcat_p2",
            "c_p2_b": "kcat_p2",
        },
        str(copies),
    )
    rows = {r["id"]: r for r in resolved["adds_parameters"]}
    check(
        "each copy's row is kcat's (bounds, estimate, unit), and says what it is",
        set(rows) == {"kcat_p1", "kcat_p2"}
        and all(
            r["lb"] == 1e-3
            and r["ub"] == 10.0
            and r["estimate"] is True
            and r["unit"] == "1/min"
            and "pop=p2" in rows["kcat_p2"]["denotes"]
            for r in rows.values()
        ),
        str(rows),
    )

    def refused(args, *, params=PARAMS, asm=ASSEMBLY, trained=None, values=None):
        out, probs = assembly_edit.resolve_split(
            args, asm, values or vals, params, trained
        )
        return out is None and probs, " ".join(probs)

    for name, got, needle in (
        ("a fixed parameter", refused({"parameter_id": "u", "by": "pop"}), "fixed"),
        (
            "an attribute the data does not carry",
            refused({"parameter_id": "kcat", "by": "cell"}),
            "carry no 'cell'",
        ),
        (
            "a single value",
            refused(
                {"parameter_id": "kcat", "by": "pop"},
                values={c: {"pop": "p1"} for c in vals},
            ),
            "nothing to split",
        ),
        (
            "a value seen only in held-out conditions",
            refused(
                {"parameter_id": "kcat", "by": "pop"}, trained={"c_p1_a", "c_p1_b"}
            ),
            "only in held-out",
        ),
        (
            "a parameter already set per condition",
            refused(
                {"parameter_id": "kcat", "by": "pop"},
                asm={
                    **ASSEMBLY,
                    "conditions": [
                        dict(c, overrides={**c["overrides"], "kcat": 0.5})
                        for c in ASSEMBLY["conditions"]
                    ],
                },
            ),
            "already set per condition",
        ),
        (
            "a copy id that is taken",
            refused(
                {"parameter_id": "kcat", "by": "pop"},
                params=PARAMS
                + [
                    {
                        "id": "kcat_p2",
                        "nominal_value": 1,
                        "lb": 0.1,
                        "ub": 1,
                        "estimate": True,
                    }
                ],
            ),
            "already parameters",
        ),
    ):
        check(f"refused by name: {name}", bool(got[0]) and needle in got[1], got[1])
    return resolved


def test_validation(resolved: dict) -> None:
    tmp = Path(tempfile.mkdtemp())
    ctx = _Ctx(tmp)
    sc = {"condition_values": _values(), "base_parameters": PARAMS, "trained_ids": None}
    axes, dropped = model_space.validate_axes(
        ctx,
        [AXIS],
        ANT,
        {"kcat", "u"},
        module="revision",
        base_assembly=ASSEMBLY,
        dof=(1, 2, 1.0),
        split_context=sc,
    )
    ok = (
        axes
        and axes[0]["kind"] == "parameter_split"
        and len(axes[0]["adds_parameters"]) == 2
    )
    check(
        "validate_axes resolves the agent's two-key patch (kind parameter_split)",
        bool(ok) and not dropped,
        f"{axes} {dropped}",
    )
    check(
        "… and its DOF check counts the net cost, values - 1 (2/2 passes a limit of 1.0)",
        not dropped,
        str(dropped),
    )
    axes2, dropped2 = model_space.validate_axes(
        ctx, [AXIS], ANT, {"kcat", "u"}, module="assembly", base_assembly=ASSEMBLY
    )
    check(
        "without the data it is dropped, and says where it is proposed",
        not axes2 and dropped2 and "expansion gate" in dropped2[0]["reason"],
        str(dropped2),
    )
    patch = resolved["on_assembly_patch"]
    adds = {r["id"] for r in resolved["adds_parameters"]}
    ents = {"A", "B", "u", "kcat", "cell"}
    good = assembly_edit.validate_patch(
        patch,
        model_entities=ents,
        parameter_ids={"kcat", "u"} | adds,
        adds=adds,
        assembly=ASSEMBLY,
    )
    check("the resolved patch is valid against the assembly", good == [], str(good))
    partial = copy.deepcopy(patch)
    del partial["split_parameter"]["copies_by_condition"]["c_p1_a"]
    bad = assembly_edit.validate_patch(
        partial,
        model_entities=ents,
        parameter_ids={"kcat", "u"} | adds,
        adds=adds,
        assembly=ASSEMBLY,
    )
    check(
        "a split that misses a condition is refused before any merge",
        any("covers every condition" in p for p in bad),
        str(bad),
    )
    check(
        "targets and description",
        assembly_edit.patch_targets(patch) == ["parameter:kcat"]
        and assembly_edit.describe(patch) == "split_parameter(kcat by pop, 2 copies)",
        f"{assembly_edit.patch_targets(patch)} {assembly_edit.describe(patch)}",
    )


def test_render_and_fit(resolved: dict) -> None:
    axis = {**AXIS, **resolved}
    grouped = supermodel.enumerate_grouped(
        ANT, PARAMS, [axis], 8, t_end=10.0, keep_base=True, one_at_a_time=True
    )
    m = next(x for x in grouped["models"] if x["axes_on"] == ["kcat_per_population"])
    rows = {p["id"]: p for p in m["parameters"]}
    check(
        "the copies are tagged layer: assembly, the model is untouched",
        rows.get("kcat_p2", {}).get("layer") == "assembly"
        and m["antimony"].strip() == ANT.strip(),
        str(rows.get("kcat_p2")),
    )
    spec = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
    ok, why = model_space.ladder_check(m["antimony"], m["parameters"], 10.0, spec)
    check(
        "the pre-gate ladder does not hand an assembly-layer parameter to the simulator",
        ok,
        str(why)[:300],
    )
    with tempfile.TemporaryDirectory() as tmp_s:
        ctx = _Ctx(Path(tmp_s), spec)
        (ctx.model / "parameters").put(m["parameters"])
        sbml, err = antimony_to_sbml(m["antimony"])
        assert sbml, err
        (ctx.model / "sbml").put_text(sbml)
        petab = ctx.work / "petab"
        merged = assembly_edit.apply_overlay(ASSEMBLY, m["assembly_overlay"])
        assembly_module._merge_to_petab(ctx, merged, sbml, _long_df(), petab)
        par = _by((petab / "parameters").table(), "parameterId")
        cond = _by((petab / "conditions").table(), "conditionId")
        check(
            "both copies are estimated parameters; kcat left the table",
            {"kcat_p1", "kcat_p2"} <= set(par.index)
            and "kcat" not in par.index
            and int(par.loc["kcat_p2", "estimate"]) == 1,
            str(sorted(par.index)),
        )
        check(
            "every condition reads its population's copy",
            cond["kcat"].to_dict()
            == {
                "c_p1_a": "kcat_p1",
                "c_p1_b": "kcat_p1",
                "c_p2_a": "kcat_p2",
                "c_p2_b": "kcat_p2",
            },
            str(cond["kcat"].to_dict()),
        )
        inp = petab_io.from_work(ctx.work, ctx.model)
        prob, _pp, _ = estimation.build_problem(inp, {}, spec)
        names = list(prob.x_names)
        result = estimation.run_multistart(prob, 4, 20260925, spec)
        best = result.optimize_result.list[0]
        x_full = prob.get_full_vector(best.x, prob.x_fixed_vals)
        un = estimation.x_to_unscaled_dict(
            np.asarray(x_full, float), names, estimation.parameter_scales(inp)
        )
        check(
            "the fit moves the copies to the planted 0.3 and 0.9",
            abs(un["kcat_p1"] - TRUE["p1"]) < 0.03
            and abs(un["kcat_p2"] - TRUE["p2"]) < 0.09,
            f"kcat_p1 {un['kcat_p1']:.3f} kcat_p2 {un['kcat_p2']:.3f} fval {float(best.fval):.2f}",
        )


def main() -> int:
    resolved = test_attributes_and_resolution()
    test_validation(resolved)
    test_render_and_fit(resolved)
    return finish(
        "\nSPLIT PARAMETER",
        "\nSPLIT PARAMETER UNIT OK — one parameter, one copy per population, resolved, rendered and fitted",
    )


if __name__ == "__main__":
    sys.exit(main())
