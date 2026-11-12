"""Additive+proportional noise: rendered, compiled, and read back from AMICI.

Token-free; compiles a tiny model (~15 s cold, then content-hash cached). It asserts values,
not calls: a bare parameter id in `noiseFormula` is legal PEtab that the importer maps to
sigma = 0, so `rdata.sigmay` is compared point by point with `sigma_abs + sigma_rel * y`.

    uv run python tests/two_component_noise_unit.py
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
logging.disable(logging.CRITICAL)

from octomod.gates.petab_gates import (  # noqa: E402
    PetabTables,
    noise_band,
    resolve_sigmas,
    sigma_components,
    sigma_kind,
)
from octomod.workflow_modules.assembly import petab_io  # noqa: E402
from octomod.workflow_modules.assembly.engine import (  # noqa: E402
    NOISE_SHAPES,
    NoiseFormulaError,
    _render_noise,
    noise_shape_help,
)
from octomod.workflow_modules.assembly.petab_io import PetabInput  # noqa: E402

OID = "obs_b"
SIGMA_ABS, SIGMA_REL = 0.5, 0.1


def _model_sbml() -> str:
    import antimony

    antimony.loadAntimonyString("model m; A=10; B=0; J0: A->B; kdeg*A; kdeg=0.3; end")
    return antimony.getSBMLString(antimony.getMainModuleName())


def _write_problem(tmp: Path, noise_formula: str, noise_params: str) -> PetabInput:
    """A PEtab problem ON DISK — an input to the library, read back through
    `petab_io.from_dir` exactly as a testcase would be."""
    pdir, mdir = tmp / "petab", tmp / "model"
    pdir.mkdir(parents=True)
    mdir.mkdir(parents=True)
    (mdir / "model.xml").write_text(_model_sbml())
    pd.DataFrame(
        [
            {
                "observableId": OID,
                "observableFormula": "B",
                "observableTransformation": "lin",
                "noiseFormula": noise_formula,
                "noiseDistribution": "normal",
            }
        ]
    ).to_csv(pdir / "observables.tsv", sep="\t", index=False)
    pd.DataFrame([{"conditionId": "c0"}]).to_csv(
        pdir / "conditions.tsv", sep="\t", index=False
    )
    times = [0.0, 1.0, 2.0, 4.0, 8.0]
    pd.DataFrame(
        [
            {
                "observableId": OID,
                "simulationConditionId": "c0",
                "time": t,
                "measurement": 10 * (1 - np.exp(-0.3 * t)),
                "noiseParameters": noise_params,
            }
            for t in times
        ]
    ).to_csv(pdir / "measurements.tsv", sep="\t", index=False)
    pd.DataFrame(
        [
            {
                "parameterId": "kdeg",
                "parameterScale": "log10",
                "lowerBound": 1e-3,
                "upperBound": 1e3,
                "nominalValue": 0.3,
                "estimate": 1,
            },
            {
                "parameterId": "sigma_abs",
                "parameterScale": "log10",
                "lowerBound": 1e-4,
                "upperBound": 1e3,
                "nominalValue": SIGMA_ABS,
                "estimate": 1,
            },
            # only when the formula uses it: a parameter the problem never
            # references makes pypesto warn on every call
            *(
                [
                    {
                        "parameterId": "sigma_rel",
                        "parameterScale": "log10",
                        "lowerBound": 1e-4,
                        "upperBound": 1e3,
                        "nominalValue": SIGMA_REL,
                        "estimate": 1,
                    }
                ]
                if "sigma_rel" in noise_params
                else []
            ),
        ]
    ).to_csv(pdir / "parameters.tsv", sep="\t", index=False)
    (pdir / "problem.yaml").write_text(
        "format_version: 1\nparameter_file: parameters.tsv\nproblems:\n"
        "- condition_files:\n  - conditions.tsv\n"
        "  measurement_files:\n  - measurements.tsv\n"
        "  observable_files:\n  - observables.tsv\n"
        "  sbml_files:\n  - ../model/model.xml\n"
    )
    return petab_io.from_dir(pdir)


def test_amici_actually_uses_both_components():
    """Compile the two-component problem and read back the sigmas AMICI used."""
    from octomod.workflow_modules.estimation.problem import build_problem

    with tempfile.TemporaryDirectory() as tmp:
        inp = _write_problem(
            Path(tmp),
            f"noiseParameter1_{OID} + noiseParameter2_{OID} * B",
            "sigma_abs;sigma_rel",
        )
        prob, _pp, _cs = build_problem(inp, {})
        free = [list(prob.x_names)[i] for i in prob.x_free_indices]
        want = {
            "kdeg": np.log10(0.3),
            "sigma_abs": np.log10(SIGMA_ABS),
            "sigma_rel": np.log10(SIGMA_REL),
        }
        out = prob.objective(
            np.array([want[n] for n in free]), return_dict=True, sensi_orders=(0,)
        )
        rd = out["rdatas"][0]
        sigmay = np.asarray(rd.sigmay, dtype=float).ravel()
        y = np.asarray(rd.y, dtype=float).ravel()

        assert not np.allclose(sigmay, 0.0), (
            "sigma is ZERO — the known trap: legal PEtab that the AMICI "
            "importer maps to sigma=0 silently"
        )
        expected = SIGMA_ABS + SIGMA_REL * y
        assert np.allclose(sigmay, expected, rtol=0, atol=1e-9), list(
            zip(y, sigmay, expected, strict=False)
        )
        # the point of the shape: sigma stays finite where the signal is zero
        zero_i = int(np.argmin(np.abs(y)))
        assert abs(y[zero_i]) < 1e-12 and abs(sigmay[zero_i] - SIGMA_ABS) < 1e-12, (
            f"at y=0 sigma must be the additive floor {SIGMA_ABS}, got "
            f"{sigmay[zero_i]}"
        )
        # and it is genuinely two-component, not a constant that happens to fit
        assert sigmay.max() > sigmay.min() * 2, sigmay
    print(
        f"  AMICI         sigmay == {SIGMA_ABS} + {SIGMA_REL}*y at every point, "
        f"and == {SIGMA_ABS} where y == 0"
    )


def test_a_one_component_problem_still_reads_back_correctly():
    """A one-component sigma still reads back as the constant."""
    from octomod.workflow_modules.estimation.problem import build_problem

    with tempfile.TemporaryDirectory() as tmp:
        inp = _write_problem(Path(tmp), f"noiseParameter1_{OID}", "sigma_abs")
        prob, _pp, _cs = build_problem(inp, {})
        free = [list(prob.x_names)[i] for i in prob.x_free_indices]
        want = {"kdeg": np.log10(0.3), "sigma_abs": np.log10(SIGMA_ABS)}
        out = prob.objective(
            np.array([want[n] for n in free]), return_dict=True, sensi_orders=(0,)
        )
        sigmay = np.asarray(out["rdatas"][0].sigmay, dtype=float).ravel()
        assert np.allclose(sigmay, SIGMA_ABS), sigmay
    print(f"  constant      sigmay == {SIGMA_ABS} everywhere, unchanged")


def test_render_produces_the_petab_the_compile_needs():
    """The renderer's output is exactly what the test above hand-wrote."""
    ids, formula, column = _render_noise(
        "sigma_abs + sigma_rel * B", OID, {"A", "B"}, set()
    )
    assert ids == ["sigma_abs", "sigma_rel"], ids
    assert formula == f"noiseParameter1_{OID} + noiseParameter2_{OID} * B", formula
    assert column == "sigma_abs;sigma_rel", column
    # index follows FIRST APPEARANCE, so the formula and the column agree
    ids2, formula2, column2 = _render_noise(
        "sigma_rel * B + sigma_abs", OID, {"A", "B"}, set()
    )
    assert ids2 == ["sigma_rel", "sigma_abs"], ids2
    assert column2 == "sigma_rel;sigma_abs", column2
    assert formula2 == f"noiseParameter1_{OID} * B + noiseParameter2_{OID}", formula2
    # the one-component shapes
    assert _render_noise("0.5", OID, set(), set()) == (
        [],
        f"noiseParameter1_{OID}",
        "0.5",
    )
    assert _render_noise("s", OID, set(), set()) == (
        ["s"],
        f"noiseParameter1_{OID}",
        "s",
    )
    assert _render_noise("s * B", OID, {"B"}, set()) == (
        ["s"],
        f"noiseParameter1_{OID} * B",
        "s",
    )
    print("  render        placeholders and the column agree, in appearance order")


