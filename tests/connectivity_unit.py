"""The completeness check: no piece of the model unobserved, every input reaching an anchor.

On small models built from Antimony (`connectivity`):
  1. a connected chain passes, and the verdict counts species, reactions,
     pieces and inputs;
  2. a component with no anchor fails, naming its species, and blames the
     model; two components that each hold an anchor pass, named piece by piece;
  3. an anchor that is not a species of the model is named, and blames the readout;
  4. a species the rate law reads joins the graph although the SBML modifier
     list leaves it out, and it moves the reaction's reactant and product;
  5. a law that reads its product carries it back to the reactant; an
     irreversible one does not;
  6. a parameter input that reaches no anchor fails, naming what it reaches;
  7. a pure time series (no input) applies the component rule alone;
  8. a species with no reaction and no anchor is its own component, and
     fails; one whose reactions touch only itself is an unobserved piece;
  9. `input_species` maps a parameter to the species its laws, rules and
     initial assignments touch, a species to itself, an unknown id to nothing;
 10. an assignment rule defines a quantity and never joins two pieces: a
     rule-defined species stands for what its rule reads, declared as a
     species or a parameter alike, and an input its rule reads reaches it;
     a signalling piece and a drift piece summed into one count pass when
     the count is the anchor, and the drift fails when nothing reads it.
On an assembled toy problem through `make_petab_gates` (`assembly_connected`):
 11. the toy problem passes; a condition column that holds one value varies nothing;
 12. a second piece an observable reads passes, recorded and ledgered like
     every S3 gate; a piece no observable reads fails and routes to
     construction, which the assembly never re-asks: a candidate is dropped,
     a single model stops the module naming the model module;
 13. a varied quantity that reaches no readout routes to the condition
     encoding; an anchor the model does not have to the observation model.

    uv run python tests/connectivity_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import libsbml
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import RecordingLedger, check, finish  # noqa: E402
from _record import rnd, temp_record  # noqa: E402

from octomod.gates import HUMAN_LABELS, run_gate_set  # noqa: E402
from octomod.gates.build_gates import antimony_to_sbml  # noqa: E402
from octomod.gates.petab_gates import (  # noqa: E402
    PetabTables,
    make_petab_gates,
    varied_columns,
)
from octomod.orchestration.interaction import battery_feedback as bf  # noqa: E402
from octomod.orchestration.run_context import ModuleFailure  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import engine as assembly_module  # noqa: E402
from octomod.workflow_modules.assembly import petab_io  # noqa: E402
from octomod.workflow_modules.model import connectivity as cn  # noqa: E402

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
TOY = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"


def _sbml(body: str) -> str:
    sbml, err = antimony_to_sbml(f"model m\n{body}\nend")
    assert sbml, err
    return sbml


CHAIN = """
  species A, B, C;
  J1: A -> B; k1*A;
  J2: B -> C; k2*B;
  A = 1; B = 0; C = 0; k1 = 1; k2 = 1;
