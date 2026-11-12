"""Every entry point as declared (`MODULES`, `SLOTS`), and what each one refuses.

  1. every declared module is reachable by name, and `required_before` only grows;
  2. each entry refuses when a slot it needs is absent, and names that slot;
  3. the refusal is the same whether the slot is missing or merely invalid;
  4. the slot->marker map covers every module, so entry invalidates the right work;
  5. every hand-over shape CLAUDE.md documents maps onto a validated slot;
  6. a problem supplied whole as PEtab refuses an entry upstream of estimation,
     by name and before anything is validated or moved, and still enters at
     estimation and evaluation;
  7. that refusal is keyed on the target round's recorded producer: a later
     round whose model an agent rebuilt re-enters at model, its user-supplied
     data slot is still refused, and a run with no supplied PEtab problem is
     never refused by it, whatever its rounds record;
  8. a finished evaluation slot validates once per round, and an evaluation
     record that lacks the interpretation, or is gone, is refused by name.

    uv run python tests/entry_matrix_unit.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import CallLedger  # noqa: E402

from octomod.orchestration import round_status as rs  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from tests._record import rnd, temp_record  # noqa: E402

MODULE_NAMES = [name for name, _slots, _markers in rs.MODULES]


class _Ctx:
    """The RunContext surface the validators read, over a single-model
    round of a record."""

    def __init__(self, rnd_node, testcase_dir: Path | None = None):
        self.root = tree.Node(rnd_node.store, "")
        self.store = rnd_node.store
        self.round = rnd_node
        self.round_idx = 0
        self.candidate = None
        self.ledger = CallLedger()
        self.spec = {}
        self.testcase = {}
        self.intent = {}
        self.testcase_dir = testcase_dir

    @property
    def work(self):
        return tree.work_node(self.round, None)

    @property
    def model(self):
        return tree.model_node(self.round, None)

    @property
    def gates(self):
        return tree.gates_node(self.round, None)

    @property
    def round_markers(self):
        return tree.markers_node(self.round, None)

    def has_marker(self, name):
        return False

    def set_marker(self, name, **kw):
        pass

    def marker(self, name):
        return self.round_markers.child(name)


def test_every_declared_module_is_reachable():
    for name in MODULE_NAMES:
        assert rs.normalise_module(name) == name, name
    assert MODULE_NAMES == ["model", "data", "assembly", "estimation", "evaluation"], (
        f"the entry points changed: {MODULE_NAMES} — update this matrix "
        f"deliberately rather than letting it drift"
    )
    print(
        f"  reachable     {len(MODULE_NAMES)} entry points: {', '.join(MODULE_NAMES)}"
    )


def test_requirements_only_grow():
    """Entering later can never need LESS than entering earlier."""
    seen: set[str] = set()
    for name in MODULE_NAMES:
        need = set(rs.required_before(name))
        assert seen <= need, (
            f"entering at {name!r} needs {sorted(need)}, which drops "
            f"{sorted(seen - need)} that an earlier entry required"
        )
        seen = need
    assert "intent" in rs.required_before(MODULE_NAMES[0]), "intent is always required"
    print("  monotonic     each entry requires a superset of the one before it")


def test_each_entry_refuses_and_names_the_missing_slot():
    for module in MODULE_NAMES:
        need = rs.required_before(module)
        with temp_record(f"empty_{module}") as root:
            ctx = _Ctx(rnd(root, 0))
            missing_named = []
            for slot in need:
                ok, why = rs.validate(ctx, slot)
                if not ok:
                    missing_named.append(slot)
                    joined = " ".join(why)
                    assert slot in joined, (
                        f"entering at {module!r}: slot {slot!r} is invalid and the "
                        f"reason does not name it: {joined[:160]}"
                    )
        assert missing_named, f"entering at {module!r} on an EMPTY round validated"
    print("  refusals      every entry names the slot it is missing")


def test_a_present_but_invalid_slot_fails_the_same_way():
    """An empty SBML is not a model. The refusal must not depend on whether
    the part exists — that is how a corrupt artifact gets past an entry."""
    with temp_record("corrupt") as root:
        r0 = rnd(root, 0)
        (r0 / "model/sbml").put_text("")  # present, meaningless
        (root / "intent").put({})
        ctx = _Ctx(r0)
        ok, why = rs.validate(ctx, "model")
    assert not ok, "an empty model sbml validated as a model"
    assert "model" in " ".join(why), why
    print("  corrupt slot  an empty artifact is refused, not accepted as present")


def test_every_module_owns_markers_and_they_are_invalidated():
    for name, _slots, markers in rs.MODULES:
        assert markers, f"module {name!r} owns no marker, so entry invalidates nothing"
        after = rs.markers_from(name)
        for m in markers:
            assert m in after, f"{name!r} does not invalidate its own marker {m!r}"
    first, last = rs.markers_from(MODULE_NAMES[0]), rs.markers_from(MODULE_NAMES[-1])
    assert set(last) < set(first), (
        "entering at the LAST module should invalidate strictly fewer markers "
        "than entering at the first"
    )
    print(
        f"  markers       entry at {MODULE_NAMES[0]!r} clears {len(first)}, "
        f"at {MODULE_NAMES[-1]!r} clears {len(last)}"
    )


def test_the_supplied_shapes_a_user_can_bring_are_declared():
    """Every hand-over shape CLAUDE.md documents is a slot the engine validates."""
    doc = (REPO / "CLAUDE.md").read_text()
    for shape in ("supplied/petab", "model.ant", "measurements_long.tsv"):
        assert shape in doc, f"{shape} is not documented as a supplied shape"
    slots = set(rs.SLOTS)
    for slot in ("model", "data", "petab", "estimation", "evaluation"):
        assert slot in slots, f"{slot} is documented but not a validated slot"
    print("  supplied      the documented hand-over shapes map onto real slots")


def _plant(node, text: str = "kept") -> None:
    """A slot part as a placeholder: the validators are replaced in these tests,
    so only presence and content (unchanged afterwards) matter."""
    node.put_text(text)


def _stage_supplied_petab(testcase_dir: Path) -> None:
    staged = testcase_dir / "supplied" / "petab"
    staged.mkdir(parents=True)
    (staged / "problem.yaml").write_text("format_version: 1\n")


def test_a_supplied_petab_problem_has_no_upstream_module_to_redo(tmp: Path):
    """Nothing upstream of estimation produced a problem the user supplied whole."""
    from octomod.orchestration.run_context import ModuleFailure

    with temp_record("supplied_run") as root:
        r0 = rnd(root, 0)
        ctx = _Ctx(r0, tmp / "supplied_run" / "input")
        _stage_supplied_petab(ctx.testcase_dir)
        slot_nodes = [
            r0 / "model/sbml",
            r0 / "data/measurements",
            tree.work_node(r0, None) / "petab/observables",
        ]
        for n in slot_nodes:
            _plant(n)
        # what the supplied-PEtab adapter records for the round it seeds
        for slot in ("model", "data", "petab"):
            rs.record_validation(
                ctx, slot, validated_by=None, default_producer="user-supplied"
            )
        validated: list[str] = []
        real_validate = rs.validate
        rs.validate = lambda c, s: (validated.append(s), (True, [f"slot {s!r}: ok"]))[1]
        try:
            for module in ("model", "data", "assembly"):
                try:
                    rs.enter(ctx, module)
                except ModuleFailure as e:
                    msg = str(e)
                else:
                    raise AssertionError(
                        f"entry at {module!r} on a supplied problem ran"
                    )
                assert "input/supplied/petab" in msg, msg
                assert "round_0's" in msg and "recorded as user-supplied" in msg, msg
                for way_on in ("--from-module estimation", "evaluation", "new run"):
                    assert way_on in msg, f"the refusal does not name {way_on!r}: {msg}"
            assert (
                not validated
            ), f"slots were validated before the refusal: {validated}"
            assert all(
                n.text() == "kept" for n in slot_nodes
            ), "a slot part was moved or changed"
            assert not (r0 / rs.SUPERSEDED_KEY).exists(), "slot records were superseded"
            assert not ctx.ledger.rows, f"an entry was ledgered: {ctx.ledger.rows}"
            # the implied entry on every invocation, and the two re-entries left open
            for module, invalidate in (
                ("estimation", False),
                ("estimation", True),
                ("evaluation", True),
            ):
                rs.enter(ctx, module, invalidate=invalidate)
            entered = [k.get("from_module") for _a, k in ctx.ledger.rows]
            assert entered == ["estimation", "estimation", "evaluation"], entered
        finally:
            rs.validate = real_validate
    print(
        "  supplied      model/data/assembly refused by name on a supplied PEtab "
        "problem; estimation and evaluation still enter"
    )


def test_the_refusal_is_keyed_on_the_target_rounds_producer(tmp: Path):
    """A later round whose model an agent rebuilt is not the user's problem."""
    from octomod.orchestration.run_context import ModuleFailure

    with temp_record("supplied_revision_run") as root:
        testcase_dir = tmp / "supplied_revision_run" / "input"
        _stage_supplied_petab(testcase_dir)
        r0, r1 = rnd(root, 0), rnd(root, 1)
        for rd in (r0, r1):
            for rel in ("model/sbml", "data/measurements"):
                _plant(rd / rel)
        ctx0 = _Ctx(r0, testcase_dir)
        for slot in ("model", "data", "petab"):
            rs.record_validation(
                ctx0, slot, validated_by=None, default_producer="user-supplied"
            )
        # the revision round: an agent rebuilt the model, the data stayed the user's
        ctx1 = _Ctx(r1, testcase_dir)
        ctx1.round_idx = 1
        rs.record_validation(
            ctx1, "model", validated_by=None, default_producer="agent:construction"
        )
        rs.record_validation(
            ctx1, "data", validated_by=None, default_producer="user-supplied"
        )

        real_validate = rs.validate
        rs.validate = lambda c, s: (True, [f"slot {s!r}: ok"])
        try:
            try:
                rs.enter(ctx1, "data")
            except ModuleFailure as e:
                msg = str(e)
            else:
                raise AssertionError("entry at 'data' on a user-supplied data slot ran")
            assert "round_1's 'data' slot" in msg, msg
            try:
                rs.enter(ctx1, "model")
            except ModuleFailure as e:
                assert "supplied whole" not in str(e), (
                    f"a round whose model an agent rebuilt was refused as the "
                    f"user's supplied problem: {e}"
                )
                raise
            entered = [k.get("from_module") for _a, k in ctx1.ledger.rows]
            assert entered == ["model"], f"entry at model did not go through: {entered}"
        finally:
            rs.validate = real_validate

    # no supplied PEtab problem: a seeded round records its model as
    # user-supplied too, and that is no reason to refuse the re-entry
    with temp_record("agent_built_run") as plain:
        rp = rnd(plain, 2)
        _plant(rp / "model/sbml")
        ctxp = _Ctx(rp, tmp / "agent_built_run" / "input")
        ctxp.round_idx = 2
        rs.record_validation(
            ctxp, "model", validated_by=None, default_producer="user-supplied"
        )
        real_validate = rs.validate
        rs.validate = lambda c, s: (True, [f"slot {s!r}: ok"])
        try:
            rs.enter(ctxp, "model")
        finally:
            rs.validate = real_validate
        entered = [k.get("from_module") for _a, k in ctxp.ledger.rows]
        assert entered == ["model"], f"entry without supplied/petab: {entered}"
    print(
        "  producers     a later round an agent rebuilt re-enters at model; its "
        "user-supplied data slot is refused; no supplied PEtab, no refusal"
    )


