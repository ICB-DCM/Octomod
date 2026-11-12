"""The redraft dossier, without the engine.

  1. failures localise to the names they implicate;
  2. the collateral-change ratio separates a minimal fix from a re-roll;
  3. attempts accumulate and persist, so a resume carries the dossier;
  4. under the size cap the oldest attempts lose detail first, never their verdicts.

    uv run python tests/redraft_unit.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.orchestration.interaction import retry  # noqa: E402
from tests._record import rnd, temp_record  # noqa: E402

A1 = """model m
  compartment cell = 1;
  species A in cell = 1;
  species B in cell = 0;
  k1 = 0.1;
  J1: A -> B; k1 * A * k_ghost;
  J2: B -> ; k2 * B;
end
"""
A2 = A1.replace("k1 * A * k_ghost", "k1 * A").replace("k2 * B", "k1 * B")  # minimal fix
A3 = (
    A1.replace("k1 * A * k_ghost", "k1 * A")
    .replace("k2 * B", "k1 * B")
    .replace(
        "species B in cell = 0;",
        "species B in cell = 0;\n  species C in cell = 0;\n  J3: B -> C; k1 * B;",
    )
)


def main() -> int:
    with temp_record() as root:
        return _check(rnd(root, 0) / "agent_calls/construction/dossier")


def _check(dossier) -> int:
    h = retry.AttemptHistory(dossier, cap_chars=500)
    f1 = [
        "reaction J1: kinetic law references undefined symbol 'k_ghost'",
        "reaction J2: kinetic law references undefined symbol 'k2'",
    ]
    assert retry.localized(f1) and retry.implicated_names(f1) >= {
        "J1",
        "J2",
        "k_ghost",
        "k2",
    }
    s1 = retry.antimony_summary(A1, f1)
    assert s1["n_reactions"] == 2 and s1["n_species"] == 2
    assert any("k_ghost" in line for line in s1["failing_lines"]), s1
    h.add(f1, s1)
    # attempt 2: a minimal fix — nothing collateral
    d = retry.diff_summary(A1, A2, retry.implicated_names(f1))
    assert d["n_collateral_lines"] == 0, d
    h.add(
        ["states stay non-negative FAILED"],
        retry.antimony_summary(A2, []),
        previous_text=A1,
        current_text=A2,
        implicated=retry.implicated_names(f1),
    )
    # attempt 3: a re-roll — new species and reaction nobody asked for
    d3 = retry.diff_summary(A2, A3, retry.implicated_names(["reaction J2 ..."]))
    assert d3["n_collateral_lines"] >= 2 and d3["collateral_change_ratio"] > 0.5, d3
    h.add(["something"], {}, previous_text=A2, current_text=A3, implicated={"J2"})
    # persisted and reloadable — a resume carries the dossier
    h2 = retry.AttemptHistory(dossier, cap_chars=500)
    assert len(h2) == 3 and h2.attempts[0]["gate_failures"] == f1
    # size cap: oldest attempts keep their one-line verdicts, lose details
    ctxd = h2.as_context()
    assert len(json.dumps(ctxd["attempts"])) <= 500 + 400, "cap not applied"
    assert ctxd["attempts"][0]["gate_failures"], "every attempt keeps its verdicts"
    assert ctxd["attempts"][0].get("details_truncated") is True
    assert "what_changed_vs_previous" in h2.attempts[2]
    print(
        "REDRAFT UNIT OK — dossier accumulates, persists, caps oldest details; "
        "collateral ratio separates a minimal fix from a re-roll"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
