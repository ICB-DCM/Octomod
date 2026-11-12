"""A compile failure that names the observation model goes back to its author once, then drops.

  1. the classifier on AMICI's own messages: the importer's wrapper around
     "State-dependent observables are not supported, but obs_x depends on {A}"
     and a failed build in `dsigmaydp.cpp` name the observation model; an
     SBML-level error ("Global parameter 'cell' is missing a value") and the
     wrapper alone name nothing;
  2. the engine's context: under `engine_feedback` with source and addressee,
     never the human's keys; the human's context is unchanged; routing grants
     the keys to both assembly roles; replies older than an engine redraft are
     not reused over it;
  3. through `_fit_and_select` with S2/S3/S6/S7 stubbed and the cost module
     raising for one candidate on every pass: the first failure raises
     RedraftRequested (role `observation`, source `engine`, the engine's
     wording, only the named observable's row) into the loop's handler, which
     re-assembles every candidate on the finding; the ledger note carries
     `engine_feedback`, the round's `compile_feedback` is written, the rebuild
     removed the old assembly, the compile approval and the fitted candidate's
     cost marker, and set aside what a re-entry at estimation sets aside — a
     candidate's remembered `budget_declined`, the round's
     `estimation_settings` and a cost profile's solver override, moved under
     the round's `superseded/` and named on the ledger row; the second failure
     drops the candidate "after one engine
     redraft" and raises nothing; the re-asked compile card and the round's
     `decisions_md` say so; a resume whose agent never answered the finding
     gets it back, one after it did does not; a fresh invocation reads the
     budget back and drops it the same way;
  4. a carried round (no observation-model reply in the round's `agent_calls`)
     drops at the first failure as before, and so does a failure that names no
     block.

    uv run python tests/compile_feedback_unit.py
"""

from __future__ import annotations

import contextlib
import copy
import io
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.WARNING)

from _harness import check, finish  # noqa: E402
from _record import record_at  # noqa: E402

from octomod.agents import routing  # noqa: E402
from octomod.orchestration import round_status as rs  # noqa: E402
from octomod.orchestration.interaction import human_redraft as hr  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.orchestration.orchestrator import Orchestrator  # noqa: E402
from octomod.orchestration.run_context import RunContext, as_candidate  # noqa: E402
from octomod.reporting import render as _render  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import engine as assembly_module  # noqa: E402
from octomod.workflow_modules.cost_probe import compile_feedback as cf  # noqa: E402
from octomod.workflow_modules.cost_probe import compile_gate  # noqa: E402
from octomod.workflow_modules.cost_probe import engine as cost_profile  # noqa: E402
from octomod.workflow_modules.cost_probe import solver_messages as msgs  # noqa: E402
from octomod.workflow_modules.data import engine as data_module  # noqa: E402
from octomod.workflow_modules.estimation import (  # noqa: E402
    engine as estimation_module,  # noqa: E402
)
from octomod.workflow_modules.estimation import estimation_settings  # noqa: E402
from octomod.workflow_modules.evaluation import (  # noqa: E402
    engine as evaluation_module,  # noqa: E402
)

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
WRAPPER = (
    "The SBML model contains features that are currently not supported by the "
    "AMICI SBML importer."
)
STATE_DEPENDENT = (
    "State-dependent observables are not supported, but obs_x depends on {A}."
)
BUILD_OUTPUT = (
    b"running build_ext\n"
    b"/Users/someone/.amici_cache/amici_ab12/m_ab12/dsigmaydp.cpp:23:45: error: "
    b"use of undeclared identifier 'S0'\n"
    b"    dsigmaydp[1] = sigma_rel_obs_x*S0;\n"
    b"1 error generated.\n"
)
MODEL_LEVEL = "Global parameter 'cell' is missing a value"
OBSERVABLES = (
    "observableId\tobservableFormula\tnoiseFormula\tnoiseDistribution\n"
    "obs_x\tA\tsigma_obs_x * A\tnormal\n"
    "obs_y\tB\tsigma_obs_y\tnormal\n"
)
REPLY = {
    "observables": [
        {"observable_id": "obs_x", "maps_to_label": "x", "formula": "A"},
        {"observable_id": "obs_y", "maps_to_label": "y", "formula": "B"},
    ]
}
FAILING = "X"


class SBMLException(Exception):
    """Stands in for AMICI's importer exception: same wrapping, no AMICI import."""


