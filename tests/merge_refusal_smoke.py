"""A value the PEtab merge cannot render goes back to its agent; the run goes on.

testcase/toy_phos_merge_refusal: observation.1.json names `sigma_obs_pR`
with `estimate_sigma: false`; .2.json is the good reply. Token-free (stub agents).

  1. the refusal is ledgered as a failing T0 check (`assembly_merge_noise`);
  2. observation is re-asked once, with the refusal as its check;
  3. the run gets past S3 (the good reply merges and the battery passes).

    uv run python tests/merge_refusal_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish, run_cli  # noqa: E402
from _record import ledger_rows, pending_gate, rnd, run_root, work  # noqa: E402

from octomod import config  # noqa: E402

# Where runs are written: `test_runs/` under the battery (run_all.py sets
# OCTOMOD_RUNS_DIR), `runs/` otherwise; a suite never hard-codes `runs/`.
RUNS = config.RUNS_DIR
RUN_ID = "merge_refusal_smoke"


def main() -> int:
    # the run is one record, <RUNS>/<id>.h5
    run_dir = run_root(RUN_ID, RUNS)
    run_dir.store.remove()
    base = [
        "run",
        "--testcase",
        "testcase/toy_phos_merge_refusal",
        "--backend",
        "stub",
        "--run-id",
        RUN_ID,
        "--gate-mode",
        "file",
    ]
    rc = run_cli(base)
    # every gate `y` until the run is past S3 (the budget card is after it)
    for _ in range(20):
        if rc != 3:
            break
        if pending_gate(run_dir)["module"] == "cost_boundary_estimation":
            break
        rc = run_cli(base + ["--gate-answer", "y"])
    rows = ledger_rows(run_dir)
    refusals = [r for r in rows if r.get("event") == "gate" and r.get("merge_refusal")]
    check(
        "the merge refusal is ledgered as a failing T0 check",
        len(refusals) == 1
        and refusals[0]["gate_id"] == "assembly_merge_noise"
        and not refusals[0]["passed"],
        str(refusals)[:300],
    )
    reasks = [r for r in rows if r.get("event") == "redraft_attributed"]
    check(
        "observation is re-asked once with it",
        len(reasks) == 1
        and reasks[0].get("role") == "observation"
        and reasks[0].get("gate_id") == "assembly_merge_noise",
        str(reasks)[:300],
    )
    ends = [
        r for r in rows if r.get("event") == "run_end" and r.get("outcome") == "stopped"
    ]
    check("the run did not end on it", not ends, str(ends)[:300])
    assembly_passed = (
        any((d / "status/markers/s3").exists() for d in [rnd(run_dir, 0)])
        or (work(run_dir, 0) / "petab/problem_yaml").exists()
    )
    check(
        "the good reply merged and the run went past S3",
        assembly_passed
        and any(r.get("module") == "cost_boundary_estimation" for r in rows),
    )
    return finish(
        "\nMERGE REFUSAL",
        "\nMERGE REFUSAL OK — an agent's unrenderable value goes back to the agent, not to the run's end",
    )


if __name__ == "__main__":
    sys.exit(main())
