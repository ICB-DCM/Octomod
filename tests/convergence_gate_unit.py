"""A failed convergence check asks a human; it does not end the run.

  1. the three post-fit checks are still T2 (a T1 check would need another mechanism);
  2. a refit resolves a preset or explicit keys, and refuses anything else by name;
  3. `accept` requires a reason, and a refused answer is asked again on resume:
     its stop is recorded as resumable, so run_guard lets the resume in;
  4. a refit keeps the previous attempt, so the two can be compared;
  5. the refit budget is bounded and spec-owned.

    uv run python tests/convergence_gate_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import yaml  # noqa: E402
from _record import ledger_rows, rnd, temp_record  # noqa: E402
from _record import work as work_node  # noqa: E402

from octomod.workflow_modules.estimation.problem import (  # noqa: E402
    REFIT_KEYS,
    apply_refit,
    resolve_refit,
)


class _Spec(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


def _spec() -> _Spec:
    raw = yaml.safe_load((REPO / "workflows" / "default.yaml").read_text())
    return _Spec(
        {
            "estimation.refit_presets": raw["estimation"]["refit_presets"],
            "retry.refit_max": raw["retry"]["refit_max"],
        }
    )


def test_the_checks_are_still_advisory_tier():
    src = (REPO / "octomod" / "gates" / "fit_gates.py").read_text()
    for gate_id in (
        "estimation_waterfall_plateau",
        "estimation_gradient_norm",
        "estimation_integration_failures",
    ):
        i = src.index(f'@gate("{gate_id}"')
        assert '"T2"' in src[i : i + 80], (
            f"{gate_id} is not T2 — a convergence GATE that stops the run "
            f"may then be right, so revisit the convergence design rather than routing a T1 failure "
            f"through a question"
        )
    print("  tier          all three checks are T2: statistics, not usability")


def test_a_preset_or_explicit_keys_resolve():
    spec = _spec()
    over, desc = resolve_refit(spec, "robust_solver")
    assert over and "robust_solver" in desc, (over, desc)
    over2, desc2 = resolve_refit(spec, "atol=1e-12 maxsteps=50000")
    assert over2 == {"atol": 1e-12, "maxsteps": 50000}, over2
    assert "explicit" in desc2
    print(f"  resolves      presets and {len(REFIT_KEYS)} explicit key(s)")


def test_an_unknown_request_is_refused_with_the_vocabulary():
    spec = _spec()
    for bad in ("turbo_mode", "", "atol", "nonsense=3"):
        try:
            resolve_refit(spec, bad)
        except ValueError as e:
            msg = str(e)
            assert (
                "robust_solver" in msg or "n_starts_factor" in msg
            ), f"the refusal for {bad!r} does not say what WOULD work: {msg}"
            continue
        raise AssertionError(f"{bad!r} was accepted as a refit request")
    print("  refusals      name the legal presets and keys, never a bare 'no'")


def test_apply_refit_reports_what_it_actually_changed():
    """apply_refit reports what it changed; the stub's setters exist in real AMICI."""
    real_solver, _real_model = _live_amici_solver()
    stub_methods = ("set_absolute_tolerance", "set_max_steps")
    for name in stub_methods:
        assert hasattr(real_solver, name), (
            f"the stub below defines {name!r}, which the installed AMICI does "
            f"not have — the stub has drifted from the library and this test "
            f"would pass against a dead code path"
        )

    class _Solver:
        def __init__(self):
            self.calls = []

        def set_absolute_tolerance(self, v):
            self.calls.append(("atol", v))

        def get_absolute_tolerance(self):
            return dict(self.calls).get("atol")

        def set_max_steps(self, v):
            self.calls.append(("maxsteps", v))

        def get_max_steps(self):
            return dict(self.calls).get("maxsteps")

    class _Obj:
        amici_solver = _Solver()
        amici_model = None

    class _Problem:
        objective = _Obj()

    prob = _Problem()
    applied, opt = apply_refit(prob, {"atol": 1e-10, "maxsteps": 1000, "maxiter": 2000})
    assert "atol=1e-10" in applied and "maxsteps=1000" in applied, applied
    assert prob.objective.amici_solver.calls, "nothing reached the solver"
    # the optimizer half comes back separately: not dropped, not reported as a
    # solver change
    assert opt == {"maxiter": 2000}, opt
    assert not any(a.startswith("maxiter") for a in applied), applied
    print("  applied       solver and optimizer halves stay separate")


