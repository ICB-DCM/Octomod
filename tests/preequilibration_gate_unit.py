"""Pre-equilibration, from the condition encoding's declaration to AMICI's report.

The condition-encoding agent declares a pre-equilibration condition as a dict
of overrides on the measured conditions it applies to; the engine renders the
rows and the column, S3 screens the steady state, AMICI runs it at the probe.

A supplied problem (the toy problem's tables, with pre-equilibration added):
  1. a pre-equilibration condition that relaxes passes `assembly_preequilibration`,
     and a leaky condition nobody pre-equilibrates on is not probed;
  2. one that never settles fails it, blocks the battery, and is named;
  3. a pre-equilibration id the conditions table lacks is refused at
     `assembly_measurements_resolve`, before anything integrates;
  4. no column, or an empty one, is skipped and says so.
The engine's own rendering (the toy assembly, merged as S3 merges it):
  5. a dict renders a `preeq_<condition>` row (the measured row with the dict on
     top) and the column on exactly that condition's rows, training and
     held-out; the ledger and the compile card name what was rendered;
  6. a bare `true`, another truthy value or an empty dict is refused at the
     conditions merge by name, and goes back to the condition-encoding agent;
  7. a dict key that is not a model entity fails `assembly_conditions_resolve`;
  8. a search axis may not change a measured condition's declaration;
  9. the roadrunner simulations S3 and S7 read start a pre-equilibrated
     condition, held-out ones included, from its steady state, and re-set a
     species the condition itself sets; a species override neither reverts a
     parameter override nor leaks into the next simulation;
 10. the fit fingerprint moves when a problem gains pre-equilibration, and a
     partly blank column is not read as timepoint-specific;
 11. the construction agent's optional `basal_state` reaches the
     condition-encoding payload;
End to end, token-free (the stub CLI on a copy of toy_phos):
 12. the compile card and the ledger name the rendered rows and the gate
     passed; the probe reports AMICI's steady state per pre-equilibrated
     condition on the budget card; AMICI and roadrunner agree on where each
     condition starts; the declared steady-state settings reach the solver
     and the model.

    uv run python tests/preequilibration_gate_unit.py
"""

from __future__ import annotations

import atexit
import copy
import json
import logging
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

import libsbml
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.WARNING)
# the end-to-end check runs the CLI in this process; `runs/` is the user's
if not os.environ.get("OCTOMOD_RUNS_DIR"):
    os.environ["OCTOMOD_RUNS_DIR"] = tempfile.mkdtemp(prefix="preeq_runs_")
    atexit.register(shutil.rmtree, os.environ["OCTOMOD_RUNS_DIR"], True)

from _harness import RecordingLedger, check, finish, run_cli_captured  # noqa: E402
from _record import (  # noqa: E402
    ledger_rows,
    pending_gate,
    record_at,
    rnd,
    run_root,
    work,
)

from octomod import config  # noqa: E402
from octomod.gates import run_gate_set  # noqa: E402
from octomod.gates.build_gates import antimony_to_sbml  # noqa: E402
from octomod.gates.petab_gates import PetabTables, make_petab_gates  # noqa: E402
from octomod.orchestration.interaction import battery_feedback  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import assembly_edit, petab_io  # noqa: E402
from octomod.workflow_modules.assembly import engine as assembly_module  # noqa: E402

SOURCE = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"
SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
GATE = "assembly_preequilibration"

# The toy cycle R <-> Rp conserves R + Rp, so no override of its own
# parameters can keep it from settling. The copy gains a constant synthesis
# of R (zero at nominal): with it switched on and nothing degrading R, the
# total grows linearly and never reaches a steady state.
BASAL = "pre_basal"  # a weak stimulus the cycle relaxes under
LEAK = "pre_leak"  # synthesis on, no degradation: unbounded


def _stage(root: Path) -> Path:
    """The toy problem, copied, with a synthesis leg and two pre-eq conditions."""
    petab_dir = root / "petab"
    shutil.copytree(SOURCE, petab_dir)
    doc = libsbml.readSBMLFromString((petab_dir / "model.xml").read_text())
    model = doc.getModel()
    k_syn = model.createParameter()
    k_syn.setId("k_syn")
    k_syn.setValue(0.0)
    k_syn.setConstant(True)
    rxn = model.createReaction()
    rxn.setId("J0")
    rxn.setReversible(False)
    prod = rxn.createProduct()
    prod.setSpecies("R")
    prod.setStoichiometry(1.0)
    prod.setConstant(True)
    rxn.createKineticLaw().setMath(libsbml.parseL3Formula("k_syn"))
    (petab_dir / "model.xml").write_text(libsbml.writeSBMLToString(doc))

    cond = pd.read_csv(petab_dir / "conditions.tsv", sep="\t")
    cond["k_syn"] = 0.0
    cond = pd.concat(
        [
            cond,
            pd.DataFrame(
                [
                    {"conditionId": BASAL, "S": 0.1, "k_syn": 0.0},
                    {"conditionId": LEAK, "S": 0.1, "k_syn": 0.1},
                ]
            ),
        ],
        ignore_index=True,
    )
    cond.to_csv(petab_dir / "conditions.tsv", sep="\t", index=False)
    return petab_dir


