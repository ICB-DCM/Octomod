"""Answering a budget card does not re-run the probe it was built from.

In file-gate mode the card is answered on the next invocation, which re-enters the
cost module from the top. Token-free (stub agents), on testcase/toy_phos.

  1. the pass that pauses at the budget card measures and saves the probe;
  2. the pass that answers it rebuilds the card from the saved probe, and ledgers the reuse;
  3. the numbers the card and the profile carry are the same ones.

    uv run python tests/probe_record_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish, run_cli_captured  # noqa: E402

from octomod import config  # noqa: E402
from tests._record import (  # noqa: E402
    ledger_rows,
    pending_gate,
    run_root,
    run_store,
    work,
)

# `test_runs/` under the battery (tests/run_all.py sets OCTOMOD_RUNS_DIR),
# `runs/` otherwise
RUNS = config.RUNS_DIR
RUN_ID = "probe_record_smoke"


def main() -> int:
    run_store(RUN_ID, RUNS).remove()
    root = run_root(RUN_ID, RUNS)
    base = [
        "run",
        "--testcase",
        "testcase/toy_phos",
        "--backend",
        "stub",
        "--run-id",
        RUN_ID,
        "--gate-mode",
        "file",
    ]

    def pending_module() -> str | None:
        return (pending_gate(root) or {}).get("module")

    rc, out = run_cli_captured(base)
    # answer every gate `y` until the budget card is the one waiting
    for _ in range(20):
        if rc != 3 or pending_module() == "cost_boundary_estimation":
            break
        rc, out = run_cli_captured(base + ["--gate-answer", "y"])
    check(
        "the run pauses at the budget card",
        rc == 3 and pending_module() == "cost_boundary_estimation",
        f"rc={rc}",
    )
    est = work(root, 0)
    rec_path = est / "probe_record"
    check(
        "the pausing pass measured the probe and saved it",
        "probing cost with" in out and rec_path.exists(),
        out[-300:],
    )
    first = (est / "cost").get()

    rc2, out2 = run_cli_captured(base + ["--gate-answer", "y"])
    check(
        "the answering pass did NOT run the probe again",
        "probing cost with" not in out2,
        out2[:400],
    )
    check(
        "… and says it reused the saved measurements",
        "reused, nothing re-measured" in out2,
        out2[:400],
    )
    rows = ledger_rows(root)
    check("the ledger records the reuse", any(r.get("probe_reused") for r in rows))
    second = (est / "cost").get()
    same = all(
        first.get(k) == second.get(k)
        for k in (
            "probe_fvals",
            "probe_median_start_s",
            "tolerance_agreement",
            "structural_nulls",
            "solver_messages",
        )
    )
    check("the card's numbers are the ones that were measured", same)
    msgs = rec_path.get().get("solver_messages") or {}
    check(
        "the saved probe carries AMICI's messages over its starts, ledgered once",
        msgs.get("available")
        and msgs.get("n_starts") == len(first.get("probe_fvals") or [])
        and sum(1 for r in rows if "solver_messages" in r) == 1,
        str({k: msgs.get(k) for k in ("n_starts", "n_failed", "source")}),
    )
    struct = first.get("structural_nulls") or {}
    check(
        "the structural probe was drawn near the nominal values",
        struct.get("center_basis", "").startswith("the nominal parameter values")
        and struct.get("spread") == 0.5,
        str({k: struct.get(k) for k in ("center_basis", "spread", "why")}),
    )
    check(
        "the run went on past the budget gate",
        rc2 != 3 or pending_module() != "cost_boundary_estimation",
        f"rc={rc2}",
    )
    return finish(
        "\nPROBE RECORD",
        "\nPROBE RECORD OK — answering a budget card reuses the probe it was built from",
    )


if __name__ == "__main__":
    sys.exit(main())