"""


def test_a_connected_chain_passes() -> None:
    sbml = _sbml(CHAIN)
    found = cn.problems(sbml, anchors={"C"}, inputs={"k1"})
    check("a connected chain has no problem", found == [], "; ".join(found))
    r = cn.model_result(sbml, {"C"}, {"k1"})
    check(
        "model_connected passes and counts species, reactions and inputs",
        r.gate_id == "model_connected"
        and r.tier == "T0"
        and r.passed
        and r.blocking
        and "3 species, 2 reactions; one piece, observed: {A, B, C}" in r.detail
        and "1 input(s), each reaching an anchor" in r.detail,
        r.detail,
    )
    g = cn.species_graph(sbml)
    check(
        "the graph: nodes, undirected edges, the directed relation, the reactions",
        g["species"] == ["A", "B", "C"]
        and g["edges"]["B"] == {"A", "C"}
        and g["directed"]["A"] == {"B"}
        and g["directed"]["C"] == set()
        and g["reactions"]["J1"]["law_refs"] == {"A"},
        str(g["directed"]),
    )
    check(
        "reaches: along the directed relation, never against it",
        cn.reaches(g, {"A", "C"}, {"A", "C"}) == {"A": {"A", "C"}, "C": {"C"}},
        str(cn.reaches(g, {"A", "C"}, {"A", "C"})),
    )


TWO = CHAIN + "  species X, Y;\n  J3: X -> Y; k3*X;\n  X = 1; Y = 0; k3 = 1;"


def test_an_unobserved_component_fails_and_observed_ones_pass() -> None:
    sbml = _sbml(TWO)
    comps = cn.components(cn.species_graph(sbml))
    check(
        "two components, largest first",
        comps == [{"A", "B", "C"}, {"X", "Y"}],
        str(comps),
    )
    found = cn.problems(sbml, anchors={"C"})
    check(
        "the component no anchor sees is named with its species",
        len(found) == 1
        and found[0].startswith("a piece of the model no readout sees: {X, Y}")
        and "invisible to the data" in found[0],
        "; ".join(found),
    )
    check(
        "… and blames the model, not a readout",
        cn.culprit(" | ".join(found)) == "model",
        str(cn.culprit(" | ".join(found))),
    )
    r = cn.assembly_result(sbml, {"C"}, set())
    check(
        "assembly_connected fails on it, blocking, at T0",
        r.gate_id == "assembly_connected"
        and r.tier == "T0"
        and not r.passed
        and r.blocking,
        r.detail,
    )
    both = cn.assembly_result(sbml, {"C", "Y"}, {"k1", "k3"})
    check(
        "two components that each hold an anchor pass, named piece by piece",
        both.passed
        and "2 pieces, each observed: {A, B, C} · {X, Y}" in both.detail
        and "2 input(s), each reaching an anchor" in both.detail,
        both.detail,
    )


def test_an_anchor_the_model_does_not_have_is_named() -> None:
    found = cn.problems(_sbml(TWO), anchors={"C", "Y", "Q"})
    joined = " | ".join(found)
    check(
        "an anchor that is not a species of the model is named, and nothing else",
        found == ["anchor not in the model: Q is not a species of the model"],
        joined,
    )
    check(
        "the finding blames the readout",
        cn.culprit(joined) == "readout",
        str(cn.culprit(joined)),
    )


def test_a_law_only_modifier_joins_the_graph() -> None:
    sbml = _sbml(
        "  species S, P, E;\n  J: S -> P; k*E*S;\n  S = 1; P = 0; E = 1; k = 1;"
    )
    doc = libsbml.readSBMLFromString(sbml)
    rx = doc.getModel().getReaction("J")
    while rx.getNumModifiers():
        rx.removeModifier(0)
    stripped = libsbml.writeSBMLToString(doc)
    check(
        "the SBML now lists no modifier",
        libsbml.readSBMLFromString(stripped)
        .getModel()
        .getReaction("J")
        .getNumModifiers()
        == 0,
    )
    g = cn.species_graph(stripped)
    check(
        "the species the law reads is a neighbour of reactant and product",
        g["edges"]["E"] == {"S", "P"} and g["reactions"]["J"]["law_refs"] == {"E", "S"},
        str(g["edges"]),
    )
    check(
        "… and moves both: the rate it sets consumes S and produces P",
        g["directed"]["E"] == {"S", "P"},
        str(g["directed"]["E"]),
    )
    check(
        "one component, no problem, E as the input reaching P",
        cn.problems(stripped, anchors={"P"}, inputs={"E"}) == [],
        "; ".join(cn.problems(stripped, anchors={"P"}, inputs={"E"})),
    )


def test_a_law_that_reads_its_product_carries_it_back() -> None:
    rev = cn.species_graph(
        _sbml(
            "  species A, B;\n  J: A -> B; kf*A - kr*B;\n  A = 1; B = 0; kf = 1; kr = 1;"
        )
    )
    irr = cn.species_graph(
        _sbml("  species A, B;\n  J: A => B; kf*A;\n  A = 1; B = 0; kf = 1;")
    )
    check(
        "a law that reads its product moves the reactant from the product",
        rev["directed"]["B"] == {"A"} and rev["directed"]["A"] == {"B"},
        str(rev["directed"]),
    )
    check(
        "an irreversible law does not",
        irr["directed"]["B"] == set() and irr["directed"]["A"] == {"B"},
        str(irr["directed"]),
    )


def test_an_input_that_reaches_no_readout_fails() -> None:
    sbml = _sbml(
        CHAIN
        + "  species W;\n  J3: C -> W; k3*C;\n  J4: W -> ; kd*W;\n  W = 0; k3 = 1; kd = 1;"
    )
    found = cn.problems(sbml, anchors={"C"}, inputs={"k1", "kd"})
    check(
        "the input that reaches no anchor is named with what it reaches",
        len(found) == 1
        and "input reaches no anchor: kd moves {W}" in found[0]
        and "{C}" in found[0],
        "; ".join(found),
    )
    check(
        "… and blames the input",
        cn.culprit(found[0]) == "input",
        str(cn.culprit(found[0] if found else "")),
    )
    unknown = cn.problems(sbml, anchors={"C"}, inputs={"nope"})
    check(
        "an input the model does not have is named",
        unknown == ["input not in the model: nope is not an id of the model"],
        "; ".join(unknown),
    )
    sbml2 = _sbml(CHAIN + "  u = 1;")
    idle2 = cn.problems(sbml2, anchors={"C"}, inputs={"u"})
    check(
        "a parameter no rate law, rule or event reads moves nothing",
        len(idle2) == 1 and "input moves nothing: u" in idle2[0],
        "; ".join(idle2),
    )


def test_a_pure_time_series_applies_the_component_rule_alone() -> None:
    sbml = _sbml(
        CHAIN
        + "  species W;\n  J3: C -> W; k3*C;\n  J4: W -> ; kd*W;\n  W = 0; k3 = 1; kd = 1;"
    )
    check(
        "no inputs: the component rule alone, and it holds",
        cn.problems(sbml, anchors={"C"}) == []
        and cn.problems(sbml, anchors={"C"}, inputs=set()) == [],
    )
    r = cn.assembly_result(sbml, {"C"}, set())
    check(
        "the verdict says so",
        r.passed and "the component rule alone" in r.detail,
        r.detail,
    )
    split = _sbml(CHAIN + "  species X;\n  X = 0;")
    check(
        "… and the component rule still fails a split model",
        len(cn.problems(split, anchors={"C"})) == 1,
    )


def test_a_species_with_no_reaction_is_its_own_component() -> None:
    sbml = _sbml(CHAIN + "  species Z;\n  Z = 0;")
    comps = cn.components(cn.species_graph(sbml))
    found = cn.problems(sbml, anchors={"C"})
    check(
        "a species with no reaction is a component of its own",
        {"Z"} in comps and len(comps) == 2,
        str(comps),
    )
    check(
        "… and fails, named as taking part in nothing",
        found
        == [
            "a piece of the model no readout sees: species Z takes part in no "
            "reaction, rate rule or event — connect it to the model or remove it"
        ],
        "; ".join(found),
    )
    # a species with a synthesis and a decay of its own is a piece, not idle
    drift = _sbml(
        CHAIN
        + "  species D;\n  Jin: -> D; a;\n  Jout: D -> ; kd*D;\n  D = 0; a = 1; kd = 1;"
    )
    lone = cn.problems(drift, anchors={"C"})
    check(
        "a species whose reactions touch only itself is an unobserved piece, said so",
        len(lone) == 1
        and "no readout sees: {D} — its parameters are invisible" in lone[0],
        "; ".join(lone),
    )


def test_input_species_maps_a_parameter_to_what_its_laws_touch() -> None:
    sbml = _sbml(
        """
  species A, B, C, R;
  J1: A -> B; k_eff*A;
  J2: B -> C; k2*B*E;
  k_eff := k*u;
  R = R0;
  J3: R -> ; kr*R;
  A = 1; B = 0; C = 0; k = 1; u = 1; k2 = 1; E = 1; R0 = 2; kr = 1;