def test_an_unrenderable_formula_is_recoverable_not_fatal():
    """An over-cap formula raises NoiseFormulaError, which a re-ask recovers."""
    from octomod.orchestration.run_context import ModuleFailure

    try:
        _render_noise("a + b + c + d", OID, set(), set(), max_components=3)
    except NoiseFormulaError as e:
        assert "4 non-model parameters" in str(e), e
        assert not isinstance(e, ModuleFailure), (
            "an authoring mistake must not be a ModuleFailure — that once "
            "killed a live run instead of re-asking the agent"
        )
    else:
        raise AssertionError("an over-cap formula was accepted")
    print("  recoverable   over-cap raises NoiseFormulaError, not ModuleFailure")


def test_the_seam_check_turns_it_into_a_named_re_ask():
    """End to end through the checker the re-ask loop actually calls."""
    from octomod.workflow_modules.assembly.engine import _observation_reply_problems

    def _reply(formula: str) -> dict:
        return {
            "observables": [
                {
                    "observable_id": OID,
                    "maps_to_label": "b",
                    "formula": "B",
                    "transformation": "lin",
                    "noise": {
                        "distribution": "normal",
                        "formula": formula,
                        "estimate_sigma": True,
                    },
                    "scaling": {"mode": "none"},
                }
            ]
        }

    ents = {"A", "B"}
    # the two-component shape passes the seam
    assert _observation_reply_problems(_reply("s_abs + s_rel * B"), ["b"], ents) == []
    # and one the engine really cannot render produces a NAMED problem
    problems = _observation_reply_problems(_reply("a + b2 + c + d"), ["b"], ents)
    assert len(problems) == 1, problems
    assert OID in problems[0] and "non-model parameters" in problems[0], problems
    for name, _form, _why in NOISE_SHAPES:
        assert name in problems[0], (name, problems[0])
    print("  re-ask        names the observable, the cause and all three shapes")


