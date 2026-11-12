"""A round starts from exactly the model it was seeded from (`round_seed.py`).

  1. seeding copies the model files byte for byte; the merged assembly becomes the shared one;
  2. the checker's audit travels only while it covers the whole assembly;
  3. a `--from-module` re-entry gets the seed back: in a seeded round it is an input;
  4. a rebuilt base takes the decided observation axes;
  5. `base_identity` says "identical" for the seeded problem, else names what differs and why;
  6. the SBML is a function of the Antimony: libantimony's modifier order is made canonical;
  7. a round is seeded only from a report whose evaluation slot validates, and the
     orchestrator validates it before the offer or the revision reads it.

    uv run python tests/round_seed_unit.py
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod.orchestration import round_seed, round_status  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.workflow_modules.assembly import assembly_edit, petab_io  # noqa: E402
from tests._record import rnd, temp_record, work  # noqa: E402

PETAB = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"

SHARED = {
    "observables": [
        {
            "observable_id": "obs_A",
            "maps_to_label": "A",
            "formula": "A",
            "transformation": "lin",
        }
    ],
    "noise": [
        {"observable_id": "obs_A", "distribution": "normal", "formula": "sigma_A"}
    ],
    "scaling": [{"observable_id": "obs_A", "mode": "none"}],
    "conditions": [{"condition_id": "c0", "overrides": {}}],
    "_version": 2,
}
OVERLAY = [{"add_offset": {"observable_id": "obs_A"}}]
ANT = "model m\n  J: A -> ; k*A;\n  A = 1; k = 0.1;\nend\n"


class _Ctx:
    """What round_seed (and the evaluation slot's validator) takes off a RunContext."""

    def __init__(self, run: Node, r: int):
        self.root, self.round_idx, self.candidate = run, r, None
        self.ledger = Ledger(run.store)

    @property
    def store(self):
        return self.root.store

    @property
    def round(self) -> Node:
        return tree.round_node(self.root, self.round_idx)

    @property
    def gates(self) -> Node:
        return tree.gates_node(self.round, None)


def _ctx(run: Node, r: int) -> _Ctx:
    return _Ctx(run, r)


def _same(a: Node, b: Node) -> bool:
    """Two records are byte for byte the same."""
    return a.exists() and b.exists() and a.sha() == b.sha()


def finished_report(round_node: Node) -> Node:
    """What S7 leaves in a finished round: the report the next round is seeded from
    (`evaluation`)."""
    rep = round_node / "evaluation"
    rep.put({"goal": "prediction", "interpretation": {"recommendation": "revise"}})
    return rep


def _candidate(round_node: Node, cid: str, *, overlay: list, audited: bool) -> Node:
    """A fitted candidate as S1-S6 leave it: model, merged assembly, PEtab, fit, audit."""
    c = tree.work_node(round_node, cid)
    inp = petab_io.from_dir(PETAB)
    (c / "model/antimony").put_text(ANT)
    (c / "model/sbml").put_text((PETAB / "model.xml").read_text())
    (c / "model/parameters").put([{"id": "k", "estimate": True}])
    (c / "model/glossary").put({"A": "a species"})
    if overlay:
        (c / "model/assembly_overlay").put(overlay)
    if overlay:
        inp = inp.with_tables(
            parameters=pd.concat(
                [
                    inp.parameters,
                    pd.DataFrame(
                        [
                            {
                                "parameterId": "off_obs_A",
                                "parameterScale": "lin",
                                "lowerBound": -5,
                                "upperBound": 5,
                                "nominalValue": 0,
                                "estimate": 1,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        )
    petab_io.to_record(inp, c / "petab")
    merged = assembly_edit.apply_overlay(SHARED, overlay, assembly_for_refs=SHARED)
    (c / "assembly").put({**merged, "_shared_version": 2})
    (c / "multistart").put_text("x")
    if audited:
        (c / "gates/assembly_verification").put({})
    return c


def _round0(run: Node, *, winner_audited: bool = True) -> Node:
    r0 = rnd(run, 0)
    (r0 / "data/measurements").put_table(pd.DataFrame({"x": ["x"]}))
    (r0 / "shared_assembly").put(SHARED)
    _candidate(r0, "base", overlay=[], audited=True)  # the shared audit
    _candidate(r0, "w", overlay=OVERLAY, audited=winner_audited)  # its overlay's
    finished_report(r0)
    return r0


def test_the_seed_is_the_chosen_candidate_exactly() -> None:
    with temp_record() as run:
        _round0(run)
        w = work(run, 0, "w")
        r1 = rnd(run, 1)
        rec = round_seed.seed_round(
            _ctx(run, 0), r1, candidate="w", why="the criterion winner w"
        )
        same_files = all(
            _same(w / "model" / f, r1 / "model" / f) for f in round_seed.MODEL_FILES
        )
        check("its model files are copied byte for byte", same_files)
        shared1 = (r1 / "shared_assembly").get()
        winner_asm = (w / "assembly").get()
        check(
            "the next round's shared assembly is the winner's MERGED one",
            shared1 == round_seed.assembly_content(winner_asm)
            and shared1["scaling"][0]["mode"] == "offset",
            str(shared1["scaling"]),
        )
        check(
            "the per-round bookkeeping does not travel",
            "_version" not in shared1 and "_shared_version" not in shared1,
        )
        check(
            "the record names the candidate, its problem, its estimated parameters and its fit",
            rec["candidate"] == "w"
            and rec["problem"]
            and "off_obs_A" in rec["estimated_parameters"]
            and rec["fit"] == w.key
            and rec["observation_overlay"] == OVERLAY,
            json.dumps({k: rec[k] for k in ("candidate", "problem", "fit")}),
        )
        audit = rec["audit_carried"]
        check(
            "the audit that covered it travels: the shared audit and its overlay's",
            audit
            and (work(run, 0, "base") / "gates/assembly_verification").key
            in audit["records"]
            and audit["overlay_audit"] == (w / "gates/assembly_verification").key,
            json.dumps(audit),
        )
        check(
            "it counts while the assembly is the seeded one",
            round_seed.carried_audit(r1, shared1) is not None,
        )
        changed = json.loads(json.dumps(shared1))
        changed["noise"][0]["distribution"] = "laplace"
        check(
            "and stops counting the moment the assembly changes",
            round_seed.carried_audit(r1, changed) is None,
        )
        (r1 / "shared_assembly").delete()
        check("a re-entry gets the seed back", round_seed.restore_shared(r1))
        check(
            "… identical to what was seeded",
            (r1 / "shared_assembly").get() == shared1,
        )
        check(
            "and a present shared assembly is never overwritten",
            not round_seed.restore_shared(r1),
        )


def test_a_reentry_gets_the_seeded_model_back() -> None:
    """`--from-module model` moves the model slot aside; in a seeded round it is the seed."""
    with temp_record() as run:
        r0 = _round0(run)
        w = work(run, 0, "w")
        r1 = rnd(run, 1)
        round_seed.seed_round(
            _ctx(run, 0), r1, candidate="w", why="the criterion winner w"
        )
        for f in round_seed.MODEL_FILES:
            (r1 / "model" / f).delete()
        check(
            "a re-entry that moved the seed aside gets it back",
            round_seed.restore_model(run, r1),
        )
        check(
            "… the winner's model files byte for byte",
            all(
                _same(w / "model" / f, r1 / "model" / f)
                for f in round_seed.MODEL_FILES
                if (w / "model" / f).exists()
            ),
        )
        check(
            "a present model is never overwritten",
            not round_seed.restore_model(run, r1),
        )
        # the seed's data travels too, and a re-entry gets it back
        (r0 / "data/measurements").put_table(
            pd.DataFrame({"observableId": ["obs_A"], "condition": ["c0"]})
        )
        round_seed.seed_round(
            _ctx(run, 0), r1, candidate="w", why="the criterion winner w"
        )
        (r1 / "data/measurements").delete()
        check(
            "a re-entry gets the seeded measurement table back",
            round_seed.restore_data(run, r1),
        )
        check(
            "… and a present table is never overwritten",
            not round_seed.restore_data(run, r1),
        )
        # a rebuilt seed, which no candidate folder holds
        r2 = rnd(run, 2)
        ant = (w / "model/antimony").text()
        round_seed.seed_round(
            _ctx(run, 0),
            r2,
            candidate=None,
            why="rebuilt base",
            antimony=ant,
            parameters=[{"id": "k1", "nominal_value": 1.0, "estimate": True}],
            glossary_from="w",
        )
        for f in round_seed.MODEL_FILES:
            (r2 / "model" / f).delete()
        check(
            "a rebuilt seed is restored from its own record",
            round_seed.restore_model(run, r2),
        )
        check("… with its Antimony", (r2 / "model/antimony").text() == ant)


def test_an_unaudited_overlay_does_not_travel_as_audited() -> None:
    with temp_record() as run:
        _round0(run, winner_audited=False)
        rec = round_seed.seed_round(_ctx(run, 0), rnd(run, 1), candidate="w", why="w")
        check(
            "an overlay nobody audited leaves the next round's checker to run",
            rec["audit_carried"] is None,
        )


def test_an_inherited_audit_travels_on() -> None:
    """A round that carried its audit passes it to the next seed."""
    with temp_record() as run:
        _round0(run)
        r1 = rnd(run, 1)
        first = round_seed.seed_round(_ctx(run, 0), r1, candidate="w", why="w")
        c = _candidate(r1, "w2", overlay=[], audited=False)
        finished_report(r1)
        shared1 = (r1 / "shared_assembly").get()
        (c / "assembly").put({**shared1, "_shared_version": 2})
        second = round_seed.seed_round(
            _ctx(run, 1), rnd(run, 2), candidate="w2", why="w2"
        )
        check(
            "the audit round 1 inherited travels to round 2 (no re-audit)",
            second["audit_carried"] == first["audit_carried"] is not None,
            json.dumps(second["audit_carried"]),
        )
        (r1 / "shared_assembly").put(
            {**shared1, "noise": [{**shared1["noise"][0], "formula": "s2"}]}
        )
        third = round_seed.seed_round(
            _ctx(run, 1), rnd(run, 3), candidate="w2", why="w2"
        )
        check(
            "… but not once round 1's shared assembly differs from the seeded one",
            third["audit_carried"] is None,
            json.dumps(third["audit_carried"]),
        )


def test_rebuild_takes_the_decided_observation_axes() -> None:
    with temp_record() as run:
        _round0(run)
        r1 = rnd(run, 1)
        rec = round_seed.seed_round(
            _ctx(run, 0),
            r1,
            candidate=None,
            why="base plus the decided axes (rebuilt)",
            antimony=ANT,
            parameters=[{"id": "k", "estimate": True}],
            overlay=OVERLAY,
            glossary_from="w",
        )
        shared1 = (r1 / "shared_assembly").get()
        check(
            "the decided observation axis is in the rebuilt base's assembly",
            shared1["scaling"][0]["mode"] == "offset",
            str(shared1["scaling"]),
        )
        check(
            "the rebuilt model is written and builds",
            (r1 / "model/antimony").text() == ANT
            and "<sbml" in (r1 / "model/sbml").text()
            and (r1 / "model/glossary").exists(),
        )
        check(
            "a rebuild claims no fitted problem and no audit of its new overlay",
            rec["problem"] is None
            and rec["fit"] is None
            and rec["audit_carried"] is None,
        )


def test_base_identity_names_what_the_base_lost() -> None:
    with temp_record() as run:
        _round0(run)
        w = work(run, 0, "w")
        r1 = rnd(run, 1)
        round_seed.seed_round(_ctx(run, 0), r1, candidate="w", why="w")
        base = work(run, 1, "base")
        (w / "model").copy_to(base / "model")
        (w / "petab").copy_to(base / "petab")
        ctx1 = _ctx(run, 1)
        ident = round_seed.base_identity(ctx1, ["base", "new_axis"])
        check(
            "the seeded problem is recognised as identical",
            ident and ident["identical"],
            json.dumps(ident),
        )
        check(
            "and the card says its fit is reused",
            any(
                "exactly" in ln and "reused" in ln
                for ln in round_seed.identity_lines(ident)
            ),
        )
        # a base that lost the winner's offset between the rounds
        pars = (base / "petab/parameters").table()
        (base / "petab/parameters").put_table(
            pars[pars["parameterId"] != "off_obs_A"].reset_index(drop=True)
        )
        ident = round_seed.base_identity(ctx1, ["base", "new_axis"])
        check(
            "a base that lost a parameter is named, with what it lost",
            ident
            and not ident["identical"]
            and ident["lost"] == ["off_obs_A"]
            and "petab/parameters" in ident["differs_in"]
            and ident["why"].startswith("unexplained"),
            json.dumps(ident),
        )
        lines = round_seed.identity_lines(ident)
        check(
            "the card line is loud and names the parameter",
            lines[0].startswith(f"** base is NOT {w.key}") and "off_obs_A" in lines[1],
            " | ".join(lines),
        )
        ctx1.ledger.append(
            "note",
            module="assembly_cost_boundary",
            round_idx=1,
            note="redraft",
            human_redraft=True,
        )
        ident = round_seed.base_identity(ctx1, ["base", "new_axis"])
        check(
            "a redraft the human asked for is the stated reason",
            "redrafted" in ident["why"],
            ident["why"],
        )
        check(
            "a round not seeded from a candidate makes no claim",
            round_seed.base_identity(_ctx(run, 0), ["base"]) is None,
        )


def test_the_sbml_is_a_function_of_the_antimony() -> None:
    """Byte identity needs it: libantimony orders inferred modifiers by internal state."""
    from octomod.gates.build_gates import antimony_to_sbml, canonical_sbml

    block = (
        '<reaction id="J3">\n        <listOfModifiers>\n'
        '          <modifierSpeciesReference species="D"/>\n'
        '          <modifierSpeciesReference species="Aa"/>\n'
        "        </listOfModifiers>\n"
    )
    fixed = canonical_sbml(block)
    check(
        "modifiers are put in species order, the formatting kept",
        fixed.index('species="Aa"') < fixed.index('species="D"')
        and fixed.count("\n") == block.count("\n"),
        fixed,
    )
    check("canonical twice is canonical once", canonical_sbml(fixed) == fixed)
    odd = block.replace(
        '<modifierSpeciesReference species="D"/>',
        '<modifierSpeciesReference species="D"><notes/></modifierSpeciesReference>',
    )
    check(
        "a block with anything but plain modifiers is left as it is",
        canonical_sbml(odd) == odd,
    )
    ant = (
        "model m\n  J1: A -> B; k1*A*C*D;\n  J2: B -> A; k2*B*D*C;\n"
        "  A = 1; B = 0; C = 1; D = 1; k1 = 0.1; k2 = 0.2;\nend\n"
    )
    first, _ = antimony_to_sbml(ant)
    for other in (
        "model o\n  J: X -> Y; k*X*Z;\n  X = 1; Y = 0; Z = 2; k = 1;\nend\n",
        "model p\n  J: D -> C; q*D*A*B;\n  A = 1; B = 1; C = 0; D = 1; q = 1;\nend\n",
    ):
        antimony_to_sbml(other)
    again, _ = antimony_to_sbml(ant)
    check(
        "the same Antimony gives the same SBML after other models were loaded",
        first == again,
    )


def test_a_round_is_seeded_only_from_a_report_that_validates() -> None:
    """The next round is built from the source round's report: one that lost
    its interpretation, or was never written, is refused by name before
    anything is copied; an intact one seeds, with its check on record."""
    from octomod.orchestration.run_context import ModuleFailure

    for label, broken in (
        ("no interpretation", {"goal": "prediction"}),
        ("no report", None),
    ):
        with temp_record() as run:
            rep = finished_report(_round0(run))
            if broken is None:
                rep.delete()
            else:
                rep.put(broken)
            r1 = rnd(run, 1)
            try:
                # the gate runner prints the failing check; the refusal is what is read
                with contextlib.redirect_stdout(io.StringIO()):
                    round_seed.seed_round(_ctx(run, 0), r1, candidate="w", why="w")
                msg = None
            except ModuleFailure as e:
                msg = str(e)
            check(
                f"({label}) seeding is refused, naming the evaluation slot and "
                f"its record (`evaluation`)",
                msg is not None and "evaluation slot" in msg and "(evaluation)" in msg,
                str(msg),
            )
            named = (
                "entry_evaluation_schema" in (msg or "")
                and "lacks ['interpretation']" in (msg or "")
                if broken
                else "missing ['evaluation']" in (msg or "")
            )
            check(f"({label}) … and what failed", named, str(msg))
            check(f"({label}) nothing of the next round is written", not r1.exists())

    with temp_record() as run:
        _round0(run)
        ctx = _ctx(run, 0)

        def checked() -> list[dict]:
            return [
                e
                for e in ctx.ledger.entries()
                if e.get("event") == "gate" and e.get("module") == "entry_evaluation"
            ]

        round_seed.seed_round(ctx, rnd(run, 1), candidate="w", why="w")
        rows = checked()
        check(
            "an intact report seeds, and the check it passed is on record",
            (rnd(run, 1) / round_seed.SEED_KEY).exists()
            and [(r["gate_id"], r["passed"]) for r in rows]
            == [("entry_evaluation_schema", True)],
            str(rows),
        )
        round_seed.seed_round(ctx, rnd(run, 2), candidate="w", why="w")
        check(
            "a report validated at its current content is not checked again",
            len(checked()) == 1,
            str(len(checked())),
        )
        (rnd(run, 0) / "evaluation").put({"goal": "prediction"})
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                round_seed.seed_round(ctx, rnd(run, 3), candidate="w", why="w")
            refused = False
        except ModuleFailure:
            refused = True
        check(
            "… but a report that changed since it was validated is validated again",
            refused and len(checked()) == 2 and not rnd(run, 3).exists(),
            f"refused={refused}, {len(checked())} check(s)",
        )
        finished_report(rnd(run, 0))
        rec = round_status.load(rnd(run, 0))["slots"].get("evaluation") or {}
        check(
            "the slot's record names the engine as its producer, not a person",
            rec.get("producer") == "engine"
            and str(rec.get("validated_by")).startswith("entry_evaluation"),
            str(rec),
        )


def test_the_orchestrator_validates_before_it_reads() -> None:
    src = (REPO / "octomod" / "orchestration" / "orchestrator.py").read_text()
    call = "_seed.require_evaluation(self.ctx)"
    exp = src[
        src.index("    def _maybe_expand_space(") : src.index("    def _model_of(")
    ]
    check(
        "the expansion offer validates the report before it reads the winner",
        call in exp
        and exp.index(call) < exp.index('winner = report["discrimination"]["winner"]'),
    )
    loop = src[src.index("    def _run_single_model_loop(") :]
    i = loop.index("report = evaluation_module.run(")
    check(
        "the revision loop validates the report before it reads the "
        "recommendation the next round is seeded on",
        call in loop[i:]
        and loop.index(call, i)
        < loop.index('report["interpretation"]["recommendation"]', i),
    )


def main() -> int:
    print("a round starts from exactly the model it was seeded from")
    test_the_sbml_is_a_function_of_the_antimony()
    test_the_seed_is_the_chosen_candidate_exactly()
    test_a_reentry_gets_the_seeded_model_back()
    test_an_unaudited_overlay_does_not_travel_as_audited()
    test_an_inherited_audit_travels_on()
    test_rebuild_takes_the_decided_observation_axes()
    test_base_identity_names_what_the_base_lost()
    test_a_round_is_seeded_only_from_a_report_that_validates()
    test_the_orchestrator_validates_before_it_reads()
    return finish("\nROUND SEED", "ROUND SEED OK")


if __name__ == "__main__":
    sys.exit(main())
