"""At the scope gate a human can buy back an earlier-declared axis by name.

  1. `axes:` adds a pooled axis (case-insensitive, deduplicated, unknown ids ignored);
  2. a model-module re-entry asks the scope gate again;
  3. a refused axis selection (none on a bought round, or none named at all)
     clears the scope answer, so a resume asks again;
  4. that refusal is a resumable stop: through the CLI, a plain resume with a
     new answer is not refused as an ended run, and the scope gate takes it;
     a refused `lattice` does not outlive its note;
  5. the rule holds however the answer arrives: a bare `--auto-approve` is
     refused in the pass that drafted the model, and `axes: none` is the
     explicit single-model answer the card offers;
  6. the construction agent's numbered questions survive a resume: the scope
     card a resumed process asks lists them, and `1: …` in the answer is
     recorded against the question as in the drafting pass;
  7. so do the citation-resolution and construction-audit lines, read back
     from what the drafting pass recorded.

    uv run python tests/human_axes_unit.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _record import (  # noqa: E402
    ledger_rows,
    pending_gate,
    rnd,
    run_root,
    temp_record,
)

from octomod.orchestration import round_status  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.workflow_modules.model import model_space  # noqa: E402

AXES = [{"id": "loop", "priority": 1}, {"id": "integrator", "priority": 2}]
POOL = {
    "loop": {"id": "loop"},
    "integrator": {"id": "integrator"},
    "arm_sigma_CXCL9": {
        "id": "arm_sigma_CXCL9",
        "on_assembly_patch": {
            "change_noise_model": {"observable_id": "obs_CXCL9", "new_per": "condition"}
        },
    },
    "amp": {
        "id": "amp",
        "on_antimony_patch": {"replace_reaction": "R1", "with": "R1: -> A; k"},
    },
}


class _Ctx:
    """What `_resolve_search` reads from a RunContext, on round 1 — on a
    record (the run is one file; `root` is its root node)."""

    def __init__(self, root):
        from octomod.orchestration.ledger import Ledger

        self.root = root
        self.store = root.store
        self.ledger = Ledger(root)
        self.round_idx = 1
        self.candidate = None
        self.spec = {"search.max_models": 8}
        self.cache: dict = {}
        self.testcase = {"t_end": 10.0}

    @property
    def round(self):
        return rnd(self.root, self.round_idx)

    @property
    def model(self):
        return tree.model_node(self.round, self.candidate)

    @property
    def gates(self):
        return tree.gates_node(self.round, self.candidate)

    @property
    def agent_calls(self):
        return self.round / "agent_calls"


def _assert_resumable_refusal(e: Exception, label: str) -> None:
    """The refusal is the stop the orchestrator records as resumable, naming
    the scope gate whose answer it cleared."""
    from octomod.orchestration import run_context as modules

    refused = getattr(modules, "NoteRefused", None)
    assert refused is not None and isinstance(e, refused), (
        f"{label}: the refusal is a plain {type(e).__name__}, so the stop ends "
        f"the run and run_guard refuses the plain resume the message promises"
    )
    assert e.gate == "model_scope", f"{label}: the refusal names {e.gate!r}"


def check_a_refused_bought_round_asks_the_scope_gate_again() -> None:
    """Selecting no axes on a round bought at the expansion gate is refused,
    and the refusal clears the recorded scope answer so a resume asks again."""
    from octomod.orchestration.run_context import ModuleFailure
    from octomod.workflow_modules.model.engine import (
        _resolve_search,
        axes_already_bought,
    )

    with temp_record() as root:
        ctx = _Ctx(root)
        prev = rnd(root, 0)
        (prev / "expansion").put({"expanded": True, "next_round": 1})
        model_dir = ctx.round / "model"
        (model_dir / "antimony").put_text("model m\n  R1: -> A; k\n  k = 1\nend\n")
        (model_dir / "parameters").put([{"id": "k"}])
        # what `ask_once` in `_scope_gate` wrote before `_resolve_search` ran
        decision = ctx.round / "decisions/model_scope"
        decision.put({"module": "model_scope", "approved": True, "note": "axes: none"})
        assert axes_already_bought(ctx), "the fixture round is not a bought round"
        try:
            _resolve_search(ctx, AXES, "axes: none", None, model_dir)
        except ModuleFailure as e:
            msg, e_seen = str(e), e
        else:
            raise AssertionError("no axes on a bought round was not refused")
        assert "already bought" in msg, msg
        _assert_resumable_refusal(e_seen, "no axes on a bought round")
        assert not decision.exists(), (
            "the refused scope answer is still recorded in decisions/model_scope, "
            "so every resume replays it into the same refusal"
        )
        assert (
            "Nothing was marked" not in msg and "asks again on resume" in msg
        ), f"the refusal does not say what a resume does: {msg}"


def _round0_model(ctx: _Ctx, note: str):
    """Round 0 with a model in the record and `note` recorded as the scope
    answer, as `ask_once` in `_scope_gate` leaves it before `_resolve_search`
    runs. Returns the round's model node."""
    ctx.round_idx = 0
    model_dir = ctx.round / "model"
    (model_dir / "antimony").put_text("model m\n  R1: -> A; k\n  k = 1\nend\n")
    (model_dir / "parameters").put([{"id": "k"}])
    _scope_decision(ctx).put({"module": "model_scope", "approved": True, "note": note})
    return model_dir


