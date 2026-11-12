"""An `add_offset` axis renders an estimated offset into the PEtab problem.

A candidate's observation overlay is applied to the shared assembly and merged
the way S3 does it (`_with_overlay`, then `_merge_to_petab`):

  1. `add_offset` on an unscaled observable makes it `offset`, on a scaled one
     `factor_offset`, each with its own offset parameter id;
  2. the parameter table carries one row per offset: linear scale, the spec's
     `assembly_defaults.offset_bounds`, nominal 0, estimated;
  3. each observable formula adds its offset through an observable-parameter
     placeholder, after the scale factor when there is one, and every
     measurement row names the real offset id in `observableParameters`;
  4. an offset id the agent declared is the one rendered, and the problem is
     petablint-clean.

    uv run python tests/offset_row_unit.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.CRITICAL)

from _harness import check, finish  # noqa: E402
from _record import rnd, temp_record  # noqa: E402

from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import engine as S3  # noqa: E402
from octomod.workflow_modules.assembly import petab_io  # noqa: E402

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
TIMES = [0.0, 1.0, 2.0, 4.0]
# bounds no default spells, so a row that ignores the spec cannot pass
OFFSET_BOUNDS = [-7.5, 42.0]


class OffsetSpec:
    """default.yaml with its own offset bounds."""

    def __init__(self, base):
        self.base = base

    def get(self, k, d=None):
        if k == "assembly_defaults.offset_bounds":
            return OFFSET_BOUNDS
        return self.base.get(k, d)

    def require(self, k):
        if k == "assembly_defaults.offset_bounds":
            return OFFSET_BOUNDS
        return self.base.require(k)


class Ctx:
    """What the overlay and the merge read off a RunContext — on a record
    (`root` is the run record's root node; the candidate's unit of work
    is `rounds/round_0/candidates/c_offset`)."""

    def __init__(self, root: Node, spec):
        self.root, self.round_idx, self.candidate = root, 0, "c_offset"
        self.spec, self.ledger, self.cache = spec, Ledger(root), {}

    @property
    def round(self) -> Node:
        return rnd(self.root, self.round_idx)

    @property
    def work(self) -> Node:
        return tree.work_node(self.round, self.candidate)

    @property
    def model(self) -> Node:
        return tree.model_node(self.round, self.candidate)

    @property
    def testcase(self) -> dict:
        return {"holdout": {"condition_labels": []}}


def _sbml() -> str:
    import antimony

    antimony.loadAntimonyString("model m; A=10; B=0; J0: A->B; kdeg*A; kdeg=0.3; end")
    return antimony.getSBMLString(antimony.getMainModuleName())


def _assembly(offset_parameter: str | None = None) -> dict:
    """Two observables: `obs_a` unscaled, `obs_b` with one scale factor."""
    scaling_a = {"observable_id": "obs_a", "mode": "none"}
    if offset_parameter:
        scaling_a["offset_parameter"] = offset_parameter
    return {
        "observables": [
            {
                "observable_id": oid,
                "maps_to_label": lab,
                "formula": sp,
                "transformation": "lin",
            }
            for oid, lab, sp in (("obs_a", "peakA", "A"), ("obs_b", "peakB", "B"))
        ],
        "noise": [
            {
                "observable_id": oid,
                "distribution": "normal",
                "formula": f"sigma_{oid}",
                "estimate_sigma": True,
            }
            for oid in ("obs_a", "obs_b")
        ],
        "scaling": [
            scaling_a,
            {"observable_id": "obs_b", "mode": "factor", "per": "observable"},
        ],
        "conditions": [
            {
                "condition_id": "c0",
                "maps_to_label": "c0",
                "overrides": {},
                "preequilibration": False,
            }
        ],
    }


def _long_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "observable_label": lab,
                "condition_label": "c0",
                "condition_key": "c0",
                "time": t,
                "value": 1.0 + t,
            }
            for t in TIMES
            for lab in ("peakA", "peakB")
        ]
    )


# one axis by data label, one by observable id: both forms resolve
OVERLAY = [
    {"add_offset": {"observable_label": "peakA"}},
    {"add_offset": {"observable_id": "obs_b"}},
]


def _render(root: Node, spec, offset_parameter: str | None = None):
    """The candidate's overlay applied and merged as S3 does: (assembly, the
    unit of work's `petab` group)."""
    ctx = Ctx(root, spec)
    sbml = _sbml()
    (ctx.model / "parameters").put(
        [{"id": "kdeg", "nominal_value": 0.3, "lb": 1e-3, "ub": 1e3, "estimate": True}],
    )
    (ctx.model / "assembly_overlay").put(OVERLAY)
    pdir = ctx.work / "petab"
    assembly = S3._with_overlay(ctx, _assembly(offset_parameter))
    S3._merge_to_petab(ctx, assembly, sbml, _long_df(), pdir)
    return assembly, pdir


