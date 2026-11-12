"""The information spectrum at the MLE is reported as a spectrum, never a rank verdict.

  1. a flat direction reads as a signed log combination and becomes an epistemic entry;
  2. the report renders a spectrum and says it is not a rank;
  3. the epistemic gate matches an echo on its claim, not its spelling;
  4. the screen hands the objective only the free parameters.

    uv run python tests/identifiability_unit.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.result.node import Node  # noqa: E402
from octomod.workflow_modules.evaluation import engine as s7  # noqa: E402
from octomod.workflow_modules.evaluation import identifiability as ident  # noqa: E402


def test_a_flat_direction_reads_as_a_combination() -> None:
    """A flat direction is a combination, and it must read like one."""
    text = ident._combination_text({"A0": 0.71, "sc": -0.70, "k1": 0.02})
    assert "log(A0)" in text and "log(sc)" in text
    assert text.startswith("0.71*log(A0)"), text
    assert "-0.70*log(sc)" in text, "the sign carries the trade-off"
    assert text.index("A0") < text.index("sc"), "largest loading first"
    assert ident._combination_text({}) == (
        "(no single parameter dominates this direction)"
    )


def test_flat_combinations_become_epistemic_entries() -> None:
    """They are entries the agent must echo, not a reason to reject a model."""
    spectrum = {
        "available": True,
        "flat_directions": [
            {
                "index": 2,
                "decades_below_largest": 11.4,
                "composition": {"A0": 0.71, "sc": -0.70},
                "reads_as": "0.71*log(A0) -0.70*log(sc)",
            },
            {
                "index": 1,
                "decades_below_largest": 9.1,
                "composition": {},
                "reads_as": "(no single parameter dominates this direction)",
            },
        ],
    }
    out = ident.computed_flat_combinations(spectrum)
    assert len(out) == 1, "a direction with no composition names nothing to echo"
    assert out[0].startswith("flat combination (FIM): ")
    assert "0.71*log(A0)" in out[0]
    assert ident.computed_flat_combinations({}) == []
    assert ident.computed_flat_combinations({"available": False}) == []


def test_the_report_gives_a_spectrum_and_says_it_is_not_a_rank() -> None:
    src = (REPO / "octomod" / "reporting" / "round_report.py").read_text()
    block = src.split("def _identifiability(")[1].split("\ndef ")[0]
    assert (
        "A SPECTRUM, not a rank" in block
    ), "the section must say outright what it is not"
    assert "eigenvalue spread" in block and "decades" in block
    assert "flat combinations" in block
    assert "predict well" in block, (
        "and that a non-identifiable model can still predict — otherwise the "
        "reader takes the spectrum as a verdict"
    )
    # no rank verdict anywhere in the renderer, only the disclaimers; matched on
    # the phrases that make a claim, not the bare substring "rank", which also
    # matches prose about ranking misfit indicators
    claims = re.compile(
        # `\b` after `=` never matches (both sides are non-word), so the word
        # forms keep their boundary and the operators have none
        r"\b(?:full[- ]rank|rank[- ]deficien\w*|numerical rank|effective rank"
        r"|rank\s*(?:(?:is|of)\b|[=:]))",
        re.I,
    )
    disclaimers = ("not a rank", "Rank deficiency", "never a rank verdict")
    for line in src.splitlines():
        if claims.search(line):
            assert any(
                w in line for w in disclaimers
            ), f"a rank claim leaked into the renderer: {line.strip()[:90]}"


# --- the echo comparison must read the claim --------------------------------


def test_a_reformatted_echo_is_not_an_overclaim() -> None:
    """Every re-spelling of the same claim passes the blocking epistemic gate."""
    computed = "flat combination (FIM): 1.00*log(k_actB) -1.00*log(k_deactB)"
    core = {
        "computed_cannot_distinguish": [computed],
        "computed_nonetheless_determined": [],
    }
    echoes = {
        "verbatim": computed,
        "unicode minus (U+2212)": (
            "flat combination (FIM): 1.00*log(k_actB) \u22121.00*log(k_deactB)"
        ),
        "unicode minus sign (U+2013)": (
            "flat combination (FIM): 1.00*log(k_actB) \u20131.00*log(k_deactB)"
        ),
        "fewer decimals": "flat combination (FIM): 1.0*log(k_actB) -1.0*log(k_deactB)",
        "terms swapped": (
            "flat combination (FIM): -1.00*log(k_deactB) +1.00*log(k_actB)"
        ),
        "extra spaces": (
            "flat  combination (FIM):  1.00 * log( k_actB )  - 1.00 * log( k_deactB )"
        ),
        "lower-cased prefix": (
            "flat combination (fim): 1.00*log(k_actB) - 1.00*log(k_deactB)"
        ),
        "prose around it": (
            "the flat combination (FIM) 1.00*log(k_actB) -1.00*log(k_deactB) is "
            "unconstrained by these data"
        ),
    }
    for label, echoed in echoes.items():
        interp = {
            "cannot_distinguish": [echoed],
            "nonetheless_determined": [],
            "answers_intent": [{"criterion": "c", "verdict": "pass"}],
        }
        r1 = s7._consistency_results(core, interp)[0]
        assert r1.passed, f"a {label} echo failed the blocking gate: {r1.detail}"
    print(f"  echoes        {len(echoes)} re-spellings of one claim all pass the gate")


def test_the_gate_still_catches_a_real_omission() -> None:
    """A real omission still fails, and the detail quotes the string to copy."""
    computed = "flat combination (FIM): 1.00*log(k_actB) -1.00*log(k_deactB)"
    core = {
        "computed_cannot_distinguish": [computed],
        "computed_nonetheless_determined": [],
    }
    cases = {
        "said nothing": [],
        "named one parameter only": ["k_actB"],
        "named a DIFFERENT combination": [
            "flat combination (FIM): 1.00*log(k_actB) -1.00*log(k_cat1)"
        ],
        "a paraphrase that names no parameter": [
            "flat combination: two rate constants trade off"
        ],
    }
    for label, echoed in cases.items():
        interp = {
            "cannot_distinguish": echoed,
            "nonetheless_determined": [],
            "answers_intent": [{"criterion": "c", "verdict": "pass"}],
        }
        r1 = s7._consistency_results(core, interp)[0]
        assert not r1.passed, f"the gate accepted {label}"
        assert (
            computed in r1.detail
        ), f"the failure for {label} does not quote what to copy: {r1.detail}"
    print(f"  omissions     {len(cases)} ways of not saying it all still fail")


def test_every_computed_entry_yields_a_key() -> None:
    """Every formatted combination parses back to a key, or the gate is unpassable."""
    comps = [
        {"k_a": 0.71, "k_b": -0.70},
        {"k_a": -1.0},
        {"A0": 0.5, "sc": -0.5, "off": 0.5, "k_deg": -0.5},
        {"sigma_obs_X": 0.99, "sc_obs_X": -0.99},
    ]
    spectrum = {
        "available": True,
        "flat_directions": [
            {"composition": c, "reads_as": ident._combination_text(c)} for c in comps
        ],
    }
    entries = ident.computed_flat_combinations(spectrum)
    assert len(entries) == len(comps)
    for comp, entry in zip(comps, entries, strict=True):
        key = ident.combination_key(entry)
        assert key is not None, f"the formatter emitted an unparseable entry: {entry}"
        assert key == "flat:" + "|".join(sorted(comp)), (
            f"the key does not name exactly the parameters in the direction: "
            f"{key} vs {sorted(comp)}"
        )
    print(f"  round trip    {len(entries)} formatted combinations all parse back")


def test_identifiers_ignore_whitespace_but_not_case() -> None:
    """Identifiers ignore whitespace, not case: SBML/PEtab ids are case-sensitive."""
    key = s7._epistemic_key
    assert key("mechanism: M3_ff") == key("mechanism:M3_ff")
    assert key(" k_actB ") == key("k_actB")
    assert key("obs_ProD @ c_u4") == key("obs_ProD@c_u4")
    assert key("K_actB") != key("k_actB"), (
        "case must not be folded: a model may hold two ids differing only in "
        "case, and a wrong match is a silent overclaim"
    )
    assert key("k_actB") != key("k_deactB")


def test_the_computed_reference_is_exactly_what_the_gate_requires() -> None:
    """What the screen feeds into `computed_cannot_distinguish` the gate insists on."""
    core = {
        "identifiability": {
            "available": True,
            "flat_directions": [
                {
                    "composition": {"k_actB": 0.71, "k_deactB": -0.70},
                    "reads_as": ident._combination_text(
                        {"k_actB": 0.71, "k_deactB": -0.70}
                    ),
                }
            ],
        },
        "computed_cannot_distinguish": ["k_slow"],
        "computed_nonetheless_determined": [],
    }
    core["computed_cannot_distinguish"] = list(
        core["computed_cannot_distinguish"]
    ) + s7._flat_combination_entries(core)
    assert len(core["computed_cannot_distinguish"]) == 2

    # echo BOTH, one of them re-spelled: the gate passes
    interp = {
        "cannot_distinguish": [
            "k_slow",
            "flat combination (FIM): 0.71*log(k_actB) \u22120.70*log(k_deactB)",
        ],
        "nonetheless_determined": [],
        "answers_intent": [{"criterion": "c", "verdict": "pass"}],
    }
    assert s7._consistency_results(core, interp)[0].passed
    # drop the parameter id and it fails, naming it
    interp["cannot_distinguish"] = interp["cannot_distinguish"][1:]
    r1 = s7._consistency_results(core, interp)[0]
    assert not r1.passed and "k_slow" in r1.detail, r1.detail
    print("  composition   the screen feeds the gate; the gate insists on it")


def check_run_screened(rnd: Node, path_name: str) -> None:
    """Assert a finished round screened, and fed every flat combination to the gate.

    `rnd` is the round's record node (`rounds/round_k`)."""
    core = (rnd / "evaluation_core").get()
    screen = core.get("identifiability")
    assert screen, f"{path_name}: no identifiability screen in evaluation_core"
    assert screen.get("available"), f"{path_name}: screen ran but failed: {screen}"
    assert screen.get("n_free", 0) > 0 and screen.get(
        "eigenvalues_log10"
    ), f"{path_name}: the screen produced no spectrum: {screen}"
    fed = set(core.get("computed_cannot_distinguish") or [])
    for entry in ident.computed_flat_combinations(screen):
        assert entry in fed, (
            f"{path_name}: the screen found a flat combination that never "
            f"reached computed_cannot_distinguish: {entry}"
        )
    n_flat = len(ident.computed_flat_combinations(screen))
    print(
        f"  screened      {path_name}: {screen['n_free']} free, spread "
        f"{screen.get('spread_decades')} decades, {n_flat} flat combination(s) fed"
    )