def test_the_sigma_consumers_do_not_invent_a_number():
    """A single sigma does not exist for two components — say so, never 1.0."""
    with tempfile.TemporaryDirectory() as tmp:
        inp = _write_problem(
            Path(tmp),
            f"noiseParameter1_{OID} + noiseParameter2_{OID} * B",
            "sigma_abs;sigma_rel",
        )
        tables = PetabTables.from_input(inp)
        assert tables.noise_expression(OID) == "sigma_abs + sigma_rel * B"
        assert sigma_kind(tables, OID) == "multi_component"
        assert sigma_components(tables, OID) == ["sigma_abs", "sigma_rel"]
        vals = {"sigma_abs": SIGMA_ABS, "sigma_rel": SIGMA_REL}
        one = resolve_sigmas(tables, values=vals)[OID]
        assert np.isnan(one), (
            f"resolve_sigmas returned {one} for a state-dependent sigma; a "
            f"number here is fabricated (1.0 reads as a fitted value)"
        )
        # the honest answer is per point, and matches AMICI's own sigmay
        times = np.array([0.0, 1.0, 2.0, 4.0, 8.0])
        series = tables.sigma_series(OID, "c0", times, vals)
        assert series[0] == SIGMA_ABS, series
        assert np.all(np.diff(series) > 0), series
        band = noise_band(tables, OID, "c0", times, vals, z=2.0)
        assert np.allclose(band, 2.0 * series), (band, series)
        assert np.all(np.isfinite(band)), band
    print("  consumers     nan for the single number; a real per-point series")