def _measurements(petab_dir: Path, preeq: dict[str, str] | None) -> None:
    """Rewrite the measurement table: `preeq` maps a simulation condition to
    its pre-equilibration condition; None drops the column."""
    meas = pd.read_csv(petab_dir / "measurements.tsv", sep="\t")
    meas = meas.drop(columns=["preequilibrationConditionId"], errors="ignore")
    if preeq is not None:
        meas["preequilibrationConditionId"] = (
            meas["simulationConditionId"].map(preeq).astype(object)
        )
    meas.to_csv(petab_dir / "measurements.tsv", sep="\t", index=False)


def _record(where: Path) -> Node:
    """A record at `where/run.h5` (created once): the verdicts and the
    engine's rendering live in a run record, never in a directory."""
    root = record_at(where / "run.h5")
    if not root.store.exists_on_disk():
        root.store.create()
    return root


def _gates(where: Path) -> Node:
    """Where the module leaves the battery's verdicts: a round's `gates` group."""
    return rnd(_record(where), 0) / "gates"


def _battery(petab_dir: Path, gates_dir: Node):
    """The S3 battery over the supplied problem (a PEtab problem on disk, as a
    user supplies it), run as the module runs it, verdicts into the record."""
    tables = PetabTables.from_input(petab_io.from_dir(petab_dir))
    ledger = RecordingLedger()
    ok, results = run_gate_set(
        make_petab_gates(tables, SPEC), gates_dir, ledger, "assembly"
    )
    return ok, {r.gate_id: r for r in results}, ledger


def test_a_relaxing_condition_passes(root: Path) -> None:
    petab_dir = _stage(root / "relax")
    _measurements(petab_dir, {c: BASAL for c in ("dose_0p3", "dose_1", "dose_3")})
    ok, res, ledger = _battery(petab_dir, _gates(root / "relax"))
    r = res.get(GATE)
    check(
        "a pre-equilibration condition that relaxes passes the gate",
        r is not None
        and r.passed
        and r.detail == "all pre-equilibration conditions reach steady state",
        f"{r.passed if r else 'not run'}: {r.detail if r else sorted(res)}",
    )
    check(
        "a leaky condition in the table that no measurement pre-equilibrates "
        "on is not probed, and the battery passes",
        ok and LEAK not in str(r.detail if r else ""),
        f"ok={ok}",
    )
    row = next(
        (x for x in ledger.rows if x["event"] == "gate" and x["gate_id"] == GATE),
        None,
    )
    check(
        "the verdict is ledgered with the integrator settings it was reached at",
        row is not None
        and row["passed"]
        and (row.get("solver_settings") or {}).get("solver") == "roadrunner/cvode",
        str(row.get("solver_settings") if row else "no gate row"),
    )


def test_a_condition_that_never_settles_fails_by_name(root: Path) -> None:
    petab_dir = _stage(root / "leak")
    _measurements(petab_dir, {"dose_0p3": BASAL, "dose_1": BASAL, "dose_3": LEAK})
    gates_dir = _gates(root / "leak")
    ok, res, _ledger = _battery(petab_dir, gates_dir)
    r = res.get(GATE)
    check(
        "a pre-equilibration condition that never settles fails the gate",
        r is not None and not r.passed,
        f"{r.passed if r else 'not run'}: {r.detail if r else sorted(res)}",
    )
    detail = str(r.detail if r else "")
    check(
        "and the failure names that condition, with its residual, and only it",
        f"{LEAK}: no steady state (residual" in detail and BASAL not in detail,
        detail,
    )
    check(
        "the failure blocks the S3 battery (T1, blocking)",
        (not ok) and r is not None and r.blocking and r.tier == "T1",
        f"ok={ok} blocking={r.blocking if r else None} tier={r.tier if r else None}",
    )
    check(
        "the failed verdict is in the record under gates/, where the module leaves it",
        gates_dir.child(GATE).exists()
        and (gates_dir.child(GATE).get() or {}).get("passed") is False,
        str(gates_dir.children()),
    )


def test_an_undeclared_preequilibration_id_is_refused(root: Path) -> None:
    petab_dir = _stage(root / "undeclared")
    _measurements(petab_dir, {c: "pre_nowhere" for c in ("dose_0p3", "dose_1")})
    ok, res, _ledger = _battery(petab_dir, _gates(root / "undeclared"))
    r = res.get("assembly_measurements_resolve")
    check(
        "a pre-equilibration id the conditions table lacks is refused, by name, "
        "before anything integrates",
        (not ok)
        and r is not None
        and not r.passed
        and "undeclared pre-equilibration conditions ['pre_nowhere']" in r.detail
        and GATE not in res,
        f"{r.detail if r else sorted(res)}",
    )