class _FixedParameterProblem:
    """A problem with a fixed parameter; its objective raises on the full vector."""

    def __init__(self, n: int = 5, fixed: int = 2, offers: str = "sres") -> None:
        self.x_names = [f"p{i}" for i in range(n)]
        self.x_free_indices = [i for i in range(n) if i != fixed]
        self.offers = offers  # "sres" | "res" | "grad"
        self.seen: list[int] = []

    def _check(self, x):
        import numpy as np

        x = np.asarray(x, dtype=float)
        self.seen.append(len(x))
        if len(x) != len(self.x_free_indices):
            raise ValueError(
                f"shape mismatch: value array of shape ({len(x)},) could not "
                f"be broadcast to indexing result of shape "
                f"({len(self.x_free_indices)},)"
            )
        return x

    def objective(self, x, sensi_orders=(0,), mode=None, return_dict=False):
        import numpy as np
        import pypesto.C as C

        x = self._check(x)
        n = len(x)
        if mode == C.MODE_RES:
            if self.offers == "grad":
                raise ValueError("this objective has no residual mode")
            # residuals that depend on x, so finite differences are non-zero
            res = np.tile(x, 3)
            out = {"res": res}
            if self.offers == "sres" and 1 in sensi_orders:
                out["sres"] = np.tile(np.eye(n), (3, 1))
            return out if return_dict else res
        # a quadratic with one nearly-flat direction, so the spectrum has one
        w = np.array([1.0, 1.0, 1e-9, 1.0][:n] + [1.0] * max(0, n - 4))
        if 1 in sensi_orders:
            return 2.0 * w * x
        return float(w @ (x**2))


