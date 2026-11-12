"""Golden path: the full pipeline, stub backend, auto-approved gates, token-free.

  1. the run exits 0 with a report, no failed blocking gate and no real human gate;
  2. toy_phos: declared constants are measured at the fit and latent states screened;
  3. toy_decay_params: the information spectrum computes and profiles are produced;
  4. the report names the screens that ran and found nothing; request kinds answer.

    uv run python tests/golden_path.py [toy_phos|toy_decay_params]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from tests import (  # noqa: E402
    curves_on_request_smoke,
    identifiability_unit,
    observation_evidence_unit,
)
from tests._record import ledger_rows, reports_dir, rnd, run_root  # noqa: E402

# where runs are written: `test_runs/` under the battery (tests/run_all.py
# sets OCTOMOD_RUNS_DIR), `runs/` otherwise — never spell `runs/` here
RUNS = config.RUNS_DIR


def run_case(case: str) -> int:
    from octomod.cli import main

    run_id = f"golden_{case}_{time.strftime('%H%M%S')}"
    rc = main(
        [
            "run",
            "--testcase",
            str(REPO / "testcase" / case),
            "--backend",
            "stub",
            "--auto-approve",
            "--run-id",
            run_id,
        ]
    )
    assert rc == 0, f"pipeline exited {rc}"

    root = run_root(run_id)  # the run is one file
    r0 = rnd(root, 0)
    evaluation = r0 / "evaluation"
    assert evaluation.exists(), "no report produced"
    report = evaluation.get()

    ledger = ledger_rows(root)
    gates = [e for e in ledger if e["event"] == "gate"]
    failed_blocking = [e for e in gates if not e["passed"] and e.get("blocking")]
    assert not failed_blocking, f"blocking gate failures: {failed_blocking}"
    human_gates = [e for e in ledger if e["event"] == "human_gate"]
    assert all(
        e["mode"] == "auto" for e in human_gates
    ), "golden path must not have blocked on a real human"

    if case == "toy_phos":
        # the stub declares `R + Rp` constant, and it genuinely is — so the
        # gate must FIRE and PASS, at nominal and again at the fit
        declared = [e for e in gates if e["gate_id"] == "model_declared_constants"]
        assert declared, "the declared-constants gate did not run"
        assert declared[-1]["passed"], declared[-1]["detail"]
        at_fit = report.get("declared_constants") or {}
        # MEASURED, not merely declared: a worst drift of 0.0 over zero measured
        # rows would read as "the constant holds" when nothing was checked
        assert (
            at_fit.get("measured", 0) > 0
        ), f"the declaration was never actually measured at the fit: {at_fit}"
        assert at_fit.get("unmeasured") == 0, at_fit
        assert at_fit.get("violated") == 0, at_fit
        assert at_fit.get("worst_drift") is not None
        print(
            f"  declared constants: {at_fit['measured']} of "
            f"{at_fit['declared']} measured at the fit, worst drift "
            f"{at_fit['worst_drift']:.2%}"
        )
        # the latent states nobody measured must have been looked at
        latent = report.get("latent_states") or {}
        assert (
            latent.get("conditions_checked", 0) > 0
        ), f"the latent-state screen never simulated anything: {latent}"
        assert not latent.get("hard_failures"), latent["hard_failures"]
        print(
            f"  latent states: {latent['conditions_checked']} condition(s) at "
            f"the MLE, {len(latent.get('findings') or [])} finding(s), "
            f"totals {latent.get('conserved_totals')}"
        )
        assert report["holdout"]["available"], "toy_phos must evaluate holdout"
        worst = max(g["nrmse"] for g in report["holdout"]["groups"])
        print(f"  holdout worst nRMSE: {worst:.3f}")
    if case == "toy_decay_params":
        # the information spectrum, on the goal where parameter values ARE the
        # deliverable; a spectrum that never computes is not a screen
        spec_ = report.get("identifiability") or {}
        assert spec_.get("available"), f"no information spectrum: {spec_}"
        eig = [v for v in (spec_.get("eigenvalues_log10") or []) if v is not None]
        assert len(eig) == spec_["n_free"], (eig, spec_["n_free"])
        assert spec_["spread_decades"] > 0
        assert "never a rank verdict" in spec_["note"]
        print(
            f"  information spectrum: {spec_['n_free']} free, spread "
            f"{spec_['spread_decades']} decades, "
            f"{len(spec_.get('flat_directions') or [])} flat, via "
            f"{spec_['method']}"
        )
        assert "profiles" in report, "parameter goal must produce profiles"
        print(
            f"  profile CIs: { {k: v['ci95'] for k, v in report['profiles'].items() if not k.startswith('_')} }"
        )

    identifiability_unit.check_run_screened(r0, f"single-model path ({case})")
    # the observation half of the differential diagnosis, read off the prompt
    # this run SENT rather than off the source
    observation_evidence_unit.check_observation_block(
        root, 0, f"single-model path ({case})"
    )
    # the screens whose result is an absence must say they ran — asserted on
    # the rendered page, where a reader would look
    report_html = reports_dir(root) / "round_0" / "report" / "report.html"
    page = report_html.read_text()
    assert "Checks that ran" in page, (
        "the report does not say which screens ran and found nothing — a "
        "reader cannot tell a check that passed from one that never happened"
    )
    said = page[page.index("Checks that ran") :][:1600]
    assert "latent states" in said, said[:200]
    assert "declared constants" in said, said[:200]
    print("  checks ran    the report names both screens that found nothing")
    # the request kinds must answer on the SINGLE-MODEL layout too, where the
    # one fitted problem is `candidates/_single`, not a candidate
    curves_on_request_smoke.check_requests_answer(
        root, [""], f"single-model path ({case})"
    )
    print(f"GOLDEN PATH OK — {case}")
    print(f"  gates run: {len(gates)}, human gates auto-approved: {len(human_gates)}")
    print(f"  report: {report_html}")
    return 0


if __name__ == "__main__":
    cases = sys.argv[1:] or ["toy_phos"]
    for c in cases:
        run_case(c)