def test_no_preequilibration_is_skipped(root: Path) -> None:
    petab_dir = _stage(root / "none")
    for label, preeq in (("no column", None), ("an empty column", {})):
        _measurements(petab_dir, preeq)
        ok, res, _ledger = _battery(petab_dir, _gates(root / "none"))
        r = res.get(GATE)
        check(
            f"{label}: the gate passes and says it skipped",
            ok
            and r is not None
            and r.passed
            and r.detail == "no pre-equilibration declared; skipped",
            f"{r.detail if r else sorted(res)}",
        )


# ------------------------------------------------ the engine's own rendering

TOY = REPO / "testcase" / "toy_phos"
PREEQ = {"S": 0}  # the ligand removed: the R <-> Rp cycle relaxes to R = total
PRE_ON = ("dose_0p3", "dose_3")  # one training condition, the held-out one
RUN_ID = "preeq_stub_cli"


def _stub(name: str) -> dict:
    return json.loads((TOY / "stubs" / f"{name}.json").read_text())


def _toy_antimony() -> str:
    """The toy model started OFF its resting state (R = Rp = 5), so that a
    pre-equilibration visibly moves the start: with S = 0 the cycle settles
    at R = 10, Rp = 0, where the data's own t = 0 samples are."""
    ant = _stub("construction")["antimony"]
    out = ant.replace("species R in cell = 10;", "species R in cell = 5;").replace(
        "species Rp in cell = 0;", "species Rp in cell = 5;"
    )
    assert out.count("= 5;") == 2, "the toy stub's initial values moved"
    return out


def _assembly(preeq: dict, extra: dict | None = None) -> dict:
    """The toy stubs' assembly, with `preeq` {condition: declaration} and
    `extra` {condition: overrides added}."""
    obs, noise, scaling = assembly_module.split_observation_reply(_stub("observation"))
    conds = copy.deepcopy(_stub("condition")["conditions"])
    for c in conds:
        c["preequilibration"] = preeq.get(c["condition_id"], False)
        c["overrides"].update((extra or {}).get(c["condition_id"], {}))
    return {"observables": obs, "noise": noise, "scaling": scaling, "conditions": conds}


def _long_df() -> pd.DataFrame:
    """The toy data as S2 extracts it: label `dose=<%g>`, the same key."""
    raw = pd.read_csv(TOY / "data" / "timecourse.csv")
    labels = [f"dose={d:g}" for d in raw["dose"]]
    return pd.DataFrame(
        {
            "observable_label": "pR_au",
            "condition_label": labels,
            "condition_key": labels,
            "time": raw["time_min"],
            "value": raw["pR_au"],
            "replicate": raw["replicate"],
        }
    )


class _Ctx:
    """The surface `_merge_to_petab` and the compile card read — a
    single-model round of a record (`root` is its root node)."""

    def __init__(self, root: Node):
        self.root, self.spec, self.ledger = root, SPEC, Ledger(root)
        self.round_idx, self.candidate = 0, None
        self.testcase = {"holdout": {"condition_labels": ["dose=3"]}}

    @property
    def round(self) -> Node:
        return rnd(self.root, self.round_idx)

    @property
    def work(self) -> Node:
        return tree.work_node(self.round, self.candidate)

    @property
    def model(self) -> Node:
        return tree.model_node(self.round, self.candidate)

    @property
    def gates(self) -> Node:
        return tree.gates_node(self.round, self.candidate)

    @property
    def agent_calls(self) -> Node:
        return self.round / "agent_calls"


def _merge(root: Path, preeq: dict, extra: dict | None = None):
    """Merge the toy assembly as S3 does: (ctx, the `petab` group, refusal or None)."""
    ctx = _Ctx(_record(root))
    (ctx.model / "parameters").put(_stub("construction")["parameters"])
    sbml, err = antimony_to_sbml(_toy_antimony())
    assert sbml, err
    petab_dir = ctx.work / "petab"
    refusal = assembly_module._merge_or_refusal(
        ctx, _assembly(preeq, extra), sbml, _long_df(), petab_dir
    )
    return ctx, petab_dir, refusal


def _model_of(petab_dir: Node) -> Node:
    """The model group beside a single-model round's `…/candidates/_single/petab`."""
    return petab_dir.parent.parent.parent / "model"


def _input(petab_dir: Node):
    return petab_io.from_record(petab_dir, model=_model_of(petab_dir))


def _tables(petab_dir: Node) -> PetabTables:
    return PetabTables.from_input(_input(petab_dir))


def _preeq_column(petab_dir: Node, name: str) -> dict[str, set[str]]:
    """{simulation condition: the pre-equilibration ids its rows carry}."""
    m = (petab_dir / name.removesuffix(".tsv")).table()
    col = m.get("preequilibrationConditionId", pd.Series(np.nan, index=m.index))
    out: dict[str, set[str]] = {}
    for sim, pre in zip(m["simulationConditionId"], col, strict=True):
        out.setdefault(str(sim), set()).add("" if pd.isna(pre) else str(pre))
    return out


