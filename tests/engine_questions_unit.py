"""A proposal that would change what the data means becomes a question, not an axis.

An observation axis that changes the VALUE of an override already encoding a
measured factor, or flips pre-equilibration on a measured condition, is
refused by the model-space validator and queued for the human instead:

  1. the axis is dropped under the expansion agent's name, one numbered
     question is queued in the record's `pending_questions` and ledgered as
     `question_raised`; a legitimate condition axis beside it is kept;
  2. the same validation run again queues nothing new; a second kind of
     reinterpretation queues a second question;
  3. the next gate card carries the questions (on the card and in the
     record's `pending_gate`); the human's answer moves them, with the gate and
     the note, to `questions` and empties `pending_questions`; the card after
     that carries none.

    uv run python tests/engine_questions_unit.py
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check_detail_on_fail, finish  # noqa: E402
from _record import rnd, temp_record  # noqa: E402

from octomod.orchestration.interaction import humangate, questions  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.workflow_modules.model.model_space import (  # noqa: E402
    dropped_axes,
    dropped_axes_card_lines,
    validate_axes,
)

ANT = """model m
  compartment cell = 1;
  species A in cell = 1;
  species B in cell = 0;
  u = 1;
  kcat = 0.3;
  mu = 1;
  J0: A -> B; kcat*mu*u*A;