def test_a_solver_missing_a_declared_setter_raises_now():
    """A refit key that binds to no setter raises, not an empty `applied` list."""
    from octomod.workflow_modules.estimation.solver_settings import SolverSettingError

    class _Deaf:
        pass

    class _Obj:
        amici_solver = _Deaf()
        amici_model = None

    class _Problem:
        objective = _Obj()

    try:
        apply_refit(_Problem(), {"rtol": 1e-12})
    except SolverSettingError as e:
        assert "rtol" in str(e) and "reaches no setter" in str(e), e
    else:
        raise AssertionError(
            "a refit key that reaches no setter was silently ignored — a key "
            "that changes nothing while claiming to"
        )
    print("  dead key      raises instead of reporting an empty success")


def _live_amici_solver():
    """A real compiled AMICI solver; raises with the reason if none loads."""
    import amici
    import amici.sim.sundials  # noqa: F401

    from octomod.workflow_modules.estimation.problem import AMICI_CACHE_DIR

    errors = []
    for d in sorted(AMICI_CACHE_DIR.glob("amici_*")):
        try:
            mod = amici.import_model_module(d.name.replace("amici_", "m_"), str(d))
            model = (mod.get_model if hasattr(mod, "get_model") else mod.getModel)()
            for name in ("create_solver", "get_solver", "getSolver"):
                if hasattr(model, name):
                    return getattr(model, name)(), model
        except Exception as e:
            errors.append(f"{d.name}: {type(e).__name__}: {e}")
    raise AssertionError(
        "no compiled AMICI model could be loaded to check the stub against; "
        "this check must not be skipped. Last: " + "; ".join(errors[-2:])
    )


class _GateCtx:
    """What `_convergence_gate` reads from a RunContext, with a real ledger,
    on a throwaway record (the run is one file)."""

    def __init__(self, root, spec: _Spec):
        from octomod.orchestration.ledger import Ledger

        self.root = root
        self.store = root.store
        self.ledger = Ledger(root)
        self.round_idx = 0
        self.candidate = None
        self.spec = spec
        self.cache: dict = {}
        self.auto = False
        self.intent = {}

    @property
    def round(self):
        return rnd(self.root, 0)

    @property
    def work(self):
        return work_node(self.root, 0)

    @property
    def model(self):
        return self.round / "model"

    @property
    def gates(self):
        return self.work / "gates"


