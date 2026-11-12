"""A signal-proportional sigma on an observable that goes through an assignment rule compiles.

  1. the seam check passes the sigma written on the rule, with or without the gain, and names one
     on any other state, also a species the formula is linear in but which is not the formula;
  2. the merge writes both formulas with the rule expanded: no rule id reaches the observables
     table, and the expansion is ledgered;
  3. `assembly_sigma_through_observable` passes the written tables, on the agent's own formula read
     from the assembly, and `sigma_series` evaluates;
  4. a noise on another state is refused at the merge with the text the seam re-asks with, and
     fails the gate by name; one on the formula without its gain is refused at the merge where
     AMICI cannot solve through the gain; supplied tables (no agent's formula) keep AMICI's rule;
  5. at full effort only: the written problem compiles with AMICI and the objective at the nominals
     is finite.

    uv run python tests/sigma_through_rule_unit.py
"""

from __future__ import annotations

import logging
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.CRITICAL)

from _harness import check, finish, quick_tier  # noqa: E402
from _record import ledger_rows, record_at  # noqa: E402

from octomod.gates.petab_gates import (  # noqa: E402
    PetabTables,
    make_petab_gates,
    sigma_state_problem,
)
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.orchestration.run_context import RunContext  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import engine as S3  # noqa: E402
from octomod.workflow_modules.assembly import petab_io  # noqa: E402

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
GATE = "assembly_sigma_through_observable"
# `total` is an assignment rule on a parameter: the observable goes through it
ANT = """
model sigma_through_rule
  species A, B;
  A = 10; B = 0;
  kdeg = 0.3;
  total := A + 2*B;
  J0: A -> B; kdeg*A;
end
"""
KDEG, A0 = 0.3, 10.0
TIMES = [0.0, 1.0, 2.0, 4.0]
GAIN = {0.0: 1.0, 1.0: 2.0, 2.0: 0.5, 4.0: 4.0}
GOOD_NOISE = "sigma_abs + sigma_rel * sc_tot * total"
# the same prediction without its gain
UNGAINED_NOISE = "sigma_abs + sigma_rel * total"
# `A` is one of the two species `total` sums: not this observable's formula
BAD_NOISE = "sigma_abs + sigma_rel * A"
# a formula linear in `B` that is not `B`: AMICI would solve for it, the
# workflow's rule does not
LINEAR_FORMULA, LINEAR_NOISE = "2 * B", "sigma_abs + sigma_rel * B"
STRICT = "other than through this observable's own formula"


class Ctx(RunContext):
    """A RunContext on a throwaway record, round 0, single model: what the
    merge and the S3 battery read."""

    def __init__(self, root: Node):
        super().__init__(
            root=root,
            testcase_dir=REPO / "testcase" / "toy_phos",
            spec=SPEC,
            ledger=Ledger(root),
            backend="stub",
            auto=False,
        )

    @property
    def testcase(self) -> dict:
        return {"holdout": {"condition_labels": []}}


def _sbml() -> str:
    import antimony

    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(ANT) >= 0, antimony.getLastError()
    return antimony.getSBMLString(antimony.getMainModuleName())


def _reply(noise: str, formula: str = "total") -> dict:
    return {
        "observables": [
            {
                "observable_id": "obs_total",
                "maps_to_label": "ms_total",
                "formula": formula,
                "transformation": "lin",
                "noise": {
                    "distribution": "normal",
                    "formula": noise,
                    "estimate_sigma": True,
                },
                "scaling": {
                    "mode": "factor",
                    "scale_parameter": "sc_tot",
                    "per": "timepoint",
                },
                "rationale": "-",
            }
        ]
    }


def _long_df() -> pd.DataFrame:
    rows = []
    for t in TIMES:
        a = A0 * np.exp(-KDEG * t)
        rows.append(
            {
                "observable_label": "ms_total",
                "condition_label": "c0",
                "condition_key": "c0",
                "time": t,
                "value": GAIN[t] * (a + 2 * (A0 - a)),
            }
        )
    return pd.DataFrame(rows)


def _problems(noise: str, sbml: str, formula: str = "total") -> list[str]:
    summary = S3._model_summary(sbml)
    rules = summary["assignment_rule_formulas"]
    return S3._observation_reply_problems(
        _reply(noise, formula),
        ["ms_total"],
        set(summary["species"]) | set(summary["parameters"]),
        rule_formulas=rules,
        states=set(summary["species"]) - set(rules),
    )


