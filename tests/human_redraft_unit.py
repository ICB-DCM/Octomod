"""A person may send an agent's work back (`redraft:`), and it must not cost them.

  1. `redraft:` is parsed out of a note that may also carry the other forms;
  2. the request reaches the agent verbatim, marked as a person's, not a failed check;
  3. it does not spend the redraft budget, which bounds failure;
  4. the gate card advertises it;
  5. it forces a fresh draft, at the scope gate and at the compile card, on both paths;
  6. the model report's M0 shows the request, or says plainly that none was made;
  7. a problem supplied whole as PEtab is not offered one at the compile card,
     and one written anyway is refused by name, its answer cleared.

    uv run python tests/human_redraft_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.orchestration.interaction import human_redraft as hr  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from tests._record import rnd, temp_record  # noqa: E402


def test_it_parses_beside_the_other_forms():
    cases = {
        "y redraft: use the full 256-state positional space": (
            "use the full 256-state positional space"
        ),
        "y redraft: add per-timepoint scaling tier: base": (
            "add per-timepoint scaling"
        ),
        "y tier: top1 redraft: model all 256 states 1: enzyme is stable": (
            "model all 256 states"
        ),
        "y REDRAFT: Mixed Case Works": "Mixed Case Works",
    }
    for note, want in cases.items():
        got = hr.parse(note)
        assert got == want, f"{note!r} -> {got!r}, wanted {want!r}"
    for quiet in ("y tier: base", "y", "", None, "y 1: no calibration exists"):
        assert hr.parse(quiet) is None, f"{quiet!r} produced a redraft request"
    print(f"  parsing       {len(cases)} combined note(s); silence stays silence")


def test_the_agent_is_told_a_person_asked():
    ctx = hr.context_for("use the full positional space", "construction")
    assert ctx["human_feedback"] == "use the full positional space", ctx
    instr = ctx["human_feedback_instruction"]
    assert "HUMAN" in instr, instr
    assert "not a gate failure" in instr, instr
    # it must be allowed to push back rather than comply silently
    assert "say so" in instr and "do not silently ignore" in instr, instr
    print("  delivery      verbatim, marked as a person's request, may disagree")


def test_it_does_not_spend_the_failure_budget():
    """The budget bounds FAILURE. A human request is granted extra instead."""
    src = (REPO / "octomod" / "workflow_modules" / "model" / "engine.py").read_text()
    i = src.index("def _take_human_redraft(")
    block = "".join(src[i : i + 900].split())  # formatting is not tested
    assert "add_grant(1)" in block, (
        "a human redraft must add a grant, otherwise it eats the budget that "
        "exists to bound an agent failing its own gates"
    )
    assert "context.update(_hr.context_for(" in block, block[:200]
    # both ways a redraft arrives (in-process, and on a resume through the
    # supplied-model path) go through that one handler
    assert "_take_human_redraft(ctx, context, req)" in src, "draft loop bypasses it"
    assert "_take_human_redraft(ctx, context, redraft)" in src, "resume bypasses it"
    print("  budget        a human request adds a grant, never spends one")


def test_a_redraft_forces_a_fresh_draft():
    """The cached reply from before the gate pause is not reused on a redraft."""
    from octomod.orchestration.interaction import retry
    from octomod.workflow_modules.model.engine import _reuse_cached_reply

    # the saved reply and the dossier are record nodes of the call
    with temp_record("fresh") as root:
        call = rnd(root, 0) / "agent_calls" / "construction"
        cached = call / "reply"
        cached.put({})
        h = retry.AttemptHistory(call / "dossier")
        assert _reuse_cached_reply(cached, h, {}, True), "a plain resume reuses"
        assert not _reuse_cached_reply(
            cached, h, {"human_feedback": "use the full positional space"}, True
        ), "the resume path would hand back the very draft the human objected to"
    print("  fresh draft   the pre-pause reply is not reused when a human asked")


def test_the_card_advertises_it():
    from octomod.workflow_modules.model.engine import SCOPE_NOTE_FORMS

    assert any("redraft:" in f for f in SCOPE_NOTE_FORMS), SCOPE_NOTE_FORMS
    assert any(
        "does not spend" in f for f in SCOPE_NOTE_FORMS
    ), "the card must say it is free, or nobody will risk it"
    print("  discoverable  the scope card lists redraft: and says it is free")


def test_it_is_wired_at_the_assembly_gates_too():
    """The compile card takes a redraft: the assembly agents author what it approves."""
    gate = (
        REPO / "octomod" / "workflow_modules" / "cost_probe" / "compile_gate.py"
    ).read_text()
    s3 = (REPO / "octomod" / "workflow_modules" / "assembly" / "engine.py").read_text()
    orch = (REPO / "octomod" / "orchestration" / "orchestrator.py").read_text()

    assert "raise_if_asked" in gate, "compile_gate: the card cannot be redrafted"
    # ONE function names what the redraft removes, on both paths: the shared
    # draft, each unit of work's merged copy AND its s3 marker, which `_run_once`
    # checks first (a stale marker reads "passed")
    assert (
        "assembly_invalidations(" in gate.split("raise_if_asked")[1][:600]
    ), "compile_gate: the cost-boundary redraft does not use assembly_invalidations"
    from octomod.workflow_modules.cost_probe.compile_gate import assembly_invalidations

    # the record nodes a legacy run directory holds as assembly.json,
    # assembly_shared.json, gates/s3.pass and gates/assembly_verification.json
    with temp_record("invalidate") as root:
        for cand_ids in (["a"], [None]):
            names = sorted(
                n.name for n in assembly_invalidations(rnd(root, 0), cand_ids)
            )
            assert names == [
                "assembly",
                "assembly_verification",
                "s3",
                "shared_assembly",
            ], (cand_ids, names)
    # both assembly agents must SEE it
    assert (
        s3.count("_human_feedback") >= 2
    ), "observation and condition must both receive the note"
    # one card, advertised, asked from one place for both paths — never by S3
    assert "_hr.NOTE_FORM" in gate, "the compile card does not offer it"
    assert (
        'module="assembly_cost_boundary"' not in s3
    ), "S3 asks a compile card of its own"
    assert orch.count("compile_gate.ask(") == 2, "a path does not ask the one card"
    print("  assembly      the one compile card accepts it, clears the cache, says so")


def test_the_restart_unwinds_far_enough():
    """The set's one cost gate runs after every assembly; the catch wraps them all."""
    orch = (REPO / "octomod" / "orchestration" / "orchestrator.py").read_text()
    i = orch.index("def _fit_and_select(")
    j = orch.index("def _fit_and_select_once(")
    wrapper = orch[i:j]
    assert "except _hr.RedraftRequested" in wrapper, wrapper[:200]
    assert "_fit_and_select_once" in wrapper
    assert j > i, "the wrapper must come before the body it retries"
    # the single model's card follows S3 in the same kind of loop
    k = orch.index("def _assemble_and_approve(")
    single = orch[k : orch.index("\n    def ", k + 1)]
    assert "except _hr.RedraftRequested" in single and "assembly_module.run" in single
    print("  unwinding     the catch is outside the whole assemble+gate step")