def test_the_merge_renders_a_declared_preequilibration(root: Path) -> None:
    ctx, petab_dir, refusal = _merge(
        root / "render", {c: PREEQ for c in PRE_ON}, extra={"dose_0p3": {"R": 10.0}}
    )
    check(
        "a dict declaration merges",
        refusal is None,
        str(refusal.detail if refusal else ""),
    )
    if refusal is not None:
        return
    cond = (petab_dir / "conditions").table().set_index("conditionId")
    check(
        "each pre-equilibrated condition has a preeq_<condition> row, and only those",
        sorted(i for i in cond.index if i.startswith("preeq_"))
        == ["preeq_dose_0p3", "preeq_dose_3"],
        str(list(cond.index)),
    )
    check(
        "a pre-eq row is its measured row with the dict on top: S = 0, and the "
        "condition's other override (R = 10) copied; a condition without R stays "
        "blank there",
        float(cond.loc["preeq_dose_0p3", "S"]) == 0.0
        and float(cond.loc["preeq_dose_0p3", "R"]) == 10.0
        and float(cond.loc["preeq_dose_3", "S"]) == 0.0
        and pd.isna(cond.loc["preeq_dose_3", "R"])
        and float(cond.loc["dose_0p3", "S"]) == 0.3,
        cond.to_string().replace("\n", " | "),
    )
    want = {"dose_0p3": {"preeq_dose_0p3"}, "dose_1": {""}}
    check(
        "measurements.tsv: the column is on exactly the pre-equilibrated "
        "condition's rows, blank on the others",
        _preeq_column(petab_dir, "measurements.tsv") == want,
        str(_preeq_column(petab_dir, "measurements.tsv")),
    )
    check(
        "holdout_measurements.tsv carries it too",
        _preeq_column(petab_dir, "holdout_measurements.tsv")
        == {"dose_3": {"preeq_dose_3"}},
        str(_preeq_column(petab_dir, "holdout_measurements.tsv")),
    )
    rows = [e for e in ctx.ledger.entries() if e.get("preequilibration_rendered")]
    rec = {
        r["condition"]: r
        for r in (rows[-1]["preequilibration_rendered"] if rows else [])
    }
    check(
        "the ledger records what was rendered: the row, what changed, and which "
        "species the measured condition re-sets at t=0",
        len(rows) == 1
        and rec.get("dose_0p3", {}).get("preequilibration_condition")
        == "preeq_dose_0p3"
        and rec["dose_0p3"].get("changed") == {"S": [0.3, 0.0]}
        and rec["dose_0p3"].get("reinitialised") == ["R"]
        and rec.get("dose_3", {}).get("reinitialised") == [],
        json.dumps(rows[-1]["preequilibration_rendered"] if rows else None),
    )
    ok, results = run_gate_set(
        make_petab_gates(_tables(petab_dir), SPEC),
        ctx.gates,
        RecordingLedger(),
        "assembly",
    )
    res = {r.gate_id: r for r in results}
    check(
        "the S3 battery passes on the rendered tables: petablint, the resolve "
        "checks, and the steady-state screen of both pre-eq rows",
        ok
        and all(
            res[g].passed
            for g in ("assembly_petablint", "assembly_measurements_resolve", GATE)
            if g in res
        )
        and GATE in res
        and res[GATE].detail == "all pre-equilibration conditions reach steady state",
        "; ".join(f"{g}: {r.passed} {r.detail[:80]}" for g, r in res.items()),
    )
    lines = battery_feedback.card_lines(ctx)
    named = [ln for ln in lines if "pre-equilibration rendered" in ln]
    check(
        "the compile card says it once: both conditions, the change, the re-set "
        "species, and the screen that passed",
        len(named) == 1
        and "dose_0p3 from preeq_dose_0p3 (S 0.3 -> 0), re-set at t=0: R" in named[0]
        and "dose_3 from preeq_dose_3 (S 3 -> 0)" in named[0]
        and any("assembly_preequilibration (ok)" in ln for ln in lines),
        " || ".join(lines),
    )


def test_a_bare_true_is_refused_at_the_merge(root: Path) -> None:
    for i, bad in enumerate((True, "yes", 1, {}, ["S"])):
        ctx, _dir, refusal = _merge(root / f"bad_{i}", {"dose_0p3": bad})
        role = battery_feedback.attribute([refusal])[0] if refusal else None
        detail = str(refusal.detail if refusal else "")
        ledgered = any(
            e.get("merge_refusal") and e.get("gate_id") == "assembly_merge_conditions"
            for e in ctx.ledger.entries()
        )
        check(
            f"preequilibration: {bad!r} is refused at the conditions merge by "
            f"name, ledgered, and goes back to the condition-encoding agent",
            refusal is not None
            and refusal.gate_id == "assembly_merge_conditions"
            and detail.startswith("condition dose_0p3: preequilibration is")
            and "say which overrides form the pre-equilibration condition" in detail
            and ledgered
            and role == "condition",
            f"{role}: {detail[:160]}",
        )
    for i, none in enumerate((False, None, "false", "no", 0)):
        _ctx, petab_dir, refusal = _merge(root / f"none_{i}", {"dose_0p3": none})
        cond = (petab_dir / "conditions").table()
        meas = (petab_dir / "measurements").table()
        check(
            f"preequilibration: {none!r} renders none: no row, no column",
            refusal is None
            and not cond["conditionId"].astype(str).str.startswith("preeq_").any()
            and "preequilibrationConditionId" not in meas.columns,
            str(refusal.detail if refusal else list(cond["conditionId"])),
        )


