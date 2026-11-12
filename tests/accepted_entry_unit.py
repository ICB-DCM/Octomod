"""A fit a human ACCEPTED at the convergence gate stays valid on re-entry.

  1. an accept in `…/decisions/estimation_convergence` reads back as accepted;
  2. a refit answer, a stop, or an unreadable decision is not an acceptance;
  3. only the estimation slot consults it, and the check is not re-asked.

    uv run python tests/accepted_entry_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.orchestration import round_status  # noqa: E402
from tests._record import temp_record, work  # noqa: E402


def main() -> int:
    with temp_record() as root:
        _decisions(work(root, 0))
    src = (REPO / "octomod" / "orchestration" / "round_status.py").read_text()
    i = src.index("accepted = human_accepted_fit(base)")
    assert (
        'slot == "estimation"' in src[i : i + 120]
    ), "only the estimation slot carries a convergence acceptance"
    assert "return True" in src[i : i + 1800] and "not re-asked" in src[i : i + 1800]
    print(
        "ACCEPTED ENTRY UNIT OK — a human-accepted fit stays valid on re-entry; a refit or stop answer does not count"
    )
    return 0


def _decisions(base) -> None:
    """The work group's convergence decision, planted in a temporary record."""
    assert round_status.human_accepted_fit(base) is None
    dec = base / "decisions" / "estimation_convergence"
    dec.put(
        {
            "approved": True,
            "note": "accept the optimum sits on bounds",
            "at": "2026-09-23T14:48:30",
            "signed": "human (via the front end)",
        }
    )
    got = round_status.human_accepted_fit(base)
    assert got and got["at"] == "2026-09-23T14:48:30"
    dec.put({"approved": True, "note": "refit more_starts"})
    assert (
        round_status.human_accepted_fit(base) is None
    ), "a refit answer is not an acceptance"
    dec.put({"approved": False, "note": "stop"})
    assert round_status.human_accepted_fit(base) is None
    dec.delete()
    dec.put_text("not json")
    assert round_status.human_accepted_fit(base) is None


if __name__ == "__main__":
    sys.exit(main())