"""
    )
    got = cn.input_species(sbml, {"u", "k2", "R0", "A", "none"})
    check(
        "a parameter maps to the species its rate laws change (through an "
        "assignment rule, an initial assignment); a species to itself; an "
        "unknown id to nothing",
        got
        == {
            "u": {"A", "B"},
            "k2": {"B", "C"},
            "R0": {"R"},
            "A": {"A"},
            "none": set(),
        },
        str(got),
    )


def test_an_assignment_rule_defines_and_never_joins() -> None:
    sbml = _sbml(CHAIN + "  species T;\n  T := A + C;")
    g = cn.species_graph(sbml)
    check(
        "a species an assignment rule defines is no node: it stands for the "
        "species its rule reads",
        "T" not in g["species"]
        and g["derived"] == {"T": {"A", "C"}}
        and cn.problems(sbml, anchors={"T"}) == [],
        f"{g['species']} / {g['derived']}",
    )
    ruled = _sbml(CHAIN + "  total := A + C;")
    reads = cn.formula_reads(ruled, "sc_obs * total + observableParameter1_obs")
    check(
        "an observable formula reads through the model's rules, species or "
        "parameter; PEtab-only ids drop out",
        reads == {"total", "A", "C"}
        and cn.formula_reads(sbml, "sc_obs * T") == {"T", "A", "C"},
        f"{sorted(reads)} / {sorted(cn.formula_reads(sbml, 'sc_obs * T'))}",
    )
    # a readout that sums the network and a state of its own (a drift): the
    # rule does not join them, whichever way its variable is declared, and
    # both pieces are observed through it
    drift = (
        "  species D;\n  Jin: -> D; a;\n  Jout: D -> ; kd*D;\n  D = 0; a = 1; kd = 1;\n"
    )
    as_param = _sbml(CHAIN + drift + "  count := C + D;")
    as_species = _sbml(CHAIN + drift + "  species count;\n  count := C + D;")
    p1 = cn.model_result(as_param, {"count"}, set())
    p2 = cn.model_result(as_species, {"count"}, set())
    check(
        "a readout rule summing two pieces observes both, declared as a "
        "parameter or as a species, and joins neither",
        p1.passed
        and p2.passed
        and "2 pieces, each observed: {A, B, C} · {D}" in p1.detail
        and p1.detail == p2.detail,
        f"{p1.detail} / {p2.detail}",
    )
    scaled = _sbml(CHAIN + "  species Tu;\n  Tu := u*C;\n  u = 1;")
    check(
        "an input read by an anchor's own rule reaches that anchor",
        cn.problems(scaled, anchors={"Tu"}, inputs={"u"}) == [],
        "; ".join(cn.problems(scaled, anchors={"Tu"}, inputs={"u"})),
    )


# a signalling piece and a readout drift with its own synthesis and decay,
# summed into one count by an assignment rule
SIGNAL_AND_DRIFT = """
  species X, Xp, D1;
  J1: X -> Xp; k1*u*X;
  J2: Xp -> X; k2*Xp;
  Jdrift_in: -> D1; a_drift / tau_drift;
  Jdrift_out: D1 -> ; D1 / tau_drift;
  count := bg + Xp + D1;
  X = 1; Xp = 0; D1 = 0; k1 = 1; k2 = 1; u = 1; bg = 0.1;
  a_drift = 1; tau_drift = 10;