def _import_failure() -> Exception:
    """AMICI's importer failure as it is raised: the wrapper, from the cause."""
    try:
        try:
            raise NotImplementedError(STATE_DEPENDENT)
        except NotImplementedError as cause:
            raise SBMLException(WRAPPER) from cause
    except SBMLException as e:
        return e


def _build_failure() -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(
        1, ["python", "setup.py", "build_ext"], output=BUILD_OUTPUT
    )


# ------------------------------------------------------ 1. the classifier


def test_the_classifier_on_amicis_messages() -> None:
    lines = msgs.failure_lines(_import_failure())
    check(
        "the importer's wrapper is read with its cause",
        lines
        == [f"SBMLException: {WRAPPER}", f"NotImplementedError: {STATE_DEPENDENT}"],
        str(lines),
    )
    check(
        "… and names the observation model",
        msgs.attribute_compile_error("\n".join(lines)) == "observation",
    )
    check(
        "the wrapper alone names nothing",
        msgs.attribute_compile_error(f"SBMLException: {WRAPPER}") is None,
    )
    build = msgs.failure_lines(_build_failure())
    check(
        "a failed build is read from the compiler's error lines, the path cut",
        "dsigmaydp.cpp:23:45: error: use of undeclared identifier 'S0'" in build
        and not any("/Users/" in ln for ln in build)
        and not any("running build_ext" in ln for ln in build),
        str(build),
    )
    check(
        "… and the dsigmaydp error names the observation model",
        msgs.attribute_compile_error("\n".join(build)) == "observation",
    )
    check(
        "an SBML-level error names nothing",
        msgs.attribute_compile_error(f"RuntimeError: {MODEL_LEVEL}") is None,
    )
    check(
        "noise and observable ids name the observation model",
        msgs.attribute_compile_error("noiseParameter1_obs_y has no value")
        == "observation"
        and msgs.attribute_compile_error("unknown observableParameter1_z")
        == "observation",
    )
    check(
        "an id is named alone or at the end of a PEtab name, not as a prefix",
        cf.named_ids("noiseParameter1_obs_x; sigma_obs_y", ["obs_x", "obs_y"])
        == ["obs_x", "obs_y"]
        and cf.named_ids("obs_x2 and obs_x_total", ["obs_x"]) == [],
    )


# ------------------------------------------------ 2. the engine's context


def test_the_engine_context_is_the_engines() -> None:
    finding = "The AMICI compile or fit of candidate 'X' failed"
    mine = hr.context_for(finding, "observation", REPLY, source=hr.ENGINE)
    theirs = hr.context_for(
        finding,
        "condition",
        {"conditions": []},
        source=hr.ENGINE,
        addressed_to="observation",
    )
    fb = mine.get("engine_feedback") or {}
    check(
        "the engine's finding is under `engine_feedback`, with source and addressee",
        fb
        == {
            "source": "engine",
            "addressed_to": "observation",
            "finding": finding,
        },
        str(fb),
    )
    check(
        "… no human key reaches the agent, and the instruction says who sent it",
        not any(k.startswith("human_") for k in (*mine, *theirs))
        and mine["engine_feedback_instruction"].startswith("The ENGINE, not a person")
        and "HUMAN" not in mine["engine_feedback_instruction"],
        str(sorted(mine)),
    )
    check(
        "… with the role's own previous reply",
        mine.get("previous_reply") == REPLY,
    )
    check(
        "a role it is not addressed to is told to keep its reply",
        "It is not addressed to you" in theirs["engine_feedback_instruction"]
        and theirs["engine_feedback"]["addressed_to"] == "observation",
    )
    human = hr.context_for("add a scaling factor", "observation")
    check(
        "the human's context is unchanged",
        sorted(human) == ["human_feedback", "human_feedback_instruction"]
        and human["human_feedback_instruction"].startswith("A HUMAN read"),
        str(sorted(human)),
    )
    check(
        "routing grants the engine's keys to both assembly roles",
        not routing.violations("observation", list(mine))
        and not routing.violations("condition", list(theirs)),
        str(
            routing.violations("observation", list(mine))
            + routing.violations("condition", list(theirs))
        ),
    )
    # the replies in the record answer the redraft only if they are younger
    # than it
    with tempfile.TemporaryDirectory() as tmp_s:
        ctx = _context(Path(tmp_s), drafted=True)
        (ctx.agent_calls.child("condition") / "reply").put({})
        ctx.store.replace_ledger(
            [
                {
                    "ts": "2026-01-01T10:00:00",
                    "round": 0,
                    "event": "agent_call",
                    "role": "observation",
                },
                {
                    "ts": "2026-01-01T10:01:00",
                    "round": 0,
                    "event": "agent_call",
                    "role": "condition",
                },
                {
                    "ts": "2026-01-01T10:05:00",
                    "round": 0,
                    "event": "note",
                    "engine_feedback": True,
                },
            ]
        )
        ctx.ledger = Ledger(ctx.root)
        check(
            "replies older than an engine redraft are not reused over it",
            assembly_module._paid_replies_to_reuse(ctx) is None,
        )
        check(
            "… and the redraft is the engine's on record, not a person's",
            assembly_module.engine_redraft_this_round(ctx)
            and not assembly_module.redraft_asked_this_round(ctx),
        )


