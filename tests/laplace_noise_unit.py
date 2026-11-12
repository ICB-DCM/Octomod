"""A Laplace observable is fitted, not crashed.

AMICI computes no Fisher information for a Laplace likelihood, so the default
`fim_for_hess=True` would index a missing array on the first Hessian request.

  1. the assembly vocabularies and the estimation path share one list of distributions;
  2. one Laplace observable turns the FIM Hessian and second order off; the Gaussian twin keeps both;
  3. a seeded multistart on the Laplace problem reaches a finite optimum.

    uv run python tests/laplace_noise_unit.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod.workflow_modules.assembly import assembly_edit, petab_io  # noqa: E402
from octomod.workflow_modules.assembly import engine as assembly_module  # noqa: E402
from octomod.workflow_modules.estimation import problem as estimation  # noqa: E402

PETAB = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"


def test_one_vocabulary() -> None:
    check(
        "assembly_edit, assembly and estimation share ONE distribution list",
        assembly_edit.DISTRIBUTIONS
        is assembly_module._DISTRIBUTIONS
        is estimation.FITTABLE_NOISE_DISTRIBUTIONS,
        f"{assembly_edit.DISTRIBUTIONS} / {assembly_module._DISTRIBUTIONS} / "
        f"{estimation.FITTABLE_NOISE_DISTRIBUTIONS}",
    )
    check(
        "and it names normal and laplace, nothing else",
        tuple(estimation.FITTABLE_NOISE_DISTRIBUTIONS) == ("normal", "laplace"),
    )


def test_detection_reads_petab_defaults() -> None:
    by_index = pd.DataFrame(
        {
            "observableId": ["o_a", "o_b", "o_c", "o_d", "o_e"],
            "noiseDistribution": ["normal", "laplace", None, "", "Laplace"],
        }
    ).set_index("observableId")
    got = estimation.non_gaussian_observables(by_index)
    check(
        "detection: explicit laplace counts, missing/empty cells are normal",
        got == ["o_b", "o_e"],
        str(got),
    )
    as_column = by_index.reset_index()
    check(
        "detection works on an unindexed table too",
        estimation.non_gaussian_observables(as_column) == ["o_b", "o_e"],
    )
    check(
        "a table with no noiseDistribution column is all-normal",
        estimation.non_gaussian_observables(pd.DataFrame({"observableId": ["x"]}))
        == [],
    )


def _variant(distribution: str):
    """The static toy_phos PEtab problem with its one observable's noise set,
    in memory (`petab_io.from_dir` reads the supplied input once)."""
    inp = petab_io.from_dir(PETAB)
    obs = inp.observables.copy()
    obs["noiseDistribution"] = distribution
    return inp.with_tables(observables=obs)


def test_laplace_problem_builds_without_fim_and_fits() -> None:
    from octomod.spec import WorkflowSpec

    spec = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
    problems = {}
    for dist in ("normal", "laplace"):
        problem, petab_problem, _ = estimation.build_problem(_variant(dist), {}, spec)
        problems[dist] = problem
        check(
            f"{dist}: the problem's own table is what decides",
            estimation.non_gaussian_observables(petab_problem.observable_df)
            == ([] if dist == "normal" else ["obs_pR"]),
        )
    gauss, lap = problems["normal"], problems["laplace"]
    check(
        "the Gaussian twin keeps the FIM Hessian and advertises second order",
        estimation.uses_fim_hessian(gauss) is True and bool(gauss.objective.has_hess),
        f"fim_for_hess={estimation.uses_fim_hessian(gauss)} "
        f"has_hess={gauss.objective.has_hess}",
    )
    check(
        "the Laplace problem has the FIM Hessian OFF and no second order",
        estimation.uses_fim_hessian(lap) is False and not lap.objective.has_hess,
        f"fim_for_hess={estimation.uses_fim_hessian(lap)} "
        f"has_hess={lap.objective.has_hess}",
    )
    # the objective itself is finite at the nominal point: the likelihood
    # exists, only its Fisher information does not
    x0 = (lap.lb + lap.ub) / 2.0  # the free vector, mid-box
    try:
        f0 = float(lap.objective(x0))
    except Exception as e:  # noqa: BLE001 — the failure IS the finding
        f0 = float("nan")
        print(f"    objective raised: {type(e).__name__}: {e}")
    check(
        "the Laplace objective evaluates to a finite number",
        math.isfinite(f0),
        f"{f0}",
    )

    # and the multistart reaches an optimum instead of dying in the
    # Hessian path on every start
    result = estimation.run_multistart(lap, 3, 20260914, spec)
    starts = result.optimize_result.list
    fvals = [float(o.fval) if o.fval is not None else float("inf") for o in starts]
    messages = [str(getattr(o, "message", "") or "") for o in starts]
    check(
        "3 Laplace starts reach a finite best objective",
        bool(fvals) and math.isfinite(min(fvals)),
        f"fvals={fvals}",
    )
    check(
        "no start died in the FIM path",
        not any("NoneType" in m or "not subscriptable" in m for m in messages),
        str(messages)[:300],
    )
    check(
        "every start has a parameter vector (none aborted before the first step)",
        all(o.x is not None for o in starts),
    )


def main() -> int:
    test_one_vocabulary()
    test_detection_reads_petab_defaults()
    test_laplace_problem_builds_without_fim_and_fits()
    return finish("\nLAPLACE", "\nlaplace noise: all checks passed")


if __name__ == "__main__":
    sys.exit(main())
