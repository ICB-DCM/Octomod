"""Every declared solver setting reaches a real setter; integrating gates record theirs.

  1. every `simulation.amici` key binds to a setter of the real AMICI API, not a stub;
  2. every refit-preset key is handled, legal, and binds to a real setter;
  3. a key that binds to nothing raises; an unknown key is refused by name;
  4. applied settings are read back from the solver;
  5. roadrunner tolerances are applied, read back, and differ from the defaults;
  6. the integrating-gate roll-call and the gate decorators agree both ways;
  7. each integrating verdict of a real S1 ladder records its tolerance, no other does;
  8. an integrating gate with no settings source records why;
  9. the FIM declares it needs forward sensitivities and names adjoint as the cause;
 10. every other top-level `simulation` key is read by name by the solver probe;
 11. `tighten`/`adjoint` are offered only when measured and read only as bare words.

    uv run python tests/solver_settings_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.gates import INTEGRATION_GATES  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.estimation import solver_settings as ss  # noqa: E402
from octomod.workflow_modules.estimation.problem import (  # noqa: E402
    OPTIMIZER_KEYS,
    REFIT_KEYS,
    SOLVER_KEYS,
)

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
RAW = yaml.safe_load((REPO / "workflows" / "default.yaml").read_text())


def _real_amici_solver():
    """Return a live (solver, model) from a cached compiled model, never a stub."""
    import amici
    import amici.sim.sundials  # noqa: F401  (the generated module needs it)

    from octomod.workflow_modules.estimation.problem import AMICI_CACHE_DIR

    errors = []
    for d in sorted(AMICI_CACHE_DIR.glob("amici_*")):
        try:
            mod = amici.import_model_module(d.name.replace("amici_", "m_"), str(d))
            # snake_case, like the rest of this AMICI — the camelCase spelling
            # is precisely what this suite exists to catch
            model = (mod.get_model if hasattr(mod, "get_model") else mod.getModel)()
            for name in ("create_solver", "get_solver", "getSolver"):
                if hasattr(model, name):
                    return getattr(model, name)(), model
            errors.append(f"{d.name}: model exposes no solver factory")
        except Exception as e:
            errors.append(f"{d.name}: {type(e).__name__}: {e}")
    raise AssertionError(
        "could not load any compiled AMICI model to check the real API "
        "against. This check must not be skipped. Last few reasons:\n  "
        + "\n  ".join(errors[-3:])
    )


def test_every_simulation_key_reaches_a_setter():
    """Every declared `simulation.amici` key binds to a setter on the real solver."""
    declared = ss.flatten_spec(SPEC)
    assert declared, "simulation.amici is empty"
    unknown = sorted(set(declared) - set(ss.ALL_KEYS))
    assert not unknown, f"`simulation:` declares {unknown}, which nothing applies"
    solver, model = _real_amici_solver()
    for key in declared:
        if key in ss._SOLVER:
            stems, _cast = ss._SOLVER[key]
            target = solver
        elif key in ss._SOLVER_ENUM:
            stems, _e = ss._SOLVER_ENUM[key]
            target = solver
        else:
            stems, _e = ss._MODEL_ENUM[key]
            target = model
        assert ss._bind(target, stems) is not None, (
            f"declared key {key!r} binds to NO setter on the real AMICI "
            f"(tried set_{stems[0]} / set{stems[1]}) — this is the camelCase "
            f"defect returning"
        )
    print(f"  simulation:   all {len(declared)} declared key(s) bind to a real setter")


def test_every_refit_preset_key_reaches_a_setter():
    """Refit presets share the solver vocabulary: every key is handled and binds."""
    handled = set(SOLVER_KEYS) | set(OPTIMIZER_KEYS) | {"n_starts_factor"}
    solver, model = _real_amici_solver()
    for name, body in RAW["estimation"]["refit_presets"].items():
        for key in body:
            assert (
                key in handled
            ), f"preset {name!r} declares {key!r}; nothing applies it"
            assert (
                key in REFIT_KEYS
            ), f"preset {name!r} key {key!r} is not legal to ask for"
            if key in ss._SOLVER:
                assert (
                    ss._bind(solver, ss._SOLVER[key][0]) is not None
                ), f"preset {name!r} key {key!r} binds to no real setter"
    print(
        f"  presets:      every key of "
        f"{len(RAW['estimation']['refit_presets'])} preset(s) reaches a setter"
    )


def test_a_key_that_binds_to_nothing_raises_rather_than_no_ops():
    """A key that binds to no setter raises instead of being skipped."""
    solver, model = _real_amici_solver()

    class _Deaf:
        pass

    try:
        ss.apply_amici(_Deaf(), _Deaf(), {"atol": 1e-12})
    except ss.SolverSettingError as e:
        assert "atol" in str(e) and "reaches no setter" in str(e), e
    else:
        raise AssertionError("a key that binds to nothing was silently skipped")
    # and an unknown key is refused by name, with the legal list
    try:
        ss.apply_amici(solver, model, {"atoll": 1e-12})
    except ss.SolverSettingError as e:
        assert "atoll" in str(e) and "legal" in str(e), e
    else:
        raise AssertionError("an unknown key was accepted")
    print("  refusals:     a dead key raises; an unknown key is named")


def test_settings_are_read_back_not_assumed():
    solver, model = _real_amici_solver()
    got = ss.apply_amici(solver, model, {"rtol": 1e-9, "maxsteps": 4321})
    assert got["rtol"] == 1e-9 and got["maxsteps"] == 4321, got
    assert float(solver.get_relative_tolerance()) == 1e-9
    assert int(solver.get_max_steps()) == 4321
    print("  read-back:    what is reported is what the solver holds")


def test_roadrunner_tolerances_are_applied_and_verified():
    import antimony

    from octomod.workflow_modules.model.simwrap import RRModel, SimError

    antimony.loadAntimonyString("model m; A=10; B=0; J0: A->B; k*A; k=0.3; end")
    sbml = antimony.getSBMLString(antimony.getMainModuleName())
    declared = SPEC.get("simulation.roadrunner")
    assert declared, "simulation.roadrunner is missing"
    m = RRModel(sbml, declared)
    for key, want in declared.items():
        assert m.tolerances[key] == float(want), (key, m.tolerances)
    # the defaults are still reachable and differ, so declaring the block
    # changes something
    assert RRModel(sbml).tolerances != m.tolerances, (
        "the declared tolerances equal roadrunner's defaults, so this block "
        "would be decoration"
    )
    try:
        RRModel(sbml, {"atoll": 1e-9})
    except SimError as e:
        assert "atoll" in str(e), e
    else:
        raise AssertionError("an unknown roadrunner key was accepted")
    print(f"  roadrunner:   {declared} applied and read back; defaults differ")


def test_every_integration_gate_declares_itself():
    """The roll-call and the decorators must agree, in both directions."""
    import octomod.gates.petab_gates as pg
    import octomod.gates.sim_gates as sg

    declared = set()
    for mod in (sg, pg):
        src = Path(mod.__file__).read_text()
        for line in src.splitlines():
            if "integrates=True" in line and "@gate(" in line:
                declared.add(line.split('"')[1])
    assert declared == set(INTEGRATION_GATES), {
        "decorated but not in INTEGRATION_GATES": sorted(declared - INTEGRATION_GATES),
        "in INTEGRATION_GATES but not decorated": sorted(INTEGRATION_GATES - declared),
    }
    print(f"  roll-call:    {len(declared)} gate(s) declared integrating, both ways")


def test_integration_gate_verdicts_record_their_tolerance():
    """On a real S1 ladder every integrating verdict records its tolerance."""
    import antimony

    from octomod.gates import run_gate_set
    from octomod.gates.sim_gates import make_sim_gates
    from tests._record import rnd, temp_record

    antimony.loadAntimonyString("model m; A=10; B=0; J0: A->B; k*A; k=0.3; end")
    sbml = antimony.getSBMLString(antimony.getMainModuleName())

    class _Ledger:
        def append(self, *a, **k):
            pass

    gates = make_sim_gates(sbml, 10.0, {"k": (0.01, 10.0)}, SPEC)
    with temp_record("verdicts") as root:
        gates_node = rnd(root, 0) / "gates"
        _ok, results = run_gate_set(gates, gates_node, _Ledger(), "model")
        declared = SPEC.get("simulation.roadrunner")
        n_int = 0
        for res in results:
            recorded = gates_node.child(res.gate_id).get()
            if res.gate_id in INTEGRATION_GATES:
                n_int += 1
                got = res.solver_settings
                assert got, f"{res.gate_id} integrates but recorded no tolerance"
                assert (
                    recorded["solver_settings"] == got
                ), f"{res.gate_id}: the record and the result disagree"
                for key, want in declared.items():
                    assert got.get(key) == float(want), (res.gate_id, key, got)
                assert got.get("solver") == "roadrunner/cvode", got
            else:
                assert (
                    res.solver_settings is None
                ), f"{res.gate_id} does not integrate but claims a tolerance"
    assert n_int >= 4, f"only {n_int} integrating gate(s) ran; expected the S1 four"
    print(
        f"  verdicts:     {n_int} integrating verdict(s) carry {declared}; "
        f"the rest carry none"
    )


def test_an_integrating_gate_with_no_source_says_so_rather_than_none():
    """An integrating gate with no settings source records why, not None."""
    from octomod.gates import GateResult, gate, run_gate_set
    from tests._record import rnd, temp_record

    @gate("model_simulates_nominal", "T1", integrates=True)
    def orphan():
        return GateResult("model_simulates_nominal", "T1", True, detail="stub")

    class _Ledger:
        def append(self, *a, **k):
            pass

    with temp_record("unwired") as root:
        _ok, results = run_gate_set(
            [orphan], rnd(root, 0) / "gates", _Ledger(), "model"
        )
    got = results[0].solver_settings
    assert got and "unavailable" in got, got
    assert "attached no solver_settings" in got["unavailable"], got
    print("  unwired:      an integrating gate with no source records why, not None")


def test_the_fim_declares_it_needs_forward_sensitivities():
    """Adjoint removes `sres`, so the FIM declares it needs forward sensitivities."""
    from octomod.workflow_modules.evaluation import identifiability as ident

    why = ident.requires_forward_sensitivities()
    assert "sres" in why and "forward" in why and "adjoint" in why, why
    src = (
        REPO / "octomod" / "workflow_modules" / "evaluation" / "identifiability.py"
    ).read_text()
    assert (
        "sensi_method_note" in src and "requires_forward_sensitivities()" in src
    ), "the requirement is declared but the FIM path never mentions it"
    # and the fallback message must name the cause rather than just the method
    i = src.index("finite differences of the residual vector at the MLE")
    assert (
        "adjoint" in src[i : i + 600]
    ), "the finite-difference fallback does not say that adjoint is why"
    print(
        "  FIM:          declares it requires forward, and names adjoint as the cause"
    )


def test_every_top_level_simulation_key_is_consumed_by_something():
    """Each top-level `simulation` knob steers the probe and is read there by name."""
    block = RAW["simulation"]
    probe_src = (
        REPO / "octomod" / "workflow_modules" / "cost_probe" / "solver_probe.py"
    ).read_text()
    setter_keys = set(ss.ALL_KEYS)
    for key in block:
        if key in ("amici", "roadrunner"):
            continue  # their contents are checked above
        assert (
            f'simulation.{key}"' in probe_src or f"simulation.{key}'" in probe_src
        ), f"`simulation.{key}` is declared and nothing reads it"
        assert (
            key not in setter_keys
        ), f"{key!r} is both a probe knob and a solver setting — ambiguous"
    # and both sub-blocks are non-empty, or the checks above are vacuous
    assert block["amici"] and block["roadrunner"], block
    print(
        f"  whole block:  {len(block) - 2} probe knob(s) are read by name; "
        f"the two sub-blocks reach setters"
    )


def test_the_gate_offers_tighten_and_adjoint_only_when_measured_and_honours_them():
    """`tighten`/`adjoint` are offered only when measured, and read as the card says."""
    from octomod.workflow_modules.cost_probe import engine as cp

    quiet_tol = {"available": True, "agrees": True, "proposal": None}
    loud_tol = {
        "available": True,
        "agrees": False,
        "proposal": {"atol": 1e-14, "rtol": 1e-12},
    }
    fwd = {"available": True, "proposed_sensi_method": "forward"}
    adj = {"available": True, "proposed_sensi_method": "adjoint"}

    assert (
        cp._solver_note_forms(quiet_tol, fwd) == []
    ), "the gate offered options this model's measurement does not support"
    forms = cp._solver_note_forms(loud_tol, adj)
    assert any(f.startswith("tighten") for f in forms), forms
    assert any(f.startswith("adjoint") for f in forms), forms
    assert "sres" in " ".join(forms), "the adjoint offer hides its consequence"

    # The answer is read the way the card says: the word on its own, never a
    # mention inside a sentence. Reaching the solver is checked, compiled, in
    # tests/estimation_settings_unit.py.
    def read(note, tol=loud_tol, sensi=adj):
        return cp.read_budget_note(note, tol, sensi, 10, 1000)

    assert read("tighten").read == {"tighten": True}, read("tighten").read
    assert read("y tighten").read == {
        "tighten": True
    }, "a leading answer word is not prose"
    assert read("n=200 adjoint").read == {"n": 200, "adjoint": True}, read(
        "n=200 adjoint"
    ).read
    assert read("solver: adjoint").read == {"adjoint": True}
    mention = read(
        "convergence: accept standing rule, forward sensitivities as in "
        "rounds 0 and 1 (adjoint not taken: it would change the FIM method)"
    )
    assert (
        "adjoint" not in mention.read and "adjoint" in mention.unread
    ), f"a mention inside a sentence became an order — {mention.read}"
    assert (
        read("tighten", tol=quiet_tol).read == {}
    ), "tighten read where nothing proposed it"
    assert "tighten" in read("tighten", tol=quiet_tol).unread, "the refusal says why"
    assert read("run=3").read == {}, "`run=3` is not `n=3`"
    assert read("n=5").read == {"n": 10}, "n is clipped to the declared bounds"
    assert read("y").read == {}, "a plain approval changes nothing"
    print(
        "  gate answers: `tighten`/`adjoint` are offered only when measured, and "
        "read only as words on their own"
    )


if __name__ == "__main__":
    test_every_simulation_key_reaches_a_setter()
    test_every_refit_preset_key_reaches_a_setter()
    test_a_key_that_binds_to_nothing_raises_rather_than_no_ops()
    test_settings_are_read_back_not_assumed()
    test_roadrunner_tolerances_are_applied_and_verified()
    test_every_integration_gate_declares_itself()
    test_integration_gate_verdicts_record_their_tolerance()
    test_an_integrating_gate_with_no_source_says_so_rather_than_none()
    test_the_fim_declares_it_needs_forward_sensitivities()
    test_every_top_level_simulation_key_is_consumed_by_something()
    test_the_gate_offers_tighten_and_adjoint_only_when_measured_and_honours_them()
    print(
        "SOLVER SETTINGS UNIT OK — every declared key reaches a real setter and "
        "every integration verdict carries its tolerance"
    )
