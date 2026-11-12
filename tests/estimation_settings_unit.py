"""The settings a candidate's problem is built with, on toy_phos_petab's real AMICI solver.

  1. a round's budget-gate choice reaches every candidate of the round and a fresh process;
  2. a refit's solver changes reach its multistart; overrides and counts survive a restart;
  3. nothing leaks: a cached solver asked for nothing gets the declared settings back;
  4. `adjoint` answered at the budget gate triggers the re-probe;
  5. a `--from-module estimation` re-entry supersedes the recorded choices.

    uv run python tests/estimation_settings_unit.py
"""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402
from _record import temp_record  # noqa: E402

from octomod.orchestration.interaction import humangate  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.orchestration.run_context import RunContext  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import petab_io  # noqa: E402
from octomod.workflow_modules.estimation import estimation_settings as es  # noqa: E402
from octomod.workflow_modules.estimation import solver_settings as ss  # noqa: E402

PETAB = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"


def _ctx(run, cache: dict | None = None) -> RunContext:
    """A RunContext on the record `run` (the run is one file)."""
    ctx = RunContext(
        root=run,
        testcase_dir=REPO / "testcase" / "toy_phos_petab",
        spec=WorkflowSpec.load(REPO / "workflows" / "default.yaml"),
        ledger=Ledger(run),
        backend="stub",
        auto=False,
    )
    if cache is not None:
        ctx.cache = cache
    (run / "intent").put(
        {
            "question": "unit",
            "system": "toy",
            "inference_target": "parameter_values",
        }
    )
    return ctx


def _candidate(ctx: RunContext, cid: str, nominal_shift: bool = False) -> None:
    """A candidate's group; `nominal_shift` edits its parameter table (new
    problem, same compile)."""
    ctx.candidate = cid
    if not (ctx.work / "petab/measurements").exists():
        inp = petab_io.from_dir(PETAB)
        if nominal_shift:
            text = petab_io.table_text(inp.parameters)
            text = text.replace("\t0.02\t", "\t0.021\t", 1)
            inp = inp.with_tables(parameters=pd.read_csv(io.StringIO(text), sep="\t"))
        petab_io.to_record(inp, ctx.work / "petab")
        (ctx.model / "sbml").put_text(inp.sbml)


def _held(problem) -> dict:
    o = problem.objective
    return ss.read_back(o.amici_solver, o.amici_model)


TOL = {"available": True, "agrees": False, "proposal": {"atol": 1e-16, "rtol": 1e-10}}
FWD = {"available": True, "proposed_sensi_method": "forward"}


def test_a_round_choice_reaches_every_candidate_and_a_restart() -> None:
    from octomod.workflow_modules.cost_probe import engine as cost_profile

    with temp_record("settings_round") as run:
        ctx = _ctx(run)
        _candidate(ctx, "a")
        declared = _held(es.build(ctx)[0])["rtol"]
        reading = cost_profile.read_budget_note("tighten", TOL, FWD, 10, 1000)
        chosen = cost_profile._apply_gate_choices(
            ctx, reading, TOL, FWD, {}, for_round=True
        )
        check(
            "the budget gate records `tighten` for the round",
            chosen == TOL["proposal"],
            str(chosen),
        )
        check(
            "the candidate it was asked on is fitted with it (it reached 1e-8 before)",
            _held(es.build(ctx)[0])["rtol"] == 1e-10,
            f"declared {declared}",
        )
        _candidate(ctx, "b", nominal_shift=True)
        prob_b = es.build(ctx)[0]
        check(
            "another candidate of the round — another problem object — gets it too",
            _held(prob_b)["rtol"] == 1e-10,
            str(_held(prob_b)["rtol"]),
        )
        fresh = _ctx(run, cache={})
        fresh.candidate = "b"
        check(
            "and so does a restarted process (nothing lives only in memory)",
            _held(es.build(fresh)[0])["rtol"] == 1e-10,
        )


def test_a_refit_reaches_its_multistart_and_survives_a_restart() -> None:
    from octomod.workflow_modules.estimation import engine as estimation_module

    with temp_record("settings_refit") as run:
        ctx = _ctx(run)
        _candidate(ctx, "a")
        (ctx.work / "cost").put({"median_start_s": 0.1, "compile_s": 0.0})
        ctx.set_marker("cost", approved_n_starts=10, median_start_s=0.1)
        preset = dict(ctx.spec.get("estimation.refit_presets")["robust_solver"])
        es.record_refit(ctx, {**preset, "maxiter": 2000}, "preset 'robust_solver'", 30)
        seen: dict = {}

        class _Stop(Exception):
            pass

        def spy(
            problem,
            n,
            seed,
            spec,
            median=None,
            optimizer_overrides=None,
            optimizer_name=None,
            **kw,
        ):
            seen.update(n=n, held=_held(problem), opt=optimizer_overrides)
            raise _Stop()

        real = estimation_module.run_multistart
        estimation_module.run_multistart = spy
        try:
            try:
                estimation_module.run(_restarted(run, "a"), 10)
            except _Stop:
                pass
        finally:
            estimation_module.run_multistart = real
        held = seen.get("held") or {}
        check(
            "the refit's solver changes reach its multistart, after a restart (a "
            "robust_solver preset once changed nothing)",
            held.get("rtol") == 1e-10 and held.get("maxsteps") == 1000000,
            f"rtol {held.get('rtol')}, maxsteps {held.get('maxsteps')}",
        )
        check(
            "its optimiser overrides and its start count are read back",
            seen.get("opt") == {"maxiter": 2000} and seen.get("n") == 30,
            f"opt {seen.get('opt')}, n {seen.get('n')}",
        )
        check(
            "its attempt count is in the record",
            es.refit_attempts(_restarted(run, "a")) == 1,
        )


