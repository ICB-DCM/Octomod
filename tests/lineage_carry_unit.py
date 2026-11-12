"""The run-level lineage of an axis carried undecided into the next round.

  1. a carried axis is off in the next round's base; the decided axes stay on;
  2. it is part of the final structure only if the final model's own id says so;
  3. the what-changed text names the re-search and what the round added.

    uv run python tests/lineage_carry_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _record import rnd, temp_record  # noqa: E402

from octomod.reporting import analysis_report as ar  # noqa: E402


def main() -> int:
    # the run is a record; each round's expansion is `rounds/round_k/expansion`
    with temp_record("lineage") as run:
        return _check(run)


def _check(run) -> int:
    (rnd(run, 0) / "expansion").put(
        {
            "expanded": True,
            "next_round": 1,
            "from_winner": "S1b",
            "carried_undecided": [],
            "axes": ["amp", "loop", "integ", "prom", "w10"],
        }
    )
    (rnd(run, 1) / "expansion").put(
        {
            "expanded": True,
            "next_round": 2,
            "from_winner": "loop+sigCX+prom",
            "carried_undecided": ["w10", "prom", "integ", "loop"],
            "axes": ["loop", "integ", "prom", "w10", "sigSO"],
        }
    )
    # round 1's winner, seen from round 1: base S1b plus its own axes
    assert ar.lineage_axes(run, 1, "loop+sigCX+prom") == [
        "S1b",
        "loop",
        "sigCX",
        "prom",
    ]
    # round 2's winner: the carried loop and prom were switched OFF in the base;
    # the decided sigCX stays; the id adds sigSO and integ
    assert ar.lineage_axes(run, 2, "sigSO+integ") == [
        "S1b",
        "sigCX",
        "sigSO",
        "integ",
    ], ar.lineage_axes(run, 2, "sigSO+integ")
    # a round-2 model that switches the loop back on carries it by its own id
    assert ar.lineage_axes(run, 2, "sigSO+loop") == ["S1b", "sigCX", "sigSO", "loop"]
    assert ar.lineage(run, 2, "sigSO+integ") == "S1b + sigCX + sigSO + integ"
    # the base model of round 2 is the inherited structure alone
    assert ar.lineage_axes(run, 2, "base") == ["S1b", "sigCX"]
    # without any carry, the lineage is the base plus the id's axes
    assert ar.lineage_axes(run, 1, "loop") == ["S1b", "loop"]
    changed = ar._what_changed(run, 2)
    assert (
        "re-searching the undecided" in changed
        and "adding sigSO" in changed
        and "on top of S1b + sigCX" in changed
    ), changed
    print(
        "LINEAGE CARRY UNIT OK — a carried-undecided axis is not inherited; the final structure is what its own id and the decided base say"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
