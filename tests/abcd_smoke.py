"""ABCD staging smoke tests (stub backend, token-free).

The stubs are deliberately imperfect baselines, so the outcomes differ from the toys:

  1. abcd_prediction: the naive chain misfits BX-11, T2' fails, the run stops (exit 1);
  2. abcd_mechanism: of three stub candidates the truth topology (M3) wins on AIC.

    uv run python tests/abcd_smoke.py [prediction] [mechanism]
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from tests import curves_on_request_smoke, identifiability_unit  # noqa: E402
from tests._record import ledger_rows, rnd, run_root  # noqa: E402

# Where runs are written: `test_runs/` under the battery (run_all.py sets
# OCTOMOD_RUNS_DIR), `runs/` otherwise; a suite never hard-codes `runs/`.
RUNS = config.RUNS_DIR


def ledger(run_id: str) -> list[dict]:
    return ledger_rows(run_root(run_id))


def run_case(case: str, run_id: str, note: str | None = None) -> int:
    """`note` is the standing note every auto-approved gate carries."""
    from octomod.cli import main

    return main(
        [
            "run",
            "--testcase",
            str(REPO / "testcase" / case),
            "--backend",
            "stub",
            "--auto-approve",
            "--run-id",
            run_id,
            *(["--gate-note", note] if note else []),
        ]
    )


def smoke_prediction() -> None:
    rid = f"smoke_abcd_pred_{time.strftime('%H%M%S')}"
    # the stub declares structural axes, and a bare yes at a card that lists
    # them is refused: the naive baseline is asked for explicitly
    rc = run_case("abcd_prediction", rid, note="axes: none")
    entries = ledger(rid)
    t2 = [e for e in entries if e.get("gate_id") == "evaluation_t2prime_holdout"]
    assert (
        t2 and not t2[-1]["passed"]
    ), "naive baseline was expected to FAIL T2' on the held-out combination"
    stopped = [e for e in entries if e["event"] == "run_end"]
    assert stopped and stopped[-1]["outcome"] in (
        "stopped",
        "completed_t2prime_unmet",
    ), f"expected an honest non-success ending, got {stopped}"
    assert rc == 1, f"expected exit 1 (T2' unmet / cycle stop), got {rc}"
    reason = stopped[-1].get("reason", "T2' unmet at loop end")
    print(
        f"ABCD PREDICTION SMOKE OK — naive baseline rejected as designed "
        f"({reason[:80]})"
    )


def smoke_mechanism() -> None:
    rid = f"smoke_abcd_mech_{time.strftime('%H%M%S')}"
    rc = run_case("abcd_mechanism", rid)
    assert rc == 0, f"mechanism run exited {rc}"
    root = run_root(rid)  # the run is one file
    report = (rnd(root, 0) / "evaluation").get()
    d = report["discrimination"]
    print(
        f"  AIC table: "
        f"{[(r['id'], r['delta_aic'], r['akaike_weight']) for r in d['candidates']]}"
    )
    truth = json.loads(
        (
            REPO / "testcase" / "abcd_mechanism" / "truth" / "true_parameters.json"
        ).read_text()
    )
    true_mech = truth.get("true_mechanism_id")
    assert (
        d["winner"] == true_mech
    ), f"winner {d['winner']} != true mechanism {true_mech}"
    scorer = subprocess.run(
        [
            sys.executable,
            str(REPO / "tests" / "score_against_truth.py"),
            "--run-id",
            rid,
            "--testcase",
            str(REPO / "testcase" / "abcd_mechanism"),
        ],
        capture_output=True,
        text=True,
    )
    print(scorer.stdout)
    # the DISCRIMINATION path's FIM screen, asserted on the run rather than
    # by counting `_fim_screen` occurrences in the source.
    identifiability_unit.check_run_screened(rnd(root, 0), "discrimination path")
    # thinning the curves must not hide the series that carry the misfit.
    # Every observable keeps its own worst series drawn, so "which
    # observable's residuals point at what" is answerable from the payload
    # alone.
    curves_on_request_smoke.check_curves_cover_every_observable(
        root, 0, "abcd_mechanism"
    )
    print("ABCD MECHANISM SMOKE OK — truth topology wins the discrimination")


if __name__ == "__main__":
    which = sys.argv[1:] or ["prediction", "mechanism"]
    if "prediction" in which:
        smoke_prediction()
    if "mechanism" in which:
        smoke_mechanism()