def test_the_screen_never_hands_the_objective_a_fixed_parameter() -> None:
    """On every method path, the vector reaching the objective is the free one."""
    import numpy as np

    for offers, expect_method in (
        ("sres", "residual sensitivities"),
        ("res", "finite differences of the residual vector"),
        ("grad", "finite differences of the gradient"),
    ):
        prob = _FixedParameterProblem(offers=offers)
        x_full = np.array([0.3, -1.2, 99.0, 0.7, -0.4])  # index 2 is the fixed one
        out = ident.fim_at_mle(prob, x_full, list(prob.x_names), flat_decades=8.0)
        assert out.get("available"), f"{offers}: {out.get('note')}"
        assert out["n_free"] == 4, out["n_free"]
        assert "p2" not in out["x_names"], (
            f"{offers}: the FIXED parameter is in the spectrum's parameter list "
            f"{out['x_names']} — the screen is reporting a direction the "
            f"optimiser never moved"
        )
        assert expect_method in out["method"], (offers, out["method"])
        assert prob.seen, f"{offers}: the objective was never called"
        assert set(prob.seen) == {4}, (
            f"{offers}: the objective was handed vectors of length "
            f"{sorted(set(prob.seen))}; only the 4 free parameters exist as far "
            f"as it is concerned"
        )
        # and the fixed parameter's value must not leak in as a perturbation
        # target: 99.0 is far from the others, so a full-index perturbation
        # would show up in the spectrum's magnitude
        spectrum = [v for v in out["eigenvalues_log10"] if v is not None]
        assert spectrum and all(np.isfinite(v) for v in spectrum), out[
            "eigenvalues_log10"
        ]