# --------------------------------------------------------- 3./4. the loop


def _context(tmp: Path, *, drafted: bool) -> RunContext:
    """A fresh context over the run record in `tmp`, as a new invocation
    builds one."""
    case = tmp / "input"
    case.mkdir(exist_ok=True)
    (case / "testcase.yaml").write_text(
        "name: compile_feedback\nt_end: 8\nholdout:\n  condition_labels: []\n"
    )
    root = record_at(tmp / "run")
    if not root.store.exists_on_disk():
        root.store.create()
    (root / "intent").put(
        {
            "question": "does A decay into B?",
            "system": "toy",
            "inference_target": "mechanism_discrimination",
        }
    )
    ctx = RunContext(
        root=root,
        testcase_dir=case,
        spec=SPEC,
        ledger=Ledger(root),
        backend="stub",
        auto=False,
    )
    if drafted:
        (ctx.agent_calls.child(cf.ROLE) / "reply").put(REPLY)
    return ctx


def _stage_round(ctx: RunContext, cands: list[str]) -> None:
    """The round as it stands when the compile card has been signed."""
    rnd = ctx.round
    (rnd / "space/candidates").put([{"id": c} for c in cands])
    (rnd / "shared_assembly").put({"observables": REPLY["observables"]})
    compile_gate.decision_node(rnd).put({"approved": True})
    ctx.set_marker("candidate_compile", n_candidates=len(cands))
    table = pd.read_csv(io.StringIO(OBSERVABLES), sep="\t")
    for cid in cands:
        with as_candidate(ctx, cid):
            (ctx.work / "petab/observables").put_table(table)
            (ctx.work / "assembly").put({"observables": []})
            ctx.set_marker("s3", producer="unit test")


class _Orch:
    """The assemble-compile-fit loop on a stand-in orchestrator; every module is
    a stub, and each RedraftRequested that leaves the inner step is recorded."""

    _fit_and_select = Orchestrator._fit_and_select

    def __init__(self, ctx):
        self.ctx, self.ledger = ctx, ctx.ledger
        self.root, self.store = ctx.root, ctx.store
        self.max_rounds = None
        self.raised: list[hr.RedraftRequested] = []

    def _fit_and_select_once(self, cand_ids):
        try:
            return Orchestrator._fit_and_select_once(self, cand_ids)
        except hr.RedraftRequested as req:
            self.raised.append(req)
            raise

    def _order_by_fit_on_disk(self, cand_ids):
        return list(cand_ids), [], None

    def _remerge_stale_candidates(self, cand_ids):
        pass

    def _maybe_expand_space(self, report, fitted):
        return None

    def _write_analysis(self):
        pass


class _Patched:
    """Module attributes replaced for a block and restored after it."""

    def __init__(self, *triples):
        self.triples = triples
        self.saved: list = []

    def __enter__(self):
        for obj, name, value in self.triples:
            self.saved.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)
        return self

    def __exit__(self, *exc):
        for obj, name, value in reversed(self.saved):
            setattr(obj, name, value)
        return False


