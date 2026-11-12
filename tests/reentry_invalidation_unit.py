"""An explicit `--from-module` re-entry forgets the decisions it must re-ask.

  1. entry at estimation removes estimation/evaluation markers in round and candidates;
  2. it forgets the decisions those modules own, not upstream ones like the scope gate;
  3. a stale `gate_overrides` in a candidate's `cost` record is moved aside, with a note;
  4. entry at evaluation leaves the estimation alone;
  5. a single-model round records its compile approval at the same round-level
     key as a candidate set (`decisions/assembly_cost_boundary`), and every re-entry at estimation or upstream
     forgets it there too; an evaluation re-entry keeps it.

    uv run python tests/reentry_invalidation_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod.orchestration import round_status  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from tests._record import temp_record  # noqa: E402

# the keys a legacy run directory's files map to (relative to the round, as
# `invalidate_from` reports them): cost_boundary.json, model/scope_gate.json,
# report/verdict.json,
# agent_io/interpretation.pinned.json, <cand>/estimation/
# convergence_gate.json, <cand>/estimation/cost_profile.json
BOUNDARY = "decisions/assembly_cost_boundary"
SCOPE = "decisions/model_scope"
VERDICT = "decisions/evaluation_verdict"
PIN = "agent_calls/interpretation/pinned"
CONVERGENCE = "decisions/estimation_convergence"
COST = "cost"


class _Ctx:
    def __init__(self, root: Node):
        self.root = root
        self.ledger = Ledger(root.store)
        self.round_idx = 0
        self.candidate = None

    @property
    def round(self) -> Node:
        return tree.round_node(self.root, 0)

    def marker(self, name: str) -> Node:
        return tree.markers_node(self.round, self.candidate) / name


def _cand(rd: Node, cid: str) -> Node:
    return tree.work_node(rd, cid)


def _marker(rd: Node, name: str, cid: str | None = None) -> Node:
    """The marker node (a legacy run directory's
    `<round or cand_<id>>/gates/<name>.pass`)."""
    return tree.markers_node(rd, cid) / name


def _stage_round(rd: Node) -> None:
    (rd / "space/candidates").put([{"id": "M1"}, {"id": "M2"}])
    # round-level markers and decisions
    for m in ("s1", "s2", "candidate_compile", "s7"):
        _marker(rd, m).put({})
    (rd / SCOPE).put({"approved": True})
    (rd / BOUNDARY).put({"approved": True, "note": ""})
    (rd / VERDICT).put({"approved": True})
    (rd / PIN).put({"recommendation": "accept"})
    # per-candidate markers, decisions and profiles
    for cid in ("M1", "M2"):
        for m in ("s3", "cost", "s6"):
            _marker(rd, m, cid).put({})
        (_cand(rd, cid) / CONVERGENCE).put({"approved": True, "note": "accept fine"})
    (_cand(rd, "M2") / COST).put(
        {
            "median_start_s": 0.4,
            "gate_overrides": {
                "requested": {"sensi_method": "adjoint"},
                "applied": {"sensi_method": "adjoint"},
            },
        }
    )
    (_cand(rd, "M1") / COST).put({"median_start_s": 0.3})


def _stage_single_model_round(rd: Node) -> None:
    """A single-model round: no candidate set, every marker in the round's
    markers, the compile approval where the candidate path keeps it, the
    convergence decision on the round's own unit of work (`_single`)."""
    for m in ("s1", "s2", "s3", "candidate_compile", "cost", "s6", "s7"):
        _marker(rd, m).put({})
    (rd / BOUNDARY).put({"approved": True, "note": ""})
    (tree.work_node(rd, None) / CONVERGENCE).put(
        {"approved": True, "note": "accept fine"}
    )
    (rd / VERDICT).put({"approved": True})


def check_the_single_model_round() -> None:
    with temp_record() as root:
        ctx = _Ctx(root)
        rd = ctx.round
        for module in ("estimation", "model", "data", "assembly"):
            _stage_single_model_round(rd)
            removed, forgotten, _dropped = round_status.invalidate_from(ctx, module)
            check(
                f"single-model round, entry at {module}: the compile approval "
                f"({BOUNDARY}) is forgotten and the card's marker removed",
                not (rd / BOUNDARY).exists()
                and BOUNDARY in forgotten
                and "candidate_compile" in removed
                and not _marker(rd, "candidate_compile").exists(),
                f"forgotten {sorted(forgotten)} removed {sorted(set(removed))}",
            )
        _stage_single_model_round(rd)
        removed, forgotten, _dropped = round_status.invalidate_from(ctx, "evaluation")
        check(
            "single-model round, entry at evaluation: the compile approval and "
            "its marker are kept (nothing is compiled again)",
            (rd / BOUNDARY).exists()
            and _marker(rd, "candidate_compile").exists()
            and BOUNDARY not in forgotten,
            f"forgotten {sorted(forgotten)} removed {sorted(set(removed))}",
        )


