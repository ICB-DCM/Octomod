"""The checks on states nobody measured, run at the MLE on models built to break them.

  1. a negative state: a species driven below zero by its own rate law;
  2. an exceeded total: a "conserved" pool the model actually leaks;
  3. a declared range: the one HARD check, because the intent asked for it;
  4. every condition is screened, and a finding names the condition behind it;
  5. nothing checked is not nothing found: a failed simulation is an ERRORED row;
  6. the card shows at most four findings, counts the rest, labels hard and advisory.

    uv run python tests/latent_states_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod.gates.build_gates import antimony_to_sbml  # noqa: E402
from octomod.workflow_modules.evaluation import latent_states  # noqa: E402


def sbml(src: str) -> str:
    out, err = antimony_to_sbml(src)
    assert out, f"the fixture model does not build: {err}"
    return out


# Three models over one skeleton: A <-> B in a unit compartment. Only what is
# added to it differs, so each check is compared against the same dynamics
# rather than against an unrelated model.
SKELETON = """
model {name}
  compartment cell = 1;
  species A in cell = 1.0;
  species B in cell = 0.5;
  J1: A -> B; k1 * A;
  J2: B -> A; k2 * B;
{extra}  k1 = 0.5;
  k2 = 0.2;
end
"""

# A constant negative influx: dB/dt = -sink, so B crosses zero at t = 0.5/sink
# and keeps going (a rate proportional to B would only decay TOWARDS zero).
LEAVES_DOMAIN = SKELETON.format(
    name="leaves_domain", extra="  J4: -> B; -sink;\n  sink = 0.0;\n"
)
# A <-> B and nothing else, so `A + B` is a structural moiety.
CONSERVED = SKELETON.format(name="conserved", extra="")
# The same stoichiometry (so the moiety is still DECLARED conserved) plus an
# event that adds to B outside the reaction network.
BREAKS_ITS_TOTAL = SKELETON.format(
    name="breaks_its_total", extra="  at (time > 5): B = B + 1;\n"
)


def test_a_negative_state_is_found_and_named() -> None:
    model = sbml(LEAVES_DOMAIN)
    quiet = latent_states.screen(
        model, t_end=10.0, conditions={"c0": {}}, best={"k1": 0.5, "k2": 0.2}
    )
    check(
        "the control model is clean, so a finding below means something",
        quiet["findings"] == [] and quiet["conditions_checked"] == 1,
        str(quiet["findings"])[:160],
    )

    loud = latent_states.screen(
        model,
        t_end=10.0,
        conditions={"c0": {}},
        best={"k1": 0.0, "k2": 0.0, "sink": 1.0},
    )
    negs = [f for f in loud["findings"] if f["kind"] == "negative_state"]
    check(
        "a state driven below zero is found",
        len(negs) == 1,
        f"{[f['kind'] for f in loud['findings']]}",
    )
    if negs:
        f = negs[0]
        check(
            "and it names the state, the condition and how far it went",
            f["state"] == "B" and f["condition"] == "c0" and f["value"] < -1.0,
            f"{f['state']} @ {f['condition']} = {f['value']:.3g}",
        )
        check(
            "as ADVISORY — a screen is not a verdict",
            f["hard"] is False and not loud["hard_failures"],
            f"hard={f['hard']}",
        )
        check(
            "and the detail says what it means, not just the number",
            "physical domain" in f["detail"],
            f["detail"][:100],
        )


def test_a_moved_total_is_found() -> None:
    """A total the stoichiometry declares conserved is found moving at the fit."""
    clean = latent_states.screen(
        sbml(CONSERVED), t_end=10.0, conditions={"c0": {}}, best={"k1": 0.5, "k2": 0.2}
    )
    check(
        "a genuinely conserved pool is detected as a structural total",
        clean["conserved_totals"] == ["A + B"],
        f"totals: {clean['conserved_totals']}",
    )
    check(
        "and it does not drift at the fit, so nothing is reported",
        clean["findings"] == [],
        str(clean["findings"])[:140],
    )

    broken = latent_states.screen(
        sbml(BREAKS_ITS_TOTAL),
        t_end=10.0,
        conditions={"c0": {}},
        best={"k1": 0.5, "k2": 0.2},
    )
    check(
        "the same total is still DECLARED conserved once the event is added",
        broken["conserved_totals"] == ["A + B"],
        f"totals: {broken['conserved_totals']}",
    )
    moved = [f for f in broken["findings"] if f["kind"] == "conservation"]
    check(
        "and the screen reports that it moves at the fit",
        len(moved) == 1 and moved[0]["value"] > 0.5,
        f"{[(f['kind'], round(f.get('value', 0), 3)) for f in broken['findings']]}",
    )
    if moved:
        check(
            "naming the total, and both explanations a reader must weigh",
            moved[0]["state"] == "A + B"
            and "integration error" in moved[0]["detail"]
            and "stoichiometry the fit exploits" in moved[0]["detail"],
            moved[0]["detail"][:120],
        )
        check(
            "advisory: a drifting total is a diagnosis, not a refusal",
            moved[0]["hard"] is False and broken["hard_failures"] == [],
        )


def test_a_declared_range_is_the_one_hard_check() -> None:
    model = sbml(CONSERVED)
    within = latent_states.screen(
        model,
        t_end=10.0,
        conditions={"c0": {}},
        best={"k1": 0.5, "k2": 0.2},
        ranges={"B": [0.0, 10.0]},
    )
    check(
        "a state inside its declared range is not reported",
        within["findings"] == [],
        str(within["findings"])[:140],
    )
    outside = latent_states.screen(
        model,
        t_end=10.0,
        conditions={"c0": {}},
        best={"k1": 0.5, "k2": 0.2},
        ranges={"B": [0.0, 0.2]},
    )
    ranged = [f for f in outside["findings"] if f["kind"] == "declared_range"]
    check("a state outside its declared range is found", len(ranged) == 1, str(ranged))
    if ranged:
        check(
            "and it is HARD, because the intent asked for this one",
            ranged[0]["hard"] is True and outside["hard_failures"] == ranged,
            f"hard={ranged[0]['hard']}, hard_failures={len(outside['hard_failures'])}",
        )
        check(
            "the detail quotes the range it broke",
            "outside the declared [0, 0.2]" in ranged[0]["detail"],
            ranged[0]["detail"][:120],
        )
    check(
        "the declared ranges are echoed in the record, so a reader can check "
        "what was asked",
        outside["declared_ranges"] == {"B": [0.0, 0.2]},
        str(outside["declared_ranges"]),
    )
    # a range naming something the model has no state for is skipped, not an error
    unknown = latent_states.screen(
        model,
        t_end=10.0,
        conditions={"c0": {}},
        best={"k1": 0.5},
        ranges={"NoSuchSpecies": [0.0, 1.0]},
    )
    check(
        "a range on a state the model does not have is skipped silently",
        unknown["findings"] == [] and unknown["conditions_checked"] == 1,
        str(unknown["findings"])[:120],
    )


def test_every_condition_is_screened_not_just_the_first() -> None:
    res = latent_states.screen(
        sbml(LEAVES_DOMAIN),
        t_end=10.0,
        conditions={"c_quiet": {"sink": 0.0}, "c_loud": {"sink": 1.0}},
        best={"k1": 0.0, "k2": 0.0},
    )
    check(
        "both conditions are simulated",
        res["conditions_checked"] == 2,
        str(res["conditions_checked"]),
    )
    conds = {f["condition"] for f in res["findings"]}
    check(
        "the finding is attributed to the condition that produced it",
        conds == {"c_loud"},
        f"conditions with findings: {sorted(conds)}",
    )


def test_nothing_checked_is_not_nothing_found() -> None:
    """A screen that could not run must not read as a screen that passed."""
    broken = latent_states.screen(
        sbml(CONSERVED),
        t_end=10.0,
        conditions={"c0": {"nonexistent_parameter": 1.0}},
        best={"k1": 0.5},
    )
    check(
        "a simulation that fails is an ERRORED row, not a finding of plausibility",
        broken["conditions_checked"] == 0
        and [f["kind"] for f in broken["findings"]] == ["simulation"],
        f"checked={broken['conditions_checked']}, "
        f"{[f['kind'] for f in broken['findings']]}",
    )
    check(
        "and it is advisory, so a broken simulation cannot fail a run",
        broken["hard_failures"] == [],
    )
    check(
        "the card says NOTHING when nothing was checked — a reassurance nobody "
        "earned is worse than silence",
        latent_states.card_lines({"conditions_checked": 0, "findings": []}) == [],
    )
    lines = latent_states.card_lines(
        {"conditions_checked": 5, "findings": [], "conserved_totals": ["A + B"]}
    )
    check(
        "and it says the check RAN when it did, with the count (review note #10)",
        len(lines) == 1
        and "all 5 condition(s)" in lines[0]
        and "1 structural" in lines[0],
        str(lines),
    )


def test_the_card_ranks_and_caps() -> None:
    many = {
        "conditions_checked": 3,
        "findings": [
            {"condition": f"c{i}", "detail": f"finding {i}", "hard": i == 0}
            for i in range(7)
        ],
    }
    lines = latent_states.card_lines(many)
    check(
        "at most four findings on the card, and the rest are counted",
        len(lines) == 6 and "3 more" in lines[-1],
        f"{len(lines)} lines: {lines[-1]}",
    )
    check(
        "a hard finding says the intent declared it",
        "HARD (the intent declared this range)" in lines[1],
        lines[1],
    )
    check(
        "an advisory one says so too, so the two never read alike",
        "(advisory)" in lines[2],
        lines[2],
    )


def main() -> int:
    print("latent states at the MLE — each check against a model built to break it\n")
    test_a_negative_state_is_found_and_named()
    test_a_moved_total_is_found()
    test_a_declared_range_is_the_one_hard_check()
    test_every_condition_is_screened_not_just_the_first()
    test_nothing_checked_is_not_nothing_found()
    test_the_card_ranks_and_caps()

    print()
    return finish(
        "LATENT STATES",
        "LATENT STATES OK — each check fires on a model built to break it, and "
        "a screen that could not run never reads as one that passed",
    )


if __name__ == "__main__":
    raise SystemExit(main())