def test_the_contract_the_skill_and_the_renderer_agree():
    """Three places describe the legal shapes. They must not drift."""
    from octomod.agents import ROLES

    contract = ROLES["observation"].contract
    skill = (REPO / "skills" / "observation.md").read_text()
    for name, _form, _why in NOISE_SHAPES:
        key = name.replace("+", "").replace(" ", "")
        assert name in contract or key in contract.replace(" ", "").replace(
            "+", ""
        ), f"the contract does not offer the {name!r} shape"
        assert name.split("+")[0].strip() in skill, f"the skill omits {name!r}"
    assert (
        "sigma_abs" in contract and "sigma_abs" in skill
    ), "the two-component shape must appear by example in both"
    # and the rule on what a signal-dependent sigma may be written on
    from octomod.workflow_modules.assembly.engine import _SIGNAL

    def _flat(text: str) -> str:
        return " ".join(text.split()).lower()

    assert _flat(_SIGNAL) in _flat(
        contract
    ), "the contract does not state the signal-expression rule the shapes carry"
    # and the renderer must actually accept every shape the two advertise —
    # the gain-scaled one names the declared scale parameter, which renders as
    # the observable placeholder, never as a sigma
    for _name, form, _why in NOISE_SHAPES:
        expr = form.replace("<this observable's signal expression>", "B")
        ids, rendered, _c = _render_noise(
            expr,
            OID,
            {"B"},
            {"sc_obs_x"},
            placeholder_map={"sc_obs_x": f"observableParameter1_{OID}"},
        )
        assert ids, f"the advertised shape {form!r} renders to no sigma parameter"
        if "sc_obs_x" in form:
            assert rendered.startswith(f"observableParameter1_{OID} *"), rendered
    assert noise_shape_help().count("`") == 2 * len(NOISE_SHAPES)
    print(
        f"  no drift      contract, skill and renderer agree on {len(NOISE_SHAPES)} shapes"
    )


def test_a_rule_symbol_is_expanded_and_the_sigma_checked_through_the_observable():
    """Rules expand to a fixed point; an agent's sigma reaches the model only
    through its own formula, and supplied tables keep AMICI's elimination."""
    from octomod.gates.petab_gates import sigma_state_problem
    from octomod.workflow_modules.assembly.engine import expand_rules

    rules = {"S0": "rho^0 * C0", "T": "S0 + 2 * B"}
    assert expand_rules("sc * (S0)", rules) == "sc * (rho^0 * C0)"
    # a rule that names a rule expands to species and parameters only
    assert expand_rules("T", rules) == "((rho^0 * C0) + 2 * B)"
    # an exponent letter is not an identifier, a longer id is not the rule's
    assert expand_rules("1e-3 * S0x + S0", rules) == "1e-3 * S0x + (rho^0 * C0)"
    try:
        expand_rules("a", {"a": "b + 1", "b": "a * 2"})
    except ValueError as e:
        assert "a -> b -> a" in str(e) and "cycle" in str(e), e
    else:
        raise AssertionError("a cycle of rules expanded")

    states = {"A", "B", "C0"}
    obs = expand_rules("S0", rules)

    # an agent's formula (`core` given): the sigma reaches the model only
    # through that formula, with or without its gain
    core = "2 * A"
    assert sigma_state_problem(f"s * ({core})", core, states, core=core) is None
    assert (
        sigma_state_problem(
            f"s_abs + s_rel * sc * ({core})", f"sc * ({core})", states, core=core
        )
        is None
    )
    assert (
        sigma_state_problem(
            f"s_abs + s_rel * ({core})", f"sc * ({core})", states, core=core
        )
        is None
    )
    # on the species a linear formula names but which is not the whole
    # formula: refused, where AMICI's rule would solve for it
    problem = sigma_state_problem("s * A", core, states, obs_id="obs_x", core=core)
    assert problem and "obs_x" in problem and "['A']" in problem, problem
    assert "other than through this observable's own formula" in problem, problem
    assert "prediction" in problem and "gain-scaled" in problem, problem
    assert sigma_state_problem("s * A", core, states) is None
    # a state the formula does not name: refused, with what to write
    problem = sigma_state_problem(
        "s_abs + s_rel * B", core, states, obs_id="obs_x", core=core
    )
    assert (
        problem
        and "['B']" in problem
        and "other than through this observable's own formula" in problem
        and "sigma_abs + sigma_rel" in problem
    ), problem
    # a rule symbol left in the sigma fails AMICI's C++ build: named
    problem = sigma_state_problem(
        "s + r * S0", "sc * S0", states, rules={"S0"}, core="S0"
    )
    assert problem and "S0" in problem and "assignment rule" in problem, problem
    # never more than AMICI accepts: on a formula AMICI cannot solve for its
    # state, a sigma without the gain is refused, and the whole prediction is not
    frac = "A / (A + B)"
    problem = sigma_state_problem(
        f"s + r * {frac}", f"sc * ({frac})", states, obs_id="obs_f", core=frac
    )
    assert problem and "obs_f" in problem and "without its gain" in problem, problem
    assert (
        sigma_state_problem(
            f"s + r * sc * ({frac})", f"sc * ({frac})", states, core=frac
        )
        is None
    )

    # supplied tables (`core` None): AMICI's elimination, unchanged
    assert sigma_state_problem(f"s_abs + s_rel * {obs}", obs, states) is None
    assert (
        sigma_state_problem(f"s_abs + s_rel * sc * ({obs})", f"sc * ({obs})", states)
        is None
    )
    # on the one species a linear formula names, too
    assert sigma_state_problem("s_abs + s_rel * C0", f"sc * ({obs})", states) is None
    # a species this observable's formula does not determine is named
    problem = sigma_state_problem("s_abs + s_rel * A", obs, states, obs_id="obs_x")
    assert problem and "obs_x" in problem and "['A']" in problem, problem
    assert "prediction" in problem and "gain-scaled" in problem, problem
    # two states, where eliminating one leaves the other
    problem = sigma_state_problem("s + r * A + q * B", "A + B", states)
    assert problem and "['A', 'B']" in problem, problem
    # a rule symbol left in the sigma fails AMICI's C++ build: named
    problem = sigma_state_problem("s + r * S0", "sc * S0", states, rules={"S0"})
    assert problem and "S0" in problem and "assignment rule" in problem, problem
    # ids a plain sympify would read as Python or sympy names
    assert sigma_state_problem("lambda + S * A", "E * A", states) is None
    assert (
        sigma_state_problem("lambda + S * E * A", "E * A", states, core="E * A") is None
    )

    # the renderer takes a rule symbol like any model symbol
    ids, rendered, _ = _render_noise(
        "sigma_abs + sigma_rel * S0", "obs_x", {"A", "B", "S0"}, set()
    )
    assert ids == ["sigma_abs", "sigma_rel"], ids
    assert rendered == "noiseParameter1_obs_x + noiseParameter2_obs_x * S0", rendered
    print(
        "  rule sigma    rules expand, a cycle is named; an agent's sigma passes only "
        "through its own formula, supplied tables keep AMICI's elimination"
    )