def _scope_decision(ctx: _Ctx):
    """The scope gate's recorded answer (was `model/scope_gate.json`)."""
    return ctx.round / "decisions/model_scope"


def check_an_unresolved_selection_asks_the_scope_gate_again() -> None:
    """A note that names no axes on a round with a model space is refused where
    the note is read, so no delivery mode can take it as a single-model round,
    and the refusal clears the recorded scope answer."""
    from octomod.orchestration.run_context import ModuleFailure
    from octomod.workflow_modules.model.engine import _resolve_search

    with temp_record() as root:
        ctx = _Ctx(root)
        model_dir = _round0_model(ctx, "looks fine")
        try:
            _resolve_search(ctx, AXES, "looks fine", None, model_dir)
        except ModuleFailure as e:
            msg, e_seen = str(e), e
        else:
            raise AssertionError("a note naming no axes was not refused")
        assert "selected no axes" in msg, msg
        _assert_resumable_refusal(e_seen, "a note naming no axes")
        assert not _scope_decision(ctx).exists(), (
            "the unresolved scope answer is still recorded in "
            "decisions/model_scope, so every resume replays it into the same "
            "refusal"
        )
        assert (
            "Nothing was marked" not in msg and "asks again on resume" in msg
        ), f"the refusal does not say what a resume does: {msg}"


def check_an_auto_answer_is_refused_or_taken_like_a_human_one() -> None:
    """The answer `--auto-approve` gives (`humangate.configure_auto_note`) is
    read by the same rule: bare, it is refused; `axes: none` keeps the round
    single-model and is recorded as the human's choice."""
    from octomod.orchestration.interaction import humangate
    from octomod.orchestration.run_context import ModuleFailure
    from octomod.workflow_modules.model.engine import SCOPE_NOTE_FORMS, _resolve_search

    def auto_answer(ctx: _Ctx, standing: str) -> str:
        saved = dict(humangate._AUTO_NOTE)
        humangate.configure_auto_note(standing)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                approved, note = humangate.ask(
                    "Is this the right model scope to spend compute on?",
                    [],
                    ledger=ctx.ledger,
                    module="model_scope",
                    round_idx=ctx.round_idx,
                    auto=True,
                )
        finally:
            humangate._AUTO_NOTE.clear()
            humangate._AUTO_NOTE.update(saved)
        assert approved, "--auto-approve did not approve"
        return note

    with temp_record() as root:
        ctx = _Ctx(root)
        model_dir = _round0_model(ctx, "")
        note = auto_answer(ctx, "")
        try:
            _resolve_search(ctx, AXES, note, None, model_dir)
        except ModuleFailure as e:
            _assert_resumable_refusal(e, f"the auto answer {note!r}")
        else:
            raise AssertionError(
                f"the bare auto answer {note!r} at a card that lists axes was "
                f"taken as a single-model round"
            )
        assert not _scope_decision(
            ctx
        ).exists(), "the refused auto answer is still recorded in decisions/model_scope"

    with temp_record() as root:
        ctx = _Ctx(root)
        note = auto_answer(ctx, "axes: none")
        model_dir = _round0_model(ctx, note)
        got = _resolve_search(ctx, AXES, note, None, model_dir)
        tiers = [r for r in ledger_rows(root) if '"tier_decision"' in json.dumps(r)]
        assert got is None and len(tiers) == 1, (got, tiers)
        assert tiers[0]["axes_selected"] == [] and tiers[0]["n_models"] == 1, tiers
        assert _scope_decision(
            ctx
        ).exists(), "`axes: none` was taken, yet its recorded answer was cleared"

    none = [f for f in SCOPE_NOTE_FORMS if f.startswith("axes: none")]
    bare = [f for f in SCOPE_NOTE_FORMS if f.startswith("(nothing)")]
    assert none and "single-model" in none[0], (
        "the scope card does not say `axes: none` keeps the round single-model: "
        f"{SCOPE_NOTE_FORMS}"
    )
    assert bare and "refused" in bare[0] and "single-model" not in bare[0], (
        "the scope card still says a bare answer keeps the round single-model: "
        f"{bare}"
    )
    print(
        "  auto answer    a bare --auto-approve is refused; `axes: none` is one "
        "model, and the card says both"
    )


