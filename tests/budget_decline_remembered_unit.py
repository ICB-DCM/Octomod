"""A candidate dropped at its re-asked budget gate stays dropped across a resume.

  1. `n` at a re-asked budget gate writes the candidate's `budget_declined`
     (candidate, note, reasons, time) before it raises;
  2. the next `cost_profile.run` on that candidate raises with `remembered=True`
     and compiles nothing, probes nothing, asks nothing and leaves a stored
     file-gate answer for the gate it was given for;
  3. through the candidate loop in file-gate mode, [base, A, B] with A and B
     re-asked and both declined: one `candidate_dropped` per declined candidate,
     a note (not a second drop) each time a decline is read back, the answer
     given for B is consumed by B, and the round is evaluated over base;
  4. a re-entry at estimation moves the records aside, so the cards are asked
     again; entry at evaluation validates a round whose declined candidates
     were never fitted, and refuses one whose unfitted candidate was not declined.

    uv run python tests/budget_decline_remembered_unit.py
"""

from __future__ import annotations

import datetime
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402
from _record import ledger_rows, record_at, temp_record  # noqa: E402

from octomod.orchestration import round_status as rs  # noqa: E402
from octomod.orchestration.interaction import humangate  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.orchestration.orchestrator import Orchestrator  # noqa: E402
from octomod.orchestration.run_context import RunContext, as_candidate  # noqa: E402
from octomod.reporting import render as _render  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import engine as assembly_module  # noqa: E402
from octomod.workflow_modules.assembly import petab_io  # noqa: E402
from octomod.workflow_modules.cost_probe import compile_gate  # noqa: E402
from octomod.workflow_modules.cost_probe import engine as cost_profile  # noqa: E402
from octomod.workflow_modules.data import engine as data_module  # noqa: E402
from octomod.workflow_modules.estimation import (  # noqa: E402
    engine as estimation_module,  # noqa: E402
)
from octomod.workflow_modules.estimation import estimation_settings  # noqa: E402
from octomod.workflow_modules.evaluation import (  # noqa: E402
    engine as evaluation_module,  # noqa: E402
)

PETAB = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"
MODULE = "cost_boundary_estimation"


class _Opt:
    def __init__(self, fval, time):
        self.fval, self.time, self.x = fval, time, None


class _FakeResult:
    """Probe starts that all return a non-finite objective: the reuse is refused."""

    def __init__(self, n):
        self.optimize_result = type("R", (), {})()
        self.optimize_result.list = [_Opt(float("inf"), 0.019) for _ in range(n)]


def _context(tmp: Path, candidates: list[str]) -> RunContext:
    """A fresh context over the run record in `tmp`, as a new invocation
    builds one: an empty cache."""
    spec = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
    root = record_at(tmp / "run")
    if not root.store.exists_on_disk():
        root.store.create()
    ctx = RunContext(
        root=root,
        testcase_dir=REPO / "testcase" / "toy_phos_petab",
        spec=spec,
        ledger=Ledger(root),
        backend="stub",
        auto=False,
    )
    if not (root / "intent").exists():
        (root / "intent").put(
            {
                "question": "unit test",
                "system": "toy",
                "inference_target": "mechanism_discrimination",
            }
        )
    inp = petab_io.from_dir(PETAB) if candidates else None
    for cid in candidates:
        with as_candidate(ctx, cid):
            if not (ctx.work / "petab/measurements").exists():
                petab_io.to_record(inp, ctx.work / "petab")
                (ctx.model / "sbml").put_text(inp.sbml)
            if not ctx.marker("s3").exists():
                ctx.set_marker("s3", producer="unit test")
    return ctx


def _rows(ctx: RunContext) -> list[dict]:
    return ledger_rows(ctx.root)


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


def _reset_file_mode() -> None:
    humangate._FILE_MODE.update(
        enabled=False, root=None, answer=None, note="", pending_module=None
    )


# ------------------------------------------------- 1./2. the module remembers


