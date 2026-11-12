"""A revision move on the observation layer or the parameter table seeds the next round.

S11's `run` is driven over a finished round in a throwaway run record, with a
canned proposal in place of the agent and the approval gate in file mode:

  1. an assembly-side move (`change_noise_model`) is applied only on the
     human's yes; the next round carries the model and parameters unchanged
     and the assembly with exactly that noise block edited, the round's
     `revision` records the move, and S3 of the next round takes the edited assembly as
     its pre-seed without drafting;
  2. a proposal that reproduces an evaluated configuration is refused before
     the gate, charged to the proposal's dossier and re-asked; the
     parameter-side move after it (`change_bounds`) edits only that row's
     bounds and carries the assembly unchanged;
  3. `fix_parameter` fixes the parameter at the proposed nominal value;
  4. a stop against open misfit indicators is put to the human once
     (`decisions/revision_proposal_stop_vs_revise`), the approval gate receives its own
     answer (`decisions/revision_proposal`), and every ask of the agent is cached
     under its own name, so no resume pays for it again (1 and 2 check the
     same for the approval gate alone, after a refusal too).

    uv run python tests/revision_moves_unit.py
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import logging
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.WARNING)

from _harness import check_detail_on_fail, finish  # noqa: E402

from octomod.orchestration.interaction import humangate  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import engine as S3  # noqa: E402
from octomod.workflow_modules.revision import engine as S11  # noqa: E402
from tests._record import rnd, temp_record, work  # noqa: E402

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
GATE = "revision_proposal"
ANT = """model m
  compartment cell = 1;
  species A in cell = 10;
  species B in cell = 0;
  k1 = 0.3;
  k2 = 1;
  J0: A -> B; k1*A;
  J1: B -> ; k2*B;