def main() -> int:
    check_the_single_model_round()
    with temp_record() as root:
        ctx = _Ctx(root)
        rd = ctx.round
        _stage_round(rd)
        removed, forgotten, dropped = round_status.invalidate_from(ctx, "estimation")
        check(
            "estimation + evaluation markers are removed in the round dir and in BOTH candidates",
            not _marker(rd, "candidate_compile").exists()
            and not _marker(rd, "s7").exists()
            and all(
                not _marker(rd, m, c).exists()
                for c in ("M1", "M2")
                for m in ("cost", "s6")
            ),
            str(sorted(set(removed))),
        )
        check(
            "…while the upstream markers stay (s1, s2, every candidate's s3)",
            _marker(rd, "s1").exists()
            and _marker(rd, "s2").exists()
            and all(_marker(rd, "s3", c).exists() for c in ("M1", "M2")),
        )
        check(
            "the compile-boundary decision, both convergence decisions, the verdict and the pin are forgotten",
            not (rd / BOUNDARY).exists()
            and not (_cand(rd, "M1") / CONVERGENCE).exists()
            and not (_cand(rd, "M2") / CONVERGENCE).exists()
            and not (rd / VERDICT).exists()
            and not (rd / PIN).exists(),
            str(forgotten),
        )
        check(
            "…and the scope-gate decision upstream is untouched",
            (rd / SCOPE).exists(),
        )
        prof = (_cand(rd, "M2") / COST).get()
        check(
            "the stale adjoint override is moved aside under a name that says so, with a note",
            "gate_overrides" not in prof
            and prof.get("gate_overrides_dropped_on_reentry", {})
            .get("applied", {})
            .get("sensi_method")
            == "adjoint"
            and "re-entered" in prof.get("gate_overrides_note", ""),
            str(prof)[:200],
        )
        check(
            "the profile without an override is left alone, and the drop list names only M2",
            dropped == [f"candidates/M2/{COST}"]
            and (_cand(rd, "M1") / COST).get() == {"median_start_s": 0.3},
            str(dropped),
        )
        check(
            "the forgotten list names every record, relative to the round",
            set(forgotten)
            >= {
                BOUNDARY,
                f"candidates/M1/{CONVERGENCE}",
                f"candidates/M2/{CONVERGENCE}",
                VERDICT,
                PIN,
            },
            str(sorted(forgotten)),
        )

        # -- evaluation entry leaves the estimation alone ----------------------
        _stage_round(rd)
        removed, forgotten, dropped = round_status.invalidate_from(ctx, "evaluation")
        check(
            "entry at evaluation removes s7 and forgets the verdict + pin only",
            set(removed) == {"s7"}
            and set(forgotten) == {VERDICT, PIN}
            and dropped == []
            and (rd / BOUNDARY).exists()
            and _marker(rd, "cost", "M2").exists(),
            f"removed {sorted(set(removed))} forgotten {sorted(forgotten)} dropped {dropped}",
        )
        check(
            "…and the adjoint override survives an evaluation-only re-entry (the fit is not redone)",
            "gate_overrides" in (_cand(rd, "M2") / COST).get(),
        )
        # -- a re-entry that rebuilds the problem forgets the compile approval
        for module in ("model", "data", "assembly"):
            _stage_round(rd)
            _removed, forgotten, _dropped = round_status.invalidate_from(ctx, module)
            check(
                f"entry at {module} forgets the candidate set's compile approval",
                not (rd / BOUNDARY).exists(),
                f"forgotten {sorted(forgotten)}",
            )
        # -- the decisions each entry module owns --------------------------------
        check(
            "the compile approval has one recorded place for both paths: "
            "MODULE_DECISIONS names no per-problem copy (under petab/, or a "
            "per-candidate `decisions/cost_boundary`)",
            round_status.MODULE_DECISIONS["estimation"] == (BOUNDARY, CONVERGENCE),
            str(round_status.MODULE_DECISIONS["estimation"]),
        )
        check(
            "MODULE_DECISIONS: estimation and evaluation as before, plus model — "
            "whose only decision is the scope gate (re-entering at model rebuilds "
            "the set the answer was given for)",
            set(round_status.MODULE_DECISIONS) == {"model", "estimation", "evaluation"}
            and round_status.MODULE_DECISIONS["model"] == (SCOPE,),
            str(round_status.MODULE_DECISIONS),
        )
    return finish(
        "\nRE-ENTRY INVALIDATION",
        "\nre-entry invalidation: markers, decisions and stale overrides go together",
    )


if __name__ == "__main__":
    sys.exit(main())