def test_a_refused_answer_is_asked_again_on_resume():
    """A note the gate refuses clears the recorded answer, so a resume asks
    the gate again instead of replaying the same note into the same refusal."""
    from octomod.gates import GateResult
    from octomod.orchestration import run_context as modules
    from octomod.orchestration.interaction import humangate
    from octomod.orchestration.run_context import ModuleFailure
    from octomod.workflow_modules.estimation.engine import ACCEPTED, _convergence_gate

    raw = yaml.safe_load((REPO / "workflows" / "default.yaml").read_text())
    results = [
        GateResult("estimation_gradient_norm", "T2", False, detail="projected norm 3.2")
    ]
    reasoned = "accept the flat direction is the known k1*k2 product"
    cases = (
        ("an accept with no reason", {}, "accept", "`accept <why>`"),
        ("a refit naming no preset", {}, "refit", "cannot refit"),
        (
            "a refit with the budget spent",
            {"retry.refit_max": 0},
            "refit more_starts",
            "refit budget spent",
        ),
    )
    real_ask = humangate.ask
    try:
        for label, overrides, refused_note, must_say in cases:
            spec = _Spec(
                {
                    "estimation.refit_presets": raw["estimation"]["refit_presets"],
                    "retry.refit_max": raw["retry"]["refit_max"],
                    "estimation.optimizer_compare.enabled": False,
                    **overrides,
                }
            )
            answers = [refused_note, reasoned]
            asked: list[str] = []

            def fake_ask(question, lines, _asked=asked, _answers=answers, **kw):
                _asked.append(kw.get("module"))
                return True, _answers[len(_asked) - 1]

            humangate.ask = fake_ask
            with temp_record("convergence") as root:
                ctx = _GateCtx(root, spec)
                decision = ctx.work / "decisions/estimation_convergence"
                try:
                    _convergence_gate(ctx, results, None, 4, 0)
                except ModuleFailure as e:
                    msg, refusal = str(e), e
                else:
                    raise AssertionError(f"{label} was not refused")
                assert must_say in msg, f"{label}: the refusal does not say why: {msg}"
                refused_type = getattr(modules, "NoteRefused", None)
                assert refused_type is not None and isinstance(refusal, refused_type), (
                    f"{label}: the refusal is a plain {type(refusal).__name__}, "
                    f"so the stop ends the run and run_guard refuses the plain "
                    f"resume the message promises"
                )
                assert (
                    refusal.gate == "estimation_convergence"
                ), f"{label}: the refusal names {refusal.gate!r}"
                assert not decision.exists(), (
                    f"{label}: the refused answer is still recorded in "
                    f"{decision.key}, so every resume replays it into the same "
                    f"refusal"
                )
                try:
                    got = _convergence_gate(ctx, results, None, 4, 0)
                except ModuleFailure as e:
                    raise AssertionError(
                        f"{label}: the resume replayed the refused answer "
                        f"(asked {len(asked)} time(s)): {str(e)[:160]}"
                    ) from e
                assert asked == [
                    "estimation_convergence",
                    "estimation_convergence",
                ], f"{label}: the resume did not ask again: {asked}"
                assert got == ACCEPTED, got
                assert "asks again on resume" in msg, (
                    f"{label}: the refusal does not say the gate is asked again: "
                    f"{msg}"
                )
    finally:
        humangate.ask = real_ask
    print(f"  replay        {len(cases)} refused answers are cleared and asked again")