def _rows(root) -> list[dict]:
    return ledger_rows(root)


def check_a_refused_scope_note_is_a_resumable_stop() -> None:
    """Through the CLI, as the front end drives it: a bare `y` at a scope card
    that lists axes is refused, the stop is recorded as resumable with the gate
    named, and the plain resume with `axes: all` is taken by the scope gate
    instead of being refused as an ended run."""
    case = REPO / "testcase" / "abcd_expansion"
    assert case.is_dir(), f"the fixture {case} is missing"
    with tempfile.TemporaryDirectory() as d:
        # every run this check makes lives in `d`; the quick overlay keeps the
        # stub run short
        env = dict(
            os.environ,
            OCTOMOD_RUNS_DIR=d,
            OCTOMOD_SPEC_OVERLAY=str(REPO / "workflows" / "overlays" / "quick.yaml"),
        )
        run_id = "note_refused"
        run_dir = run_root(run_id, Path(d))  # the record, runs/<id>.h5
        base = ["run", "--backend", "stub", "--run-id", run_id, "--gate-mode", "file"]

        # a fresh process per answer, as in file-gate mode; stderr is kept,
        # because the guard's refusal and the stop's instructions print there
        def cli(*extra: str) -> tuple[int, str]:
            p = subprocess.run(
                [sys.executable, "-m", "octomod", *base, *extra],
                cwd=REPO,
                env=env,
                capture_output=True,
                text=True,
            )
            return p.returncode, p.stdout + p.stderr

        def paused_at() -> str | None:
            pending = pending_gate(run_dir)
            return pending["module"] if pending is not None else None

        rc, out = cli("--testcase", "testcase/abcd_expansion")
        assert rc == 3 and paused_at() == "intent", (rc, paused_at(), out[-600:])
        rc, out = cli("--gate-answer", "y")
        assert rc == 3 and paused_at() == "model_scope", (
            rc,
            paused_at(),
            out[-600:],
        )
        # a bare yes names no axes on a card that lists them: refused
        rc, out = cli("--gate-answer", "y")
        assert rc == 1, f"a bare yes at the scope card was not refused: rc={rc}"
        rows = _rows(run_dir)
        end = [r for r in rows if r.get("event") == "run_end"][-1]
        assert end.get("outcome") == "stopped", end
        assert end.get("resumable") is True and end.get("gate") == "model_scope", (
            "the refusal's stop is recorded as an ending, so the guard refuses "
            f"the plain resume: {end}"
        )
        answered = max(
            i
            for i, r in enumerate(rows)
            if r.get("event") == "human_gate" and r.get("module") == "model_scope"
        )
        said = [
            r.get("note", "")
            for r in rows[answered:]
            if r.get("event") == "note" and "stays single-model" in r.get("note", "")
        ]
        assert not said, (
            "the ledger says the round stays single-model and then the run "
            f"stops on the refusal: {said}"
        )
        assert "RUN STOPPED" in out, out[-600:]
        assert "--gate-answer" in out.split("RUN STOPPED", 1)[1], (
            "the stop does not say how to answer again: " + out[-600:]
        )

        # `lattice` alone names no axes either: refused, and the mode it asked
        # for goes with it, so the next answer is not searched as a lattice
        mode_file = model_space.search_mode_node(rnd(run_dir, 0))
        rc, out = cli("--gate-answer", "y", "--gate-note", "lattice")
        assert rc == 1 and "selected no axes" in out, (rc, out[-600:])
        left = mode_file.get(None) or {}
        assert left.get("mode") != model_space.LATTICE, (
            "the refused note's `lattice` is still recorded for the round, so "
            f"the next answer would be searched as a lattice: {left}"
        )

        # the plain resume with an answer the card accepts
        rc, out = cli("--gate-answer", "y", "--gate-note", "axes: all")
        assert "already ended" not in out, (
            "the guard refused the plain resume after a refused note: " + out[-600:]
        )
        assert rc in (0, 1, 3), (rc, out[-600:])
        if rc == 3:
            assert (
                paused_at() != "model_scope"
            ), "the scope gate asked again after taking the new answer"
        rows = _rows(run_dir)
        scope = [
            r.get("note", "")
            for r in rows
            if r.get("event") == "human_gate"
            and r.get("module") == "model_scope"
            and r.get("mode") != "recorded"
        ]
        assert scope == [
            "",
            "lattice",
            "axes: all",
        ], f"the scope gate did not take the third answer: {scope}"
        tiers = [r for r in rows if r.get("event") == "tier_decision"]
        assert tiers and tiers[-1].get(
            "axes_selected"
        ), f"`axes: all` bought no axes: {tiers}"
        k = len(tiers[-1]["axes_selected"])
        assert (
            tiers[-1].get("search_mode") == model_space.CANDIDATES
            and tiers[-1].get("n_models") == k + 1
        ), (
            "an answer without `lattice`, after a refused one with it, was not "
            f"searched one axis at a time: {tiers[-1]}"
        )
        print(
            f"  refused note   a resumable stop, twice; the resume took `axes: all` "
            f"({tiers[-1]['axes_selected']}) one at a time, then "
            f"{f'paused at {paused_at()}' if rc == 3 else f'exit {rc}'}"
        )


