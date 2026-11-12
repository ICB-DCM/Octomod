"""Entry at a named module, token-free: a supplied PEtab problem, re-entry, refusal.

  1. toy_phos_petab's supplied PEtab enters at estimation, validated, no agent called;
  2. re-entry at evaluation re-runs S7 and re-asks the verdict;
  3. entry at estimation with nothing supplied stops before any agent, naming the slot;
  4. re-entry at estimation re-asks the budget gate and refits.

    uv run python tests/petab_entry_smoke.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from octomod import config  # noqa: E402
from tests._record import ledger_rows, rnd, run_root  # noqa: E402

# Where runs are written: `test_runs/` under the battery (run_all.py sets
# OCTOMOD_RUNS_DIR), `runs/` otherwise; a suite never hard-codes `runs/`.
RUNS = config.RUNS_DIR


AGENT_ROLES_THAT_MUST_NOT_RUN = {
    "construction",
    "data_extraction",
    "observation",
    "condition",
    "construction_verification",
    "assembly_verification",
}


def ledger(run_id: str) -> list[dict]:
    return ledger_rows(run_root(run_id, RUNS))


def main() -> int:
    from octomod.cli import main as cli

    rid = f"petab_entry_{time.strftime('%H%M%S')}"
    rc = cli(
        [
            "run",
            "--testcase",
            "testcase/toy_phos_petab",
            "--backend",
            "stub",
            "--auto-approve",
            "--run-id",
            rid,
        ]
    )
    assert rc == 0, f"PEtab entry run exited {rc}"
    rows = ledger(rid)
    called = {r["role"] for r in rows if r["event"] == "agent_call"}
    forbidden = called & AGENT_ROLES_THAT_MUST_NOT_RUN
    assert (
        not forbidden
    ), f"agents that must not run on a supplied PEtab problem ran: {forbidden}"
    entries = [r for r in rows if r["event"] == "entry"]
    assert (
        entries and entries[0]["from_module"] == "estimation"
    ), f"expected an entry event at estimation, got {entries}"
    markers = {r["module"]: r for r in rows if r["event"] == "marker"}
    for m in ("s1", "s2", "s3"):
        assert markers[m].get("entry") is True, f"marker {m} should be an entry marker"
        assert markers[m].get("producer") == "user-supplied", markers[m]
    # there is no round-status file: the slot state is computed
    # into the run's record from the artifacts and the marker payloads
    from octomod.result.access import record_for

    status = record_for(run_root(rid, RUNS)).round(0).status
    assert status is not None, "no slot state in the record"
    for slot in ("model", "data", "petab"):
        rec = status.slots[slot]
        assert rec["present"], f"slot {slot} not present in the record's slot state"
        assert str(rec.get("validated_by", "")).startswith(
            "entry_"
        ), f"slot {slot} not validated by an entry battery: {rec}"
    assert (rnd(run_root(rid, RUNS), 0) / "evaluation").exists()
    gates = [
        r
        for r in rows
        if r["event"] == "gate" and str(r["module"]).startswith("entry_")
    ]
    assert gates and all(
        r["passed"] or not r["blocking"] for r in gates
    ), "entry batteries recorded a blocking failure"
    print(
        f"PETAB ENTRY OK — {len(gates)} entry checks, agents called: {sorted(called)}"
    )

    # --- 2. re-entry at evaluation on the finished run -----------------------
    rc = cli(
        [
            "run",
            "--testcase",
            "testcase/toy_phos_petab",
            "--backend",
            "stub",
            "--auto-approve",
            "--run-id",
            rid,
            "--from-module",
            "evaluation",
        ]
    )
    assert rc == 0, f"re-entry at evaluation exited {rc}"
    rows = ledger(rid)
    s7 = [r for r in rows if r["event"] == "marker" and r["module"] == "s7"]
    assert len(s7) == 2, f"S7 should have run twice (once per entry), saw {len(s7)}"
    entry_row = [r for r in rows if r["event"] == "entry"][-1]
    inval = entry_row["invalidated_markers"]
    assert "s7" in inval, f"re-entry should invalidate s7, invalidated {inval}"
    # An explicit re-entry forgets the recorded verdict, so the gate is asked
    # again (auto mode answers it) rather than read back from disk.
    verdicts = [
        r
        for r in rows
        if r["event"] == "human_gate" and r["module"] == "evaluation_verdict"
    ]
    assert len(verdicts) >= 2 and verdicts[-1].get("mode") != "recorded", (
        f"re-entry at evaluation must RE-ASK the verdict, saw modes "
        f"{[v.get('mode') for v in verdicts]}"
    )
    forgotten = entry_row.get("forgotten_decisions") or []
    assert (
        "decisions/evaluation_verdict"
        in forgotten  # the record key (a legacy run's report/verdict.json)
    ), f"the verdict decision was not forgotten: {entry_row}"
    print(
        f"RE-ENTRY OK — evaluation re-ran; invalidated {inval}; verdict re-asked "
        f"({verdicts[-1].get('mode')}); forgot {forgotten}"
    )

    # --- 3. refusal: nothing supplied, entry at estimation --------------------
    rid2 = f"petab_entry_refused_{time.strftime('%H%M%S')}"
    rc = cli(
        [
            "run",
            "--testcase",
            "testcase/toy_phos",
            "--backend",
            "stub",
            "--auto-approve",
            "--run-id",
            rid2,
            "--from-module",
            "estimation",
        ]
    )
    assert rc == 1, f"entry without upstream artifacts must stop (exit 1), got {rc}"
    rows = ledger(rid2)
    end = [r for r in rows if r["event"] == "run_end"][-1]
    assert "slot 'model'" in end.get("reason", ""), f"refusal must name the slot: {end}"
    assert not any(
        r["event"] == "agent_call" for r in rows
    ), "refusal must not call agents"
    print(f"REFUSAL OK — {end['reason'][:110]}")

    # --- 4. re-entry at estimation re-asks the budget gate and refits --------
    rows = ledger(rid)

    def _n(rows_, event, module):
        return sum(1 for r in rows_ if r["event"] == event and r["module"] == module)

    budget_before = _n(rows, "human_gate", "cost_boundary_estimation")
    estimation_before = _n(rows, "marker", "s6")
    rc = cli(
        [
            "run",
            "--testcase",
            "testcase/toy_phos_petab",
            "--backend",
            "stub",
            "--auto-approve",
            "--run-id",
            rid,
            "--from-module",
            "estimation",
        ]
    )
    assert rc == 0, f"re-entry at estimation exited {rc}"
    rows = ledger(rid)
    entry_row = [r for r in rows if r["event"] == "entry"][-1]
    assert {"cost", "s6", "s7"} <= set(entry_row["invalidated_markers"]), entry_row
    budget_after = _n(rows, "human_gate", "cost_boundary_estimation")
    estimation_after = _n(rows, "marker", "s6")
    assert budget_after == budget_before + 1, (
        f"an explicit re-entry at estimation must ASK the budget gate again "
        f"({budget_before} -> {budget_after})"
    )
    assert (
        estimation_after == estimation_before + 1
    ), f"the fit must run again ({estimation_before} -> {estimation_after})"
    print(
        f"RE-ENTRY OK — estimation re-asked the budget ({budget_after} asks) and "
        f"refitted ({estimation_after} S6 markers)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
