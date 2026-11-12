"""A T0/T1 failure blocks the artifact, never the run: the routing of gate failures.

  1. every declared S2/S3 gate id is attributed to a role, unattributable, or advisory;
  2. the feedback payload carries the failing check verbatim and the agent's own block;
  3. `assembly_dof` and `assembly_magnitude_reconciliation` are advisory on real tables;
  4. the three declared fallbacks produce their shapes; an unknown name is refused;
  5. the failure-point gate advertises its forms; auto mode grants, never falls back;
  6. on a replayed live reply the magnitude gate routes nowhere and the payload builds.

    uv run python tests/battery_feedback_unit.py
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish, fixture_or_skip  # noqa: E402

from octomod import config  # noqa: E402
from octomod.gates import GateResult  # noqa: E402
from octomod.orchestration.interaction import battery_feedback as bf  # noqa: E402
from octomod.orchestration.interaction import human_redraft  # noqa: E402
from octomod.orchestration.interaction.retry import (  # noqa: E402
    AttemptHistory,
    dossier_of,
)
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from tests._record import (  # noqa: E402
    ledger_rows,
    record_at,
    rnd,
    run_root,
    temp_record,
)

# The user's runs folder, not the battery's redirected one: this reads their
# previous runs, not runs this suite makes.
USER_RUNS = config.USER_RUNS_DIR

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")


def _declared_gate_ids(module_path: Path) -> set[str]:
    return set(
        re.findall(r'@gate\("((?:assembly|data)_[a-z_]+)"', module_path.read_text())
    )


def test_every_declared_gate_is_routed() -> None:
    s3 = _declared_gate_ids(REPO / "octomod" / "gates" / "petab_gates.py")
    s2 = _declared_gate_ids(
        REPO / "octomod" / "workflow_modules" / "data" / "engine.py"
    )
    # the merge's refusals are routed like gates, declared in assembly
    s3 |= set(
        re.findall(
            r'gate_id="(assembly_merge_[a-z_]+)"',
            (
                REPO / "octomod" / "workflow_modules" / "assembly" / "engine.py"
            ).read_text(),
        )
    )
    check(
        "the roll-call is not empty",
        len(s3) >= 8 and len(s2) >= 3,
        f"{len(s3)} S3, {len(s2)} S2 gates",
    )
    routed = set(bf.ATTRIBUTION) | set(bf.ADVISORY)
    missing = sorted((s3 | s2) - routed)
    check(
        "every declared S2/S3 gate is attributed, unattributable, or advisory",
        not missing,
        ", ".join(missing) or "all routed",
    )
    stale = sorted(set(bf.ATTRIBUTION) - (s3 | s2))
    check(
        "the table names only gates the engine declares",
        not stale,
        ", ".join(stale),
    )
    check(
        "parameters_sane routes only an assembly-created row",
        bf.role_for(
            GateResult(
                "assembly_parameters_sane",
                "T0",
                False,
                detail="sc_obs_x: bounds inverted",
            )
        )
        == "observation"
        and bf.role_for(
            GateResult(
                "assembly_parameters_sane",
                "T0",
                False,
                detail="k_phos: nominal outside bounds",
            )
        )
        is None,
    )
    # pre-equilibration is declared by the condition-encoding agent (a dict
    # of overrides per measured condition) and rendered by the engine as a
    # `preeq_<id>` row, so a condition that never settles is that agent's
    preeq = GateResult(
        "assembly_preequilibration",
        "T1",
        False,
        detail="preeq_dose_3: no steady state (residual 1.20e+00)",
    )
    check(
        "a pre-equilibration that never settles goes back to condition",
        bf.role_for(preeq) == "condition" and bf.attribute([preeq])[0] == "condition",
        str(bf.role_for(preeq)),
    )
    ids = bf.implicated_ids(preeq.detail, ["dose_0p3", "dose_3", "dose_30"])
    check(
        "the rendered `preeq_<id>` row implicates the measured condition it "
        "belongs to, and only that one",
        ids == ["dose_3"],
        str(ids),
    )
    with temp_record() as root:
        petab = rnd(root, 0) / "candidates/_single/petab"
        (petab / "conditions").put_table(
            pd.DataFrame(
                [
                    {"conditionId": c, "S": v}
                    for c, v in (
                        ("dose_0p3", 0.3),
                        ("dose_3", 3.0),
                        ("preeq_dose_0p3", 0.0),
                        ("preeq_dose_3", 0.0),
                    )
                ]
            )
        )
        rows = bf.table_rows(petab, "assembly_preequilibration", ids)
    check(
        "the re-ask shows the measured row and the pre-equilibration row the "
        "engine rendered from it",
        sorted(r["conditionId"] for r in rows) == ["dose_3", "preeq_dose_3"],
        str(rows),
    )
    check(
        "and the model entities an override may name",
        "model_entities"
        in bf.legal_vocabulary("assembly_preequilibration", {"species": ["S"]}),
    )
    check(
        "the FIRST blocking failure decides — an unattributable one first goes to a person",
        bf.attribute(
            [
                GateResult("assembly_petablint", "T0", False, detail="x"),
                GateResult("assembly_observables_resolve", "T0", False, detail="y"),
            ]
        )[0]
        is None,
    )


def test_the_payload_is_verbatim_and_the_agents_own() -> None:
    reply = {
        "observables": [
            {
                "observable_id": "obs_a",
                "maps_to_label": "A",
                "formula": "Rp_total",
                "noise": {"formula": "s"},
                "scaling": {"mode": "none"},
            },
            {
                "observable_id": "obs_b",
                "maps_to_label": "B",
                "formula": "R",
                "noise": {"formula": "s"},
                "scaling": {"mode": "none"},
            },
        ]
    }
    gate = GateResult(
        "assembly_observables_resolve",
        "T0",
        False,
        detail="obs_a: formula names unknown symbol(s) ['Rp_total']",
    )
    ids = bf.implicated_ids(gate.detail, ["obs_a", "obs_b"])
    fb = bf.feedback(
        bf.gate_record(gate),
        "observation",
        bf.observation_block(reply, ids),
        [{"observableId": "obs_a", "observableFormula": "Rp_total"}],
        bf.legal_vocabulary(
            "assembly_observables_resolve",
            {"species": ["R", "Rp"], "parameters": ["k"]},
        ),
    )
    check("the implicated id is found in the detail", ids == ["obs_a"], str(ids))
    check(
        "the gate is carried verbatim",
        fb["gate"]["detail"] == gate.detail and fb["gate"]["tier"] == "T0",
    )
    check(
        "your_block is the agent's OWN entry, not the merged row",
        fb["your_block"] == [reply["observables"][0]]
        and fb["your_block"][0]["formula"] == "Rp_total",
    )
    check(
        "the merged row is shown separately",
        fb["merged_rows"][0]["observableFormula"] == "Rp_total",
    )
    check(
        "the legal vocabulary names boundary species too",
        "boundary" in fb["legal_vocabulary"]["note"]
        and fb["legal_vocabulary"]["model_entities"] == ["R", "Rp", "k"],
    )
    check(
        "the instruction tells the agent to SAY SO when the merge is wrong",
        "say so" in fb["instruction"],
    )


def test_magnitude_and_dof_are_advisory_on_real_tables() -> None:
    import antimony

    from octomod.gates.petab_gates import PetabTables, make_petab_gates

    antimony.loadAntimonyString("model m; A=10; B=0; J0: A->B; kdeg*A; kdeg=0.3; end")
    sbml = antimony.getSBMLString(antimony.getMainModuleName())
    tables = PetabTables(
        observables=pd.DataFrame(
            [
                {
                    "observableId": "o",
                    "observableFormula": "B",
                    "observableTransformation": "lin",
                    "noiseFormula": "noiseParameter1_o",
                    "noiseDistribution": "normal",
                }
            ]
        ),
        conditions=pd.DataFrame([{"conditionId": "c0"}]),
        # measurements five ORDERS above the model and MORE parameters than points: both checks fail
        measurements=pd.DataFrame(
            [
                {
                    "observableId": "o",
                    "simulationConditionId": "c0",
                    "time": 1.0,
                    "measurement": 1e6,
                    "noiseParameters": "sigma_o",
                }
            ]
        ),
        parameters=pd.DataFrame(
            [
                {
                    "parameterId": p,
                    "parameterScale": "log10",
                    "lowerBound": 1e-3,
                    "upperBound": 1e3,
                    "nominalValue": 0.3,
                    "estimate": 1,
                }
                for p in ("kdeg", "sigma_o", "extra1", "extra2")
            ]
        ),
        sbml=sbml,
    )
    results = {}
    for g in make_petab_gates(tables, SPEC):
        if getattr(g, "gate_id", "") in (
            "assembly_dof",
            "assembly_magnitude_reconciliation",
        ):
            results[g.gate_id] = g()
    for gid, r in results.items():
        check(
            f"{gid} FAILS on this problem but is advisory (blocking=False)",
            (not r.passed) and r.blocking is False,
            f"passed={r.passed} blocking={r.blocking} · {str(r.detail)[:80]}",
        )
    check(
        "both were exercised",
        set(results) == {"assembly_dof", "assembly_magnitude_reconciliation"},
        str(sorted(results)),
    )


def test_fallbacks_produce_their_declared_shapes() -> None:
    asm = {
        "observables": [{"observable_id": "o1"}, {"observable_id": "o2"}],
        "noise": [
            {"observable_id": "o1", "formula": "a+b*X"},
            {"observable_id": "o2", "formula": "c"},
        ],
        "scaling": [
            {"observable_id": "o1", "mode": "none"},
            {"observable_id": "o2", "mode": "factor_offset"},
        ],
    }
    new, rep = bf.apply_fallback("additive-noise", asm, SPEC)
    check(
        "additive-noise: one constant sigma per observable, estimated",
        [n["formula"] for n in new["noise"]] == ["sigma_o1", "sigma_o2"]
        and all(n["estimate_sigma"] for n in new["noise"])
        and "noise" in rep,
    )
    check("… and the scaling block is untouched", new["scaling"] == asm["scaling"])
    new, rep = bf.apply_fallback("scaling", asm, SPEC)
    check(
        "scaling: mode factor, sc_<obs>, per observable",
        all(
            s["mode"] == "factor"
            and s["scale_parameter"] == f"sc_{s['observable_id']}"
            and s["per"] == "observable"
            for s in new["scaling"]
        ),
    )
    new, rep = bf.apply_fallback("no-scaling", asm, SPEC)
    check(
        "no-scaling: mode none everywhere",
        all(s["mode"] == "none" for s in new["scaling"]),
    )
    try:
        bf.apply_fallback("laplace-everything", asm, SPEC)
        check("an unknown name is refused", False, "accepted")
    except ValueError as e:
        check(
            "an unknown name is refused, naming the legal list",
            "additive-noise" in str(e) and "no-scaling" in str(e),
        )
    reply = {
        "observables": [
            {
                "observable_id": "o1",
                "noise": {"formula": "s1+s2*X+s3*Y+s4"},
                "scaling": {"mode": "none"},
            }
        ]
    }
    new_reply, rep = bf.fallback_into_reply("additive-noise", reply, SPEC)
    check(
        "the same rewrite works on a REPLY at the seam module",
        new_reply["observables"][0]["noise"]["formula"] == "sigma_o1"
        and reply["observables"][0]["noise"]["formula"].startswith("s1"),
        "and the original reply object is not mutated",
    )
    check(
        "the declared names and the implemented names agree",
        set(bf.fallback_names(SPEC)) == {"additive-noise", "scaling", "no-scaling"},
        str(bf.fallback_names(SPEC)),
    )
    check(
        "parse: the form is found beside other words",
        bf.parse_fallback("y fallback: additive-noise") == "additive-noise"
        and bf.parse_fallback("n=2") is None,
    )


AUTO_CAP = int(SPEC.require("retry.auto_grants"))


class _Ctx:
    def __init__(self, root, auto: bool):
        # `root` is the record's root Node: the run is one file
        self.root = root
        self.round = rnd(root, 0)
        self.agent_calls = self.round / "agent_calls"
        self.spec, self.ledger, self.round_idx, self.auto = SPEC, Ledger(root), 0, auto
        self.intent = {"question": "?"}
        if auto:
            # as the orchestrator does whenever auto is on: an auto run that
            # reaches an exhaustion gate without a cap is refused
            from octomod.orchestration.interaction import humangate

            humangate.configure_auto_grants(AUTO_CAP)


def test_the_gate_advertises_its_forms_and_never_falls_back_unasked() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = record_at(Path(tmp) / "run")
        ctx = _Ctx(root, auto=True)
        hist = AttemptHistory(dossier_of(ctx, "observation"))
        hist.add(["seam: bad"], {})
        hist.add(["seam: bad again"], {})
        failing = [
            GateResult(
                "assembly_observables_resolve",
                "T0",
                False,
                detail="obs_a: formula names unknown symbol(s) ['Rp_total']",
            )
        ]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            decision, arg = bf.failure_point_gate(
                ctx,
                "assembly",
                "observation",
                failing,
                [{"observable_id": "obs_a", "formula": "Rp_total"}],
                hist,
                2,
                offer_fallbacks=True,
            )
        card = buf.getvalue()
        for needle in (
            "n=<attempts>",
            "redraft:",
            "fallback: <name>",
            "additive-noise",
            "Rp_total",
            "assembly_observables_resolve",
        ):
            check(
                f"the card advertises / shows {needle!r}",
                needle in card,
                card[-300:] if needle not in card else "",
            )
        check(
            f"auto mode grants the declared allowance ({AUTO_CAP}) as one grant — never a fallback",
            decision == "more" and arg == AUTO_CAP,
            f"{decision} {arg}",
        )
        check("the grant is durable in the dossier", hist.grants_total == AUTO_CAP)
        rows = ledger_rows(root)
        check(
            "no assembly_fallback row was written by an unasked path",
            not any(r["event"] == "assembly_fallback" for r in rows),
        )
        check(
            "the module of the gate is cost-shaped (copilot answers it by shape)",
            any(
                r["event"] == "human_gate" and r["module"] == "assembly_redraft_budget"
                for r in rows
            ),
        )
    # the unattributable branch: a bare `y` buys one whole redraft per round, a
    # second identical failure stops (a measurement id no condition row
    # carries is the engine's own join, not an agent's value)
    with tempfile.TemporaryDirectory() as tmp:
        ctx = _Ctx(record_at(Path(tmp) / "run"), auto=True)
        failing = [
            GateResult(
                "assembly_measurements_resolve",
                "T0",
                False,
                detail="measurement condition c9 has no row in conditions.tsv",
            )
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            d1, a1 = bf.failure_point_gate(
                ctx, "assembly", None, failing, None, None, 2, offer_fallbacks=True
            )
        check(
            "unattributable + bare y: the whole assembly is redrafted once, with the check named",
            d1 == "redraft" and "assembly_measurements_resolve" in str(a1),
            f"{d1} {str(a1)[:60]}",
        )
        ctx.ledger.append(
            "note",
            module="assembly",
            round_idx=0,
            note="human asked the assembly agents to redraft: x",
            human_redraft=True,
            role="the assembly agents",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            d2, _ = bf.failure_point_gate(
                ctx, "assembly", None, failing, None, None, 2, offer_fallbacks=True
            )
        check(
            "… and the second identical failure stops honestly, not a loop",
            d2 == "stop",
            d2,
        )
    # the parser for the human's other words is the shared one
    check(
        "redraft: is the shared human_redraft form",
        "redraft:" in human_redraft.NOTE_FORM
        and human_redraft.parse("y redraft: add a scaling factor")
        == "add a scaling factor",
    )
    # copilot names the gate explicitly, as it names s1's and s2's
    import yaml

    cp = yaml.safe_load((REPO / "workflows" / "policies" / "copilot.yaml").read_text())
    check(
        "copilot.yaml declares assembly_redraft_budget: {answer: y} — an attempt, not a fallback",
        cp["answers"].get("assembly_redraft_budget") == {"answer": "y"},
        str(cp["answers"].get("assembly_redraft_budget")),
    )


def test_blind_3_replay_in_the_form_item_4_leaves_it() -> None:
    # the user's live run, not part of the repository: the replay needs its
    # nine-observable reply and its own gate verdict — too much to freeze here
    root = run_root("live_ctd_blind_3", USER_RUNS)
    if not fixture_or_skip(root.store.path, "runs/live_ctd_blind_3.h5"):
        return
    run = rnd(root, 0)
    reply = ((run / "agent_calls").child("observation") / "reply").get()
    ids = [str(o["observable_id"]) for o in reply["observables"]]
    check("nine observables in the live reply", len(ids) == 9, str(len(ids)))
    # the run's magnitude verdict failed; it is advisory, so it routes to nobody
    verdicts = [
        tree.gates_node(run, cid).child("assembly_magnitude_reconciliation")
        for cid in [*tree.candidate_ids(run), None]
    ]
    verdicts = [v for v in verdicts if v.exists()]
    check("the run's own magnitude verdict is in the record", bool(verdicts))
    if verdicts:
        g = verdicts[0].get()
        check("it FAILED in that run", g.get("passed") is False, str(g.get("passed")))
        check(
            "and it is advisory: not attributed, never a stop",
            "assembly_magnitude_reconciliation" in bf.ADVISORY
            and "assembly_magnitude_reconciliation" not in bf.ATTRIBUTION,
        )
    # the payload builder on the same reply, for a resolve failure naming one peak
    gate = GateResult(
        "assembly_observables_resolve",
        "T0",
        False,
        detail=f"{ids[0]}: formula names unknown symbol(s) ['P0_frac']",
    )
    block = bf.observation_block(reply, bf.implicated_ids(gate.detail, ids))
    fb = bf.feedback(bf.gate_record(gate), "observation", block, [], {})
    check(
        "the re-ask context carries the implicated peak's OWN scaling block",
        len(block) == 1
        and block[0]["observable_id"] == ids[0]
        and "scaling" in block[0],
    )
    all_blocks = bf.observation_block(reply, [])
    check(
        "… and with no id named, all nine scaling blocks",
        len(all_blocks) == 9 and all("scaling" in b for b in all_blocks),
    )
    check(
        "the gate detail is verbatim in the payload",
        fb["gate"]["detail"] == gate.detail,
    )


def main() -> int:
    test_every_declared_gate_is_routed()
    test_the_payload_is_verbatim_and_the_agents_own()
    test_magnitude_and_dof_are_advisory_on_real_tables()
    test_fallbacks_produce_their_declared_shapes()
    test_the_gate_advertises_its_forms_and_never_falls_back_unasked()
    test_blind_3_replay_in_the_form_item_4_leaves_it()
    return finish(
        "BATTERY FEEDBACK",
        "BATTERY FEEDBACK OK — every gate routed, the payload verbatim, fallbacks declared and never unasked",
    )


if __name__ == "__main__":
    sys.exit(main())