def test_a_finished_evaluation_slot_validates_and_a_broken_one_is_named():
    """The evaluation slot's own validator: the evaluation must carry the goal
    and the interpretation. The slot is round-scoped, so a candidate-set round
    validates it once, at the round, not per candidate."""
    with temp_record("evaluated_run") as root:
        rd = rnd(root, 0)
        ctx = _Ctx(rd)
        (rd / "space/candidates").put([{"id": "M1"}, {"id": "M2"}])
        full = {"goal": "mechanism_discrimination", "interpretation": {"verdict": "M1"}}
        (rd / "evaluation").put(full)
        (rd / "evaluation_core").put({})
        (rd / "report_md").put_text("# round 0\n")

        ok, why = rs.validate(ctx, "evaluation")
        assert ok and why == ["slot 'evaluation': 1/1 checks passed"], why
        verdict = ctx.gates.child("entry_evaluation_schema").get()
        assert verdict["passed"], verdict
        assert (
            verdict["detail"] == "the evaluation carries goal + interpretation"
        ), verdict
        rows = [k for a, k in ctx.ledger.rows if a and a[0] == "gate"]
        assert [(k["module"], k["gate_id"]) for k in rows] == [
            ("entry_evaluation", "entry_evaluation_schema")
        ], rows
        status = rs.load(rd)
        rec = status["slots"]["evaluation"]
        assert rec["validated_by"] == "entry_evaluation battery", rec
        # `./run.sh status` says what that validator is on an ordinary round: the
        # slot's own check before the next round is seeded, not an entry
        shown = [
            ln for ln in rs.summary_lines(rd) if ln.lstrip().startswith("evaluation")
        ]
        assert len(shown) == 1 and shown[0].endswith(
            "by=entry_evaluation battery (the slot's own validator, run before the "
            "next round was seeded)"
        ), shown
        assert not any(
            "the slot's own validator" in ln
            for ln in rs.summary_lines(rd)
            if not ln.lstrip().startswith("evaluation")
        ), rs.summary_lines(rd)
        assert {f["part"] for f in rec["files"]} == {
            "evaluation",
            "evaluation_core",
            "report_md",
        }, rec["files"]
        assert not any(
            "evaluation" in c for c in status.get("candidates", {}).values()
        ), f"the round-scoped slot was recorded per candidate: {status['candidates']}"

        (rd / "evaluation").put({"goal": full["goal"]})
        ok, why = rs.validate(ctx, "evaluation")
        assert not ok, "an evaluation without an interpretation validated"
        assert why == [
            "slot 'evaluation': the evaluation lacks ['interpretation']"
        ], why

        (rd / "evaluation").delete()
        ok, why = rs.validate(ctx, "evaluation")
        assert not ok, "an evaluation slot with no evaluation validated"
        assert len(why) == 1 and "missing ['evaluation']" in why[0], why
    print(
        "  evaluation    a finished slot validates once per round; an evaluation "
        "without an interpretation, or none at all, is refused by name"
    )


if __name__ == "__main__":
    test_every_declared_module_is_reachable()
    test_requirements_only_grow()
    test_each_entry_refuses_and_names_the_missing_slot()
    test_a_present_but_invalid_slot_fails_the_same_way()
    test_every_module_owns_markers_and_they_are_invalidated()
    test_the_supplied_shapes_a_user_can_bring_are_declared()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        test_a_supplied_petab_problem_has_no_upstream_module_to_redo(tmp)
        test_the_refusal_is_keyed_on_the_target_rounds_producer(tmp)
    test_a_finished_evaluation_slot_validates_and_a_broken_one_is_named()
    print(
        "ENTRY MATRIX UNIT OK — all five entry points, what each requires, and "
        "what each refuses when it is not there"
    )