def _restarted(run, cid: str) -> RunContext:
    ctx = _ctx(run, cache={})
    ctx.candidate = cid
    return ctx


def test_nothing_leaks_from_one_caller_to_the_next() -> None:
    with temp_record("settings_leak") as run:
        ctx = _ctx(run)
        _candidate(ctx, "a")
        es.record_gate_choice(
            ctx, {"sensi_method": "adjoint"}, for_round=True, note="adjoint"
        )
        check(
            "round 0 asked for adjoint and gets it",
            _held(es.build(ctx)[0])["sensi_method"] == 2,
        )
        ctx.round_idx = 1  # the next round: the same problem, the same cached object
        _candidate(ctx, "a")
        held = _held(es.build(ctx)[0])
        check(
            "the next round, which asked for nothing, gets the declared settings back",
            held["sensi_method"] == 1,
            f"sensi_method {held['sensi_method']} (1 = forward)",
        )


def test_adjoint_at_the_budget_gate_triggers_the_reprobe() -> None:
    from octomod.workflow_modules.cost_probe import engine as cost_profile
    from octomod.workflow_modules.cost_probe import solver_probe

    logging.disable(logging.WARNING)
    with temp_record("settings_adjoint") as run:
        ctx = _ctx(run)
        _candidate(ctx, "a")
        ctx.set_marker("s3", n_estimated=0)
        calls: list[dict] = []
        real = (solver_probe.sensitivity_probe, cost_profile._reprobe_after_override)
        # the REAL probe, with only its proposal changed: toy_phos is too small
        # for the measured ratio to propose adjoint on its own
        solver_probe.sensitivity_probe = lambda *a, **k: {
            **real[0](*a, **k),
            "proposed_sensi_method": "adjoint",
        }

        def reprobe(ctx_, problem, *a, **k):
            calls.append(_held(problem))
            return 0.5

        cost_profile._reprobe_after_override = reprobe
        humangate.configure_file_mode(run, True, "adjoint")
        try:
            cost_profile.run(ctx, ask_human=True)
        finally:
            solver_probe.sensitivity_probe, cost_profile._reprobe_after_override = real
            humangate.configure_file_mode(run, None, "")
            logging.disable(logging.NOTSET)
        check(
            "`adjoint` answered at the gate re-probes, on a solver that holds it",
            len(calls) == 1 and calls[0].get("sensi_method") == 2,
            f"{len(calls)} re-probe(s)",
        )
        check(
            "the choice is recorded for the round",
            es.round_choice(ctx).get("solver") == {"sensi_method": "adjoint"},
            str(es.round_choice(ctx)),
        )
        rows = [e for e in ctx.ledger.entries() if e.get("note_read") is not None]
        check(
            "and the engine said what it read",
            rows and rows[-1]["note_read"] == {"adjoint": True},
            str(rows[-1]["note_read"] if rows else None),
        )


def test_a_reentry_supersedes_the_choices() -> None:
    from octomod.orchestration import round_status

    with temp_record("settings_reentry") as run:
        ctx = _ctx(run)
        _candidate(ctx, "a")
        es.record_gate_choice(
            ctx, {"sensi_method": "adjoint"}, for_round=True, note="adjoint"
        )
        es.record_refit(ctx, {"maxiter": 2000}, "preset 'optimizer'", 10)
        ctx.candidate = None
        moved = round_status.supersede_slots(ctx, "estimation")
        ctx.candidate = "a"
        check(
            "`--from-module estimation` moves the round's and the candidate's choices aside",
            not es.round_choice(ctx)
            and not es.candidate_record(ctx)
            and any("estimation_settings" in m for m in moved),
            str([m for m in moved if "settings" in m]),
        )


def main() -> int:
    print(
        "the settings a candidate's problem is built with — recorded, applied everywhere"
    )
    test_a_round_choice_reaches_every_candidate_and_a_restart()
    test_a_refit_reaches_its_multistart_and_survives_a_restart()
    test_nothing_leaks_from_one_caller_to_the_next()
    test_adjoint_at_the_budget_gate_triggers_the_reprobe()
    test_a_reentry_supersedes_the_choices()
    return finish("\nESTIMATION SETTINGS", "ESTIMATION SETTINGS OK")


if __name__ == "__main__":
    sys.exit(main())
