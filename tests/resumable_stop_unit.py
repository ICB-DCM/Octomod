"""A run stopped at the agent-call byte cap is resumable, not an ended run.

The gate text says "raise the cap or trim it and resume", every artifact is in the record
and no answer is outstanding, so run_guard does not refuse the plain resume.

    uv run python tests/resumable_stop_unit.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.orchestration import run_guard  # noqa: E402
from tests._record import record_at  # noqa: E402


def _ledger(rows):
    """A throwaway run record holding exactly these ledger rows."""
    root = record_at(Path(tempfile.mkdtemp()) / "run.h5")
    root.store.create()
    root.store.replace_ledger(rows)
    return root


def main() -> int:
    plain_stop = _ledger(
        [
            {"event": "run_start"},
            {"event": "run_end", "outcome": "stopped", "reason": "user declined"},
        ]
    )
    assert run_guard.ended_outcome(plain_stop) == "stopped"
    cap_stop = _ledger(
        [
            {"event": "run_start"},
            {"event": "human_gate", "module": "evaluation_verdict", "approved": True},
            {
                "event": "run_end",
                "outcome": "stopped",
                "reason": "agent prompt within the declared byte cap",
                "resumable": True,
                "gate_id": "agent_prompt_bytes",
            },
        ]
    )
    assert run_guard.ended_outcome(cap_stop) is None, "a byte-cap stop resumes plainly"
    # a later real end still ends the run
    ended_after = _ledger(
        [
            {
                "event": "run_end",
                "outcome": "stopped",
                "resumable": True,
                "gate_id": "agent_prompt_bytes",
            },
            {"event": "run_start"},
            {"event": "run_end", "outcome": "completed"},
        ]
    )
    assert run_guard.ended_outcome(ended_after) == "completed"
    src = (REPO / "octomod" / "orchestration" / "orchestrator.py").read_text()
    assert 'gate_id == "agent_prompt_bytes"' in src and '"resumable": True' in src
    print(
        "RESUMABLE STOP UNIT OK — a byte-cap stop is fixable and resumable, not an ended run"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