def test_the_module_writes_and_reads_back_the_decline() -> None:
    asks: list[str] = []

    def _declining_ask(question, lines, **kw):
        asks.append(question)
        return False, "not worth fitting"

    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        ctx = _context(tmp, ["A"])
        ctx.candidate = "A"
        ctx.cache["_budget_reference"] = {
            "candidate": "base",
            "median_start_s": 0.05,
            "n_starts": 30,
        }
        with _Patched(
            (cost_profile, "run_multistart", lambda p, n, s, sp, **kw: _FakeResult(n)),
            (humangate, "ask", _declining_ask),
        ):
            try:
                cost_profile.run(ctx, ask_human=False, n_candidates=3, preapproved_n=30)
                raised = None
            except cost_profile.BudgetDeclinedForCandidate as e:
                raised = e
        check(
            "`n` at the re-asked card raises BudgetDeclinedForCandidate, not remembered",
            raised is not None
            and raised.candidate == "A"
            and raised.remembered is False,
            repr(raised),
        )
        check("the re-asked card was asked once", len(asks) == 1, str(asks))
        rec = (ctx.work / cost_profile.DECLINED_KEY).get(None) or {}
        check(
            "the candidate's budget_declined records the candidate and the note",
            rec.get("candidate") == "A" and rec.get("note") == "not worth fitting",
            str(rec),
        )
        check(
            "… and the reasons the reuse was refused",
            any("non-finite" in r for r in rec.get("reasons") or []),
            str(rec.get("reasons")),
        )
        try:
            datetime.datetime.fromisoformat(str(rec.get("at")))
            at_ok = True
        except ValueError:
            at_ok = False
        check("… and when it was given (ISO time)", at_ok, str(rec.get("at")))
        check(
            "no cost marker: the candidate is not approved",
            not ctx.marker("cost").exists(),
        )

        # -- the next invocation: a fresh context over the same record -------
        builds: list = []
        probes: list = []
        asks.clear()

        def _no_build(c):
            builds.append(c.candidate)
            raise AssertionError("a declined candidate must not be compiled")

        def _no_probe(*a, **k):
            probes.append(1)
            raise AssertionError("a declined candidate must not be probed")

        ctx2 = _context(tmp, ["A"])
        ctx2.candidate = "A"
        # an answer stored for another candidate's card
        humangate.configure_file_mode(ctx2.root, False, "for B")
        try:
            with _Patched(
                (estimation_settings, "build", _no_build),
                (cost_profile, "run_multistart", _no_probe),
                (humangate, "ask", _declining_ask),
            ):
                try:
                    cost_profile.run(
                        ctx2, ask_human=False, n_candidates=3, preapproved_n=30
                    )
                    again = None
                except cost_profile.BudgetDeclinedForCandidate as e:
                    again = e
            stored_left = humangate._FILE_MODE["answer"]
        finally:
            _reset_file_mode()
        check(
            "the next run() raises with remembered=True, naming the candidate",
            again is not None and again.remembered is True and again.candidate == "A",
            repr(again),
        )
        check(
            "… carrying the human's note and saying it is not asked again",
            again is not None
            and again.note == "not worth fitting"
            and "not asked again" in str(again),
            str(again),
        )
        check(
            "… with no compile, no probe and no card",
            not builds and not probes and not asks,
            f"builds={builds} probes={len(probes)} asks={asks}",
        )
        check(
            "… and the answer stored for another card is left for that card",
            stored_left is False,
            repr(stored_left),
        )


# ----------------------------------------------- 3. the loop across resumes


class _Orch:
    """The candidate loop on a stand-in orchestrator: every module except the
    cost module and the gate is a stub."""

    _fit_and_select_once = Orchestrator._fit_and_select_once
    _order_by_fit_on_disk = Orchestrator._order_by_fit_on_disk

    def __init__(self, ctx):
        self.ctx, self.ledger = ctx, ctx.ledger
        self.root, self.store = ctx.root, ctx.store
        self.max_rounds = None

    def _remerge_stale_candidates(self, cand_ids):
        pass

    def _maybe_expand_space(self, report, fitted):
        return None

    def _write_analysis(self):
        pass