def _tsv(pdir: Node, name: str) -> pd.DataFrame:
    """A PEtab table of the record's `petab` group (`parameters.tsv` → `parameters`)."""
    return (pdir / name.removesuffix(".tsv")).table()


def test_the_patch_sets_the_mode(assembly: dict) -> None:
    modes = {s["observable_id"]: s for s in assembly["scaling"]}
    check(
        "add_offset on an unscaled observable makes it `offset`",
        modes["obs_a"].get("mode") == "offset"
        and modes["obs_a"].get("offset_parameter") == "off_obs_a",
        str(modes["obs_a"]),
    )
    check(
        "add_offset on a scaled observable keeps the factor: `factor_offset`",
        modes["obs_b"].get("mode") == "factor_offset"
        and modes["obs_b"].get("offset_parameter") == "off_obs_b",
        str(modes["obs_b"]),
    )


def test_the_parameter_rows(pdir: Node) -> None:
    par = _tsv(pdir, "parameters.tsv").set_index("parameterId")
    for pid in ("off_obs_a", "off_obs_b"):
        row = par.loc[pid].to_dict() if pid in par.index else {}
        check(
            f"{pid}: linear scale, the spec's offset bounds, nominal 0, estimated",
            row.get("parameterScale") == "lin"
            and [row.get("lowerBound"), row.get("upperBound")] == OFFSET_BOUNDS
            and row.get("nominalValue") == 0.0
            and row.get("estimate") == 1,
            str(row) if row else f"no row; ids {sorted(par.index)}",
        )
    check(
        "the scale factor beside it keeps its own log10 row",
        "sc_obs_b" in par.index and par.loc["sc_obs_b", "parameterScale"] == "log10",
        str(sorted(par.index)),
    )


def test_the_formulas_and_the_rows(pdir: Node) -> None:
    obs = _tsv(pdir, "observables.tsv").set_index("observableId")
    check(
        "obs_a adds its offset through placeholder 1",
        obs.loc["obs_a", "observableFormula"] == "A + observableParameter1_obs_a",
        str(obs.loc["obs_a", "observableFormula"]),
    )
    check(
        "obs_b adds its offset after the scale factor, through placeholder 2",
        obs.loc["obs_b", "observableFormula"]
        == "observableParameter1_obs_b * (B) + observableParameter2_obs_b",
        str(obs.loc["obs_b", "observableFormula"]),
    )
    meas = _tsv(pdir, "measurements.tsv")
    cells = {
        oid: sorted(set(meas.loc[meas["observableId"] == oid, "observableParameters"]))
        for oid in ("obs_a", "obs_b")
    }
    check(
        "every measurement row names the real offset id, in placeholder order",
        cells == {"obs_a": ["off_obs_a"], "obs_b": ["sc_obs_b;off_obs_b"]},
        str(cells),
    )


def test_a_declared_offset_id_and_lint(root: Node) -> None:
    _assembly_out, pdir = _render(root, SPEC, offset_parameter="bg_A")
    par = _tsv(pdir, "parameters.tsv").set_index("parameterId")
    meas = _tsv(pdir, "measurements.tsv")
    a_cells = set(meas.loc[meas["observableId"] == "obs_a", "observableParameters"])
    lb, ub = SPEC.require("assembly_defaults.offset_bounds")
    check(
        "the agent's own offset id is the one rendered, at the default bounds",
        "bg_A" in par.index
        and "off_obs_a" not in par.index
        and a_cells == {"bg_A"}
        and [par.loc["bg_A", "lowerBound"], par.loc["bg_A", "upperBound"]]
        == [float(lb), float(ub)],
        f"{sorted(par.index)} · {a_cells}",
    )
    import petab.v1 as pv

    # the problem from the record (its yaml, tables and the model's SBML)
    has_yaml = (pdir / "problem_yaml").exists()
    problem = petab_io.load_problem(
        petab_io.from_record(pdir, model=pdir.parent / "model")
    )
    check(
        "the rendered problem is petablint-clean",
        has_yaml and not pv.lint.lint_problem(problem),
    )


def main() -> int:
    with temp_record("own_bounds") as own, temp_record("declared_id") as declared:
        assembly, pdir = _render(own, OffsetSpec(SPEC))
        applied = (pdir.parent / "assembly_overlay_applied").get()
        check(
            "the overlay the candidate carries is recorded as applied",
            [a["patch"] for a in applied] == OVERLAY,
            str(applied),
        )
        test_the_patch_sets_the_mode(assembly)
        test_the_parameter_rows(pdir)
        test_the_formulas_and_the_rows(pdir)
        test_a_declared_offset_id_and_lint(declared)
    return finish(
        "\nOFFSET ROW",
        "\nOFFSET ROW UNIT OK — an add_offset axis renders an estimated, linear, "
        "spec-bounded offset row, and every formula and measurement row carries it",
    )


if __name__ == "__main__":
    sys.exit(main())