def _merge(noise: str, tmp: Path, formula: str = "total") -> Ctx:
    """A fresh record in `tmp`, and the merge of the reply into its problem."""
    root = record_at(tmp / "sigma_through_rule")
    root.store.create()
    ctx = Ctx(root)
    sbml = _sbml()
    (ctx.model / "sbml").put_text(sbml)
    (ctx.model / "parameters").put(
        [
            {
                "id": "kdeg",
                "nominal_value": KDEG,
                "lb": 1e-3,
                "ub": 1e3,
                "estimate": True,
            }
        ]
    )
    obs, noise_block, scaling = S3.split_observation_reply(_reply(noise, formula))
    assembly = {
        "observables": obs,
        "noise": noise_block,
        "scaling": scaling,
        "conditions": [
            {
                "condition_id": "c0",
                "maps_to_label": "c0",
                "overrides": {},
                "preequilibration": False,
            }
        ],
    }
    # beside the tables, as the module writes it before the merge
    (ctx.work / "assembly").put(assembly)
    S3._merge_to_petab(ctx, assembly, sbml, _long_df(), ctx.work / "petab")
    return ctx


def _tables(ctx: Ctx, **changed: pd.DataFrame) -> PetabTables:
    """The merged problem as the battery reads it, with `changed` tables in
    place of the record's."""
    inp = petab_io.from_work(ctx.work, ctx.model)
    return PetabTables.from_input(inp.with_tables(**changed) if changed else inp)


def _gate(tables: PetabTables, cores: dict[str, str] | None = None):
    fn = next(
        g for g in make_petab_gates(tables, SPEC, cores=cores) if g.gate_id == GATE
    )
    return fn()


def test_the_seam_check() -> None:
    sbml = _sbml()
    check(
        "the model summary carries the rule's formula",
        S3._model_summary(sbml)["assignment_rule_formulas"] == {"total": "A + 2 * B"},
        str(S3._model_summary(sbml)["assignment_rule_formulas"]),
    )
    good = _problems(GOOD_NOISE, sbml)
    check(
        "a sigma on the rule, scaled by the gain, passes the seam", not good, str(good)
    )
    ungained = _problems(UNGAINED_NOISE, sbml)
    check(
        "and without the gain, too: the reply alone names no gain",
        not ungained,
        str(ungained),
    )
    bad = _problems(BAD_NOISE, sbml)
    check(
        "a sigma on another state is named at the seam, with what to write",
        len(bad) == 1
        and "obs_total" in bad[0]
        and "['A']" in bad[0]
        and STRICT in bad[0]
        and "sigma_abs + sigma_rel * <this observable's formula>" in bad[0],
        str(bad),
    )
    linear = _problems(LINEAR_NOISE, sbml, LINEAR_FORMULA)
    check(
        "a sigma on the species a linear formula names, not the formula, is named "
        "at the seam",
        len(linear) == 1 and "['B']" in linear[0] and STRICT in linear[0],
        str(linear),
    )
    check(
        "which AMICI's rule, for tables nobody in this run wrote, accepts",
        sigma_state_problem(LINEAR_NOISE, LINEAR_FORMULA, {"A", "B"}) is None,
    )


def test_the_merge_writes_no_rule_id(tmp: Path) -> Ctx:
    ctx = _merge(GOOD_NOISE, tmp)
    obs = (ctx.work / "petab/observables").table()
    written = " ".join(
        str(v) for col in ("observableFormula", "noiseFormula") for v in obs[col]
    )
    check(
        "the written observables table carries no rule id",
        not re.search(r"\btotal\b", written),
        written[:200],
    )
    check(
        "both formulas are written in species",
        all("A + 2 * B" in str(f) for f in obs["observableFormula"])
        and all("A + 2 * B" in str(f) for f in obs["noiseFormula"]),
        written[:200],
    )
    notes = [str(e.get("note", "")) for e in ledger_rows(ctx.root)]
    expanded = [n for n in notes if n.startswith("assignment-rule symbols expanded")]
    check(
        "the expansion is ledgered once for the merge",
        len(expanded) == 1
        and "1 observable and 1 noise formulas" in expanded[0]
        and "total" in expanded[0],
        str(expanded),
    )
    tables = _tables(ctx)
    cores = S3._assembled_cores(ctx, _sbml())
    check(
        "the agent's own formula is read from the assembly, rule expanded",
        cores == {"obs_total": "(A + 2 * B)"},
        str(cores),
    )
    res = _gate(tables, cores)
    check(f"{GATE} passes the written tables", res.passed, res.detail)
    meas = tables.measurements
    series_ok, per_point_ok = True, True
    for oid, grp in meas.groupby("observableId"):
        times = np.sort(grp["time"].unique()).astype(float)
        sig = tables.sigma_series(str(oid), "c0", times)
        y = tables.simulate_observables("c0", times)[str(oid)]
        # nominals: sigma_abs = sigma_rel = 1, so sigma = 1 + y at every point
        series_ok &= bool(np.all(np.isfinite(sig)) and np.all(sig > 0))
        per_point_ok &= bool(np.allclose(sig, 1.0 + y, rtol=1e-6))
    check("PetabTables.sigma_series evaluates, finite and positive", series_ok)
    check("and it is sigma_abs + sigma_rel * y at every point", per_point_ok)
    return ctx


def _refusal(noise: str, formula: str = "total") -> S3.MergeRefusal | None:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            _merge(noise, Path(tmp), formula)
        except S3.MergeRefusal as e:
            return e
    return None


