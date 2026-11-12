"""Model-space search end to end, token-free: axes declared, bought, fitted, selected.

  1. the axes reach the scope gate as a question the human can answer;
  2. an axis selection in the gate note turns the round into a search;
  3. 2 axes -> 4 fitted models, each having passed the S1 gate ladder;
  4. the selection reports a winner, AIC weights and an indistinguishable set;
  5. the winner carries both axes, as the data were generated with both mechanisms.

    uv run python tests/search_smoke.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from tests import (  # noqa: E402
    curves_on_request_smoke,
    observation_evidence_unit,
    tried_models_unit,
)
from tests._record import ledger_rows, rnd, run_root  # noqa: E402

# where runs are written: `test_runs/` under the battery (tests/run_all.py
# sets OCTOMOD_RUNS_DIR), `runs/` otherwise; never spell `runs/` in a suite
RUNS = config.RUNS_DIR

RUN_ID = "search_smoke"


def main() -> int:
    root = run_root(RUN_ID, RUNS)  # the run is one file
    if root.exists():
        root.store.remove()

    # every gate is auto-approved, and the note names the axes, which is what
    # turns this round into a search
    cmd = [
        str(REPO / "run.sh"),
        "run",
        "--testcase",
        "testcase/abcd_prediction",
        "--backend",
        "stub",
        "--run-id",
        RUN_ID,
        "--auto-approve",
        "--gate-note",
        "axes: basal_route, product_feedback; lattice",
    ]
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    out = proc.stdout + proc.stderr

    if "OPEN STRUCTURAL AXES" not in out:
        print(out[-3000:])
        print("FAIL: the declared axes never reached the scope gate")
        return 1
    if "MODEL-SPACE SEARCH" not in out:
        print(out[-3000:])
        print("FAIL: the axis selection did not turn the round into a search")
        return 1

    r0 = rnd(root, 0)
    cands_node = r0 / "space/candidates"
    if not cands_node.exists():
        print(f"FAIL: no {cands_node.key} — enumeration did not persist")
        return 1
    cands = cands_node.get()
    ids = sorted(c["id"] for c in cands)
    print(f"enumerated and gate-passed {len(cands)} models: {ids}")
    if len(cands) != 4:
        print(f"FAIL: expected 4 models from 2 axes, got {len(cands)}")
        return 1

    report = r0 / "evaluation"
    if not report.exists():
        print(out[-3000:])
        print("FAIL: no report — the search did not reach evaluation")
        return 1
    disc = report.get().get("discrimination")
    if not disc:
        print("FAIL: report carries no discrimination block")
        return 1

    print("\nselection by AIC:")
    for c in sorted(disc["candidates"], key=lambda c: c["delta_aic"]):
        print(
            f"  {c['id']:34s} dAIC {c['delta_aic']:9.2f}  "
            f"weight {c['akaike_weight']:.4f}"
        )
    print(
        f"winner: {disc['winner']}  decisive={disc['decisive']}  "
        f"indistinguishable={disc['indistinguishable']}"
    )

    both = "basal_route+product_feedback"
    if disc["winner"] != both:
        print(
            f"FAIL: expected {both} to win (the data carry both mechanisms), "
            f"got {disc['winner']}"
        )
        return 1

    # --- PEtab Select integration -------------------------------------------
    ps_block = disc.get("petab_select") or {}
    if not ps_block.get("version"):
        print("FAIL: discrimination block carries no petab_select record")
        return 1
    ps_files = r0 / "selection_files"
    if not (ps_files / "petab_select_problem.yaml").exists():
        print(f"FAIL: petab_select problem not emitted at {ps_files.key}")
        return 1
    # the interchange files live in the record, as text. They must still
    # load in a plain petab_select session outside the engine, written out the
    # way a collaborator would (`selection.export_selection`).
    import shutil
    import tempfile

    from octomod.workflow_modules.evaluation.selection import export_selection

    tmp = Path(tempfile.mkdtemp(prefix="search_smoke_ps_"))
    try:
        import petab_select

        problem = petab_select.Problem.from_yaml(export_selection(r0, tmp))
        n_sub = len(problem.model_space.model_subspaces)
    except Exception as e:
        print(f"FAIL: emitted petab_select problem does not load: {e}")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if n_sub != 4:
        print(f"FAIL: petab_select model space has {n_sub} subspaces, expected 4")
        return 1
    ledger = ledger_rows(root)
    xg = [e for e in ledger if e.get("gate_id") == "evaluation_selection_crosscheck"]
    if not xg or not xg[-1]["passed"]:
        print(f"FAIL: selection cross-check gate missing or failed: {xg}")
        return 1
    print(
        f"petab_select {ps_block['version']}: problem emitted, reloads with "
        f"{n_sub} subspaces, cross-check passed ({xg[-1]['detail'][:80]})"
    )

    # a discrimination round records what it declared, in its own record
    # (`space/declared`)
    tried_models_unit.check_declared_axes_record(root)
    # the interpreter's prompt on this round stays under its ceiling
    observation_evidence_unit.check_interpreter_prompt_ceiling(root, 0)
    curves_on_request_smoke.check_requests_answer(
        root, sorted(ps_block.get("candidates") or ["base"]), "discrimination path"
    )

    print(
        "\nSEARCH SMOKE OK — axes declared, bought at the gate, enumerated, "
        "fitted and selected"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
