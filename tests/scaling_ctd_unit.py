"""The CTD deposit, re-rendered from an assembly with per-timepoint shared gains, is
the deposit's own likelihood on the installed AMICI.

  1. the re-rendered problem is petablint-clean, with 36 observables and k = 7 free;
  2. both objectives read the recorded nllh at the optimum and agree at a random point.

    uv run python tests/scaling_ctd_unit.py
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.CRITICAL)

from _harness import check, finish  # noqa: E402
from tolerance_probe import _staged_ctd  # noqa: E402

from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import engine as S3  # noqa: E402
from octomod.workflow_modules.assembly import petab_io  # noqa: E402
from octomod.workflow_modules.estimation.problem import build_problem  # noqa: E402
from tests._record import record_at  # noqa: E402

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
DEPOSIT = REPO / "testcase" / "ctd_petab" / "supplied" / "petab"
TRUTH = json.loads(
    (REPO / "testcase" / "ctd_petab" / "truth" / "true_parameters.json").read_text()
)


class Ctx:
    """What `_merge_to_petab` reads off a RunContext."""

    def __init__(self, root):
        # a run is one record file; `root` is its root node
        self.root, self.round_idx, self.candidate = root, 0, None
        self.spec, self.ledger, self.cache = SPEC, Ledger(root), {}

    @property
    def round(self):
        return tree.round_node(self.root, self.round_idx)

    @property
    def work(self):
        return tree.work_node(self.round, self.candidate)

    @property
    def model(self):
        return tree.model_node(self.round, self.candidate)

    @property
    def testcase(self) -> dict:
        return {"holdout": {"condition_labels": []}}


def _rerender(root: Path):
    """The deposit's data and model through the engine's OWN renderer,
    written into a throwaway record at `root`. Returns the problem as the
    engine would fit it (`petab_io.from_work`) and its `petab` node."""
    ctx = Ctx(record_at(root))
    sbml = (DEPOSIT / "pysb_model.sbml").read_text()
    (ctx.model / "sbml").put_text(sbml)
    dep_par = pd.read_csv(DEPOSIT / "parameters.tsv", sep="\t")
    dyn = dep_par[dep_par["parameterId"].isin(["k_p", "alpha"])]
    (ctx.model / "parameters").put(
        [
            {
                "id": r.parameterId,
                "nominal_value": float(r.nominalValue),
                "lb": float(r.lowerBound),
                "ub": float(r.upperBound),
                "estimate": True,
            }
            for r in dyn.itertuples()
        ]
    )
    meas = pd.read_csv(DEPOSIT / "measurementData.tsv", sep="\t")
    long_df = pd.DataFrame(
        {
            "observable_label": meas["observableId"].astype(str),
            "condition_label": "condition1",
            "condition_key": "condition1",
            "time": meas["time"].astype(float),
            "value": meas["measurement"].astype(float),
        }
    )
    obs_ids = sorted(
        set(long_df["observable_label"]), key=lambda s: int(s.split("_")[1])
    )
    reply = {
        "observables": [
            {
                "observable_id": oid,
                "maps_to_label": oid,
                "formula": f"__obs{oid.split('_')[1]}",
                "transformation": "lin",
                "noise": {
                    "distribution": "normal",
                    "formula": "sc_ctd_ms * sd",
                    "estimate_sigma": True,
                },
                "scaling": {
                    "mode": "factor",
                    "scale_parameter": "sc_ctd_ms",
                    "per": "timepoint",
                    "shared_across_observables": "ctd_ms",
                    "pin_first_to_one": False,
                },
                "rationale": "the deposit's own shape: one gain per injection, shared by the nine peaks, noise scaling with it",
            }
            for oid in obs_ids
        ]
    }
    ents = set(S3._model_summary(sbml)["species"]) | set(
        S3._model_summary(sbml)["parameters"]
    )
    problems = S3._observation_reply_problems(reply, obs_ids, ents)
    check(
        "the deposit's shape passes the seam checks", not problems, "; ".join(problems)
    )
    obs, noise, scaling = S3.split_observation_reply(reply)
    assembly = {
        "observables": obs,
        "noise": noise,
        "scaling": scaling,
        "conditions": [
            {
                "condition_id": "condition1",
                "maps_to_label": "condition1",
                "overrides": {},
                "preequilibration": False,
            }
        ],
    }
    petab = ctx.work / "petab"
    S3._merge_to_petab(ctx, assembly, sbml, long_df, petab)
    return petab_io.from_work(ctx.work, ctx.model), petab


def _free(prob) -> list[str]:
    return [prob.x_names[i] for i in prob.x_free_indices]


def _eval(prob, values: dict[str, float]) -> float:
    x = np.array([np.log10(values[n]) for n in _free(prob)])
    return float(prob.objective(x))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="scaling_ctd_"))
    try:
        inp, petab = _rerender(tmp / "ours")
        import petab.v1 as pv

        pp = petab_io.load_problem(inp)
        check("re-rendered problem is petablint-clean", not pv.lint.lint_problem(pp))
        obs = (petab / "observables").table()
        check(
            "flattened to the deposit's 36 observables, names kept",
            len(obs) == 36
            and sorted(set(obs["observableName"])) == [f"p_{k}" for k in range(9)],
            f"{len(obs)} observables, names {sorted(set(obs['observableName']))[:3]}…",
        )
        check(
            "noise renders as gain x sd — the deposit's own shape",
            all(
                f.startswith("observableParameter1_") and "noiseParameter1_" in f
                for f in obs["noiseFormula"]
            ),
            obs["noiseFormula"].iloc[0],
        )

        print(
            "  compiling the re-rendered problem (258 states; cached after the first run) …"
        )
        ours, _pp, cs_ours = build_problem(inp, {}, SPEC)
        # the deposit is an INPUT on disk, staged as real PEtab files
        dep_inp = petab_io.from_dir(_staged_ctd(tmp / "deposit"))
        dep, _pp2, cs_dep = build_problem(dep_inp, {}, SPEC)
        print(f"  compiled: ours {cs_ours:.0f} s, deposit {cs_dep:.0f} s")
        check(
            "seven free parameters, like the deposit (k = 7)",
            len(_free(ours)) == 7 == len(_free(dep)),
            f"ours {_free(ours)} / deposit {_free(dep)}",
        )

        tp = TRUTH["true_parameters"]
        sd = TRUTH["noise_sd"]["sigma"]
        dep_truth = {**tp, "sd": sd}
        # the deposit's noise is `xi_t * sd` (relative gain, xi_0 = 1); the
        # engine's is `sc_t * sd'` with sc_t = xi_t * s_t0: the same likelihood
        # under sd' = sd / s_t0 (intensity units vs model units)
        ours_truth = {
            "k_p": tp["k_p"],
            "alpha": tp["alpha"],
            "sd": sd / tp["s_t0"],
            "sc_ctd_ms_t0": tp["s_t0"] * tp["xi_0"],
            "sc_ctd_ms_t60": tp["s_t0"] * tp["xi_1"],
            "sc_ctd_ms_t120": tp["s_t0"] * tp["xi_2"],
            "sc_ctd_ms_t960": tp["s_t0"] * tp["xi_16"],
        }
        f_ours, f_dep = _eval(ours, ours_truth), _eval(dep, dep_truth)
        recorded = TRUTH["model_space_and_criteria"][0]["nllh"]
        check(
            "at the published optimum both problems read the recorded nllh",
            abs(f_ours - recorded) < 1e-3 and abs(f_dep - recorded) < 1e-3,
            f"ours {f_ours:.6f}, deposit {f_dep:.6f}, recorded {recorded:.6f}",
        )
        check(
            "and read EACH OTHER to 1e-6 relative — one likelihood, two parametrisations",
            abs(f_ours - f_dep) <= 1e-6 * max(1.0, abs(f_dep)),
            f"|Δ| = {abs(f_ours - f_dep):.2e}",
        )
        rng = np.random.default_rng(7)
        # a random point in the deposit's box, mapped the same way
        rnd = {
            k: 10 ** rng.uniform(-2, 2)
            for k in ("k_p", "alpha", "s_t0", "xi_1", "xi_2", "xi_16", "sd")
        }
        rnd["xi_0"] = 1.0
        rnd_ours = {
            "k_p": rnd["k_p"],
            "alpha": rnd["alpha"],
            "sd": rnd["sd"] / rnd["s_t0"],
            "sc_ctd_ms_t0": rnd["s_t0"],
            "sc_ctd_ms_t60": rnd["s_t0"] * rnd["xi_1"],
            "sc_ctd_ms_t120": rnd["s_t0"] * rnd["xi_2"],
            "sc_ctd_ms_t960": rnd["s_t0"] * rnd["xi_16"],
        }
        g_ours, g_dep = _eval(ours, rnd_ours), _eval(dep, rnd)
        check(
            "at a random point away from the optimum the identity still holds",
            np.isfinite(g_ours)
            and np.isfinite(g_dep)
            and abs(g_ours - g_dep) <= 1e-6 * max(1.0, abs(g_dep)),
            f"ours {g_ours:.6f}, deposit {g_dep:.6f}",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return finish(
        "SCALING CTD",
        "SCALING CTD OK — the engine writes the deposit's per-injection gains, and it is the same likelihood",
    )


if __name__ == "__main__":
    sys.exit(main())