end
"""
PARAMETER_IDS = {"kcat", "mu"}
# both conditions are measured at u = 1: `u` encodes the dose the lab applied
ASSEMBLY = {
    "observables": [
        {
            "observable_id": "obs_b",
            "maps_to_label": "b",
            "formula": "B",
            "transformation": "lin",
        }
    ],
    "noise": [
        {
            "observable_id": "obs_b",
            "distribution": "normal",
            "formula": "sigma_obs_b",
            "estimate_sigma": True,
        }
    ],
    "scaling": [{"observable_id": "obs_b", "mode": "none"}],
    "conditions": [
        {"condition_id": "c_a", "maps_to_label": "lig=a", "overrides": {"u": 1.0}},
        {"condition_id": "c_b", "maps_to_label": "lig=b", "overrides": {"u": 1.0}},
    ],
}
REDOSE = {
    "id": "c_b_was_dosed_three",
    "kind": "observation",
    "rationale": "the second condition behaves as if it had three times the dose",
    "on_assembly_patch": {
        "change_condition": {"condition_id": "c_b", "overrides": {"u": 3.0}}
    },
}
PREEQ = {
    "id": "c_a_was_preequilibrated",
    "kind": "observation",
    "on_assembly_patch": {
        "change_condition": {
            "condition_id": "c_a",
            "overrides": {"mu": "mu_a"},
            "preequilibration": True,
        }
    },
    "adds_parameters": [
        {"id": "mu_a", "nominal_value": 1.0, "lb": 0.05, "ub": 20.0, "estimate": True}
    ],
}
# which parameter a perturbation enters is a hypothesis, not a reinterpretation
OWN_RATE = {
    "id": "b_own_rate",
    "kind": "observation",
    "on_assembly_patch": {
        "change_condition": {
            "condition_id": "c_b",
            "overrides": {"mu": "mu_b"},
        }
    },
    "adds_parameters": [
        {"id": "mu_b", "nominal_value": 1.0, "lb": 0.05, "ub": 20.0, "estimate": True}
    ],
}
MODULE = "revision"
GATE = "assembly_cost_boundary"
NOTE = "1: keep the encoding as is"


class _Ctx:
    """What the validator and the question queue read from a RunContext."""

    def __init__(self, root):
        self.root = root  # the run is one record file
        self.round_idx = 0
        self.candidate = None
        self.ledger = Ledger(root)

    @property
    def round(self):
        return rnd(self.root, self.round_idx)


def _validate(ctx: _Ctx, proposed: list[dict]):
    return validate_axes(
        ctx, proposed, ANT, PARAMETER_IDS, module=MODULE, base_assembly=ASSEMBLY
    )


def _rows(ctx: _Ctx, event: str) -> list[dict]:
    return [e for e in ctx.ledger.entries() if e.get("event") == event]


def _read(node):
    return node.get(None) if node.exists() else None


def test_a_reinterpretation_is_dropped_and_asked(ctx: _Ctx) -> None:
    kept, dropped = _validate(ctx, [REDOSE, OWN_RATE])
    check_detail_on_fail(
        "the axis that changes a measured override's value is dropped",
        [d["id"] for d in dropped] == [REDOSE["id"]]
        and "reinterprets the data" in dropped[0]["reason"],
        str(dropped),
    )
    check_detail_on_fail(
        "a condition axis that only re-routes the perturbation is kept beside it",
        [a["id"] for a in kept] == [OWN_RATE["id"]],
        str([a["id"] for a in kept]),
    )
    check_detail_on_fail(
        "the drop is recorded for the gate card, with the module that made it",
        [(d["id"], d["module"]) for d in dropped_axes(ctx)] == [(REDOSE["id"], MODULE)],
        str(dropped_axes(ctx)),
    )
    # the axis names no author, so the module decides who is shown as one
    card = dropped_axes_card_lines(ctx)
    check_detail_on_fail(
        "the dropped axis is the expansion agent's, in the record and on the card, "
        "never the assembly agents'",
        dropped_axes(ctx)[0].get("declared_by") == "revision"
        and len(card) == 1
        and f"axis {REDOSE['id']} declared by revision, DROPPED" in card[0],
        f"{dropped_axes(ctx)[0].get('declared_by')!r} · {card}",
    )
    pending = _read(questions.pending_node(ctx.root)) or []
    q = pending[0] if len(pending) == 1 else {}
    check_detail_on_fail(
        "pending_questions holds one question, numbered for this round",
        len(pending) == 1 and q.get("id") == "r0_engine_1",
        str([p.get("id") for p in pending]),
    )
    check_detail_on_fail(
        "the question names the condition and the axis, and offers both readings",
        q.get("topic") == "condition c_b"
        and REDOSE["id"] in str(q.get("question"))
        and "Re-stage the data" in str(q.get("question"))
        and "keep the encoding as is" in str(q.get("question"))
        and q.get("raised_by") == MODULE
        and q.get("detail") == REDOSE["rationale"],
        str(q)[:240],
    )
    raised = _rows(ctx, "question_raised")
    check_detail_on_fail(
        "and the question is ledgered as `question_raised` under the module",
        len(raised) == 1
        and raised[0].get("question_id") == "r0_engine_1"
        and raised[0].get("module") == MODULE,
        str(raised),
    )


def test_validation_twice_asks_once(ctx: _Ctx) -> None:
    _validate(ctx, [REDOSE, OWN_RATE])
    pending = questions.pending(ctx.root)
    check_detail_on_fail(
        "the same validation run again queues no second copy of the question",
        [q["id"] for q in pending] == ["r0_engine_1"]
        and len(_rows(ctx, "question_raised")) == 1,
        f"{[q['id'] for q in pending]}, "
        f"{len(_rows(ctx, 'question_raised'))} raised row(s)",
    )
    _kept, dropped = _validate(ctx, [PREEQ])
    pending = questions.pending(ctx.root)
    check_detail_on_fail(
        "flipping pre-equilibration on a measured condition is the other "
        "reinterpretation: dropped, and queued as the second question",
        [d["id"] for d in dropped] == [PREEQ["id"]]
        and "pre-equilibration" in dropped[0]["reason"]
        and [q["id"] for q in pending] == ["r0_engine_1", "r0_engine_2"]
        and pending[1]["topic"] == "condition c_a",
        f"{dropped} · {[q['id'] for q in pending]}",
    )


@contextlib.contextmanager
def _file_gate(root):
    """The gate module in file mode for this run, put back as found after."""
    saved = (
        dict(humangate._FILE_MODE),
        dict(humangate._QUESTIONS),
        dict(humangate._POLICY),
    )
    humangate.configure_policy(None)
    humangate.configure_questions(root)
    try:
        yield
    finally:
        humangate._FILE_MODE.clear()
        humangate._FILE_MODE.update(saved[0])
        humangate._QUESTIONS.clear()
        humangate._QUESTIONS.update(saved[1])
        humangate._POLICY.clear()
        humangate._POLICY.update(saved[2])


def _ask(ctx: _Ctx):
    """One gate card: (approved, note) when answered, the payload when it pauses."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            got = humangate.ask(
                "Approve the compile and the probe?",
                ["measured probe: 0.4 s per start"],
                ledger=ctx.ledger,
                module=GATE,
                round_idx=ctx.round_idx,
            )
    except humangate.GatePending as e:
        return e.payload, buf.getvalue()
    return got, buf.getvalue()


