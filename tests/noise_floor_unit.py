"""The replicate noise floor is pooled over every replicate, whatever the design.

  1. three replicates per cell with a planted SD come back as that SD, with its dof;
  2. donors that never share a cell: a first-pair estimator finds nothing, pooling does;
  3. through `structural_misfit_evidence`, `sigma_vs_floor` carries the floor and dof;
  4. the post-fit noise-model gate that rejects the assumed noise model says
     passed=False (advisory, not blocking), and passes when the residuals fit.

    uv run python tests/noise_floor_unit.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.WARNING)

from _harness import check, finish  # noqa: E402

from octomod.gates.petab_gates import PetabTables  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.evaluation.engine import (  # noqa: E402
    _noise_model_check,
    _post_fit_gates,
    replicate_noise_floors,
    sim_group,
    structural_misfit_evidence,
)

PETAB = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"
SD = 0.4


def _long(donors_by_cond: dict[str, list[int]], seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for cond, donors in donors_by_cond.items():
        for t in (0.0, 5.0, 10.0, 20.0, 40.0, 60.0):
            mean = 5.0 * (1 - np.exp(-t / 15.0)) + (0.5 if cond == "dose=1" else 0.0)
            for d in donors:
                rows.append(
                    {
                        "observable_label": "pR_au",
                        "condition_label": cond,
                        "time": t,
                        "value": mean + rng.normal(0.0, SD),
                        "replicate": d,
                    }
                )
    return pd.DataFrame(rows)


def _old_first_pair_floor(long_df: pd.DataFrame) -> dict:
    """A first-two-replicate-columns estimator, as the reference to compare with."""
    out = {}
    for label, grp in long_df.groupby("observable_label"):
        wide = grp.pivot_table(
            index=["condition_label", "time"], columns="replicate", values="value"
        )
        if wide.shape[1] < 2:
            continue
        diff = (wide.iloc[:, 0] - wide.iloc[:, 1]).dropna().to_numpy()
        if len(diff) < 3:
            continue
        out[str(label)] = float(np.sqrt((diff**2).mean() / 2))
    return out


def _noise_gate(tables: PetabTables, best: dict, spec, residuals: np.ndarray):
    """The post-fit noise-model gate on measurements planted at `sim + residuals`
    (the fitted sigma is 1 at the nominal vector, so residuals are standardized)."""
    from types import SimpleNamespace

    planted = tables.measurements.copy()
    k = 0
    for (obs_id, cond_id), grp in planted.groupby(
        ["observableId", "simulationConditionId"]
    ):
        times = grp["time"].to_numpy(dtype=float)
        sim = sim_group(tables, str(obs_id), str(cond_id), times, best)
        planted.loc[grp.index, "measurement"] = sim + residuals[k : k + len(grp)]
        k += len(grp)
    tables.measurements = planted
    core = {"noise_check": _noise_model_check(tables, best, spec)}
    gates = _post_fit_gates(core, tables, best, SimpleNamespace(spec=spec))
    g = next(
        g for g in gates if getattr(g, "gate_id", "") == "evaluation_noise_model_check"
    )
    return core["noise_check"], g()


def main() -> int:
    # 1 ---- planted: three donors everywhere ---------------------------------
    df = _long({"dose=0.3": [1, 2, 3], "dose=1": [1, 2, 3]}, seed=3)
    floors = replicate_noise_floors(df)
    f = floors.get("pR_au")
    check("a floor is found for the label", f is not None, str(floors))
    if f:
        check(
            f"the pooled SD recovers the planted {SD} within 20%",
            abs(f["sigma_replicate"] - SD) / SD < 0.2,
            f"{f['sigma_replicate']:.3f}",
        )
        check(
            "degrees of freedom = sum over cells of (n - 1): 12 cells x 2",
            f["dof"] == 24 and f["n_cells"] == 12 and f["n_values"] == 36,
            f"dof {f['dof']} cells {f['n_cells']} values {f['n_values']}",
        )
    # 2 ---- donors that never share a cell ----------------------------------
    disjoint = _long({"dose=0.3": [1, 3], "dose=1": [2, 3]}, seed=5)
    old = _old_first_pair_floor(disjoint)
    new = replicate_noise_floors(disjoint)
    check(
        "the first-pair estimator finds NOTHING when replicate 1 and 2 never meet",
        old == {},
        str(old),
    )
    check(
        "the pooled estimator finds the floor from every cell that has two values",
        "pR_au" in new
        and new["pR_au"]["dof"] == 12
        and abs(new["pR_au"]["sigma_replicate"] - SD) / SD < 0.35,
        str(new.get("pR_au")),
    )
    # a single replicate everywhere: honestly nothing
    single = _long({"dose=0.3": [1], "dose=1": [1]})
    check(
        "one replicate per cell gives no floor (nothing to pool)",
        replicate_noise_floors(single) == {},
    )
    # the holdout stays sealed: only the conditions the labels name are pooled
    held = replicate_noise_floors(df, cond_labels={"c0": "dose=0.3"})
    check(
        "only the named (training) conditions are pooled",
        held["pR_au"]["n_cells"] == 6,
        str(held.get("pR_au")),
    )

    # 3 ---- end to end through structural_misfit_evidence --------------------
    tables = PetabTables(
        observables=pd.read_csv(PETAB / "observables.tsv", sep="\t"),
        conditions=pd.read_csv(PETAB / "conditions.tsv", sep="\t"),
        measurements=pd.read_csv(PETAB / "measurements.tsv", sep="\t"),
        parameters=pd.read_csv(PETAB / "parameters.tsv", sep="\t"),
        sbml=(PETAB / "model.xml").read_text(),
    )
    par = pd.read_csv(PETAB / "parameters.tsv", sep="\t")
    best = dict(
        zip(par["parameterId"], par["nominalValue"].astype(float), strict=False)
    )
    spec = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
    ev = structural_misfit_evidence(
        tables,
        best,
        disjoint,
        [],
        spec,
        obs_labels={"obs_pR": "pR_au"},
        cond_labels={"dose_0p3": "dose=0.3", "dose_1": "dose=1"},
    )
    recs = (ev.get("signals") or {}).get("sigma_vs_floor") or []
    check(
        "sigma_vs_floor is populated for the observable — the floor reached the evidence",
        len(recs) == 1 and recs[0]["observable"] == "obs_pR",
        str(recs)[:200],
    )
    if recs:
        check(
            "the record carries the floor, its dof and the fitted/floor ratio",
            recs[0].get("floor_dof") == 12
            and recs[0].get("ratio") is not None
            and abs(
                recs[0]["sigma_fitted"] / recs[0]["sigma_replicate"] - recs[0]["ratio"]
            )
            < 1e-2,
            str(recs[0]),
        )

    # 4 ---- the noise-model gate: a rejection is a flag, not a pass ----------
    n = len(tables.measurements)
    rng = np.random.default_rng(7)
    two_point = np.where(np.arange(n) % 2, 2.0, -2.0) + 0.01 * rng.standard_normal(n)
    nc, g = _noise_gate(tables, best, spec, two_point)
    check(
        "planted two-point residuals are rejected by the distribution test",
        nc["obs_pR"].get("p_value") is not None and nc["obs_pR"]["p_value"] < 0.01,
        str({k: v for k, v in nc["obs_pR"].items() if k != "qq"}),
    )
    check(
        "a gate that rejects the noise model says passed=False, blocking=False",
        g.passed is False and g.blocking is False and "REJECT" in g.detail,
        f"passed={g.passed} blocking={g.blocking} detail={g.detail[:120]}",
    )
    check(
        "…and the card line for it is a flag, not a pass",
        g.summary().lstrip().startswith("⚑ flag"),
        g.summary()[:120],
    )
    nc, g = _noise_gate(
        tables, best, spec, np.random.default_rng(11).standard_normal(n)
    )
    check(
        "standard-normal residuals pass the same gate, still advisory",
        g.passed is True and g.blocking is False and not g.advisory_findings,
        f"p={nc['obs_pR'].get('p_value')} passed={g.passed} detail={g.detail[:120]}",
    )
    return finish(
        "\nNOISE FLOOR",
        "\nnoise floor: pooled over every replicate, and it reaches the evidence",
    )


if __name__ == "__main__":
    sys.exit(main())