def check_the_agents_questions_survive_a_resume_of_the_scope_card() -> None:
    """In file-gate mode every scope answer arrives on a resume, which finds the
    agent's model on disk and no construction reply in hand, with the model
    space already recorded. The card that resume asks still lists the agent's
    numbered questions and the construction audit's findings, and `1: …` in
    the answer is recorded against the question exactly as in the pass that
    drafted the model."""
    import shutil

    source = REPO / "testcase" / "abcd_expansion"
    assert source.is_dir(), f"the fixture {source} is missing"
    # the stub construction reply's one `user_decision_required` decision
    question = "Is a direct KinA->ProD leg plausible?"
    with tempfile.TemporaryDirectory() as d:
        # the case with an audit reply that raises one concern, so the card has
        # a construction-audit line to carry across the resume
        case = Path(d) / "abcd_expansion_audited"
        shutil.copytree(source, case, ignore=shutil.ignore_patterns("truth"))
        (case / "stubs" / "construction_verification.json").write_text(
            json.dumps(
                {
                    "verdicts": [
                        {
                            "aspect": "structure sanity",
                            "ok": False,
                            "note": "stub concern the resumed card must still show",
                        }
                    ],
                    "overall": "concerns",
                }
            )
        )
        env = dict(
            os.environ,
            OCTOMOD_RUNS_DIR=d,
            OCTOMOD_SPEC_OVERLAY=str(REPO / "workflows" / "overlays" / "quick.yaml"),
        )
        run_id = "questions_resumed"
        run_dir = run_root(run_id, Path(d))  # the record, runs/<id>.h5
        base = ["run", "--backend", "stub", "--run-id", run_id, "--gate-mode", "file"]

        def cli(*extra: str) -> tuple[int, str]:
            p = subprocess.run(
                [sys.executable, "-m", "octomod", *base, *extra],
                cwd=REPO,
                env=env,
                capture_output=True,
                text=True,
            )
            return p.returncode, p.stdout + p.stderr

        def card() -> tuple[str | None, list[str]]:
            payload = pending_gate(run_dir)
            if payload is None:
                return None, []
            return payload["module"], [str(x) for x in payload.get("lines") or []]

        rc, out = cli("--testcase", str(case))
        assert rc == 3 and card()[0] == "intent", (rc, card()[0], out[-600:])
        rc, out = cli("--gate-answer", "y")
        module, first = card()
        assert rc == 3 and module == "model_scope", (rc, module, out[-600:])
        asked = [x for x in first if question in x]
        assert asked and asked[0].strip().startswith("1. "), (
            "the drafting pass's scope card does not list the agent's question "
            f"as 1 — the fixture does not exercise this path: {first}"
        )
        audited = [x for x in first if x.startswith("checker[")]
        assert audited == [
            "checker[structure sanity]: CONCERN — stub concern the resumed card "
            "must still show"
        ], (
            "the drafting pass's scope card does not carry the audit's concern — "
            f"the fixture does not exercise this path: {first}"
        )
        assert (
            rnd(run_dir, 0) / "space/axes"
        ).exists(), "the fixture declares no model space, so the resume path is not the one under test"

        # a resume without an answer: a fresh process builds the card from the record
        rc, out = cli()
        module, again = card()
        assert rc == 3 and module == "model_scope", (rc, module, out[-600:])
        assert [x for x in again if question in x] == asked, (
            "the scope card asked on a resume lost the agent's numbered "
            f"question (the drafting pass listed it as {asked}): {again}"
        )
        assert any("THE AGENT ASKS" in x for x in again), again
        assert [x for x in again if x.startswith("checker[")] == audited, (
            "the scope card asked on a resume lost the construction audit's "
            f"finding (the drafting pass showed {audited}): {again}"
        )

        # the answer, which also arrives on a resume
        rc, out = cli("--gate-answer", "y", "--gate-note", "axes: none; 1: keep lumped")
        assert rc in (0, 1, 3) and card()[0] != "model_scope", (
            rc,
            card()[0],
            out[-600:],
        )
        assert "answers to questions: 1" in out, (
            "the note's numbered answer was not read back: " + out[-600:]
        )
        kept = (run_dir / "questions").get(None) or []
        mine = [q for q in kept if question in str(q.get("question", ""))]
        assert len(mine) == 1, (
            "the agent's question and the human's answer to it are not in the "
            f"open-questions record after the answer on a resume: {kept}"
        )
        assert mine[0]["id"] == "r0_s1_0" and mine[0]["raised_round"] == 0, mine
        assert "1: keep lumped" in mine[0]["human_answer"], mine
        assert mine[0]["status"] == "deferred_by_human", mine
        print(
            "  questions      the resumed scope card lists the agent's question as "
            "1 and the audit's concern, and `1: keep lumped` is recorded against it"
        )