def _drive(ctx: RunContext, cands: list[str], failure) -> dict:
    """`_fit_and_select` over `cands` with the cost module raising `failure()`
    for the failing candidate on every pass; what each stub saw, returned."""
    seen: dict = {"s3": [], "cards": [], "costs": [], "evaluated": []}

    def _s3(c):
        block = c.cache.get("_human_feedback")
        seen["s3"].append(
            {
                "candidate": c.candidate,
                "block": copy.deepcopy(block),
                "obs_ctx": hr.with_previous(c, "observation", block),
                "cond_ctx": hr.with_previous(c, "condition", block),
                "shared_in_record": (c.round / "shared_assembly").exists(),
            }
        )

    def _card(c, ids):
        seen["cards"].append(
            {
                "ids": list(ids),
                "signed": c.has_marker("candidate_compile"),
                "decision": compile_gate.decision_node(c.round).exists(),
            }
        )

    def _cost(c, **kw):
        seen["costs"].append(
            (
                c.candidate,
                c.marker("cost").exists(),
                c.cache.get("_budget_reference"),
            )
        )
        if c.candidate == FAILING:
            raise failure()
        c.set_marker("cost", approved_n_starts=30, median_start_s=0.05)
        c.cache["_budget_reference"] = {"candidate": c.candidate, "n_starts": 30}
        return 30

    def _s7(c, cand_ids=None, rounds_left=None):
        seen["evaluated"].append(list(cand_ids or []))
        return {
            "discrimination": {"winner": cand_ids[0], "decisive": True},
            "t2prime_passed": True,
        }

    orch = _Orch(ctx)
    buf = io.StringIO()
    with (
        _Patched(
            (data_module, "run", lambda c: None),
            (assembly_module, "run", _s3),
            (compile_gate, "ask", _card),
            (cost_profile, "run", _cost),
            (estimation_module, "run", lambda c, n: None),
            (evaluation_module, "run", _s7),
            (_render, "decisions_md", lambda rd: ""),
        ),
        contextlib.redirect_stdout(buf),
    ):
        try:
            seen["out"] = orch._fit_and_select(list(cands))
        except Exception as e:  # noqa: BLE001 — the outcome under test
            seen["out"] = e
    seen["raised"] = orch.raised
    seen["stdout"] = buf.getvalue()
    return seen


def _rows(ctx: RunContext, event: str, **match) -> list[dict]:
    return [
        e
        for e in ctx.ledger.entries()
        if e.get("event") == event and all(e.get(k) == v for k, v in match.items())
    ]