end
"""
PARAMETERS = [
    {"id": "k1", "nominal_value": 0.3, "lb": 1e-3, "ub": 1e3, "estimate": True},
    {"id": "k2", "nominal_value": 1.0, "lb": 1e-3, "ub": 1e3, "estimate": True},
]
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
        {
            "condition_id": "c0",
            "maps_to_label": "c0",
            "overrides": {},
            "preequilibration": False,
        }
    ],
}


def _proposal(mtype: str, **args) -> dict:
    return {
        "move": {"type": mtype, "args": args},
        "motivated_by": f"the residuals point at {mtype}",
        "expected_effect": "the tails of the residuals shrink; falsified if not",
    }


TO_LAPLACE = _proposal(
    "change_noise_model", observable_id="obs_b", new_distribution="laplace"
)
# undoes TO_LAPLACE: the configuration round 0 already evaluated
BACK_TO_NORMAL = _proposal(
    "change_noise_model",
    observable_id="obs_b",
    new_distribution="normal",
    new_formula="sigma_obs_b",
)
WIDER_K1 = _proposal("change_bounds", parameter_id="k1", lb=0.01, ub=50.0)
FIX_K2 = _proposal("fix_parameter", parameter_id="k2", value=0.7)
STOP = {
    "move": {"type": "stop", "args": {}},
    "motivated_by": "the fit meets the intent's criteria",
    "expected_effect": "",
}
NARROW_K1 = _proposal("change_bounds", parameter_id="k1", lb=0.02, ub=20.0)


class Ctx:
    """What S11 (and S3's pre-seed read) takes off a RunContext."""

    def __init__(self, root: Node, round_idx: int, replies: list[dict]):
        self.root, self.round_idx, self.candidate = root, round_idx, None
        self.spec, self.ledger, self.auto = SPEC, Ledger(root.store), False
        self.intent = {"question": "how fast is B cleared?"}
        self.description = "A converts to B, which is cleared; B is measured."
        self.replies = list(replies)
        self.contexts: list[dict] = []

    @property
    def store(self):
        return self.root.store

    @property
    def round(self) -> Node:
        return tree.round_node(self.root, self.round_idx)

    @property
    def work(self) -> Node:
        return tree.work_node(self.round, None)

    @property
    def model(self) -> Node:
        return tree.model_node(self.round, None)

    @property
    def gates(self) -> Node:
        return tree.gates_node(self.round, None)

    @property
    def agent_calls(self) -> Node:
        return self.round / "agent_calls"

    def call(self, role: str, context: dict, name: str | None = None) -> dict:
        """The canned proposal in place of the agent; no model is asked. The
        ask and its reply are archived under `agent_calls/<name>` as the real
        call archives them."""
        assert role == "revision_proposal", role
        self.contexts.append(copy.deepcopy(context))
        reply = copy.deepcopy(
            self.replies[min(len(self.contexts), len(self.replies)) - 1]
        )
        call = self.agent_calls.child(name or role)
        (call / "prompt").put_text(_identity(context))
        (call / "reply").put(reply)
        return reply

    def call_cached(
        self, role: str, context: dict, calls=None, name: str | None = None
    ) -> dict:
        """`RunContext.call_cached`'s rule: an ask already answered under this
        name with the same prompt is read back, not asked again. The context
        stands in for the prompt, which is a function of it."""
        call = self.agent_calls.child(name or role)
        if (call / "reply").exists() and (call / "prompt").text(None) == _identity(
            context
        ):
            return (call / "reply").get()
        return self.call(role, context, name=name)


def _identity(context: dict) -> str:
    return json.dumps(context, sort_keys=True, default=str)


def _stage_round_0(root: Node) -> None:
    rd = rnd(root, 0)
    (tree.model_node(rd, None) / "antimony").put_text(ANT)
    (tree.model_node(rd, None) / "parameters").put(PARAMETERS)
    (work(root, 0) / "assembly").put(ASSEMBLY)
    (rd / "data/measurements").put_table(
        pd.DataFrame(
            [
                {
                    "observable_label": "b",
                    "condition_label": "c0",
                    "condition_key": "c0",
                    "time": t,
                    "value": v,
                }
                for t, v in ((0.0, 0.0), (1.0, 2.1), (2.0, 2.9), (4.0, 2.4))
            ]
        )
    )


@contextlib.contextmanager
def _file_gate(root: Node):
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


def _revise(ctx: Ctx, history: list[dict]):
    """S11 as the loop calls it: the returned move, or the exception raised."""
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return S11.run(ctx, {}, history, 3)
    except Exception as e:  # noqa: BLE001 — the outcome under test
        return e


def _history(root: Node, upto: int) -> list[dict]:
    return [
        {
            "round": k,
            "config_hash": S11.config_hash(rnd(root, k)),
            "best_fval": 1.0,
            "move": None,
        }
        for k in range(upto + 1)
    ]


def _seeded(root: Node, k: int) -> bool:
    """Round k was prepared; otherwise that is recorded as a failure."""
    rd = rnd(root, k)
    ok = (tree.model_node(rd, None) / "antimony").exists() and (
        work(root, k) / "assembly"
    ).exists()
    check_detail_on_fail(f"round {k} was seeded, so the next move starts from it", ok)
    return ok


def _gate_rows(ctx: Ctx, round_idx: int) -> list[dict]:
    return [
        e
        for e in ctx.ledger.entries()
        if e.get("event") == "human_gate"
        and e.get("module") == GATE
        and e.get("round") == round_idx
    ]


def test_an_assembly_move_seeds_the_next_round(root: Node) -> None:
    ctx = Ctx(root, 0, [TO_LAPLACE])
    humangate.configure_file_mode(root, None)
    out = _revise(ctx, _history(root, 0))
    r1 = rnd(root, 1)
    check_detail_on_fail(
        "the proposal pauses at the approval gate, and nothing is applied yet",
        isinstance(out, humangate.GatePending)
        and out.payload.get("module") == GATE
        and not r1.exists()
        and not (rnd(root, 0) / "revision").exists(),
        repr(out)[:200],
    )
    humangate.configure_file_mode(root, True, "")
    out = _revise(ctx, _history(root, 0))
    check_detail_on_fail(
        "on the human's yes the move is returned", out == TO_LAPLACE, repr(out)[:200]
    )
    check_detail_on_fail(
        "the resume that answers the gate asks the agent nothing: the proposal "
        "the card showed is read back from the record under its own name",
        len(ctx.contexts) == 1
        and (rnd(root, 0) / "agent_calls/revision_proposal_1/reply").get(None)
        == TO_LAPLACE,
        f"{len(ctx.contexts)} call(s)",
    )
    decided = (rnd(root, 0) / "decisions/revision_proposal").get(None) or {}
    check_detail_on_fail(
        "the approval is recorded at decisions/revision_proposal",
        decided.get("approved") is True and decided.get("module") == GATE,
        str(decided)[:200],
    )
    check_detail_on_fail(
        "the round's revision records the move with its motivation and prediction",
        (rnd(root, 0) / "revision").get(None) == TO_LAPLACE,
    )
    asm = (work(root, 1) / "assembly").get(None) or {}
    expected = copy.deepcopy(ASSEMBLY)
    expected["noise"][0]["distribution"] = "laplace"
    check_detail_on_fail(
        "the next round's assembly differs from this one in that noise block only",
        asm == expected,
        str(asm.get("noise")),
    )
    ant = tree.model_node(r1, None) / "antimony"
    check_detail_on_fail(
        "the model and the parameter table carry forward unchanged, with the data",
        ant.exists()
        and ant.text() == ANT
        and (tree.model_node(r1, None) / "parameters").get(None) == PARAMETERS
        and (r1 / "data/measurements").exists()
        and not (r1 / "directive").exists(),
        str(sorted(r1.children()) if r1.exists() else []),
    )
    check_detail_on_fail(
        "the move makes a new configuration",
        ant.exists() and S11.config_hash(r1) != S11.config_hash(rnd(root, 0)),
    )
    rows = _gate_rows(ctx, 0)
    check_detail_on_fail(
        "the approval is ledgered as the human's answer, pause first",
        [r.get("approved") for r in rows] == [True]
        and rows[0].get("mode") == "file"
        and any(
            e.get("event") == "gate_pending" and e.get("module") == GATE
            for e in ctx.ledger.entries()
        ),
        str(rows)[:200],
    )
    if not (work(root, 1) / "assembly").exists():
        return  # nothing was seeded; the checks above say so
    ctx1 = Ctx(root, 1, [])
    long_df = (r1 / "data/measurements").table()
    seeded = S3._get_or_draft_assembly(ctx1, "", long_df, {})
    check_detail_on_fail(
        "S3 of the next round takes the edited assembly as its pre-seed, with no "
        "agent drafting it",
        seeded == expected
        and not ctx1.contexts
        and any(
            e.get("note") == "assembly pre-seeded by revision move"
            and e.get("round") == 1
            for e in ctx1.ledger.entries()
        ),
        str(seeded.get("noise") if isinstance(seeded, dict) else seeded),
    )


def test_a_repeat_is_refused_then_a_bound_move_applies(root: Node) -> None:
    ctx = Ctx(root, 1, [BACK_TO_NORMAL, WIDER_K1])
    humangate.configure_file_mode(root, None)
    paused = _revise(ctx, _history(root, 1))
    humangate.configure_file_mode(root, True, "")
    out = _revise(ctx, _history(root, 1))
    check_detail_on_fail(
        "the pass after a refusal pauses at the gate, and the resume replays both "
        "asks from the record: the refused one and the one the card showed",
        isinstance(paused, humangate.GatePending)
        and paused.payload.get("module") == GATE
        and len(ctx.contexts) == 2,
        f"{paused!r:.120} · {len(ctx.contexts)} call(s)",
    )
    dossier = (rnd(root, 1) / "agent_calls/revision_proposal/dossier").get(None) or {}
    tried = dossier.get("attempts") or []
    check_detail_on_fail(
        "a move that undoes the last one reproduces round 0 and is refused before "
        "the gate, into the proposal's dossier",
        len(tried) == 1
        and "reproduces an already-evaluated configuration" in str(tried[0])
        and (tried[0].get("draft_summary") or {}).get("rejected_move")
        == BACK_TO_NORMAL["move"],
        str(tried)[:300],
    )
    redrafts = [
        e
        for e in ctx.ledger.entries()
        if e.get("event") == "redraft" and e.get("module") == GATE
    ]
    check_detail_on_fail(
        "the refusal is ledgered as a redraft of revision_proposal, and the re-ask "
        "carries it",
        len(redrafts) == 1
        and redrafts[0].get("role") == "revision_proposal"
        and len(ctx.contexts) == 2
        and "attempt_history" in ctx.contexts[1]
        and "attempt_history" not in ctx.contexts[0],
        f"{redrafts} · {len(ctx.contexts)} call(s)",
    )
    check_detail_on_fail(
        "the bound move is what is applied and recorded",
        out == WIDER_K1
        and (rnd(root, 1) / "revision").get(None) == WIDER_K1
        and [r.get("approved") for r in _gate_rows(ctx, 1)] == [True],
        repr(out)[:200],
    )
    r2 = rnd(root, 2)
    pars = (tree.model_node(r2, None) / "parameters").get(None) or []
    expected = copy.deepcopy(PARAMETERS)
    expected[0]["lb"], expected[0]["ub"] = 0.01, 50.0
    check_detail_on_fail(
        "the next round's parameter table has k1's bounds moved and nothing else",
        pars == expected,
        str(pars),
    )
    check_detail_on_fail(
        "and it carries this round's assembly unchanged",
        (work(root, 2) / "assembly").get(None) == (work(root, 1) / "assembly").get(),
    )


def test_fix_parameter_sets_the_nominal(root: Node) -> None:
    ctx = Ctx(root, 2, [FIX_K2])
    humangate.configure_file_mode(root, True, "")
    out = _revise(ctx, _history(root, 2))
    pars = (tree.model_node(rnd(root, 3), None) / "parameters").get(None) or []
    k2 = next((p for p in pars if p.get("id") == "k2"), {})
    k1 = next((p for p in pars if p.get("id") == "k1"), {})
    check_detail_on_fail(
        "fix_parameter fixes k2 at the proposed value and leaves k1 as round 2 had it",
        out == FIX_K2
        and k2.get("estimate") is False
        and k2.get("nominal_value") == 0.7
        and (k1.get("lb"), k1.get("ub"), k1.get("estimate")) == (0.01, 50.0, True),
        str(pars),
    )


def test_a_stop_against_open_indicators_is_asked_once(root: Node) -> None:
    """Two gates in one module, each answer resumed through the file protocol:
    the stop gate is asked once, the approval gate receives its own answer,
    and neither ask of the agent is paid twice."""
    ctx = Ctx(root, 3, [STOP, NARROW_K1])
    report = {"misfit_evidence": {"open": True, "reasons": ["sigma above floor"]}}

    def revise():
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                return S11.run(ctx, report, _history(root, 3), 3)
        except Exception as e:  # noqa: BLE001 — the outcome under test
            return e

    humangate.configure_file_mode(root, None)
    first = revise()
    humangate.configure_file_mode(root, True, "")
    second = revise()
    humangate.configure_file_mode(root, True, "")
    third = revise()
    check_detail_on_fail(
        "the stop pauses at its own gate; its yes buys the override ask, which "
        "pauses at the approval gate; that yes approves the move the card showed",
        isinstance(first, humangate.GatePending)
        and first.payload.get("module") == "revision_proposal_stop_vs_revise"
        and isinstance(second, humangate.GatePending)
        and second.payload.get("module") == GATE
        and third == NARROW_K1,
        f"{first!r:.80} · {second!r:.80} · {third!r:.80}",
    )
    r3 = rnd(root, 3)
    check_detail_on_fail(
        "each ask of the agent is made once, under its own name",
        len(ctx.contexts) == 2
        and (r3 / "agent_calls/revision_proposal_1/reply").get(None) == STOP
        and (r3 / "agent_calls/revision_override_1/reply").get(None) == NARROW_K1
        and "human_override" in ctx.contexts[1],
        f"{len(ctx.contexts)} call(s)",
    )
    stop_rows = [
        e
        for e in ctx.ledger.entries()
        if e.get("event") == "human_gate"
        and e.get("module") == "revision_proposal_stop_vs_revise"
        and e.get("round") == 3
    ]
    check_detail_on_fail(
        "the stop gate is answered once and read back from "
        "decisions/revision_proposal_stop_vs_revise on the resume after it",
        [(r.get("approved"), r.get("mode")) for r in stop_rows]
        == [(True, "file"), (True, "recorded")]
        and ((r3 / "decisions/revision_proposal_stop_vs_revise").get(None) or {}).get(
            "approved"
        )
        is True
        and ((r3 / "decisions/revision_proposal").get(None) or {}).get("approved")
        is True,
        str([(r.get("approved"), r.get("mode")) for r in stop_rows]),
    )


def test_a_reentry_warns_when_an_assembly_move_is_not_carried() -> None:
    """A revision round's assembly-editing move is in the SEEDED assembly; a
    `--from-module assembly` re-entry sets it aside and the agents rebuild
    without it — S3 warns (console + ledger) and builds as asked. No warning for
    a parameter move, for a round whose assembly is still there, or after a
    human asked for a redraft (the redraft note is where the move is stated)."""
    from types import SimpleNamespace

    from octomod.workflow_modules.assembly import engine as assembly_module

    noise = {
        "type": "change_noise_model",
        "args": {"observable_id": "obs_Z", "new_distribution": "log-normal"},
    }
    with temp_record("warn") as root:
        led = Ledger(root.store)
        led.append("run_start")
        r1 = rnd(root, 1)
        ctx = SimpleNamespace(
            root=root,
            round=r1,
            work=work(root, 1),
            ledger=led,
            round_idx=1,
            candidate=None,
        )

        def seed(move):
            (r1 / "model/seed").put(
                {"seeded_from": {"round": 0, "via": "revision", "move": move}}
            )

        seed(noise)
        warned = assembly_module.warn_revision_move_not_carried(ctx)
        check_detail_on_fail(
            "an assembly move set aside by a re-entry is warned about",
            bool(warned) and "change_noise_model" in warned,
            str(warned),
        )
        rows = [r for r in led.entries() if r.get("revision_move_not_reapplied")]
        check_detail_on_fail(
            "and the warning is in the ledger with the move",
            len(rows) == 1 and rows[0]["move"]["type"] == "change_noise_model",
            str(rows),
        )
        # the shape S11 writes: the seed names the move's TYPE, and its
        # arguments are the previous round's recorded revision
        (rnd(root, 0) / "revision").put({"move": noise})
        seed("change_noise_model")
        warned = assembly_module.warn_revision_move_not_carried(ctx)
        check_detail_on_fail(
            "the seed's move type is resolved to the recorded move, arguments included",
            bool(warned) and "obs_Z" in warned,
            str(warned),
        )
        (work(root, 1) / "assembly").put({"observables": []})
        check_detail_on_fail(
            "no warning while the seeded assembly is still there",
            assembly_module.warn_revision_move_not_carried(ctx) is None,
        )
        (work(root, 1) / "assembly").delete()
        seed({"type": "free_parameter", "args": {"parameter_id": "k1"}})
        check_detail_on_fail(
            "no warning for a parameter move (it lives in the model)",
            assembly_module.warn_revision_move_not_carried(ctx) is None,
        )
        seed(noise)
        led.append("note", round_idx=1, note="redraft", human_redraft=True)
        check_detail_on_fail(
            "no warning after a human asked for a redraft",
            assembly_module.warn_revision_move_not_carried(ctx) is None,
        )


def main() -> int:
    with temp_record("run") as root:
        _stage_round_0(root)
        with _file_gate(root):
            test_an_assembly_move_seeds_the_next_round(root)
            # each test starts from the round the previous one seeded
            if _seeded(root, 1):
                test_a_repeat_is_refused_then_a_bound_move_applies(root)
            if _seeded(root, 2):
                test_fix_parameter_sets_the_nominal(root)
            if _seeded(root, 3):
                test_a_stop_against_open_indicators_is_asked_once(root)
    test_a_reentry_warns_when_an_assembly_move_is_not_carried()
    return finish(
        "\nREVISION MOVES",
        "\nREVISION MOVES UNIT OK — an observation-layer move and a parameter-table "
        "move are applied on the human's yes, recorded, and seed the next round; "
        "a repeat configuration is refused before the gate; each gate is asked "
        "once and each ask of the agent paid once across the file-gate resumes",
    )


if __name__ == "__main__":
    sys.exit(main())