def test_a_dict_key_is_checked_like_an_override(root: Path) -> None:
    ctx, petab_dir, refusal = _merge(root / "typo", {"dose_0p3": {"S_typo": 0}})
    ok, results = run_gate_set(
        make_petab_gates(_tables(petab_dir), SPEC),
        ctx.gates,
        RecordingLedger(),
        "assembly",
    )
    r = {x.gate_id: x for x in results}.get("assembly_conditions_resolve")
    role = battery_feedback.attribute(results)[0]
    check(
        "a pre-equilibration key that is no model entity fails "
        "assembly_conditions_resolve by name, which re-asks the condition-encoding agent",
        refusal is None
        and not ok
        and r is not None
        and not r.passed
        and "'S_typo'" in r.detail
        and role == "condition",
        f"{role}: {r.detail if r else sorted(x.gate_id for x in results)}",
    )


def test_a_search_axis_cannot_change_the_declaration() -> None:
    asm = {
        "conditions": [
            {
                "condition_id": "c_a",
                "maps_to_label": "a",
                "overrides": {"S": 1.0},
                "preequilibration": {"S": 0},
            },
            {
                "condition_id": "c_b",
                "maps_to_label": "b",
                "overrides": {"S": 1.0},
                "preequilibration": False,
            },
        ]
    }
    cases = (
        ("switching it on with a dict", "c_b", {"S": 0}, True),
        ("switching it on with a bare true", "c_b", True, True),
        ("switching it off", "c_a", False, True),
        ("changing which overrides form it", "c_a", {"S": 0.5}, True),
        ("restating the same dict", "c_a", {"S": 0.0}, False),
        ("restating none", "c_b", None, False),
    )
    for label, cid, value, refused in cases:
        probs = assembly_edit._condition_class_problems(
            {"condition_id": cid, "overrides": {"k2": 1.0}, "preequilibration": value},
            asm,
        )
        hit = any("pre-equilibration" in p for p in probs)
        check(
            f"an axis {label} is {'refused' if refused else 'not refused'}",
            hit == refused,
            str(probs),
        )


def test_the_roadrunner_path_starts_from_the_steady_state(root: Path) -> None:
    _ctx, petab_dir, refusal = _merge(
        root / "start", {c: PREEQ for c in PRE_ON}, extra={"dose_0p3": {"R": 10.0}}
    )
    if refusal is not None:
        check("the start-state fixture merges", False, refusal.detail)
        return
    t = np.array([0.0, 5.0, 60.0])
    full = _tables(petab_dir)
    train_only = PetabTables(
        observables=full.observables,
        conditions=full.conditions,
        measurements=full.measurements,
        parameters=full.parameters,
        sbml=full.sbml,
    )

    def start(tables, cid):
        ns = tables._namespace(cid, t)
        return round(float(ns["R"][0]), 6), round(float(ns["Rp"][0]), 6)

    got = {
        "dose_0p3": start(full, "dose_0p3"),
        "dose_1": start(full, "dose_1"),
        "dose_3": start(full, "dose_3"),
        "dose_3 (training table only)": start(train_only, "dose_3"),
    }
    check(
        "a pre-equilibrated condition starts from its pre-eq row's steady state "
        "(Rp = 0), and R, which the condition sets itself, is re-set (R = 10)",
        got["dose_0p3"] == (10.0, 0.0),
        str(got),
    )
    check(
        "a condition without pre-equilibration starts from the model's initial "
        "values (R = Rp = 5)",
        got["dose_1"] == (5.0, 5.0),
        str(got),
    )
    check(
        "a held-out condition pre-equilibrates too — read from the held-out "
        "rows — and would not from the training rows alone",
        got["dose_3"] == (10.0, 0.0)
        and got["dose_3 (training table only)"] == (5.0, 5.0),
        str(got),
    )


def test_roadrunner_overrides_do_not_leak() -> None:
    """The two roadrunner behaviours the start state rests on."""
    from octomod.workflow_modules.model.simwrap import RRModel

    sbml, err = antimony_to_sbml(
        "model m; compartment cell = 1; species A in cell; species B in cell = 2;"
        " A = Atot; Atot = 3; k = 1; J: A -> B; k*A; end"
    )
    assert sbml, err
    m = RRModel(sbml)
    first = m.simulate(1.0, n_points=3, overrides={"k": 0.0, "B": 7.0})
    check(
        "a parameter override survives a species override applied after it "
        "(k = 0 holds A constant)",
        float(first["A"][-1]) == 3.0 and float(first["B"][0]) == 7.0,
        f"A {first['A']} B {first['B']}",
    )
    later = m.simulate(1.0, n_points=3, overrides={"Atot": 4.0})
    check(
        "a species override does not leak into the next simulation, and an "
        "initial assignment still reads its parameter there",
        float(later["B"][0]) == 2.0 and float(later["A"][0]) == 4.0,
        f"A0 {later['A'][0]} B0 {later['B'][0]}",
    )
    check(
        "the declared integrator tolerances survive the reload",
        m.tolerances == m._apply_tolerances(m.tolerances),
        str(m.tolerances),
    )


