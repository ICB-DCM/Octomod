"""The two-tolerance agreement check and the sensitivity timing, on a toy and on ctd_petab.

Token-free but it compiles: `ctd_petab` (258 species, 1024 reactions) costs ~80 s once, then
the AMICI content-hash cache makes it free, so the flattening must stay byte-deterministic.
Its size is checked first, so the assertions run on a model where tolerance could bite.

    uv run python tests/tolerance_probe.py
"""

from __future__ import annotations

import logging
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.CRITICAL)  # AMICI's petab mapping logs a screenful

from _harness import check, finish  # noqa: E402

from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import petab_io  # noqa: E402
from octomod.workflow_modules.cost_probe import solver_probe as sp  # noqa: E402
from octomod.workflow_modules.estimation.problem import build_problem  # noqa: E402

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")


def _staged_ctd(tmp: Path) -> Path:
    """The CTD deposit, flattened as the supplied-PEtab adapter does (AMICI refuses overrides),
    staged as a PEtab problem on disk (an input: `petab_io.from_dir` reads it)."""
    import petab.v1 as pv
    from petab.v1.core import flatten_timepoint_specific_output_overrides

    src = REPO / "testcase" / "ctd_petab" / "supplied" / "petab"
    pdir, mdir = tmp / "petab", tmp / "model"
    pdir.mkdir(parents=True)
    mdir.mkdir(parents=True)
    shutil.copy(src / "pysb_model.sbml", mdir / "model.xml")
    pp = pv.Problem.from_yaml(str(src / "problem.yaml"))
    flatten_timepoint_specific_output_overrides(pp)
    pp.observable_df.to_csv(pdir / "observables.tsv", sep="\t")
    meas = pp.measurement_df
    meas = meas.drop(columns=[c for c in meas.columns if str(c).startswith("Unnamed:")])
    meas.to_csv(pdir / "measurements.tsv", sep="\t", index=False)
    pp.condition_df.to_csv(pdir / "conditions.tsv", sep="\t")
    pp.parameter_df.to_csv(pdir / "parameters.tsv", sep="\t")
    (pdir / "problem.yaml").write_text(
        "format_version: 1\nparameter_file: parameters.tsv\nproblems:\n"
        "- condition_files:\n  - conditions.tsv\n"
        "  measurement_files:\n  - measurements.tsv\n"
        "  observable_files:\n  - observables.tsv\n"
        "  sbml_files:\n  - ../model/model.xml\n"
    )
    return pdir


def _probe(inp: petab_io.PetabInput, label: str, seed: int = 1) -> tuple[dict, dict]:
    prob, _pp, _cs = build_problem(inp, {}, SPEC)
    rng = np.random.default_rng(seed)
    lb, ub = np.asarray(prob.lb), np.asarray(prob.ub)  # already the FREE bounds
    x = lb + rng.random(len(lb)) * (ub - lb)
    return (
        sp.tolerance_agreement(prob, SPEC, x),
        sp.sensitivity_probe(prob, x, SPEC),
    )


def main() -> int:
    toys = {
        "toy_phos_petab": REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab",
    }

    print("TWO-TOLERANCE AGREEMENT\n")
    for name, pdir in toys.items():
        tol, sens = _probe(petab_io.from_dir(pdir), name)
        check(
            f"{name}: the check runs at all",
            bool(tol.get("available")),
            tol.get("why", ""),
        )
        if not tol.get("available"):
            continue
        check(
            f"{name}: both runs integrated every condition",
            bool(tol["all_integrated"]),
            "",
        )
        check(
            f"{name}: declared vs {tol['tighten_factor']:g}x tighter agree",
            bool(tol["agrees"]),
            f"worst rel diff {tol['worst_rel_diff']:.2e} "
            f"(limit {tol['threshold']:.0e})",
        )
        check(
            f"{name}: the comparison is real, not two identical runs",
            tol["declared"]["rtol"] != tol["tightened"]["rtol"],
            f"{tol['declared']['rtol']:.0e} vs {tol['tightened']['rtol']:.0e}",
        )
        check(
            f"{name}: sensitivities integrate and the gradient is finite",
            bool(sens["gradient_computable"]),
            f"ratio {sens['ratio']}x over {sens['n_estimated']} parameters",
        )

    print("\nAND ON THE ONE FIXTURE WHERE TOLERANCE PLAUSIBLY BITES\n")
    with tempfile.TemporaryDirectory() as tmp:
        pdir = _staged_ctd(Path(tmp))
        import pandas as pd

        n_species = len(
            pd.read_csv(pdir / "observables.tsv", sep="\t")
        )  # flattened observables, a proxy for the problem's size
        check(
            "ctd_petab: the fixture is big enough for the question",
            n_species >= 30,
            f"{n_species} flattened observables over 258 species / 1024 reactions",
        )
        tol, sens = _probe(petab_io.from_dir(pdir), "ctd_petab")
        check(
            "ctd_petab: the check runs on a 258-state model",
            bool(tol.get("available")),
            tol.get("why", ""),
        )
        if tol.get("available"):
            check(
                "ctd_petab: both runs integrated",
                bool(tol["all_integrated"]),
                f"declared {tol['declared_s']:.3f}s, "
                f"tightened {tol['tightened_s']:.3f}s",
            )
            check(
                "ctd_petab: declared and tighter trajectories agree",
                bool(tol["agrees"]),
                f"worst rel diff {tol['worst_rel_diff']:.2e} at {tol['worst_at']}",
            )
            check(
                "ctd_petab: and the reading states the number either way",
                str(tol["worst_rel_diff"])[:6] in tol["reading"]
                or f"{tol['worst_rel_diff']:.2e}" in tol["reading"],
                tol["reading"][:80],
            )
        # the sensitivity timing is the measurement that pays for itself here
        check(
            "ctd_petab: sensitivities integrate",
            bool(sens["gradient_computable"]),
            sens.get("gradient_note") or "gradient finite",
        )
        check(
            "ctd_petab: the gradient is where the cost is, and it is MEASURED",
            (sens["ratio"] or 0) > 20,
            f"forward sensitivities cost {sens['ratio']}x the residual for "
            f"{sens['n_estimated']} parameters",
        )
        # the number that triggered it must be IN the message, both sides of
        # the comparison — asserted on the formatting the message actually
        # uses, not on a substring of the raw float (108.0x vs 107.957)
        check(
            "ctd_petab: so adjoint is proposed, with the number that triggered it",
            sens["proposed_sensi_method"] == "adjoint"
            and f"{sens['ratio']:.1f}x" in sens["why"]
            and f"{sens['adjoint_threshold']:g}x" in sens["why"],
            sens["why"][:90],
        )
        check(
            "ctd_petab: and the proposal names the sres consequence for the FIM",
            "sres" in sens["why"],
            "",
        )

    print()
    return finish(
        "TOLERANCE PROBE",
        "TOLERANCE PROBE OK — the integrator is checked against a tighter run "
        "before the budget, and the gradient's cost is measured",
    )


if __name__ == "__main__":
    raise SystemExit(main())
