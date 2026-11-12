"""A redraft's new candidate set does not leave the failed attempt's groups beside it.

  1. every candidate outside the new set is moved to `superseded/` and ledgered;
  2. a candidate of the set being written is left where it is;
  3. `_persist_md` does it before it writes the new set.

The run is one record; a candidate is `rounds/round_k/candidates/<id>`,
and "moved aside" is `rounds/round_k/superseded/model_candidates_<stamp>/candidates/<id>`.

    uv run python tests/stale_candidates_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _record import ledger_rows, rnd, temp_record, work  # noqa: E402

from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.workflow_modules.model import engine as model_module  # noqa: E402


def main() -> int:
    with temp_record() as run:
        rd = rnd(run, 0)
        for cid in ("M1_old", "M2_old", "M2_kept"):
            (work(run, 0, cid) / "model" / "antimony").put_text(f"// {cid}\n")
        ctx = SimpleNamespace(root=run, round=rd, round_idx=0, ledger=Ledger(run))
        moved = model_module._move_aside_stale_candidates(ctx, {"M2_kept", "M3_new"})
        # the moved groups are named by candidate id
        assert moved == ["M1_old", "M2_old"], moved
        assert (
            work(run, 0, "M2_kept") / "model" / "antimony"
        ).exists(), "a kept candidate was moved"
        assert (
            not work(run, 0, "M1_old").exists() and not work(run, 0, "M2_old").exists()
        )
        sup = [
            n
            for n in (
                (rd / "superseded").children() if (rd / "superseded").exists() else []
            )
            if n.startswith("model_candidates_")
        ]
        kept = (rd / "superseded").child(sup[0]) if len(sup) == 1 else None
        assert (
            kept is not None
            and ((kept / "candidates").child("M1_old") / "model" / "antimony").exists()
        ), sup
        rows = [r for r in ledger_rows(run) if r.get("superseded_candidates")]
        assert rows and rows[0]["superseded_candidates"] == moved, rows
        assert (
            model_module._move_aside_stale_candidates(ctx, {"M2_kept"}) == []
        ), "nothing stale, nothing moved"
    src = (REPO / "octomod" / "workflow_modules" / "model" / "engine.py").read_text()
    i = src.index("def _persist_md(")
    body = src[i : i + 1200]
    assert body.index("_move_aside_stale_candidates(") < body.index(
        "for cand, sbml in survivors:"
    ), "the stale groups must be moved before the new set is written"
    print(
        "STALE CANDIDATES UNIT OK — an earlier draft's candidate groups are moved aside, never left beside the new set"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