def test_the_fingerprint_and_the_timepoint_check(root: Path) -> None:
    import petab.v1 as petab

    from octomod.orchestration import artifacts
    from octomod.orchestration.reuse import fit_fingerprint

    _c0, plain, _r0 = _merge(root / "fp_plain", {})
    _c1, pre, _r1 = _merge(root / "fp_pre", {c: PREEQ for c in PRE_ON})
    k0, p0 = fit_fingerprint(_input(plain), plain.parent, None, SPEC, 0)
    k1, p1 = fit_fingerprint(_input(pre), pre.parent, None, SPEC, 0)
    check(
        "the fit fingerprint moves when the problem gains pre-equilibration (it "
        "hashes the conditions and measurement tables), so no old fit is read back",
        k0 != k1 and p0["problem"] != p1["problem"],
        f"{k0} vs {k1}",
    )
    m = (pre / "measurements").table()
    kw = {"allow_scalar_numeric_noise_parameters": True}
    real = artifacts._petab_timepoint_check()
    check(
        "petab's own check reads a partly blank pre-equilibration column as "
        "timepoint-specific (the reason for the engine's check; if this fails, "
        "petab is fixed and the patch can go)",
        bool(real(m, **kw)),
    )
    genuine = m.copy()
    genuine["observableParameters"] = [f"sc_{i % 2}" for i in range(len(m))]
    check(
        "the engine's check reads it right, and still catches a genuinely "
        "timepoint-specific table",
        not artifacts.timepoint_specific(m, **kw)
        and artifacts.timepoint_specific(genuine, **kw),
    )
    with artifacts.timepoint_check_patched():
        patched = petab.lint.measurement_table_has_timepoint_specific_mappings(m, **kw)
    check(
        "AMICI's import asks the engine's check only while the patch is in place",
        patched is False
        and petab.lint.measurement_table_has_timepoint_specific_mappings is real,
    )


def test_the_builder_can_suggest_it(root: Path) -> None:
    from octomod.agents import routing
    from octomod.workflow_modules.model.engine import basal_state

    said = {
        "initial_values_are_steady_state": False,
        "suggest_preequilibration": True,
        "note": "SOCS has a basal level set by synthesis against decay",
        "extra": "dropped",
    }
    check(
        "construction's optional basal_state keeps its three fields; a string "
        "is its note; nothing, or junk, is nothing",
        basal_state({"basal_state": said})
        == {k: v for k, v in said.items() if k != "extra"}
        and basal_state({"basal_state": " resting cells "}) == {"note": "resting cells"}
        and basal_state({}) is None
        and basal_state({"basal_state": {"note": "", "x": 1}}) is None
        and basal_state({"basal_state": 3}) is None,
    )
    ctx = _Ctx(_record(root / "basal"))
    check(
        "no build report, or one without basal_state: the key is absent",
        assembly_module._basal_state_for(ctx) == {},
    )
    (ctx.round / "model" / "build_report").put(
        {"decisions": [], "basal_state": basal_state({"basal_state": said})},
    )
    check(
        "a build report with one hands it to the condition-encoding payload",
        assembly_module._basal_state_for(ctx)
        .get("basal_state", {})
        .get("suggest_preequilibration")
        is True,
    )
    check(
        "the routing table grants it to the condition-encoding agent",
        routing.violations("condition", ["basal_state"]) == [],
    )


# ------------------------------------------------------------ end to end


def _cli_case(root: Path) -> Path:
    """toy_phos, copied: the dose_0p3 and dose_3 encodings declare {"S": 0},
    and the model starts off its resting state (see `_toy_antimony`)."""
    case = root / "toy_phos_preeq"
    shutil.copytree(TOY, case, ignore=shutil.ignore_patterns("truth"))
    enc = json.loads((case / "stubs" / "condition.json").read_text())
    for c in enc["conditions"]:
        if c["condition_id"] in PRE_ON:
            c["preequilibration"] = dict(PREEQ)
    (case / "stubs" / "condition.json").write_text(json.dumps(enc, indent=2))
    con = json.loads((case / "stubs" / "construction.json").read_text())
    con["antimony"] = _toy_antimony()
    (case / "stubs" / "construction.json").write_text(json.dumps(con, indent=2))
    return case


