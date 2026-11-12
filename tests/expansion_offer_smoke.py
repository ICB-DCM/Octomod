"""Asking for another round at the verdict gate reaches the expansion agent.

One run of `abcd_prediction` (round 0: no indicator fires, the agent says `revise`),
set aside at its round-0 verdict pause and answered there twice, with two
verdict notes:

  1. a note that says nothing: the run ends after round 0;
  2. `expand: yes`: the expansion agent is called and the request is ledgered;
  3. the verdict card carries the question, both note forms, margins and disagreement.

    uv run python tests/expansion_offer_smoke.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.result import node as tree  # noqa: E402
from tests._record import (  # noqa: E402
    ledger_rows,
    restore_run,
    rnd,
    run_root,
    save_run,
)

sys.path.insert(0, str(REPO / "tests"))

from file_gate_loop import drive  # noqa: E402

from octomod import config  # noqa: E402

# where runs are written: `test_runs/` under the battery (tests/run_all.py
# sets OCTOMOD_RUNS_DIR), `runs/` otherwise; never spell `runs/` in a suite
RUNS = config.RUNS_DIR

CASE = "abcd_prediction"
AXES = "axes: basal_route, product_feedback"
RUN_ID = "expoffer"


def _run(
    run_id: str,
    verdict_note: str,
    collect: list[dict] | None = None,
    at_pause=None,
    fresh: bool = True,
):
    """Drive the run to its end; `fresh=False` resumes it where it paused."""
    root = run_root(run_id)  # the run is one file
    if fresh and root.exists():
        root.store.remove()
    rc, gates = drive(
        CASE,
        run_id,
        answers={
            "model_scope": [("y", AXES), ("y", "")],
            # the note under test at round 0; a plain yes afterwards, so the
            # run cannot loop to the round budget and look like a success
            "evaluation_verdict": [("y", verdict_note), ("y", "")],
        },
        max_gates=40,
        collect=collect,
        at_pause=at_pause,
        resume=not fresh,
    )
    assert rc == 0, f"{run_id} ended {rc}"
    return rc, gates, root


def _ledger(root) -> list[dict]:
    return ledger_rows(root)


def _roles(root) -> set[str]:
    return {str(r.get("role")) for r in _ledger(root) if r.get("event") == "agent_call"}


def _called(root, role: str) -> bool:
    """Was this agent called? The stub declines every expansion, so no gate pauses."""
    return role in _roles(root)


def main() -> int:
    t0 = time.time()

    # ---- the premise: no indicator fires, the agent says revise --------
    # Both answers are given at the SAME round-0 verdict pause: the run is set
    # aside there, answered with silence, then put back and answered `expand:
    # yes`, so round 0 is fitted once rather than once per answer.
    cards: list[dict] = []
    saved: list[Path] = []

    def at_pause(payload: dict, root) -> None:
        if (
            payload["module"] == "evaluation_verdict"
            and payload["round"] == 0
            and not saved
        ):
            saved.append(save_run(RUN_ID))

    _, gates, quiet = _run(RUN_ID, "", collect=cards, at_pause=at_pause)
    assert saved, "the run never paused at round 0's verdict"
    core = (rnd(quiet, 0) / "evaluation").get()
    ev = core.get("misfit_evidence") or {}
    assert ev.get("open") is False, (
        "this suite needs a round where NO indicator fires — if this case has "
        "started firing, the quiet-indicators path is not being exercised and the "
        "suite is measuring nothing"
    )
    assert str((core.get("interpretation") or {}).get("recommendation")) == "revise", (
        "and one where the agent wants another round, so the disagreement "
        "check has something to disagree with"
    )
    from octomod.workflow_modules.evaluation import misfit_margins as mm

    near = mm.nearest(ev)
    assert near and near["closeness"] is not None, ev

    # ---- 1. silence ends the run after round 0 ------------------------
    assert not _called(quiet, "revision"), (
        "the note said nothing, so the run must end on the indicator "
        "default; it called the expansion agent anyway"
    )
    assert tree.round_indices(quiet) == [0], (
        "a silent note must not buy a round — asking changes what a human "
        "CAN do, not what happens to one who says nothing"
    )
    print(
        f"  default       no indicator open (closest "
        f"{near['closeness']:.0%}), agent said revise, run ended after "
        f"round_0, as the default says"
    )

    # ---- 2. asking for one reaches the agent --------------------------
    restore_run(saved[0], RUN_ID)
    _, gates2, asked = _run(RUN_ID, "expand: yes", fresh=False)

    assert _called(asked, "revision"), (
        f"`expand: yes` with rounds remaining must reach the expansion "
        f"agent; the roles called were "
        f"{sorted(_roles(asked))}. A break in this segment is silent: the "
        f"run simply ends."
    )
    assert "evaluation_verdict" in gates2, gates2

    led = _ledger(asked)
    requests = [r for r in led if r.get("human_expansion_request") is True]
    assert len(requests) >= 2, (
        f"the request must be recorded at the verdict AND where it is acted "
        f"on; found {len(requests)} row(s)"
    )
    dis = [r for r in led if "DISAGREEMENT" in str(r.get("note", ""))]
    assert dis, "the agent's `revise` must leave a disagreement row in the ledger"
    assert dis[0].get("agent_recommendation") == "revise", dis[0]
    assert dis[0].get("engine_default") == "end", dis[0]
    bought = [
        r
        for r in led
        if "indicators set the default, not the decision" in str(r.get("note", ""))
    ]
    assert bought, "a round bought with no indicator open must say so"

    print(
        f"  asked         `expand: yes` reached revision; "
        f"{len(requests)} ledger rows for the request, "
        f"{len(dis)} for the disagreement"
    )

    # ---- 3. the card carried the question, uncapped -------------------
    # the silent run's card, collected in run 1: the one a reader sees when
    # nothing is asked for; its question lines are `always_show`, never capped
    verdict = next(c for c in cards if c["module"] == "evaluation_verdict")
    text = "\n".join(str(x) for x in verdict.get("lines") or [])
    assert "ANOTHER ROUND?" in text, "the verdict card does not ask the question"
    # the note forms live in their own payload field, so a front end can offer
    # them without knowing the parsers
    forms = "\n".join(str(x) for x in verdict.get("note_forms") or [])
    for must in ("expand: yes", "expand: no"):
        assert must in forms, (
            f"the verdict payload does not declare {must!r}; note_forms="
            f"{verdict.get('note_forms')!r}"
        )
    assert "% of the way to firing" in text, "the margins are not on the card"
    assert "RECOMMENDS 'revise'" in text, "the disagreement is not on the card"
    conseq = " ".join(str(x) for x in (verdict.get("consequences") or []))
    assert "expand: yes" in conseq and "DEFAULT" in conseq, conseq
    print(
        f"  card          question, both note forms, margins and the "
        f"disagreement all present in the payload ({len(text)} chars)"
    )

    print(
        f"\nEXPANSION OFFER SMOKE OK — silence still ends the run, and asking "
        f"reaches the agent ({time.time() - t0:.0f}s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