"""


def test_a_drift_summed_into_the_readout_is_observed() -> None:
    sbml = _sbml(SIGNAL_AND_DRIFT)
    anchors = cn.formula_reads(sbml, "log(count/5 + sqrt(1 + count*count/25))")
    anchors &= set(cn.species_graph(sbml)["species"])
    r = cn.assembly_result(sbml, anchors, {"u"})
    check(
        "the count's species are the anchors: the signalling piece and the "
        "drift piece both pass, and the input reaches the readout",
        anchors == {"Xp", "D1"}
        and r.passed
        and "2 pieces, each observed: {X, Xp} · {D1}" in r.detail
        and "1 input(s), each reaching an anchor" in r.detail,
        r.detail,
    )
    unread = cn.problems(sbml, anchors={"Xp"}, inputs={"u"})
    check(
        "a drift no readout reads fails, named by its species",
        unread
        == [
            "a piece of the model no readout sees: {D1} — its parameters are "
            "invisible to the data; connect it to an observed piece, observe it, "
            "or remove it"
        ],
        "; ".join(unread),
    )


# -- the assembly: `assembly_connected` in the S3 battery -------------------------

TOY_MODEL = """
  species R, Rp;
  J1: R -> Rp; k_phos*S*R;
  J2: Rp -> R; k_dephos*Rp;
  R = 1; Rp = 0; S = 1; k_phos = 0.02; k_dephos = 0.2;