def _amici_against_roadrunner(root: Node) -> dict:
    """{condition: (AMICI y(0), roadrunner y(0), worst relative difference)}
    at the nominal parameters, over the training conditions (the round-0
    problem of the run record `root`)."""
    from octomod.workflow_modules.estimation import problem as estimation

    inp = petab_io.from_work(work(root, 0), rnd(root, 0) / "model")
    problem, petab_problem, _ = estimation.build_problem(inp, {}, SPEC)
    scales = estimation.parameter_scales(inp)
    par = petab_problem.parameter_df
    nominal = {p: float(par.loc[p, "nominalValue"]) for p in problem.x_names}
    scaled = {"log10": math.log10, "log": math.log}
    x = np.array([scaled.get(scales[p], float)(v) for p, v in nominal.items()])
    out = problem.objective(
        x[problem.x_free_indices], return_dict=True, sensi_orders=(0,)
    )
    tables = PetabTables.from_input(inp)
    got = {}
    for r in out["rdatas"]:
        cid = str(r.id).split("+")[0]
        t = np.asarray(r.ts, dtype=float)
        y = np.asarray(r.y, dtype=float)[:, 0]
        sim = tables.simulate_observables(cid, t, param_override=nominal)["obs_pR"]
        rel = float(np.max(np.abs(y - sim)) / max(float(np.max(np.abs(y))), 1e-12))
        got[cid] = (float(y[0]), float(sim[0]), rel)
    return got


def _declared_settings(root: Node) -> tuple[dict, dict, bool]:
    """What the solver and model hold under the spec and under a spec whose
    steady-state block differs from AMICI's defaults; and whether the fit
    fingerprint tells the two apart."""
    from octomod.orchestration.reuse import fit_fingerprint
    from octomod.workflow_modules.estimation import problem as estimation
    from octomod.workflow_modules.estimation import solver_settings as ss

    changed = copy.deepcopy(SPEC)
    changed.raw["simulation"]["amici"]["steady_state"] = {
        "newton_maxsteps": 7,
        "newton_damping_factor_lower_bound": 1.0e-6,
        "steadystate_tol_factor": 50.0,
        "sensitivity_mode": "newtonOnly",
    }
    held, keys = {}, {}
    inp = petab_io.from_work(work(root, 0), rnd(root, 0) / "model")
    for name, spec in (("declared", SPEC), ("changed", changed)):
        prob, _pp, _ = estimation.build_problem(inp, {}, spec)
        o = prob.objective
        held[name] = ss.read_back(o.amici_solver, o.amici_model)
        keys[name] = fit_fingerprint(inp, work(root, 0), prob, spec, 0)[0]
    return held["declared"], held["changed"], keys["declared"] != keys["changed"]


