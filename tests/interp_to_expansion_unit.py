"""The interpreter's hypotheses reach the agent that proposes the next axes.

  1. the expansion context carries `interpretation_hypotheses` from the round's report;
  2. routing allows them for `revision` only;
  3. the skill says they are hypotheses to test, not decisions;
  4. on a machine-local run, the interpretation names the STAT5 corner (else skipped).

    uv run python tests/interp_to_expansion_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from _record import rnd, run_root, run_store  # noqa: E402

from octomod import config  # noqa: E402
from octomod.agents import routing  # noqa: E402

# a machine-local run in the user's library, read-only; skipped when absent
LIVE_RUN = "bodenmiller2012_20260924_201837"


def _live_interpretation() -> dict | None:
    """The round-2 interpretation of the machine-local run, or None when its
    record is not on this machine."""
    if not run_store(LIVE_RUN, config.USER_RUNS_DIR).path.exists():
        return None
    report = (rnd(run_root(LIVE_RUN, config.USER_RUNS_DIR), 2) / "evaluation").get(None)
    return (report or {}).get("interpretation") or {}


def main() -> int:
    src = (REPO / "octomod" / "orchestration" / "orchestrator.py").read_text()
    i = src.index('_interp = report.get("interpretation") or {}')
    body = src[i : i + 1500]
    for key in (
        "recommendation",
        "diagnosis",
        "misfit_hypotheses",
        "cannot_distinguish",
    ):
        assert f'"{key}"' in body, key
    assert (
        'context["interpretation_hypotheses"]' in body and "SUGGESTIONS TO TEST" in body
    )
    print("  context       the expansion context carries the interpreter's hypotheses")
    assert "interpretation_hypotheses" in routing.allowed("revision")
    others = [
        r
        for r in routing.ROUTING
        if r != "revision" and "interpretation_hypotheses" in routing.allowed(r)
    ]
    assert not others, f"the interpreter's hypotheses reached other roles: {others}"
    print("  routing       allowed for revision only")
    skill = (REPO / "skills" / "revision.md").read_text()
    assert "interpretation_hypotheses" in skill and "hypothesis to TEST" in skill
    print("  skill         hypotheses to test, not decisions")
    interp = _live_interpretation()
    if interp is not None:
        hyp = " ".join(str(h) for h in interp.get("misfit_hypotheses") or [])
        assert "STAT5 off the shared sites" in hyp, hyp[:300]
        print(
            "  live          the round-2 interpretation names the STAT5 corner it would now pass on"
        )
    else:
        print("  live          (machine-local run not on disk — skipped)")
    print(
        "\nINTERPRETATION TO EXPANSION UNIT OK — the interpreter's hypotheses reach the next round's proposer"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