"""


def _toy(extra_model: str = "", *, observables=None, conditions=None) -> PetabTables:
    inp = petab_io.from_dir(TOY)
    return PetabTables(
        observables=observables if observables is not None else inp.observables,
        conditions=conditions if conditions is not None else inp.conditions,
        measurements=inp.measurements,
        parameters=inp.parameters,
        sbml=_sbml(TOY_MODEL + extra_model),
    )


def _battery(
    tables: PetabTables, gates_dir
) -> tuple[bool, dict, RecordingLedger, list]:
    ledger = RecordingLedger()
    ok, results = run_gate_set(
        make_petab_gates(tables, SPEC), gates_dir, ledger, "assembly"
    )
    return ok, {r.gate_id: r for r in results}, ledger, results


def test_the_toy_problem_passes_and_constant_columns_vary_nothing() -> None:
    with temp_record() as root:
        ok, res, _, _ = _battery(_toy(), rnd(root, 0) / "gates")
    r = res.get("assembly_connected")
    check(
        "the toy problem passes the S3 battery, assembly_connected among it",
        ok and r is not None and r.passed and "1 input(s), each reaching" in r.detail,
        r.detail if r else "not run",
    )
    cond = pd.DataFrame(
        {
            "conditionId": ["a", "b", "preeq_a"],
            "S": [1.0, "1", 1],
            "k_dephos": [0.2, 0.2, 0.5],
            "R": [None, None, 3.0],
        }
    )
    check(
        "a column holding one value varies nothing; a pre-equilibration row "
        "that sets a quantity differently varies it",
        varied_columns(cond) == ["k_dephos", "R"],
        str(varied_columns(cond)),
    )


def test_observed_pieces_pass_and_an_unobserved_one_is_the_models() -> None:
    obs = pd.concat(
        [
            petab_io.from_dir(TOY).observables,
            pd.DataFrame(
                [
                    {
                        "observableId": "obs_y",
                        "observableFormula": "Y",
                        "observableTransformation": "lin",
                        "noiseFormula": "sigma_obs_pR",
                        "noiseDistribution": "normal",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    second = "  species X, Y;\n  J3: X -> Y; k3*X;\n  X = 1; Y = 0; k3 = 1;"
    with temp_record() as root:
        gates = rnd(root, 0) / "gates"
        ok, res, ledger, _ = _battery(_toy(second, observables=obs), gates)
        stored = (gates / "assembly_connected").get(None)
    r = res.get("assembly_connected")
    check(
        "a second piece an observable reads passes, each piece named",
        ok
        and r is not None
        and r.passed
        and "2 pieces, each observed: {R, Rp} · {X, Y}" in r.detail,
        r.detail if r else "not run",
    )
    rows = [x for x in ledger.rows if x.get("gate_id") == "assembly_connected"]
    check(
        "recorded under the round's gates and ledgered as a gate row, like every S3 gate",
        stored is not None
        and stored.get("passed") is True
        and len(rows) == 1
        and rows[0]["event"] == "gate"
        and rows[0]["module"] == "assembly"
        and rows[0]["tier"] == "T0",
        str(rows),
    )
    with temp_record() as root:
        gates = rnd(root, 0) / "gates"
        ok, res, ledger, results = _battery(_toy(second), gates)
        stored = (gates / "assembly_connected").get(None)
    r = res.get("assembly_connected")
    check(
        "the same piece with no observable reading it fails assembly_connected, "
        "blocks the battery and is named by its species",
        not ok
        and r is not None
        and not r.passed
        and results[-1].gate_id == "assembly_connected"
        and "a piece of the model no readout sees: {X, Y}" in r.detail,
        r.detail if r else "not run",
    )
    check(
        "… recorded and ledgered as failed",
        stored is not None
        and stored.get("passed") is False
        and [
            x["passed"] for x in ledger.rows if x.get("gate_id") == "assembly_connected"
        ]
        == [False],
    )
    role, failing = bf.attribute(results)
    check(
        "attributed to construction: the piece is the model's",
        role == "construction" and failing[0].gate_id == "assembly_connected",
        str(role),
    )
    unknown = cn.assembly_result(_sbml(TOY_MODEL), {"Rp", "Q"}, set())
    check(
        "an anchor the model does not have routes to the observation model",
        not unknown.passed and bf.role_for(unknown) == "observation",
        f"{unknown.detail} → {bf.role_for(unknown)}",
    )


def test_an_unreached_input_and_a_stray_species_route_as_declared() -> None:
    cond = petab_io.from_dir(TOY).conditions.copy()
    cond["kd"] = [0.1 * (k + 1) for k in range(len(cond))]
    tables = _toy(
        "  species W;\n  J3: Rp -> W; k3*Rp;\n  J4: W -> ; kd*W;\n  W = 0; k3 = 1; kd = 1;",
        conditions=cond,
    )
    with temp_record() as root:
        ok, res, _, results = _battery(tables, rnd(root, 0) / "gates")
    r = res.get("assembly_connected")
    check(
        "a varied quantity that reaches no readout fails, naming what it moves",
        not ok
        and r is not None
        and "input reaches no anchor: kd moves {W}" in r.detail,
        r.detail if r else "not run",
    )
    check(
        "… and routes to the condition encoding",
        bf.attribute(results)[0] == "condition",
        str(bf.attribute(results)[0]),
    )
    stray = _toy("  species Z;\n  Z = 0;")
    with temp_record() as root:
        ok, res, _, results = _battery(stray, rnd(root, 0) / "gates")
    r = res.get("assembly_connected")
    check(
        "a species with no reaction and no readout routes to construction",
        not ok and r is not None and bf.attribute(results)[0] == "construction",
        (r.detail if r else "not run") + f" → {bf.attribute(results)[0]}",
    )
    check(
        "construction is upstream of the assembly: never among the roles it re-asks",
        "construction" not in bf.ASSEMBLY_ROLES,
    )
    ledger = RecordingLedger()
    single = SimpleNamespace(candidate=None, ledger=ledger, round_idx=0, gates=None)
    try:
        assembly_module._upstream_defect(single, "construction", r, results)
        stopped = ""
    except assembly_module.CandidateDefect:
        stopped = "dropped"
    except ModuleFailure as e:
        stopped = str(e)
    check(
        "a single model stops the module, naming the model module to re-enter",
        "--from-module model" in stopped and "assembly_connected" in stopped,
        stopped[:300],
    )
    cand = SimpleNamespace(candidate="c1", ledger=ledger, round_idx=0, gates=None)
    try:
        assembly_module._upstream_defect(cand, "construction", r, results)
        dropped = None
    except assembly_module.CandidateDefect as e:
        dropped = e
    check(
        "a candidate is dropped instead, with the reason",
        dropped is not None
        and dropped.candidate == "c1"
        and "blames the model itself" in dropped.reason,
        str(dropped),
    )
    check(
        "both are ledgered as notes naming the role and the check",
        [(x["event"], x["role"], x["gate_id"]) for x in ledger.rows]
        == [("note", "construction", "assembly_connected")] * 2,
        str(ledger.rows),
    )


def test_both_gates_are_labelled() -> None:
    check(
        "both gate ids carry a plain label",
        "model_connected" in HUMAN_LABELS and "assembly_connected" in HUMAN_LABELS,
    )


def main() -> int:
    test_a_connected_chain_passes()
    test_an_unobserved_component_fails_and_observed_ones_pass()
    test_an_anchor_the_model_does_not_have_is_named()
    test_a_law_only_modifier_joins_the_graph()
    test_a_law_that_reads_its_product_carries_it_back()
    test_an_input_that_reaches_no_readout_fails()
    test_a_pure_time_series_applies_the_component_rule_alone()
    test_a_species_with_no_reaction_is_its_own_component()
    test_input_species_maps_a_parameter_to_what_its_laws_touch()
    test_an_assignment_rule_defines_and_never_joins()
    test_a_drift_summed_into_the_readout_is_observed()
    test_the_toy_problem_passes_and_constant_columns_vary_nothing()
    test_observed_pieces_pass_and_an_unobserved_one_is_the_models()
    test_an_unreached_input_and_a_stray_species_route_as_declared()
    test_both_gates_are_labelled()
    return finish(
        "CONNECTED",
        "CONNECTED OK — no piece unobserved, every input reaching an anchor; "
        "S3 failures routed to the part that caused them",
    )


if __name__ == "__main__":
    sys.exit(main())