def test_the_next_gate_carries_them_and_records_the_answer(ctx: _Ctx) -> None:
    root = ctx.root
    with _file_gate(root):
        humangate.configure_file_mode(root, None)
        payload, printed = _ask(ctx)
        on_disk = _read(humangate.pending_path(root)) or {}
        check_detail_on_fail(
            "the paused card prints the numbered questions",
            isinstance(payload, dict)
            and "QUESTIONS THE ENGINE RAISES" in printed
            and "Q1. " in printed
            and "Q2. " in printed,
            printed[-400:],
        )
        check_detail_on_fail(
            "pending_gate carries them, as lines and as records",
            any(str(x).startswith("  Q1. ") for x in on_disk.get("lines", []))
            and [q.get("id") for q in on_disk.get("engine_questions", [])]
            == ["r0_engine_1", "r0_engine_2"],
            str(on_disk.get("engine_questions"))[:200],
        )
        check_detail_on_fail(
            "a pause that nobody answered moves nothing",
            len(questions.pending(root)) == 2
            and not questions.open_node(root).exists(),
            str(questions.pending(root))[:120],
        )

        humangate.configure_file_mode(root, True, NOTE)
        answer, _printed = _ask(ctx)
        check_detail_on_fail(
            "the stored answer is taken at the gate that paused",
            answer == (True, NOTE),
            str(answer)[:160],
        )
        opened = _read(questions.open_node(root)) or []
        check_detail_on_fail(
            "questions holds both questions, with the gate and the " "human's note",
            [q.get("id") for q in opened] == ["r0_engine_1", "r0_engine_2"]
            and all(
                q.get("shown_at_gate") == GATE
                and q.get("human_answer") == NOTE
                and q.get("status") == "answered_at_gate"
                for q in opened
            ),
            str(opened)[:240],
        )
        check_detail_on_fail(
            "pending_questions is emptied",
            questions.pending(root) == [] and not questions.pending_node(root).exists(),
            str(questions.pending(root))[:120],
        )
        shown = _rows(ctx, "question_shown")
        check_detail_on_fail(
            "each is ledgered as `question_shown` with the note",
            sorted(r.get("question_id") for r in shown)
            == ["r0_engine_1", "r0_engine_2"]
            and all(
                r.get("human_note") == NOTE and r.get("module") == GATE for r in shown
            ),
            str(shown)[:200],
        )

        humangate.configure_file_mode(root, None)
        payload, printed = _ask(ctx)
        check_detail_on_fail(
            "the card after that carries no question: each is put once",
            isinstance(payload, dict)
            and payload.get("engine_questions") == []
            and "QUESTIONS THE ENGINE RAISES" not in printed,
            str(
                payload.get("engine_questions")
                if isinstance(payload, dict)
                else payload
            ),
        )


def main() -> int:
    with temp_record("run") as root:
        ctx = _Ctx(root)
        test_a_reinterpretation_is_dropped_and_asked(ctx)
        test_validation_twice_asks_once(ctx)
        test_the_next_gate_carries_them_and_records_the_answer(ctx)
    return finish(
        "\nENGINE QUESTIONS",
        "\nENGINE QUESTIONS UNIT OK — a reinterpretation is refused as an axis, "
        "queued once as a numbered question, carried on the next gate card, and "
        "recorded with the human's answer",
    )


if __name__ == "__main__":
    sys.exit(main())