def test_the_loop_sends_it_back_once_then_drops() -> None:
    cands = ["base", FAILING]
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        ctx = _context(tmp, drafted=True)
        _stage_round(ctx, cands)
        # records made on the old problem, as a re-entry at estimation finds
        # them: a decline given at base's re-asked budget card (the stubbed
        # cost module does not read it), the round's solver choice, and base's
        # cost profile with the override that choice put on it
        base = tree.work_node(ctx.round, "base")
        (base / cost_profile.DECLINED_KEY).put(
            {
                "candidate": "base",
                "note": "not worth fitting",
                "reasons": [],
                "at": "2026-01-01T10:00:00",
            }
        )
        (ctx.round / estimation_settings.ROUND_KEY).put(
            {
                "solver": {"sensi_method": "adjoint"},
                "note": "adjoint",
                "at": "2026-01-01T10:00:00",
                "source": "the round's budget gate",
            }
        )
        (base / "cost").put(
            {
                "median_start_s": 0.05,
                "compile_s": 0.0,
                "gate_overrides": {"sensi_method": "adjoint"},
            }
        )
        seen = _drive(ctx, cands, _import_failure)

        raised = seen["raised"]
        check(
            "one RedraftRequested reached the loop's handler, for observation, from the engine",
            len(raised) == 1
            and raised[0].role == "observation"
            and raised[0].source == hr.ENGINE,
            str([(r.role, r.source) for r in raised]),
        )
        text = raised[0].text if raised else ""
        check(
            "… in the engine's words: what failed, AMICI's lines, what to return",
            text.startswith(f"The AMICI compile or fit of candidate '{FAILING}' failed")
            and STATE_DEPENDENT in text
            and WRAPPER in text
            and text.rstrip().endswith(
                "Change what the error names and return the same contract in full."
            ),
            text[:400],
        )
        check(
            "… carrying the row of the observable it names, and not the other",
            "obs_x\tA\tsigma_obs_x * A\tnormal" in text
            and "obs_y\t" not in text
            and "ids it names (obs_x)" in text,
            text[-300:],
        )
        notes = _rows(ctx, "note", engine_feedback=True)
        check(
            "one ledger note carries engine_feedback, at candidate_compile, naming role and candidate",
            len(notes) == 1
            and notes[0].get("module") == "candidate_compile"
            and notes[0].get("role") == "observation"
            and notes[0].get("candidate") == FAILING
            and "State-dependent observables" in str(notes[0].get("error_head"))
            and "not a person's request" in str(notes[0].get("note")),
            str(notes)[:300],
        )
        check(
            "… and no row claims a human asked",
            not [e for e in ctx.ledger.entries() if e.get("human_redraft")],
        )
        decline_key = f"candidates/base/{cost_profile.DECLINED_KEY}"
        moved = [decline_key, estimation_settings.ROUND_KEY]
        kept = ctx.round / rs.SUPERSEDED_KEY
        stamps = [s for s in kept.children() if s.startswith("estimation_")]
        check(
            "the redraft moved base's decline and the round's solver choice under "
            "superseded/estimation_<stamp>/, as a re-entry at estimation does",
            len(stamps) == 1 and all((kept / stamps[0] / k).exists() for k in moved),
            f"{kept.key}: {kept.children()}",
        )
        check(
            "… and neither is at its key any more",
            not (base / cost_profile.DECLINED_KEY).exists()
            and not (ctx.round / estimation_settings.ROUND_KEY).exists(),
        )
        check(
            "… so the decline is not remembered on the rebuilt problem",
            cost_profile.remembered_decline(base) is None,
        )
        row = notes[0] if notes else {}
        check(
            "the engine-feedback row names what was set aside: the moved keys, the "
            "forgotten compile approval and the dropped solver override",
            set(moved + ["candidates/base/cost"])
            <= set(row.get("superseded_files") or [])
            and "decisions/assembly_cost_boundary"
            in (row.get("forgotten_decisions") or [])
            and row.get("dropped_solver_overrides") == ["candidates/base/cost"],
            str(
                {
                    k: row.get(k)
                    for k in (
                        "superseded_files",
                        "forgotten_decisions",
                        "dropped_solver_overrides",
                    )
                }
            ),
        )
        rec = cf.spent(ctx.round)
        check(
            "the round's compile_feedback records candidate, role, error head and attempt",
            rec is not None
            and rec.get("candidate") == FAILING
            and rec.get("role") == "observation"
            and rec.get("attempt") == 1
            and "State-dependent" in str(rec.get("error_head")),
            str(rec)[:200],
        )
        passes = [s["candidate"] for s in seen["s3"]]
        check(
            "every candidate was assembled again after the redraft",
            passes == cands + cands,
            str(passes),
        )
        second = [s for s in seen["s3"][len(cands) :]]
        block = second[0]["block"] if second else None
        check(
            "the second pass assembles on the engine's finding, cached for both agents",
            isinstance(block, dict)
            and block.get("engine_feedback", {}).get("finding") == text
            and "human_feedback" not in block,
            str(block)[:200],
        )
        obs_ctx = second[0]["obs_ctx"] if second else {}
        check(
            "… which the observation agent sees as the engine's, with its own reply",
            obs_ctx.get("engine_feedback", {}).get("addressed_to") == "observation"
            and obs_ctx.get("previous_reply") == REPLY
            and obs_ctx["engine_feedback_instruction"].startswith(
                "The ENGINE, not a person"
            )
            and not any(k.startswith("human_") for k in obs_ctx),
            str(sorted(obs_ctx)),
        )
        cond_ctx = second[0]["cond_ctx"] if second else {}
        check(
            "… and the condition agent as addressed to another role",
            "It is not addressed to you"
            in cond_ctx.get("engine_feedback_instruction", ""),
        )
        check(
            "the rebuild removed the old shared assembly before the second pass",
            seen["s3"][0]["shared_in_record"]
            and second
            and not second[0]["shared_in_record"]
            and not (tree.work_node(ctx.round, FAILING) / "assembly").exists()
            and not tree.markers_node(ctx.round, FAILING).child("s3").exists(),
        )
        cards = seen["cards"]
        check(
            "… and the compile approval: the card is asked again on the rebuilt problem",
            len(cards) == 2
            and cards[0]["signed"]
            and cards[0]["decision"]
            and not cards[1]["signed"]
            and not cards[1]["decision"],
            str(cards),
        )
        costs = seen["costs"]
        check(
            "… and the fitted candidate's cost marker and the round's budget reference",
            [c[0] for c in costs] == ["base", FAILING, "base", FAILING]
            and costs[2][1] is False
            and costs[2][2] is None,
            str(costs),
        )
        drops = _rows(ctx, "candidate_dropped", candidate=FAILING)
        check(
            "the second failure drops the candidate, after one engine redraft",
            len(drops) == 1
            and drops[0].get("module") == "candidate_compile"
            and str(drops[0].get("reason", "")).startswith(
                "compile or fit failed after one engine redraft of the observation model this round"
            )
            and f"(sent for candidate {FAILING})" in str(drops[0].get("reason")),
            str(drops)[:300],
        )
        check(
            "… the round goes on with the other candidate",
            seen["out"] == 0 and seen["evaluated"] == [["base"]],
            f"{seen['out']!r} {seen['evaluated']}",
        )
        check(
            "the finding is not handed to a later call once the pass is assembled",
            ctx.cache.get("_human_feedback") is None,
        )
        card = cf.card_lines(ctx)
        check(
            "the re-asked compile card says why it is asked again",
            len(card) == 1
            and f"candidate {FAILING}'s compile failure" in card[0]
            and "asked again on the redrafted assembly" in card[0],
            str(card),
        )
        record = _render.decisions_md(ctx.round)
        check(
            "the round's decisions_md lists the engine's redraft beside the drop",
            "the engine sent candidate X's compile or fit failure back" in record
            and "after one engine redraft" in record,
            record[-400:],
        )

        # -- a resume whose agent never answered gets the finding back -------
        ctx_r = _context(tmp, drafted=True)
        cf.restore(ctx_r)
        back = (ctx_r.cache.get("_human_feedback") or {}).get("engine_feedback") or {}
        check(
            "a resume with no accepted reply after the redraft gets the finding back",
            back.get("finding") == text and back.get("source") == "engine",
            str(back)[:160],
        )
        ctx_r.ledger.append(
            "agent_call", module="assembly", round_idx=0, role="observation"
        )
        ctx_a = _context(tmp, drafted=True)
        cf.restore(ctx_a)
        check(
            "… and a resume after the agent answered it does not",
            ctx_a.cache.get("_human_feedback") is None,
        )

        # -- a fresh invocation reads the spent budget back ------------------
        ctx2 = _context(tmp, drafted=True)
        _stage_round(ctx2, cands)
        seen2 = _drive(ctx2, cands, _import_failure)
        check(
            "a resume reads the budget back: no second redraft",
            not seen2["raised"] and len(_rows(ctx2, "note", engine_feedback=True)) == 1,
            f"raised={len(seen2['raised'])}",
        )
        drops = _rows(ctx2, "candidate_dropped", candidate=FAILING)
        check(
            "… and drops the candidate after one engine redraft",
            len(drops) == 2
            and "after one engine redraft" in str(drops[-1].get("reason")),
            str([d.get("reason") for d in drops])[:300],
        )