def test_the_compile_loop_lets_control_flow_through():
    from octomod.orchestration.orchestrator import _is_control_flow
    from octomod.orchestration.run_context import ModuleFailure

    assert _is_control_flow(ModuleFailure("x")) and _is_control_flow(
        KeyboardInterrupt()
    )
    assert not _is_control_flow(RuntimeError("cmake --build failed"))
    print("  compile loop  re-raises control flow, drops on anything else")


def test_the_formula_that_killed_the_live_run_now_renders():
    """A recorded two-component CTD reply, inlined, renders for all 9 observables."""
    ents = {f"P{i}" for i in range(9)}
    for k in range(9):
        ids, formula, column = _render_noise(
            f"sigma_ctd_ms_abs + sigma_ctd_ms_rel * P{k}",
            f"obs_ctd_phos{k}",
            ents,
            set(),
        )
        assert ids == ["sigma_ctd_ms_abs", "sigma_ctd_ms_rel"], ids
        assert column == "sigma_ctd_ms_abs;sigma_ctd_ms_rel", column
        assert formula == (
            f"noiseParameter1_obs_ctd_phos{k} + "
            f"noiseParameter2_obs_ctd_phos{k} * P{k}"
        ), formula
    print("  live run      all 9 CTD observables render; the run stopped on the first")


def test_a_state_dependent_sigma_is_reported_not_comparable_not_dropped():
    """The misfit apparatus says why it cannot compare a state-dependent sigma."""
    import inspect

    from octomod.workflow_modules.evaluation import engine as evaluation_module

    src = inspect.getsource(evaluation_module)
    i_const = src.index("constant = tables.sigma_is_constant")
    i_guard = src.index("if not f or not np.isfinite(sigma) or sigma <= 0:")
    assert i_const < i_guard, (
        "the finiteness guard runs BEFORE the state-dependence check, so a "
        "two-component sigma is skipped silently instead of explained"
    )
    seg = src[i_const : i_guard + 200]
    assert "sigma_not_constant" in seg and "components" in seg, seg[:300]
    # and the reader-facing line exists for that signal
    margins = (
        REPO / "octomod" / "workflow_modules" / "evaluation" / "misfit_margins.py"
    ).read_text()
    assert (
        "NOT COMPARABLE" in margins and "sigma_not_constant" in margins
    ), "nothing renders the not-comparable signal for a human"
    print("  misfit        state-dependent sigma is explained, never silently skipped")