def test_the_stub_cli_renders_and_probes(root: Path) -> None:
    import amici.sim.sundials as sd

    # the run is one record, <RUNS_DIR>/<id>.h5
    run_dir = run_root(RUN_ID, config.RUNS_DIR)
    run_dir.store.remove()
    case = _cli_case(root)
    base = [
        "run",
        "--testcase",
        str(case),
        "--backend",
        "stub",
        "--run-id",
        RUN_ID,
        "--gate-mode",
        "file",
    ]

    def module():
        pending = pending_gate(run_dir)
        return pending["module"] if pending is not None else None

    rc, out = run_cli_captured(base)
    for _ in range(6):
        if rc != 3 or module() == "assembly_cost_boundary":
            break
        rc, out = run_cli_captured(base + ["--gate-answer", "y"])
    check(
        "y at the intent and scope cards: the run pauses at the compile card",
        rc == 3 and module() == "assembly_cost_boundary",
        f"rc={rc} at {module()}\n{out[-1200:]}",
    )
    if module() != "assembly_cost_boundary":
        return
    rd = rnd(run_dir, 0)
    petab = work(run_dir, 0) / "petab"  # the single model's unit of work
    card = pending_gate(run_dir)
    cond = (petab / "conditions").table().set_index("conditionId")
    check(
        "conditions.tsv has the preeq_* rows, with S = 0",
        sorted(i for i in cond.index if i.startswith("preeq_"))
        == ["preeq_dose_0p3", "preeq_dose_3"]
        and all(float(cond.loc[f"preeq_{c}", "S"]) == 0.0 for c in PRE_ON)
        and list(cond.columns) == ["S"],
        cond.to_string().replace("\n", " | "),
    )
    check(
        "measurements.tsv and holdout_measurements.tsv carry the column on "
        "exactly the pre-equilibrated rows",
        _preeq_column(petab, "measurements.tsv")
        == {"dose_0p3": {"preeq_dose_0p3"}, "dose_1": {""}}
        and _preeq_column(petab, "holdout_measurements.tsv")
        == {"dose_3": {"preeq_dose_3"}},
        f"{_preeq_column(petab, 'measurements.tsv')} / "
        f"{_preeq_column(petab, 'holdout_measurements.tsv')}",
    )
    gate = (rd / "gates").child(GATE).get()
    check(
        "assembly_preequilibration ran on the rendered rows and passed",
        gate["passed"]
        and gate["detail"] == "all pre-equilibration conditions reach steady state",
        str(gate.get("detail")),
    )
    named = [ln for ln in card["lines"] if "pre-equilibration rendered" in ln]
    check(
        "the compile card names the rendered pre-equilibration once, and the "
        "screen it passed",
        len(named) == 1
        and "dose_0p3 from preeq_dose_0p3 (S 0.3 -> 0)" in named[0]
        and "dose_3 from preeq_dose_3 (S 3 -> 0)" in named[0]
        and any("assembly_preequilibration (ok)" in ln for ln in card["lines"]),
        " || ".join(card["lines"]),
    )
    ledger = ledger_rows(run_dir)
    rendered = [e for e in ledger if e.get("preequilibration_rendered")]
    check(
        "the ledger names it too",
        bool(rendered)
        and [r["condition"] for r in rendered[-1]["preequilibration_rendered"]]
        == list(PRE_ON),
        str(rendered[-1]["preequilibration_rendered"] if rendered else None),
    )

    rc, out = run_cli_captured(base + ["--gate-answer", "y"])
    check(
        "y at the compile card: AMICI compiles, the probe runs, and the run "
        "pauses at the budget card",
        rc == 3 and module() == "cost_boundary_estimation",
        f"rc={rc} at {module()}\n{out[-1200:]}",
    )
    if module() != "cost_boundary_estimation":
        return
    budget = pending_gate(run_dir)
    steady = (work(run_dir, 0) / "probe_record").get()["steady"]
    rows = steady.get("per_condition") or []
    pre = [r for r in rows if "+preeq_" in str(r.get("condition"))]
    plain = [r for r in rows if r not in pre]
    check(
        "the probe read AMICI's steady state: used, the pre-equilibrated "
        "training condition ran to a finite wrms below 1, the other did not run",
        steady.get("used") is True
        and [r["condition"] for r in pre] == ["dose_0p3+preeq_dose_0p3"]
        and all(
            r["ran"]
            and r["wrms"] is not None
            and math.isfinite(r["wrms"])
            and r["wrms"] < 1.0
            and min(r["status"]) >= 0
            for r in pre
        )
        and bool(plain)
        and not any(r["ran"] for r in plain),
        json.dumps(rows),
    )
    line = next(
        (ln for ln in budget["lines"] if "pre-equilibration: ran for" in ln), ""
    )
    check(
        "the budget card carries the steady-state line, naming the condition",
        "ran for 1 condition(s)" in line and "dose_0p3+preeq_dose_0p3" in line,
        line or " || ".join(budget["lines"]),
    )
    got = _amici_against_roadrunner(run_dir)
    check(
        "AMICI and roadrunner agree where each condition starts: the "
        "pre-equilibrated one at its steady state (0), the other at the "
        "model's initial value (5), and along the whole trajectory",
        set(got) == {"dose_0p3", "dose_1"}
        and abs(got["dose_0p3"][0]) < 1e-6
        and abs(got["dose_0p3"][1]) < 1e-6
        and abs(got["dose_1"][0] - 5.0) < 1e-6
        and abs(got["dose_1"][1] - 5.0) < 1e-6
        and all(v[2] < 1e-2 for v in got.values()),
        str(got),
    )
    declared, changed, fingerprint_moves = _declared_settings(run_dir)
    newton_only = int(sd.SteadyStateSensitivityMode.newtonOnly)
    check(
        "the declared steady-state settings reach the solver and the model: "
        "AMICI's defaults as declared, and a changed block read back as declared",
        declared.get("newton_maxsteps") == 0
        and declared.get("steadystate_tol_factor") == 100.0
        and changed.get("newton_maxsteps") == 7
        and changed.get("newton_damping_factor_lower_bound") == 1.0e-6
        and changed.get("steadystate_tol_factor") == 50.0
        and changed.get("sensitivity_mode") == newton_only
        and declared.get("sensitivity_mode") != newton_only,
        f"declared {declared} | changed {changed}",
    )
    check(
        "a changed steady-state setting is a different fit fingerprint",
        fingerprint_moves,
    )
    rc, out = run_cli_captured(base + ["--gate-answer", "n"])
    check(
        "n at the budget card stops the run before any estimation",
        rc == 1 and not (work(run_dir, 0) / "estimation").exists(),
        f"rc={rc}\n{out[-400:]}",
    )
    run_dir.store.remove()


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        test_a_relaxing_condition_passes(root)
        test_a_condition_that_never_settles_fails_by_name(root)
        test_an_undeclared_preequilibration_id_is_refused(root)
        test_no_preequilibration_is_skipped(root)
        test_the_merge_renders_a_declared_preequilibration(root)
        test_a_bare_true_is_refused_at_the_merge(root)
        test_a_dict_key_is_checked_like_an_override(root)
        test_a_search_axis_cannot_change_the_declaration()
        test_the_roadrunner_path_starts_from_the_steady_state(root)
        test_roadrunner_overrides_do_not_leak()
        test_the_fingerprint_and_the_timepoint_check(root)
        test_the_builder_can_suggest_it(root)
        test_the_stub_cli_renders_and_probes(root)
    return finish(
        "\nPRE-EQUILIBRATION",
        "\nPRE-EQUILIBRATION OK — a declared pre-equilibration is rendered, "
        "screened at S3, run by AMICI at the probe and reported on the budget "
        "card; a bare true is refused by name; roadrunner starts each condition "
        "where AMICI does; a supplied one is probed the same way",
    )


if __name__ == "__main__":
    sys.exit(main())