def test_the_report_shows_what_the_human_asked():
    """The model report's M0 section shows the request, the gate and the agent."""
    from octomod.reporting import render_model_report_html

    rows = [
        {
            "ts": "2026-09-11T16:55:02",
            "round": 0,
            "module": "model_scope",
            "event": "note",
            "human_redraft": True,
            "role": "construction",
            "note": "human asked construction to redraft: use the full 256-state space",
        },
    ]
    with temp_record("run") as root:
        (root / "run").put({"testcase": "t"})
        for row in rows:
            root.store.append_ledger(row)
        html = render_model_report_html(rnd(root, 0))
    assert 'id="m0"' in html, "no M0 section"
    assert "use the full 256-state space" in html, "the request is not shown"
    assert "model_scope" in html and "construction" in html
    assert html.index('id="m0"') < html.index(
        'id="m1"'
    ), "M0 must come before M1 — it is the reader's own words"
    print("  report M0     the request, the gate and the agent are on the page")


def test_the_report_is_honest_when_nobody_asked():
    from octomod.reporting import render_model_report_html

    with temp_record("quiet") as root:
        (root / "run").put({"testcase": "t"})
        html = render_model_report_html(rnd(root, 0))
    assert "no redraft was requested" in html, "silence must be stated, not implied"
    print("  report M0     says plainly when the agents were left alone")