def test_the_two_sigma_definitions_agree():
    """`nan` from `resolve_sigmas` iff `sigma_kind` says multi_component."""
    import logging

    logging.disable(logging.CRITICAL)
    import antimony
    import numpy as np
    import pandas as pd

    from octomod.gates.petab_gates import PetabTables, resolve_sigmas, sigma_kind

    antimony.loadAntimonyString("model m; A=10; B=0; J0: A->B; kdeg*A; kdeg=0.3; end")
    sbml = antimony.getSBMLString(antimony.getMainModuleName())

    def tab(formula, col):
        return PetabTables(
            observables=pd.DataFrame(
                [
                    {
                        "observableId": "o",
                        "observableFormula": "B",
                        "observableTransformation": "lin",
                        "noiseFormula": formula,
                        "noiseDistribution": "normal",
                    }
                ]
            ),
            conditions=pd.DataFrame([{"conditionId": "c0"}]),
            measurements=pd.DataFrame(
                [
                    {
                        "observableId": "o",
                        "simulationConditionId": "c0",
                        "time": t,
                        "measurement": 1.0,
                        "noiseParameters": col,
                    }
                    for t in (0.0, 1.0)
                ]
            ),
            parameters=pd.DataFrame(
                [
                    {
                        "parameterId": p,
                        "parameterScale": "lin",
                        "lowerBound": 1e-4,
                        "upperBound": 1e3,
                        "nominalValue": v,
                        "estimate": 1,
                    }
                    for p, v in (("s_abs", 0.5), ("s_rel", 0.1), ("kdeg", 0.3))
                ]
            ),
            sbml=sbml,
        )

    vals = {"s_abs": 0.5, "s_rel": 0.1, "kdeg": 0.3}
    cases = [
        ("noiseParameter1_o", "s_abs", "constant"),
        ("noiseParameter1_o", "0.5", "constant"),
        ("noiseParameter1_o * B", "s_rel", "proportional"),
        # two symbols, the second a parameter and not a species: constant across
        # points, so a number exists
        ("noiseParameter1_o + noiseParameter2_o * kdeg", "s_abs;s_rel", "constant"),
        ("noiseParameter1_o + noiseParameter2_o * B", "s_abs;s_rel", "multi_component"),
    ]
    for formula, col, want_kind in cases:
        t = tab(formula, col)
        kind = sigma_kind(t, "o")
        val = resolve_sigmas(t, values=vals)["o"]
        assert kind == want_kind, (formula, kind, want_kind)
        assert np.isnan(val) == (kind == "multi_component"), (
            f"{formula!r}: kind={kind} but resolve_sigmas={val} — the two "
            f"definitions disagree, which is the defect this check exists for"
        )
    # a constant two-symbol sigma resolves to a real value
    t = tab("noiseParameter1_o + noiseParameter2_o * kdeg", "s_abs;s_rel")
    assert abs(resolve_sigmas(t, values=vals)["o"] - (0.5 + 0.1 * 0.3)) < 1e-12
    print(f"  sigma agree   {len(cases)} shapes: nan iff multi_component, never else")


if __name__ == "__main__":
    test_render_produces_the_petab_the_compile_needs()
    test_an_unrenderable_formula_is_recoverable_not_fatal()
    test_the_seam_check_turns_it_into_a_named_re_ask()
    test_the_contract_the_skill_and_the_renderer_agree()
    test_the_sigma_consumers_do_not_invent_a_number()
    test_a_state_dependent_sigma_is_reported_not_comparable_not_dropped()
    test_a_rule_symbol_is_expanded_and_the_sigma_checked_through_the_observable()
    test_the_compile_loop_lets_control_flow_through()
    test_the_formula_that_killed_the_live_run_now_renders()
    test_a_one_component_problem_still_reads_back_correctly()
    test_amici_actually_uses_both_components()
    test_the_two_sigma_definitions_agree()
    print(
        "TWO-COMPONENT NOISE OK — AMICI uses both components, the single-sigma "
        "consumers refuse to invent a number, and a bad formula is a re-ask"
    )