def check_the_recorded_checks_are_read_back_for_the_agents_model() -> None:
    """The citation and audit lines a resumed card shows are read from what
    the drafting pass recorded — the resolutions it wrote into the build
    report, the audit's gate record, the redraft dossier — without resolving
    a citation or calling the auditor again, and only for a model the
    construction agent wrote in this round."""
    from octomod.workflow_modules.model.engine import (
        _citation_findings,
        _recorded_checker_lines,
    )

    decisions = [
        {
            "decision": "a leg with a fabricated source",
            "evidence_tier": "default",
            "tier_demoted_from": "direct",
            "evidence": [{"source": "10.9999/none", "resolution": "unresolvable"}],
        },
        {
            "decision": "a leg with one bad source among good ones",
            "evidence_tier": "direct",
            "evidence": [
                {"source": "10.9999/none", "resolution": "unresolvable"},
                {"source": "10.1000/ok", "resolution": "resolved"},
            ],
        },
        {"decision": "a leg from the lab note", "evidence": [{"source": "lab_note"}]},
    ]
    want_citations = [
        "UNRESOLVABLE source(s) on: a leg with a fabricated source (tier demoted)",
        "unresolvable source among evidence for: a leg with one bad source among "
        "good ones",
    ]
    assert _citation_findings(decisions) == want_citations, _citation_findings(
        decisions
    )
    with temp_record() as root:
        ctx = _Ctx(root)
        ctx.round_idx = 0
        model_dir = ctx.round / "model"
        (model_dir / "build_report").put({"decisions": decisions})
        audit = ctx.round / "gates" / "model_verification"
        audit.put(
            {
                "gate_id": "model_verification",
                "value": "concerns",
                "advisory_findings": [
                    {"aspect": "tiers", "ok": False, "note": "one tier is generous"}
                ],
            }
        )
        assert _recorded_checker_lines(ctx, model_dir) == [], (
            "a supplied or seeded model (no construction reply in the round) was "
            "given the construction checks' lines"
        )
        (ctx.round / "agent_calls/construction/reply").put({})
        got = _recorded_checker_lines(ctx, model_dir)
        assert got == want_citations + [
            "checker[tiers]: CONCERN — one tier is generous"
        ], got
        audit.put({"gate_id": "model_verification", "advisory_findings": []})
        got = _recorded_checker_lines(ctx, model_dir)
        assert got[-1] == "independent construction audit: no concerns", got
        audit.delete()
        assert (
            _recorded_checker_lines(ctx, model_dir) == want_citations
        ), "an audit that did not run was reported"
    print(
        "  checks         the resumed card's citation and audit lines are read "
        "from the round's record, for the agent's own model only"
    )