def test_a_carried_round_or_an_unnamed_failure_drops_as_before() -> None:
    cands = ["base", FAILING]
    for label, drafted, failure, attributed in (
        ("a carried round", False, _import_failure, True),
        (
            "a failure that names no block",
            True,
            lambda: RuntimeError(MODEL_LEVEL),
            False,
        ),
    ):
        with tempfile.TemporaryDirectory() as tmp_s:
            ctx = _context(Path(tmp_s), drafted=drafted)
            _stage_round(ctx, cands)
            seen = _drive(ctx, cands, failure)
            drops = _rows(ctx, "candidate_dropped", candidate=FAILING)
            check(
                f"{label}: the first failure drops the candidate as before",
                not seen["raised"]
                and len(drops) == 1
                and str(drops[0].get("reason")).startswith("compile or fit failed — ")
                and "engine redraft" not in str(drops[0].get("reason")),
                str([d.get("reason") for d in drops])[:300],
            )
            check(
                f"{label}: no compile_feedback record, no engine_feedback note, "
                f"one assembly pass",
                cf.spent(ctx.round) is None
                and not _rows(ctx, "note", engine_feedback=True)
                and [s["candidate"] for s in seen["s3"]] == cands
                and seen["out"] == 0,
                f"{seen['out']!r}",
            )
            carried_note = [
                e
                for e in _rows(ctx, "note", candidate=FAILING)
                if "carried its assembly" in str(e.get("note"))
            ]
            check(
                (
                    f"{label}: the ledger says why it was not sent back"
                    if attributed
                    else f"{label}: nothing is said about sending it back"
                ),
                bool(carried_note) == attributed,
                str(carried_note)[:200],
            )


def main() -> int:
    test_the_classifier_on_amicis_messages()
    test_the_engine_context_is_the_engines()
    test_the_loop_sends_it_back_once_then_drops()
    test_a_carried_round_or_an_unnamed_failure_drops_as_before()
    return finish(
        "\nCOMPILE FEEDBACK UNIT",
        "\nCOMPILE FEEDBACK UNIT OK — a compile failure that names the observation "
        "model goes back to its author once, as the engine's finding, and a second "
        "failure, a carried round or an unnamed failure drops the candidate",
    )


if __name__ == "__main__":
    sys.exit(main())