def test_a_sigma_on_another_state(ctx: Ctx) -> None:
    sbml = _sbml()
    for what, noise, formula, state in (
        ("a species the rule sums", BAD_NOISE, "total", "A"),
        ("the species a linear formula names", LINEAR_NOISE, LINEAR_FORMULA, "B"),
    ):
        refusal = _refusal(noise, formula)
        seam = _problems(noise, sbml, formula)
        check(
            f"the merge refuses a sigma on {what} as assembly_merge_noise, naming the "
            f"observable and the state",
            refusal is not None
            and refusal.gate_id == "assembly_merge_noise"
            and f"observable obs_total depends on ['{state}']" in refusal.detail
            and STRICT in refusal.detail,
            str(refusal),
        )
        check(
            "with the text the seam re-asks the agent with",
            len(seam) == 1
            and refusal is not None
            and refusal.detail.split(" depends on ", 1)[1] in seam[0],
            f"{seam} · {refusal}",
        )
    # under a per-timepoint gain, AMICI reaches the prediction from a sum of
    # species only by solving it for one of them, which does not succeed for
    # each: never more than AMICI accepts, so the whole prediction is asked for
    ungained = _refusal(UNGAINED_NOISE)
    check(
        "a sigma on the formula without its gain is refused at the merge, with "
        "the whole prediction to write",
        ungained is not None
        and ungained.gate_id == "assembly_merge_noise"
        and "without its gain" in ungained.detail
        and "Write it on the whole prediction" in ungained.detail,
        str(ungained),
    )

    # the gate on tables that say so (the record's problem with its
    # observables table changed in memory)
    obs = (ctx.work / "petab/observables").table()
    obs["noiseFormula"] = [
        f"noiseParameter1_{oid} + noiseParameter2_{oid} * A"
        for oid in obs["observableId"]
    ]
    tables = _tables(ctx, observables=obs)
    res = _gate(tables, S3._assembled_cores(ctx, sbml))
    check(
        f"{GATE} fails it by name on the agent's formula: the assembly's "
        f"observable, once for its {len(obs)} flattened copies",
        not res.passed
        and "observable obs_total depends on ['A']" in res.detail
        and STRICT in res.detail
        and res.detail.count("The noise formula") == 1,
        res.detail[:240],
    )
    # as a supplied problem could say it: AMICI's rule, and its own text
    res = _gate(tables)
    check(
        f"{GATE} on supplied tables fails it by AMICI's rule",
        not res.passed
        and "observable obs_total depends on ['A']" in res.detail
        and STRICT not in res.detail
        and "solvable" in res.detail,
        res.detail[:240],
    )
    # a formula linear in B with the sigma on B: AMICI compiles it, so a
    # supplied problem passes; the agent's formula is refused
    obs["observableFormula"] = [
        f"observableParameter1_{oid} * (2 * B)" for oid in obs["observableId"]
    ]
    obs["noiseFormula"] = [
        f"noiseParameter1_{oid} + noiseParameter2_{oid} * B"
        for oid in obs["observableId"]
    ]
    tables = _tables(ctx, observables=obs)
    res = _gate(tables)
    check(
        f"{GATE} on supplied tables passes a sigma AMICI can solve for",
        res.passed,
        res.detail[:240],
    )
    res = _gate(tables, {"obs_total": "2 * B"})
    check(
        f"{GATE} on the agent's formula refuses it",
        not res.passed and "['B']" in res.detail and STRICT in res.detail,
        res.detail[:240],
    )


def test_it_compiles(ctx: Ctx) -> None:
    """Full tier: the written problem through the compile the estimation uses."""
    if quick_tier():
        print(
            "  – AMICI compile skipped under the reduced-effort overlay (full effort only)"
        )
        return
    from octomod.workflow_modules.estimation.problem import build_problem

    prob, pp, compile_s = build_problem(
        petab_io.from_work(ctx.work, ctx.model), {}, SPEC
    )
    free = [prob.x_names[i] for i in prob.x_free_indices]
    nominal = dict(zip(pp.x_ids, pp.x_nominal_scaled, strict=True))
    x = np.array([nominal[n] for n in free])
    out = prob.objective(x, return_dict=True, sensi_orders=(0, 1))
    check(
        "the problem compiles and the objective and its gradient at the nominals "
        "are finite",
        np.isfinite(out["fval"]) and np.all(np.isfinite(out["grad"])),
        f"compile {compile_s:.0f} s, fval {out['fval']:.6g}, free {free}",
    )


if __name__ == "__main__":
    test_the_seam_check()
    with tempfile.TemporaryDirectory() as tmp:
        merged = test_the_merge_writes_no_rule_id(Path(tmp))
        test_it_compiles(merged)
        test_a_sigma_on_another_state(merged)
    sys.exit(
        finish(
            "\nSIGMA THROUGH RULE UNIT",
            "SIGMA THROUGH RULE UNIT OK — the rule is expanded in both formulas, the "
            "sigma compiles through its observable, and one on any other state is "
            "refused by name",
        )
    )