def test_the_loop_drops_each_declined_candidate_once() -> None:
    cands = ["base", "A", "B"]
    evaluated: list[list[str]] = []
    fitted_calls: list[str] = []
    builds: list = []
    real_build = estimation_settings.build

    def _counting_build(c):
        builds.append(c.candidate)
        return real_build(c)

    def _s6(c, n):
        fitted_calls.append(c.candidate)

    def _s7(c, cand_ids=None, rounds_left=None):
        evaluated.append(list(cand_ids or []))
        return {
            "discrimination": {"winner": cand_ids[0], "decisive": True},
            "t2prime_passed": True,
        }

    patches = _Patched(
        (data_module, "run", lambda c: None),
        (assembly_module, "run", lambda c: None),
        (compile_gate, "ask", lambda c, ids: None),
        (estimation_module, "run", _s6),
        (evaluation_module, "run", _s7),
        (_render, "decisions_md", lambda rd: ""),
        (cost_profile, "run_multistart", lambda p, n, s, sp, **kw: _FakeResult(n)),
        (estimation_settings, "build", _counting_build),
    )
    with tempfile.TemporaryDirectory() as tmp_s, patches:
        tmp = Path(tmp_s)
        ctx = _context(tmp, cands)
        # base's budget was approved at the round's first card
        with as_candidate(ctx, "base"):
            ctx.set_marker(
                "cost", approved_n_starts=30, median_start_s=0.05, budget_reference=True
            )

        def _invoke(answer):
            builds.clear()
            ctx = _context(tmp, cands)
            humangate.configure_file_mode(ctx.root, answer, "")
            try:
                return "done", _Orch(ctx)._fit_and_select_once(list(cands))
            except humangate.GatePending as g:
                return "paused", g.payload

        def _count(event, cid, **match):
            return sum(
                1
                for e in _rows(ctx)
                if e.get("event") == event
                and e.get("candidate") == cid
                and all(e.get(k) == v for k, v in match.items())
            )

        try:
            kind, out = _invoke(None)
            check(
                "first invocation: A's probe does not match, its card pauses the run",
                kind == "paused"
                and out.get("module") == MODULE
                and "'A'" in out.get("question", ""),
                f"{kind} {out if kind == 'done' else out.get('question')}",
            )
            kind, out = _invoke(False)
            check(
                "`n` for A: A is dropped and B's card pauses the run",
                kind == "paused" and "'B'" in out.get("question", ""),
                f"{kind} {out if kind == 'done' else out.get('question')}",
            )
            check(
                "… one candidate_dropped for A, marked as the human's decline",
                _count("candidate_dropped", "A", human_declined_budget=True) == 1,
            )
            kind, out = _invoke(False)
            check(
                "`n` for B: consumed by B's card, and the round reaches its evaluation",
                kind == "done" and out == 0,
                f"{kind} {out if kind == 'done' else out.get('question')}",
            )
            check(
                "A was not compiled on that resume — only B was",
                "A" not in builds and "B" in builds,
                str(builds),
            )
            check(
                "exactly one candidate_dropped for A and one for B",
                _count("candidate_dropped", "A") == 1
                and _count("candidate_dropped", "B") == 1,
                f"A={_count('candidate_dropped', 'A')} B={_count('candidate_dropped', 'B')}",
            )
            check(
                "A's decline read back is a note, not a drop",
                _count("note", "A", budget_decline_remembered=True) == 1,
            )
            check(
                "the evaluation reads the fitted set: base alone",
                evaluated == [["base"]]
                and fitted_calls.count("A") == 0
                and fitted_calls.count("B") == 0,
                f"evaluated={evaluated} fitted={fitted_calls}",
            )
            gates = [
                e
                for e in _rows(ctx)
                if e.get("event") == "human_gate" and e.get("module") == MODULE
            ]
            check(
                "two answers given, two consumed, one per candidate's card",
                len(gates) == 2
                and "'A'" in gates[0]["question"]
                and "'B'" in gates[1]["question"],
                str([g.get("question", "")[:60] for g in gates]),
            )
            check(
                "no gate is left pending",
                not humangate.pending_path(ctx.root).exists(),
            )
            # -- every further replay reads both declines back ---------------
            kind, out = _invoke(None)
            check(
                "a further replay asks nothing and compiles nothing",
                kind == "done" and out == 0 and not builds,
                f"{kind} builds={builds}",
            )
            check(
                "… and still one candidate_dropped per declined candidate",
                _count("candidate_dropped", "A") == 1
                and _count("candidate_dropped", "B") == 1,
            )
        finally:
            _reset_file_mode()


