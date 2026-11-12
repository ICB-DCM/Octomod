"""The redraft dossier and the redraft-budget exhaustion gate, token-free.

`toy_phos_redraft` ships two failing drafts then a good one; the budget is two attempts:

  1. attempt 3's prompt carries both prior failures and both draft summaries;
  2. the collateral-change ratio is ledgered;
  3. exhaustion pauses once at the redraft-budget gate, and `y n=2` grants two;
  4. the run then finishes.

    uv run python tests/redraft_smoke.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO))

from file_gate_loop import drive  # noqa: E402

from octomod import config  # noqa: E402
from tests._record import ledger_rows, rnd, run_root  # noqa: E402

# where runs are written: `test_runs/` under the battery (tests/run_all.py
# sets OCTOMOD_RUNS_DIR), `runs/` otherwise; never spell `runs/` in a suite
RUNS = config.RUNS_DIR


def main() -> int:
    run_id = f"redraft_{time.strftime('%H%M%S')}"
    root = run_root(run_id, RUNS)
    rc, gates = drive(
        "toy_phos_redraft",
        run_id,
        extra=["--workflow", "workflows/test_redraft.yaml"],
        answers={"model_redraft_budget": ("y", "n=2")},
    )
    print(f"exit {rc}; gates: {gates}")
    assert rc == 0, f"run ended {rc}"
    assert (
        gates.count("model_redraft_budget") == 1
    ), "the exhaustion gate must pause exactly once"
    assert gates.index("model_redraft_budget") < gates.index("model_scope")
    ledger = ledger_rows(root)
    calls = [
        e for e in ledger if e["event"] == "agent_call" and e["role"] == "construction"
    ]
    assert len(calls) == 3, f"expected exactly 3 construction calls, saw {len(calls)}"
    redrafts = [e for e in ledger if e["event"] == "redraft"]
    assert len(redrafts) == 2, f"expected 2 redraft rows, saw {len(redrafts)}"
    assert all("collateral_change_ratio" in e for e in redrafts[1:]), redrafts
    grants = [e for e in ledger if e["event"] == "redraft_grant"]
    assert grants and grants[0]["granted"] == 2, grants
    construction = (rnd(root, 0) / "agent_calls").child("construction")
    dossier = (construction / "dossier").get()
    assert len(dossier["attempts"]) == 2
    prompt = (construction / "prompt").text()
    assert (
        "attempt_history" in prompt and "k_ghost" in prompt and '"attempt": 2' in prompt
    ), "attempt 3's prompt must carry both prior attempts"
    # minimal repair is offered only when a failure names something: attempt 1
    # names k_ghost, so attempt 2 gets a minimal edit; attempt 2's integrator
    # error names nothing, so attempt 3 does not
    mr = [
        e
        for e in ledger
        if e["event"] == "note" and "minimal-repair mode" in str(e.get("note"))
    ]
    assert len(mr) == 1, f"expected exactly one minimal-repair offer, saw {len(mr)}"
    assert "k_ghost" in mr[0]["note"], mr[0]["note"]
    assert (
        redrafts[0]["localized"] is True and redrafts[1]["localized"] is False
    ), "the localized flag is what decides minimal repair; both classes must appear"
    grant_record = (construction / "dossier").get()
    assert (
        grant_record.get("grants") and grant_record["grants"][0]["granted"] == 2
    ), "the grant must be persisted, so a resume never re-asks it"
    print(
        "REDRAFT SMOKE OK — dossier carried both failures, collateral ledgered, "
        "exhaustion gate paused once and its grant finished the run"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
