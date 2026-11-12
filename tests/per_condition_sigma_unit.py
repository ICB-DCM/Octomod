"""One sigma per condition (`noise.per: condition`), asserted on a real compile.

`noise.per: condition` renders `sigma_<obs>_<cond>` per condition and fills PEtab's
noiseParameters row by row, the way `per: condition` works for a scale factor.

  1. grammar: the contract declares it; `change_noise_model` takes `new_per`; `apply_patch` sets it;
  2. render: an estimated sigma per training condition, none for the held-out one, lint clean;
  3. readers: `sigma_series` resolves per condition, `resolve_sigmas` has no single number;
  4. fit: a seeded multistart recovers the planted asymmetry; each arm is judged separately.

    uv run python tests/per_condition_sigma_unit.py
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
from _record import rnd, temp_record  # noqa: E402

from octomod.agents import ROLES  # noqa: E402
from octomod.gates.petab_gates import (  # noqa: E402
    PetabTables,
    per_condition_sigmas,
    resolve_sigmas,
)
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import assembly_edit, petab_io  # noqa: E402
from octomod.workflow_modules.assembly import engine as assembly_module  # noqa: E402
from octomod.workflow_modules.estimation import problem as estimation  # noqa: E402
from octomod.workflow_modules.evaluation.engine import (  # noqa: E402
    structural_misfit_evidence,
)

SD_LOW, SD_MID = 0.05, 0.30  # the planted asymmetry between the two training arms
K = 0.3


def _sbml() -> str:
    import antimony

    antimony.clearPreviousLoads()
    antimony.loadAntimonyString(
        "model m\n  compartment cell = 1;\n  species A in cell = 1;\n"
        "  species B in cell = 0;\n  u = 1;\n  kcat = 0.3;\n  J0: A -> B; kcat*u*A;\nend"
    )
    return antimony.getSBMLString(antimony.getMainModuleName())


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
            "per": "condition",
        }
    ],
    "scaling": [{"observable_id": "obs_b", "mode": "none"}],
    "conditions": [
        {"condition_id": "c_low", "maps_to_label": "u=1", "overrides": {"u": 1.0}},
        {"condition_id": "c_mid", "maps_to_label": "u=2", "overrides": {"u": 2.0}},
        {"condition_id": "c_hold", "maps_to_label": "u=3", "overrides": {"u": 3.0}},
    ],
}


def _long_df(seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for u, sd in ((1.0, SD_LOW), (2.0, SD_MID), (3.0, 0.1)):
        for t in (0.5, 1.0, 2.0, 4.0, 8.0):
            mean = 1.0 - math.exp(-K * u * t)
            for rep in (1, 2, 3):
                rows.append(
                    {
                        "observable_label": "b",
                        "condition_label": f"u={u:g}",
                        "condition_key": f"u={u:g}",
                        "time": t,
                        "value": mean + rng.normal(0.0, sd),
                        "replicate": rep,
                    }
                )
    return pd.DataFrame(rows)


class _Ctx:
    """Just the surface `_merge_to_petab` touches — on a record (`root` is
    the run record's root node; a single-model round)."""

    def __init__(self, root, spec):
        self.root = root
        self.spec = spec
        self.ledger = Ledger(root)
        self.round_idx = 0
        self.candidate = None
        self.testcase = {"holdout": {"condition_labels": ["u=3"]}}

    @property
    def round(self):
        return rnd(self.root, self.round_idx)

    @property
    def work(self):
        return tree.work_node(self.round, self.candidate)

    @property
    def model(self):
        return tree.model_node(self.round, self.candidate)


def test_grammar() -> None:
    contract = ROLES["observation"].contract
    check(
        "the observation contract declares noise.per with both values",
        '"per": "observable|condition"' in contract and "noise.per" in contract,
    )
    check(
        "the expansion agent is offered the axis form (new_per)",
        "new_per" in ROLES["revision"].contract,
    )
    ents, pars = {"A", "B", "u", "kcat"}, {"kcat", "sigma_obs_b"}
    ok = assembly_edit.validate_patch(
        {"change_noise_model": {"observable_id": "obs_b", "new_per": "condition"}},
        model_entities=ents,
        parameter_ids=pars,
        assembly=ASSEMBLY,
    )
    check("`new_per: condition` alone is a valid change_noise_model", ok == [], str(ok))
    bad = assembly_edit.validate_patch(
        {"change_noise_model": {"observable_id": "obs_b", "new_per": "donor"}},
        model_entities=ents,
        parameter_ids=pars,
        assembly=ASSEMBLY,
    )
    check(
        "an unknown `new_per` is refused naming the legal values",
        any("new_per" in p and "condition" in p for p in bad),
        str(bad),
    )
    asm = {**ASSEMBLY, "noise": [{**ASSEMBLY["noise"][0], "per": "observable"}]}
    out = assembly_edit.apply_patch(
        asm, {"change_noise_model": {"observable_id": "obs_b", "new_per": "condition"}}
    )
    check(
        "apply_patch sets per on the noise block and touches nothing else",
        out["noise"][0]["per"] == "condition"
        and out["noise"][0]["formula"] == "sigma_obs_b"
        and asm["noise"][0]["per"] == "observable",
    )


def test_render_readers_and_fit() -> None:
    spec = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
    with temp_record() as root:
        ctx = _Ctx(root, spec)
        (ctx.model / "parameters").put(
            [
                {
                    "id": "kcat",
                    "lb": 1e-3,
                    "ub": 10.0,
                    "nominal_value": 0.3,
                    "estimate": True,
                }
            ],
        )
        sbml = _sbml()
        long_df = _long_df()
        petab_dir = ctx.work / "petab"  # the unit of work's `petab` group
        assembly_module._merge_to_petab(ctx, ASSEMBLY, sbml, long_df, petab_dir)

        par = (petab_dir / "parameters").table().set_index("parameterId")
        meas = (petab_dir / "measurements").table()
        hold = (petab_dir / "holdout_measurements").table()
        obs = (petab_dir / "observables").table()
        check(
            "two ESTIMATED sigma rows, one per training condition",
            {"sigma_obs_b_c_low", "sigma_obs_b_c_mid"} <= set(par.index)
            and int(par.loc["sigma_obs_b_c_low", "estimate"]) == 1
            and int(par.loc["sigma_obs_b_c_mid", "estimate"]) == 1,
            str(sorted(par.index)),
        )
        check(
            "the held-out condition gets NO sigma parameter (petablint forbids an "
            "unreferenced one; T2' uses the replicate floor)",
            "sigma_obs_b_c_hold" not in par.index,
            str(sorted(par.index)),
        )
        check(
            "no shared sigma_obs_b row remains",
            "sigma_obs_b" not in par.index,
        )
        by_row = dict(
            zip(meas["simulationConditionId"], meas["noiseParameters"], strict=False)
        )
        check(
            "every training row names ITS condition's sigma",
            by_row == {"c_low": "sigma_obs_b_c_low", "c_mid": "sigma_obs_b_c_mid"}
            and meas["noiseParameters"].notna().all(),
            str(by_row),
        )
        check(
            "held-out rows name the held-out sigma",
            set(hold["noiseParameters"]) == {"sigma_obs_b_c_hold"},
            str(set(hold["noiseParameters"])),
        )
        check(
            "the noiseFormula keeps the canonical placeholder",
            obs["noiseFormula"].tolist() == ["noiseParameter1_obs_b"],
            str(obs["noiseFormula"].tolist()),
        )
        rows = [x for x in ctx.ledger.entries() if x.get("noise_per_condition")]
        check(
            "the assembly ledgers the choice: 2 estimated sigmas, each in k, held-out unfitted",
            len(rows) == 1
            and "2 estimated" in rows[0]["note"]
            and "c_hold" in rows[0]["note"]
            and "no sigma parameter" in rows[0]["note"],
            rows[0]["note"][:160] if rows else "no row",
        )
        import petab.v1 as petab

        # the problem from the record: yaml, tables and the model's SBML
        inp = petab_io.from_work(ctx.work, ctx.model)
        problem = petab_io.load_problem(inp)
        check(
            "petablint accepts the problem",
            (petab_dir / "problem_yaml").exists()
            and not petab.lint.lint_problem(problem),
        )

        # -- the readers ------------------------------------------------------
        tables = PetabTables(
            observables=obs,
            conditions=(petab_dir / "conditions").table(),
            measurements=meas,
            parameters=par.reset_index(),
            sbml=sbml,
        )
        values = {"sigma_obs_b_c_low": 0.07, "sigma_obs_b_c_mid": 0.29, "kcat": 0.3}
        s_low = tables.sigma_series("obs_b", "c_low", np.array([1.0, 2.0]), values)
        s_mid = tables.sigma_series("obs_b", "c_mid", np.array([1.0, 2.0]), values)
        check(
            "sigma_series resolves each condition to ITS parameter",
            np.allclose(s_low, 0.07) and np.allclose(s_mid, 0.29),
            f"{s_low} {s_mid}",
        )
        # a noise formula may also carry the observable's own placeholders
        # (PEtab's flattening writes `observableParameter1_<obs> * noiseParameter1_<obs>`)
        scaled = PetabTables(
            observables=obs.assign(
                noiseFormula="observableParameter1_obs_b * noiseParameter1_obs_b"
            ),
            conditions=tables.conditions,
            measurements=meas.assign(observableParameters="xi_b"),
            parameters=par.reset_index(),
            sbml=sbml,
        )
        s_scaled = scaled.sigma_series(
            "obs_b", "c_low", np.array([1.0, 2.0]), {**values, "xi_b": 2.0}
        )
        check(
            "a noise formula's observable-parameter placeholder resolves too",
            scaled.noise_expression("obs_b", "c_low") == "xi_b * sigma_obs_b_c_low"
            and np.allclose(s_scaled, 0.14),
            f"{scaled.noise_expression('obs_b', 'c_low')} {s_scaled}",
        )
        one = resolve_sigmas(tables, values=values)
        check(
            "resolve_sigmas says there is no single number (nan), as for state-dependent noise",
            "obs_b" in one and math.isnan(one["obs_b"]),
            str(one),
        )
        pc = per_condition_sigmas(tables, values=values)
        check(
            "per_condition_sigmas gives both, keyed by condition",
            pc == {"obs_b": {"c_low": 0.07, "c_mid": 0.29}},
            str(pc),
        )

        # -- the fit: compile, recover the planted asymmetry -------------------
        prob, _pp, _ = estimation.build_problem(inp, {}, spec)
        names = list(prob.x_names)
        check(
            "both training sigmas are FREE parameters of the built problem",
            {"sigma_obs_b_c_low", "sigma_obs_b_c_mid"}
            <= {names[i] for i in prob.x_free_indices}
            and "sigma_obs_b_c_hold" not in names,
            f"free={[names[i] for i in prob.x_free_indices]}",
        )
        result = estimation.run_multistart(prob, 4, 20260914, spec)
        best = result.optimize_result.list[0]
        check(
            "the multistart reaches a finite optimum",
            best.fval is not None and math.isfinite(float(best.fval)),
            str(best.fval),
        )
        x_full = prob.get_full_vector(best.x, prob.x_fixed_vals)
        unscaled = estimation.x_to_unscaled_dict(
            np.asarray(x_full, float), names, estimation.parameter_scales(inp)
        )
        lo, mid = unscaled["sigma_obs_b_c_low"], unscaled["sigma_obs_b_c_mid"]
        check(
            f"the fitted sigmas recover the planted asymmetry ({SD_LOW} vs {SD_MID}): mid/low > 2.5",
            mid / lo > 2.5
            and 0.3 * SD_LOW < lo < 3 * SD_LOW
            and 0.4 * SD_MID < mid < 2.5 * SD_MID,
            f"low {lo:.3f} mid {mid:.3f} kcat {unscaled['kcat']:.3f}",
        )
        # -- the misfit evidence judges each arm against the floor -------------
        train = long_df[long_df["condition_label"] != "u=3"]
        ev = structural_misfit_evidence(
            tables,
            unscaled,
            train,
            [],
            spec,
            obs_labels={"obs_b": "b"},
            cond_labels={"c_low": "u=1", "c_mid": "u=2"},
        )
        recs = {
            r.get("condition"): r
            for r in (ev.get("signals") or {}).get("sigma_vs_floor") or []
        }
        check(
            "sigma_vs_floor carries one record per condition, against the pooled floor",
            set(recs) == {"c_low", "c_mid"}
            and all("floor_dof" in r for r in recs.values()),
            str(list(recs)),
        )
        if set(recs) == {"c_low", "c_mid"}:
            check(
                "the noisy arm's ratio to the floor is the larger one",
                recs["c_mid"]["ratio"] > recs["c_low"]["ratio"],
                f"low {recs['c_low']['ratio']} mid {recs['c_mid']['ratio']}",
            )


def main() -> int:
    test_grammar()
    test_render_readers_and_fit()
    return finish(
        "\nPER-CONDITION SIGMA",
        "\nper-condition sigma: declared, rendered, compiled, recovered",
    )


if __name__ == "__main__":
    sys.exit(main())