# ------------------------------------------------------------ 4. re-entry


def test_reentry_forgets_it_and_evaluation_entry_validates() -> None:
    check(
        "the index and the module name the same key",
        rs.DECLINED_BUDGET == cost_profile.DECLINED_KEY,
        rs.DECLINED_BUDGET,
    )
    pats = rs._MODULE_CACHE_PATTERNS["estimation"]
    check(
        "the estimation re-entry patterns carry the record of every unit of work",
        f"candidates/*/{cost_profile.DECLINED_KEY}" in pats,
        str(pats),
    )
    with temp_record() as scratch:
        rnd0 = tree.round_node(scratch, 0)
        for cid in (None, "A"):
            (tree.work_node(rnd0, cid) / cost_profile.DECLINED_KEY).put(
                {"candidate": cid or "", "note": "", "reasons": [], "at": "x"}
            )
        named = sorted(rs._rel(rnd0, n) for n in rs._module_caches(rnd0, "estimation"))
    check(
        "… which names the single model's record and each candidate's",
        f"candidates/{tree.SINGLE}/{cost_profile.DECLINED_KEY}" in named
        and f"candidates/A/{cost_profile.DECLINED_KEY}" in named,
        str(named),
    )
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        ctx = _context(tmp, [])
        rnd = ctx.round
        (rnd / "space/candidates").put([{"id": c} for c in ("base", "A", "B")])
        for cid in ("base", "A", "B"):
            (tree.work_node(rnd, cid) / "cost").put(
                {"median_start_s": 0.05, "compile_s": 0.0}
            )
        (tree.work_node(rnd, "base") / "estimation").put({})
        for cid in ("A", "B"):
            (tree.work_node(rnd, cid) / rs.DECLINED_BUDGET).put(
                {"candidate": cid, "note": "", "reasons": [], "at": "x"}
            )
        real_gates = rs._gates_for

        def _schema_only_for_fits(c, slot, base):
            # the fit battery is not what is tested here: base's fit passes it
            return None if slot == "estimation" else real_gates(c, slot, base)

        with _Patched((rs, "_gates_for", _schema_only_for_fits)):
            ok, why = rs.validate(ctx, "estimation")
            check(
                "entry at evaluation: the estimation slot validates with A and B "
                "declined and unfitted",
                ok and any(w.startswith("A: not fitted") for w in why),
                " | ".join(why),
            )
            ok_c, why_c = rs.validate(ctx, "compiled")
            check(
                "… and the compiled slot validates on every candidate's profile",
                ok_c,
                " | ".join(why_c),
            )
            ctx.candidate = None
            moved = rs.supersede_slots(ctx, "estimation")
            kept = rnd / rs.SUPERSEDED_KEY
            check(
                "a re-entry at estimation moves both records aside (kept, not deleted)",
                f"candidates/A/{rs.DECLINED_BUDGET}" in moved
                and f"candidates/B/{rs.DECLINED_BUDGET}" in moved
                and not (tree.work_node(rnd, "A") / rs.DECLINED_BUDGET).exists()
                and any(
                    (kept / s / f"candidates/A/{rs.DECLINED_BUDGET}").exists()
                    for s in kept.children()
                ),
                str(moved),
            )
            (tree.work_node(rnd, "base") / "estimation").put({})
            ok, why = rs.validate(ctx, "estimation")
            check(
                "without the record an unfitted candidate still refuses the slot",
                not ok and any(w.startswith("A: ") and "missing" in w for w in why),
                " | ".join(why),
            )


def main() -> int:
    import logging

    logging.disable(logging.WARNING)
    test_the_module_writes_and_reads_back_the_decline()
    test_the_loop_drops_each_declined_candidate_once()
    test_reentry_forgets_it_and_evaluation_entry_validates()
    return finish(
        "\nBUDGET DECLINE REMEMBERED",
        "\nbudget decline remembered: one `n` is one drop, on every resume",
    )


if __name__ == "__main__":
    sys.exit(main())
