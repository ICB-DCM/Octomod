"""What the note says is constant is measured for drift, and a drift is flagged.

The conservation scan reports what a model does conserve; this checks what the note says
it should. A flag, not a constraint: a sink stays allowed, since the note may be wrong.

    uv run python tests/declared_constants_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.workflow_modules.model import declared_constants as dc  # noqa: E402
from tests._record import rnd, temp_record  # noqa: E402

HEAD = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" '
    'level="3" version="1"><model id="m">'
    '<listOfCompartments><compartment id="cell" size="1" constant="true"/>'
    "</listOfCompartments>"
)


def _sbml(species: dict[str, float], reactions: list[tuple]) -> str:
    """(id, reactants, products, law) — an empty product list is a sink."""
    sp = "".join(
        f'<species id="{s}" compartment="cell" initialConcentration="{v}" '
        f'hasOnlySubstanceUnits="false" boundaryCondition="false" '
        f'constant="false"/>'
        for s, v in species.items()
    )

    def refs(tag, ids):
        if not ids:
            return ""
        inner = "".join(
            f'<speciesReference species="{i}" stoichiometry="1" constant="true"/>'
            for i in ids
        )
        return f"<listOf{tag}>{inner}</listOf{tag}>"

    rx = "".join(
        f'<reaction id="{rid}" reversible="false">'
        + refs("Reactants", rs)
        + refs("Products", ps)
        + '<kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML">'
        + f"<apply><times/><cn>{rate}</cn><ci>{rs[0]}</ci></apply></math>"
        + "</kineticLaw></reaction>"
        for rid, rs, ps, rate in reactions
    )
    return (
        HEAD
        + f"<listOfSpecies>{sp}</listOfSpecies>"
        + f"<listOfReactions>{rx}</listOfReactions></model></sbml>"
    )


CLOSED = _sbml(
    {"A": 5.0, "B": 0.0}, [("J1", ["A"], ["B"], 0.05), ("J2", ["B"], ["A"], 0.02)]
)
OPEN_SINK = _sbml(
    {"A": 5.0, "B": 0.0}, [("J1", ["A"], ["B"], 0.05), ("J2", ["B"], [], 0.02)]
)
DECL = [
    {
        "expression": "A + B",
        "tolerance": 0.10,
        "locator": "the A + B pool is 5 uM and does not change appreciably",
    }
]


def test_a_conserved_pool_passes() -> None:
    rows = dc.drift(CLOSED, DECL, t_end=120.0)
    assert len(rows) == 1 and not rows[0].get("error"), rows
    assert rows[0]["within_tolerance"] is True
    assert rows[0]["drift"] < 0.01, rows[0]["drift"]
    assert dc.offenders(rows) == []
    lines = dc.card_lines(rows)
    assert len(lines) == 1 and "hold" in lines[0], lines
    print(f"  closed pool   drift {rows[0]['drift']:.2%}, reported as holding")


def test_an_open_sink_is_flagged_but_not_refused() -> None:
    rows = dc.drift(OPEN_SINK, DECL, t_end=120.0)
    r = rows[0]
    assert r["within_tolerance"] is False
    assert r["drift"] > 0.30, f"expected a large drift, got {r['drift']:.1%}"
    assert r["at_t0"] == 5.0 and r["worst"] < 4.0
    assert 0 < r["at_time"] <= 120.0

    lines = "\n".join(dc.card_lines(rows))
    assert "THE NOTE SAYS THESE ARE CONSTANT" in lines
    assert "A + B" in lines and "tolerance 10%" in lines
    assert "does not change appreciably" in lines, "quote the sentence back"
    assert "a flag, not a refusal" in lines, (
        "the card must say a sink is still allowed — a constraint here would "
        "forbid a mechanism the note might be wrong about"
    )
    s = dc.summary(rows)
    assert s["declared"] == 1 and s["violated"] == 1 and s["worst_drift"] > 0.30
    print(f"  open sink     drift {r['drift']:.0%} flagged, and stated as advisory")


def test_the_declaration_is_read_forgivingly() -> None:
    """A malformed row must cost that row, never the whole check."""
    assert dc.parse(None) == [] and dc.parse({}) == []
    parsed = dc.parse(
        {
            "declared_constants": [
                "A + B",  # a bare string is enough
                {"expression": "  ", "tolerance": 0.2},  # nothing to measure
                {"expression": "A", "tolerance": "wrong"},  # unusable tolerance
                {"expression": "B", "tolerance": 9.0},  # out of range
                {"quantity": "A + B", "source": "the note"},  # the other field names
            ]
        }
    )
    assert [p["expression"] for p in parsed] == ["A + B", "A", "B", "A + B"]
    assert parsed[0]["tolerance"] == dc.DEFAULT_TOLERANCE
    assert parsed[1]["tolerance"] == dc.DEFAULT_TOLERANCE, "unusable -> default"
    assert parsed[2]["tolerance"] == dc.DEFAULT_TOLERANCE, "out of range -> default"
    assert parsed[3]["locator"] == "the note"

    # an expression naming something absent is reported, not raised
    rows = dc.drift(
        CLOSED,
        [{"expression": "A + Nope", "tolerance": 0.1, "locator": ""}],
        t_end=10.0,
    )
    assert rows[0].get("error"), rows
    assert "not measured" in "\n".join(dc.card_lines(rows))
    assert dc.drift(CLOSED, [], t_end=10.0) == [], "nothing declared, nothing said"
    assert dc.card_lines([]) == []
    print("  parsing       a bad row costs that row, never the check")


VIOLATION = {
    "expression": "PreC + ProD",
    "tolerance": 0.1,
    "locator": "the precursor pool is fixed at 5 uM, neither made nor destroyed",
    "drift": 0.26,
    "within_tolerance": False,
    "condition": "c_u4_bx11",
    "at_t0": 5.0,
    "worst": 3.7,
    "at_time": 120.0,
}
SUMMARY = {
    "declared": 1,
    "measured": 1,
    "unmeasured": 0,
    "violated": 1,
    "worst_drift": 0.26,
    "rows": [VIOLATION],
}


def test_a_violated_declaration_only_corroborates() -> None:
    """A drift joins `reasons` beside a hard signal; otherwise it is only in `also_seen`."""
    from octomod.workflow_modules.evaluation.engine import (
        _join_declared_constants as join,
    )

    # nothing hard open: reported, and it must not open the flag
    quiet = {
        "declared_constants": SUMMARY,
        "misfit_evidence": {
            "open": False,
            "reasons": [],
            "also_seen": [],
            "signals": {},
        },
    }
    join(quiet)
    ev = quiet["misfit_evidence"]
    assert ev["open"] is False, (
        "a violated note must not open the misfit flag on its own — it gates "
        "the stop move and buys expansion rounds"
    )
    assert ev["reasons"] == [], ev["reasons"]
    assert len(ev["also_seen"]) == 1 and "26%" in ev["also_seen"][0], ev["also_seen"]
    assert (
        ev["signals"]["declared_constant_drift"] is True
    ), "demoted is not hidden: the signal is always recorded"

    # a hard signal open: the drift corroborates it and joins the reasons
    loud = {
        "declared_constants": SUMMARY,
        "misfit_evidence": {
            "open": True,
            "reasons": ["fitted sigma exceeds the replicate noise floor"],
            "also_seen": [],
            "signals": {},
        },
    }
    join(loud)
    ev = loud["misfit_evidence"]
    assert ev["open"] is True and len(ev["reasons"]) == 2, ev
    assert "constant" in ev["reasons"][1], ev["reasons"]
    assert ev["also_seen"] == [], "it corroborates rather than sitting apart"

    # and a declaration that HOLDS changes nothing at all
    held = dict(VIOLATION, drift=0.001, within_tolerance=True)
    clean = {
        "declared_constants": {"rows": [held]},
        "misfit_evidence": {"open": False, "reasons": [], "signals": {}},
    }
    join(clean)
    assert clean["misfit_evidence"] == {
        "open": False,
        "reasons": [],
        "signals": {},
    }, clean["misfit_evidence"]
    print("  corroborates  reported alone, decisive only beside a hard signal")


def test_the_prose_says_it_was_a_decision() -> None:
    """The verdict prose is plain, and honest about what a note can do."""
    lines = dc.verdict_prose(SUMMARY)
    assert len(lines) == 2, lines
    first = lines[0]
    for piece in ("PreC + ProD", "26%", "c_u4_bx11", "10%", "preferred"):
        assert piece in first, f"{piece!r} missing from: {first}"
    assert "the precursor pool is fixed" in first, (
        "the note's own sentence must be quoted — a reader has to be able to "
        "check whether the declaration was transcribed right"
    )
    # nothing in the engine refuses a model for breaking a declaration, so the
    # wording must not promise a constraint that does not exist
    assert "not a constraint the engine enforces" in lines[1], lines[1]
    assert "scope gate" in lines[1], lines[1]
    assert dc.verdict_prose({"rows": []}) == [], "silent when nothing is violated"
    assert dc.verdict_prose({}) == [] and dc.verdict_prose(None) == []
    held = dict(VIOLATION, drift=0.001, within_tolerance=True)
    assert dc.verdict_prose({"rows": [held]}) == [], "silent when it holds"
    # the same sentence reaches the gate card, so the two surfaces cannot drift
    card = "\n".join(dc.card_lines([VIOLATION], where="at the fit"))
    assert dc.SCOPE_NOTE_EFFECT in card, card
    print("  prose         names the drift, quotes the note, and is honest")


def test_it_is_on_the_first_screen_of_both_documents() -> None:
    """Both reports state the contradiction above their verdict; a minimal round renders."""
    from octomod.reporting.analysis_report import build as build_analysis
    from octomod.reporting.analysis_report import render_html
    from octomod.reporting.round_report import render_report_html

    with temp_record("dc_first_screen") as root:  # the run is one record
        r0 = rnd(root, 0)
        core = {"declared_constants": SUMMARY}
        (r0 / "evaluation_core").put(core)
        (r0 / "evaluation").put(core)

        html = render_report_html(r0)
        pos = html.find('class="against"')
        assert pos > 0, "the round report says nothing about the contradiction"
        assert pos < html.find("Intent (frozen)"), (
            "the statement is below section 2 — the requirement is the FIRST "
            "screen, before anything else the reader might stop at"
        )
        assert "26%" in html and "preferred here" in html

        summary = build_analysis(root)
        run_html = render_html(summary)
        pos = run_html.find('class="against"')
        assert pos > 0, "ANALYSIS says nothing about the contradiction"
        from octomod.reporting.analysis_report import VERDICT_HEADING

        assert pos < run_html.find(VERDICT_HEADING), (
            "ANALYSIS states its answer before admitting the model breaks a "
            "declaration; a reader who stops at the answer never learns it"
        )

        # and a clean run must not carry the device at all
        for k in ("evaluation_core", "evaluation"):
            (r0 / k).put({"declared_constants": {"rows": []}})
        assert 'class="against"' not in render_report_html(r0)
        assert 'class="against"' not in render_html(build_analysis(root))
        print("  first screen  both documents state it above their own verdict")


def test_a_check_that_found_nothing_still_says_so() -> None:
    """A screen that found nothing says it ran, so "fine" reads apart from "not looked"."""
    sys.path.insert(0, str(REPO / "tests"))
    from report_budget_unit import fake_round, visible

    from octomod.reporting.round_report import _checks_that_ran

    held = dict(VIOLATION, within_tolerance=True, drift=0.0004)
    clean = visible(
        _checks_that_ran(
            fake_round(
                core={
                    "latent_states": {
                        "conditions_checked": 3,
                        "findings": [],
                        "conserved_totals": ["R + Rp"],
                    },
                    "declared_constants": {
                        "declared": 3,
                        "measured": 3,
                        "unmeasured": 0,
                        "violated": 0,
                        "worst_drift": 0.0004,
                        "rows": [held, held, held],
                    },
                }
            )
        )
    )
    assert "all 3 condition(s)" in clean, clean
    assert clean.count("PreC + ProD") == 1, (
        f"the expression is printed once per condition; a declaration is "
        f"measured per condition and the line must collapse them: {clean}"
    )
    assert "all 3 measurement(s)" in clean, clean
    assert "worst drift 0.0%" in clean and "10% tolerance" in clean, clean
    assert "never happened" in clean, (
        f"the block does not say why it exists, so its lines read as filler: "
        f"{clean[:160]}"
    )

    none_declared = visible(
        _checks_that_ran(
            fake_round(core={"declared_constants": {"declared": 0, "rows": []}})
        )
    )
    assert "none were declared" in none_declared, none_declared
    # and the GATE card still says nothing, which is the right answer there
    assert dc.card_lines([]) == []

    unmeasured = visible(
        _checks_that_ran(
            fake_round(
                core={
                    "declared_constants": {
                        "declared": 2,
                        "measured": 1,
                        "unmeasured": 1,
                        "violated": 0,
                        "worst_drift": 0.0,
                        "rows": [
                            dict(VIOLATION, within_tolerance=True, drift=0.0),
                            {"expression": "X + Y", "error": "could not simulate"},
                        ],
                    }
                }
            )
        )
    )
    assert "could not be measured" in unmeasured, unmeasured
    assert "empty measurement is not a pass" in unmeasured, unmeasured

    violated = visible(
        _checks_that_ran(fake_round(core={"declared_constants": SUMMARY}))
    )
    assert "contradict the note" in violated and "at the top" in violated, violated

    assert (
        _checks_that_ran(fake_round()) == ""
    ), "a round that ran neither screen must carry no block at all"
    print("  checks ran    both screens report their own absence, once each")


def test_the_engine_is_wired_to_it() -> None:
    """Source-text wiring; the behavioural halves are `golden_path` and the tests above."""
    s1 = (REPO / "octomod" / "workflow_modules" / "model" / "engine.py").read_text()
    assert "model_declared_constants" in s1
    assert (
        "blocking=False" in s1.split("model_declared_constants")[2]
    ), "the S1 gate must be ADVISORY: a flag, not a constraint"
    assert '"declared_constants": _dc.parse(construction)' in s1, (
        "the declaration must be persisted, or the fit cannot be measured "
        "against the same claim"
    )
    # the single-model scope card, the discrimination scope card, and the base
    # gate of a staged round
    assert s1.count("_dc.card_lines(") == 3, "every gate card should carry it"

    s7 = (
        REPO / "octomod" / "workflow_modules" / "evaluation" / "engine.py"
    ).read_text()
    assert "_declared_constants_at_fit" in s7 and "_join_declared_constants" in s7
    orch = (REPO / "octomod" / "orchestration" / "orchestrator.py").read_text()
    assert '"declared_constant_drift"' in orch, (
        "the expansion agent must be told, or it invents a law for the arm "
        "the drift would have explained"
    )
    contract = (REPO / "octomod" / "agents" / "__init__.py").read_text()
    assert "declared_constants" in contract and "quote the sentence" in contract
    stub = (REPO / "testcase" / "toy_phos" / "stubs" / "construction.json").read_text()
    assert (
        "declared_constants" in stub
    ), "one stub should exercise the whole path in the battery"
    print(
        "  wiring        S1 advisory gate, persisted, S7 at the fit, "
        "expansion payload"
    )


if __name__ == "__main__":
    test_a_conserved_pool_passes()
    test_an_open_sink_is_flagged_but_not_refused()
    test_the_declaration_is_read_forgivingly()
    test_a_violated_declaration_only_corroborates()
    test_the_prose_says_it_was_a_decision()
    test_it_is_on_the_first_screen_of_both_documents()
    test_a_check_that_found_nothing_still_says_so()
    test_the_engine_is_wired_to_it()
    print(
        "DECLARED CONSTANTS UNIT OK — the note is measured, the sink is "
        "flagged, and neither is refused"
    )