def check_only_the_rounds_own_reply_asks() -> None:
    """The resume reads the questions back only for a model the construction
    agent wrote in this round; a build report beside a model with no reply (a
    supplied or seeded model) asks nothing and records nothing."""
    from octomod.workflow_modules.model.engine import _scope_questions

    decisions = [
        {"decision": "a", "user_decision_required": True, "confidence": "high"},
        {"decision": "b", "user_decision_required": False},
        {"decision": "c", "user_decision_required": True, "confidence": "low"},
    ]
    with temp_record() as root:
        ctx = _Ctx(root)
        ctx.round_idx = 0
        model_dir = ctx.round / "model"
        (model_dir / "build_report").put({"decisions": decisions})
        assert _scope_questions(ctx, None) is None, (
            "a build report with no construction reply in the round was read as "
            "the agent's questions"
        )
        (ctx.round / "agent_calls/construction/reply").put({})
        got = [q["decision"] for q in _scope_questions(ctx, None)]
        drafted = [
            q["decision"]
            for q in _scope_questions(ctx, {"build_report": {"decisions": decisions}})
        ]
        assert got == drafted == ["c", "a"], (got, drafted)


def check_a_bare_auto_approve_is_refused_in_the_construction_pass() -> None:
    """Through the CLI with `--auto-approve`, where the scope answer arrives in
    the same pass that drafted the model: a bare yes at a card that lists axes
    is refused as it is from the front end, and nothing of it is kept (the
    answer, the round's marker, answers to the agent's questions); a standing
    `axes: none` is taken there and the round is one model."""
    case = REPO / "testcase" / "abcd_prediction"
    assert case.is_dir(), f"the fixture {case} is missing"
    with tempfile.TemporaryDirectory() as d:
        env = dict(
            os.environ,
            OCTOMOD_RUNS_DIR=d,
            OCTOMOD_SPEC_OVERLAY=str(REPO / "workflows" / "overlays" / "quick.yaml"),
        )

        def cli(run_id: str, *extra: str) -> tuple[int, str]:
            p = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "octomod",
                    "run",
                    "--testcase",
                    "testcase/abcd_prediction",
                    "--backend",
                    "stub",
                    "--auto-approve",
                    "--max-rounds",
                    "1",
                    "--run-id",
                    run_id,
                    *extra,
                ],
                cwd=REPO,
                env=env,
                capture_output=True,
                text=True,
            )
            return p.returncode, p.stdout + p.stderr

        rc, out = cli("auto_bare")
        run_dir = run_root("auto_bare", Path(d))
        rows = _rows(run_dir)
        end = [r for r in rows if r.get("event") == "run_end"][-1]
        assert rc == 1 and end.get("gate") == "model_scope", (
            f"a bare --auto-approve at a card that lists axes was not refused "
            f"(rc={rc}): {end}"
        )
        assert end.get("resumable") is True, end
        said = [
            r.get("note", "")
            for r in rows
            if r.get("event") == "note" and "stays single-model" in r.get("note", "")
        ]
        assert not said, f"the ledger still says the round stays single-model: {said}"
        r0 = rnd(run_dir, 0)
        assert not (
            r0 / "decisions/model_scope"
        ).exists(), "the refused auto answer is still recorded in decisions/model_scope"
        assert not (
            r0 / "status/markers/s1"
        ).exists(), "the round was marked as having passed S1 on a refused answer"
        kept = (run_dir / "questions").get(None) or []
        assert not kept, (
            "the refused note's answers to the agent's questions were recorded, "
            f"and the first answer recorded is the one kept: {kept}"
        )

        rc, out = cli("auto_none", "--gate-note", "axes: none")
        run_dir = run_root("auto_none", Path(d))
        rows = _rows(run_dir)
        tiers = [r for r in rows if r.get("event") == "tier_decision"]
        assert (
            tiers
            and tiers[0].get("axes_selected") == []
            and tiers[0].get("n_models") == 1
        ), f"a standing `axes: none` was not taken as one model: {tiers}"
        assert not (rnd(run_dir, 0) / "space/candidates").exists()
        assert any(
            r.get("event") == "human_gate"
            and r.get("module") == "assembly_cost_boundary"
            for r in rows
        ), f"the run did not go on past S1 (rc={rc}): {out[-600:]}"
        kept = (run_dir / "questions").get()
        assert kept and "axes: none" in kept[0]["human_answer"], kept
        print(
            "  auto-approve   a bare yes is refused in the drafting pass; a "
            "standing `axes: none` is one model and the run goes on"
        )