def test_a_refused_note_stops_the_run_resumably():
    """The orchestrator records a refused note's stop as resumable, naming the
    gate, says how to answer again, and run_guard lets the plain resume in."""
    import contextlib
    import io

    from octomod.orchestration import orchestrator, run_guard
    from octomod.orchestration import run_context as modules
    from octomod.orchestration.ledger import Ledger

    refused_type = getattr(modules, "NoteRefused", None)
    assert refused_type is not None, (
        "no NoteRefused in octomod.orchestration.run_context: a refused note is a plain "
        "ModuleFailure, whose stop ends the run"
    )

    class _Shim:
        """What `Orchestrator.run` reads before its first module raises."""

        def _run(self):
            return orchestrator.Orchestrator._run(self)

    def refuse(ctx):
        raise refused_type(
            "the convergence gate needs `accept <why>`, `refit <preset>` or `n`.",
            gate="estimation_convergence",
        )

    real = orchestrator.intent_module.run
    orchestrator.intent_module.run = refuse
    try:
        with temp_record("stop") as root:
            shim = _Shim()
            shim.root, shim.store, shim.ctx = root, root.store, None
            shim.ledger = Ledger(root)
            err = io.StringIO()
            with (
                contextlib.redirect_stderr(err),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                rc = orchestrator.Orchestrator.run(shim)
            rows = ledger_rows(root)
            end = [r for r in rows if r.get("event") == "run_end"][-1]
            assert rc == 1, rc
            assert end.get("outcome") == "stopped", end
            assert (
                end.get("resumable") is True
                and end.get("gate") == "estimation_convergence"
            ), f"the stop row does not say it is resumable at the gate: {end}"
            assert run_guard.ended_outcome(root) is None, (
                "run_guard reads the refused note's stop as an ending and "
                "refuses the plain resume"
            )
            said = err.getvalue()
            assert "--gate-answer" in said and "estimation_convergence" in said, (
                "the stop does not say how to answer the gate again: " + said
            )
    finally:
        orchestrator.intent_module.run = real
    print("  stop          a refused note's stop is resumable and says how to answer")


def test_the_gate_demands_a_reason_and_keeps_the_previous_fit():
    src = (
        REPO / "octomod" / "workflow_modules" / "estimation" / "engine.py"
    ).read_text()
    assert "_convergence_gate" in src and "estimation_convergence" in src
    assert "len(text.split()) < 2" in src, (
        "`accept` with no reason must be refused — an unreasoned accept is how "
        "an unconverged fit becomes a result"
    )
    assert (
        'ctx.work / "attempts" / str(n)' in src
        and "_keep_attempt(ctx, attempts + 1)" in src
    ), (
        "the previous attempt is not kept, so a refit cannot be compared "
        "against what it replaced"
    )
    assert (
        '"multistart"' in src and ".copy_to(keep" in src
    ), "the persisted result is not carried over"
    assert "retry.refit_max" in src, "the refit budget is not bounded"
    assert "raise ModuleFailure" in src, "stopping must remain possible"
    print("  gate          accept needs a why; refit archives; budget bounded")


def test_the_spec_owns_the_vocabulary():
    raw = yaml.safe_load((REPO / "workflows" / "default.yaml").read_text())
    presets = raw["estimation"]["refit_presets"]
    assert {"more_starts", "robust_solver"} <= set(presets), presets
    assert raw["estimation"]["escalation"], "no escalation order declared"
    for name, body in presets.items():
        for key in body:
            assert key in REFIT_KEYS, f"preset {name!r} uses unknown key {key!r}"
    print("  workflow      presets and escalation are spec-owned, keys all legal")


def test_every_preset_key_actually_reaches_something():
    """Every key a refit preset or `simulation:` declares reaches a setter."""
    from octomod.workflow_modules.estimation.problem import OPTIMIZER_KEYS, SOLVER_KEYS

    raw = yaml.safe_load((REPO / "workflows" / "default.yaml").read_text())
    handled = set(SOLVER_KEYS) | set(OPTIMIZER_KEYS) | {"n_starts_factor"}
    for name, body in raw["estimation"]["refit_presets"].items():
        for key in body:
            assert (
                key in handled
            ), f"preset {name!r} declares {key!r}, which nothing applies"
    # the optimizer half must be carried to the optimizer, not dropped
    est = (
        REPO / "octomod" / "workflow_modules" / "estimation" / "problem.py"
    ).read_text()
    assert (
        "options=dict(optimizer_overrides or {})" in est
    ), "FidesOptimizer never receives the optimizer overrides"
    s6 = (
        REPO / "octomod" / "workflow_modules" / "estimation" / "engine.py"
    ).read_text()
    # carried through the candidate's recorded settings, which a resume reads
    # back (estimation_settings_unit checks it behaviourally)
    assert (
        "estimation_settings.optimizer_overrides(ctx)" in s6
    ), "the optimizer overrides are not carried"

    # `simulation:` uses the same vocabulary as a refit, so its keys must reach
    # a setter too
    from octomod.workflow_modules.estimation import solver_settings as _ss

    sim = _ss.flatten_spec(_spec())
    assert sim, "`simulation.amici` is empty"
    unknown = sorted(set(sim) - set(_ss.ALL_KEYS))
    assert not unknown, f"`simulation:` declares {unknown}, which nothing applies"
    assert set(sim) <= set(SOLVER_KEYS), (
        "a `simulation:` key that a refit cannot also name breaks the "
        "one-vocabulary rule: " + str(sorted(set(sim) - set(SOLVER_KEYS)))
    )
    rr = _spec().get("simulation.roadrunner") or {}
    from octomod.workflow_modules.model.simwrap import RRModel

    assert set(rr) <= set(RRModel._SETTING_NAMES), (
        f"`simulation.roadrunner` declares {sorted(set(rr) - set(RRModel._SETTING_NAMES))}, "
        f"which RRModel cannot apply"
    )
    print(
        f"  presets live  every key of {len(raw['estimation']['refit_presets'])} "
        f"preset(s), {len(sim)} amici and {len(rr)} roadrunner key(s) reaches a setter"
    )


def _spec():
    from octomod.spec import WorkflowSpec

    return WorkflowSpec.load(REPO / "workflows" / "default.yaml")


class _Res:
    def __init__(self, gate_id, passed):
        self.gate_id, self.passed, self.blocking = gate_id, passed, True


def test_the_escalation_order_is_recommended_and_says_why():
    """The card recommends an escalation order, specialised to what failed."""
    from octomod.workflow_modules.estimation.engine import _escalation_lines

    raw = yaml.safe_load((REPO / "workflows" / "default.yaml").read_text())
    ctx = _Spec({"estimation.escalation": raw["estimation"]["escalation"]})
    ctx.spec = ctx

    crashed = _escalation_lines(
        ctx,
        [
            _Res("estimation_integration_failures", False),
            _Res("estimation_gradient_norm", True),
        ],
    )
    order = [ln for ln in crashed if ln.startswith("suggested order")][0]
    assert order.index("robust_solver") < order.index(
        "more_starts"
    ), f"crashes must put the solver first, got {order!r}"
    assert any("survivorship" in ln for ln in crashed), crashed

    clean = _escalation_lines(ctx, [_Res("estimation_waterfall_plateau", False)])
    order = [ln for ln in clean if ln.startswith("suggested order")][0]
    assert order.index("more_starts") < order.index(
        "robust_solver"
    ), f"without crashes the declared order stands, got {order!r}"
    print("  escalation    order is recommended, reordered by crashes, reasoned")


def test_refit_state_is_per_candidate():
    """Refit state is keyed per candidate, since one search round fits several."""
    from octomod.orchestration.run_context import RunContext

    key = RunContext.candidate_key
    a, b = _Spec({}), _Spec({})
    a.candidate, b.candidate = "M2_kina_drives_prod", "M3_lumped"
    single = _Spec({})
    single.candidate = None

    for name in ("_refit_optimizer", "_refit_attempts", "pypesto_result"):
        assert key(a, name) != key(b, name), name
        assert key(single, name) not in (key(a, name), key(b, name)), name

    s6 = (
        REPO / "octomod" / "workflow_modules" / "estimation" / "engine.py"
    ).read_text()
    s7 = (
        REPO / "octomod" / "workflow_modules" / "evaluation" / "engine.py"
    ).read_text()
    for bare in (
        '"_refit_optimizer"]',
        '"_refit_attempts"]',
        '"pypesto_result")',
        '"pypesto_result"]',
    ):
        assert f"ctx.cache[{bare}" not in s6, f"bare round-level key back in s6: {bare}"
        assert (
            f"ctx.cache.get({bare}" not in s7 and f"ctx.cache[{bare}" not in s7
        ), f"bare round-level key back in s7: {bare}"
    print("  per-candidate refit state and the optimize result do not leak")


def test_the_winner_is_profiled_from_its_own_optimum():
    """`_profiles` reads the winner's own optimize result, not a bare cache key."""
    s7 = (
        REPO / "octomod" / "workflow_modules" / "evaluation" / "engine.py"
    ).read_text()
    body = s7.split("def _profiles(")[1].split("\ndef ")[0]
    assert (
        'ctx.candidate_key("pypesto_result")' in body
    ), "the profiler reads an unscoped optimize result again"
    print("  profiles      the winner is profiled from the winner's own optimum")


def test_a_mismatched_candidate_id_is_refused_by_name():
    from octomod.workflow_modules.estimation.engine import _strip_candidate

    ctx = _Spec({})
    ctx.candidate = "M2_kina_drives_prod"
    assert (
        _strip_candidate(ctx, "M2_kina_drives_prod: robust_solver") == "robust_solver"
    )
    assert _strip_candidate(ctx, "robust_solver") == "robust_solver"
    for bad, must_name in (("M3_other: robust_solver", "M2_kina_drives_prod"),):
        try:
            _strip_candidate(ctx, bad)
        except ValueError as e:
            assert must_name in str(e), e
        else:
            raise AssertionError(f"{bad!r} was accepted for the wrong candidate")

    single = _Spec({})
    single.candidate = None
    try:
        _strip_candidate(single, "M2: robust_solver")
    except ValueError as e:
        assert "single model" in str(e), e
    else:
        raise AssertionError("a candidate id was accepted in a single-model round")
    print("  addressing    a wrong candidate id is refused, not silently refitted")


def test_the_seed_is_an_invariant_not_a_gate():
    """The seed stamp is an invariant, not a gate: only an engine bug can fail it."""
    gates_src = (REPO / "octomod" / "gates" / "fit_gates.py").read_text()
    assert (
        '@gate("estimation_reproducibility_stamp"' not in gates_src
    ), "the stamp is still a gate"
    assert "g_seed" not in gates_src, "the stamp's gate function is still defined"
    registry = (REPO / "octomod" / "gates" / "__init__.py").read_text()
    assert (
        '"estimation_reproducibility_stamp":' not in registry
    ), "the stamp is still in the gate registry, so it still counts as one"
    s6 = (
        REPO / "octomod" / "workflow_modules" / "estimation" / "engine.py"
    ).read_text()
    assert (
        'invariant="estimation_reproducibility_stamp"' in s6
    ), "the invariant is not ledgered"
    assert "engine invariant violated" in s6, "a missing seed does not fail loudly"
    print("  invariant     the seed is asserted and ledgered, not gated")


def test_the_gradient_check_measures_the_projected_gradient():
    """The gradient check uses the projected (KKT) norm and names parked parameters."""
    import numpy as np

    from octomod.gates.fit_gates import make_fit_gates
    from octomod.workflow_modules.estimation.problem import projected_gradient

    class _Opt:
        # scaled space: a at its upper bound pushing up, b at its lower bound
        # pushing down, c free, d at its lower bound pointing INTO the box
        x = np.array([1.0, -3.0, 0.2, -3.0, 0.0])
        grad = np.array([-9.0, 5.0, 0.3, -0.4, float("nan")])

    class _Problem:
        lb_full = np.array([-3.0, -3.0, -3.0, -3.0, -3.0])
        ub_full = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        x_free_indices = [0, 1, 2, 3, 4]

    names = ["a", "b", "c", "d", "e"]
    g = projected_gradient(_Opt(), _Problem(), names)
    assert [p["id"] for p in g["parked"]] == ["a", "b"], g["parked"]
    assert abs(g["projected_norm"] - float(np.hypot(0.3, 0.4))) < 1e-9, g
    assert g["raw_norm"] > 10, g
    assert g["nonfinite"] == ["e"], "a NaN component is named, not silently dropped"
    summary = {
        "fvals": [1.0, 1.1, 1.2],
        "best_grad_norm": g["raw_norm"],
        "best_projected_grad_norm": g["projected_norm"],
        "grad_at_active_bounds": g["parked"],
        "grad_nonfinite": g["nonfinite"],
        "n_starts": 3,
        "at_bounds": ["a", "b"],
    }
    gates = {r.gate_id: r for r in (fn() for fn in make_fit_gates(summary, _Spec({})))}
    grad = gates["estimation_gradient_norm"]
    assert grad.passed, f"a converged-in-its-box fit failed the check: {grad.detail}"
    assert "a (upper)" in grad.detail and "b (lower)" in grad.detail, grad.detail
    assert "NON-FINITE" in grad.detail, grad.detail
    print(
        "  gradient      projected (KKT) norm judged; parked parameters named; NaN named"
    )


if __name__ == "__main__":
    test_the_gradient_check_measures_the_projected_gradient()
    test_the_checks_are_still_advisory_tier()
    test_a_preset_or_explicit_keys_resolve()
    test_an_unknown_request_is_refused_with_the_vocabulary()
    test_apply_refit_reports_what_it_actually_changed()
    test_a_solver_missing_a_declared_setter_raises_now()
    test_the_gate_demands_a_reason_and_keeps_the_previous_fit()
    test_a_refused_answer_is_asked_again_on_resume()
    test_a_refused_note_stops_the_run_resumably()
    test_the_spec_owns_the_vocabulary()
    test_every_preset_key_actually_reaches_something()
    test_the_escalation_order_is_recommended_and_says_why()
    test_refit_state_is_per_candidate()
    test_the_winner_is_profiled_from_its_own_optimum()
    test_a_mismatched_candidate_id_is_refused_by_name()
    test_the_seed_is_an_invariant_not_a_gate()
    print(
        "CONVERGENCE GATE UNIT OK — a crossed check asks a human, an accept "
        "needs a reason, a refit keeps what it replaced, and each candidate "
        "carries its own refit budget"
    )