class _CompileCtx:
    """What the compile card reads and writes on a single-model round — on a
    record (`root` is the run record's root node)."""

    def __init__(self, root):
        from octomod.orchestration.ledger import Ledger

        self.root = root
        self.store = root.store
        self.round_idx = 0
        self.candidate = None
        self.ledger = Ledger(root)
        self.spec = {}
        self.intent = {}
        self.set_markers: list[str] = []

    @property
    def round(self):
        return rnd(self.root, self.round_idx)

    @property
    def work(self):
        return tree.work_node(self.round, self.candidate)

    @property
    def gates(self):
        return tree.gates_node(self.round, self.candidate)

    @property
    def markers(self):
        return tree.markers_node(self.round, self.candidate)

    @property
    def agent_calls(self):
        return self.round / "agent_calls"

    def has_marker(self, name: str) -> bool:
        return self.markers.child(name).exists()

    def set_marker(self, name: str, **payload) -> None:
        self.set_markers.append(name)


def test_a_supplied_problem_refuses_a_redraft():
    """No agent assembled a supplied problem: `redraft:` is neither offered nor
    sent anywhere, and the card asks again on the resume."""
    with temp_record("supplied_run") as root:
        _supplied_problem_refuses_a_redraft(root)


def _supplied_problem_refuses_a_redraft(root) -> None:
    import pandas as pd

    from octomod.orchestration.interaction import humangate
    from octomod.orchestration.run_context import NoteRefused
    from octomod.workflow_modules.cost_probe import compile_gate

    ctx = _CompileCtx(root)
    rd = ctx.round
    # the entry marker over a supplied problem carries no counts
    ctx.markers.child("s3").put({"producer": "user-supplied", "entry": True})
    petab = ctx.work / "petab"
    petab.child("parameters").put_table(
        pd.DataFrame({"parameterId": ["k1", "k2", "S"], "estimate": [1, 1, 0]})
    )
    petab.child("measurements").put_table(
        pd.DataFrame({"observableId": ["obs"] * 3, "measurement": [1, 2, 3]})
    )
    seen: dict = {}
    note = "redraft: add a scale factor on the readout"

    def fake_ask_once(ctx_, decision, question, lines, **kw):
        seen.update(kw, lines=lines)
        decision.put(
            {"module": "assembly_cost_boundary", "approved": True, "note": note}
        )
        return True, note

    saved = humangate.ask_once
    humangate.ask_once = fake_ask_once
    try:
        compile_gate.ask(ctx, [None])
    except NoteRefused as e:
        assert e.gate == "assembly_cost_boundary", e.gate
        assert "supplied whole as PEtab" in str(e), str(e)
    else:
        raise AssertionError("a redraft of a supplied problem was not refused")
    finally:
        humangate.ask_once = saved
    assert seen["note_forms"] == (), f"the card offers {seen['note_forms']}"
    assert not compile_gate.decision_node(rd).exists(), "the answer was kept"
    assert ctx.set_markers == [], "the card was marked signed on a refused note"
    assert not any(
        e.get("human_redraft") for e in ctx.ledger.entries()
    ), "a redraft was ledgered as sent to agents that never assembled it"
    assert (
        seen["lines"][0]
        == "estimation problem: 2 estimated parameters, 3 training points, 0 held-out points"
    ), seen["lines"][0]
    assert not any(
        "reasoning of every agent" in ln for ln in seen["lines"]
    ), "the card points to agent reasoning on a problem no agent assembled"
    print("  supplied      a supplied problem's card offers no redraft, refuses one")


if __name__ == "__main__":
    test_it_parses_beside_the_other_forms()
    test_the_agent_is_told_a_person_asked()
    test_it_does_not_spend_the_failure_budget()
    test_a_redraft_forces_a_fresh_draft()
    test_the_card_advertises_it()
    test_it_is_wired_at_the_assembly_gates_too()
    test_the_restart_unwinds_far_enough()
    test_the_report_shows_what_the_human_asked()
    test_the_report_is_honest_when_nobody_asked()
    test_a_supplied_problem_refuses_a_redraft()
    print(
        "HUMAN REDRAFT UNIT OK — a person can send the work back, in their own "
        "words, without spending a budget meant for failures"
    )