def main() -> int:
    check_a_refused_bought_round_asks_the_scope_gate_again()
    check_an_unresolved_selection_asks_the_scope_gate_again()
    check_an_auto_answer_is_refused_or_taken_like_a_human_one()
    check_a_refused_scope_note_is_a_resumable_stop()
    check_the_agents_questions_survive_a_resume_of_the_scope_card()
    check_the_recorded_checks_are_read_back_for_the_agents_model()
    check_only_the_rounds_own_reply_asks()
    check_a_bare_auto_approve_is_refused_in_the_construction_pass()
    got = model_space.human_added_axes(
        "axes: loop, integrator, arm_sigma_CXCL9", AXES, POOL
    )
    assert [a["id"] for a in got] == ["arm_sigma_CXCL9"], got
    assert got[0]["human_added"] is True and got[0]["frozen"] is False
    # case-insensitive, deduplicated, unknown ids ignored, no `axes:` -> nothing
    got = model_space.human_added_axes(
        "AXES: Arm_Sigma_CXCL9, arm_sigma_cxcl9, nothere", AXES, POOL
    )
    assert [a["id"] for a in got] == ["arm_sigma_CXCL9"], got
    assert model_space.human_added_axes("tier: all", AXES, POOL) == []
    assert model_space.human_added_axes(None, AXES, POOL) == []
    # the round's own selection still parses with the joined list
    joined = AXES + got
    keep = model_space.parse_axis_selection("axes: loop, arm_sigma_CXCL9", joined)
    assert keep == {"loop", "arm_sigma_CXCL9"}, keep
    assert "decisions/model_scope" in round_status.MODULE_DECISIONS["model"]
    print(
        "HUMAN AXES UNIT OK — a declared axis can be bought back by name, and re-entry re-asks the scope gate"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