def test_a_problem_with_nothing_fixed_is_unchanged() -> None:
    """With nothing fixed, the free vector is the whole vector and the screen works."""
    import numpy as np

    prob = _FixedParameterProblem(n=4, fixed=99, offers="sres")  # nothing fixed
    assert prob.x_free_indices == [0, 1, 2, 3]
    out = ident.fim_at_mle(
        prob, np.array([0.3, -1.2, 0.7, -0.4]), list(prob.x_names), flat_decades=8.0
    )
    assert out.get("available"), out.get("note")
    assert out["n_free"] == 4 and set(prob.seen) == {4}
    print(
        "  free space    the objective is handed the free vector on all three "
        "method paths, fixed or not"
    )


if __name__ == "__main__":
    test_a_flat_direction_reads_as_a_combination()
    print("  combination   reads as a signed log combination, largest first")
    test_flat_combinations_become_epistemic_entries()
    print("  epistemics    flat directions become entries to echo, not vetoes")
    test_the_report_gives_a_spectrum_and_says_it_is_not_a_rank()
    print("  renderer      a spectrum, and it says it is not a rank")
    test_a_reformatted_echo_is_not_an_overclaim()
    test_the_gate_still_catches_a_real_omission()
    test_every_computed_entry_yields_a_key()
    test_identifiers_ignore_whitespace_but_not_case()
    print("  identifiers   whitespace ignored, case never folded")
    test_the_screen_never_hands_the_objective_a_fixed_parameter()
    test_a_problem_with_nothing_fixed_is_unchanged()
    test_the_computed_reference_is_exactly_what_the_gate_requires()
    print(
        "IDENTIFIABILITY UNIT OK — the spectrum is reported, the rank is not, "
        "and the echo is matched on the claim rather than its spelling"
    )
