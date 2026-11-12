"""A seeded round's S3 inherits the checker's audit; an overlay's delta is audited alone.

Round 0 has an audited shared assembly and an audited winner with an
observation overlay; round 1 is seeded from the winner (`round_seed`). S3 is
run for round-1 candidates with the checker replaced by a canned verdict:

  1. S3 finds the carried audit (`_carried_audit`) and counts the shared
     assembly as audited while it is the seeded one; once it changes, neither;
  2. a candidate without an overlay runs S3 with no checker call, ledgered as
     audited where the seed was built, naming the round-0 records;
  3. a candidate whose overlay changes one noise block is audited on that
     delta only: the checker sees the changed entry before and after and the
     overlay, the verdict is recorded among the candidate's gate verdicts, and its
     lines name the concern;
  4. the identical delta question is answered once: asked again, the stored
     verdict is reused and ledgered, with no second call.

    uv run python tests/carried_audit_unit.py
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import logging
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.WARNING)

from _harness import check_detail_on_fail, finish  # noqa: E402
from _record import rnd, temp_record, work  # noqa: E402

from octomod.orchestration import round_seed  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.orchestration.run_context import RunContext  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import assembly_edit  # noqa: E402
from octomod.workflow_modules.assembly import engine as S3  # noqa: E402

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
ANT = "model m\n  J: A -> ; k*A;\n  A = 10; k = 0.3;\nend\n"
PARAMETERS = [
    {"id": "k", "nominal_value": 0.3, "lb": 1e-3, "ub": 1e3, "estimate": True}
]
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
        {
            "observable_id": "obs_A",
            "distribution": "normal",
            "formula": "sigma_A",
            "estimate_sigma": True,
        }
    ],
    "scaling": [{"observable_id": "obs_A", "mode": "none"}],
    "conditions": [
        {
            "condition_id": "c0",
            "maps_to_label": "c0",
            "overrides": {},
            "preequilibration": False,
        }
    ],
}
WINNER_OVERLAY = [{"add_offset": {"observable_id": "obs_A"}}]
LAPLACE = [
    {"change_noise_model": {"observable_id": "obs_A", "new_distribution": "laplace"}}
]
VERDICT = {
    "overall": "concerns",
    "verdicts": [
        {"aspect": "noise", "ok": False, "note": "laplace on obs_A has no replicate"},
        {"aspect": "scaling", "ok": True, "note": "the offset is unchanged"},
    ],
}


class Ctx(RunContext):
    """A RunContext whose checker is a canned verdict; every call is recorded."""

    def call(self, role: str, context: dict, calls=None) -> dict:
        self.calls.append((role, copy.deepcopy(context)))
        if role != "assembly_verification":
            raise AssertionError(f"only the checker may be asked; {role} was")
        return copy.deepcopy(VERDICT)


def _sbml() -> str:
    import antimony

    antimony.loadAntimonyString(ANT)
    return antimony.getSBMLString(antimony.getMainModuleName())


def _model_dir(model, sbml: str) -> None:
    (model / "antimony").put_text(ANT)
    (model / "sbml").put_text(sbml)
    (model / "parameters").put(PARAMETERS)


def _round0(run, sbml: str) -> None:
    """A finished round: shared assembly audited on `base`, overlay on `w`."""
    r0 = rnd(run, 0)
    (r0 / "data/measurements").put_table(
        pd.DataFrame(
            [
                {
                    "observable_label": "A",
                    "condition_label": "c0",
                    "condition_key": "c0",
                    "time": t,
                    "value": v,
                }
                for t, v in ((0.0, 10.2), (1.0, 7.3), (2.0, 5.6), (4.0, 3.1))
            ]
        )
    )
    (r0 / "data/report").put({"flags": []})
    (r0 / "shared_assembly").put({**SHARED, "_version": 1})
    for cid, overlay in (("base", []), ("w", WINNER_OVERLAY)):
        c = work(run, 0, cid)
        _model_dir(c / "model", sbml)
        if overlay:
            (c / "model/assembly_overlay").put(overlay)
        merged = assembly_edit.apply_overlay(SHARED, overlay, assembly_for_refs=SHARED)
        (c / "assembly").put({**merged, "_shared_version": 1})
        (c / "gates/assembly_verification").put(
            {"gate_id": "assembly_verification", "tier": "T3", "passed": True}
        )
    # the report the next round is seeded from
    (r0 / "evaluation").put(
        {"goal": "prediction", "interpretation": {"recommendation": "revise"}}
    )


def _ctx(run, case: Path, round_idx: int, candidate: str | None) -> Ctx:
    ctx = Ctx(
        root=run,
        testcase_dir=case,
        spec=SPEC,
        ledger=Ledger(run),
        backend="stub",
        auto=False,
        round_idx=round_idx,
        candidate=candidate,
    )
    ctx.calls = []
    return ctx


def _candidate(run, cid: str, sbml: str, overlay: list) -> None:
    """A round-1 candidate at S3: the seeded model, and its own overlay."""
    c = work(run, 1, cid)
    for k in ("antimony", "sbml", "parameters"):
        (rnd(run, 1) / "model" / k).copy_to(c / "model" / k)
    if overlay:
        (c / "model/assembly_overlay").put(overlay)


def _s3(ctx: Ctx):
    """S3 as the orchestrator runs a candidate's, before the cost boundary."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            S3._run_once(ctx)
    except Exception as e:  # noqa: BLE001 — the outcome under test
        return e, buf.getvalue()
    return None, buf.getvalue()


def _notes(ctx: Ctx, cid: str) -> list[dict]:
    return [
        e
        for e in ctx.ledger.entries()
        if e.get("event") == "note"
        and e.get("round") == 1
        and str(e.get("note", "")).startswith(f"candidate {cid}:")
    ]


def test_the_carried_audit_is_found(run, case: Path, seed: dict) -> None:
    ctx = _ctx(run, case, 1, "c1")
    carried = S3._carried_audit(ctx)
    check_detail_on_fail(
        "S3 finds the audit the seed carried: both round-0 records and the "
        "winner's overlay audit",
        carried is not None
        and carried == seed["audit_carried"]
        and carried.get("records")
        == [
            (work(run, 0, "base") / "gates/assembly_verification").key,
            (work(run, 0, "w") / "gates/assembly_verification").key,
        ]
        and carried.get("overlay_audit")
        == (work(run, 0, "w") / "gates/assembly_verification").key,
        json.dumps(carried),
    )
    check_detail_on_fail(
        "the seeded shared assembly counts as audited", S3._shared_audited(ctx)
    )
    shared_p = rnd(run, 1) / "shared_assembly"
    kept = shared_p.get()
    changed = copy.deepcopy(kept)
    changed["noise"][0]["formula"] = "sigma_A_other"
    shared_p.put(changed)
    check_detail_on_fail(
        "once the shared assembly is not the seeded one, nothing is carried",
        S3._carried_audit(ctx) is None and not S3._shared_audited(ctx),
    )
    shared_p.put(kept)


def test_a_candidate_without_overlay_is_not_rechecked(run, case, sbml) -> None:
    _candidate(run, "c1", sbml, [])
    ctx = _ctx(run, case, 1, "c1")
    err, printed = _s3(ctx)
    check_detail_on_fail(
        "S3 passes for the candidate",
        err is None and ctx.marker("s3").exists(),
        f"{err!r}"[:240] + " · " + printed[-300:],
    )
    check_detail_on_fail(
        "and asks the checker nothing: the shared assembly's audit is carried",
        ctx.calls == [],
        str([r for r, _c in ctx.calls]),
    )
    rows = [e for e in _notes(ctx, "c1") if "already audited" in str(e.get("note"))]
    note = str(rows[0].get("note")) if rows else ""
    check_detail_on_fail(
        "ledgered as audited where the seed was built, naming the round-0 records",
        len(rows) == 1
        and rows[0].get("audit_carried") is True
        and "in round_0, where this round's seed was built" in note
        and (work(run, 0, "base") / "gates/assembly_verification").key in note
        and f"its overlay: {(work(run, 0, 'w') / 'gates/assembly_verification').key}"
        in note
        and "checker not re-run" in note,
        note or str(_notes(ctx, "c1"))[:240],
    )
    check_detail_on_fail(
        "no verdict of its own is written for it",
        not (ctx.gates / "assembly_verification").exists(),
    )


def test_an_overlay_delta_is_audited_alone(run, case, sbml) -> None:
    _candidate(run, "c2", sbml, LAPLACE)
    ctx = _ctx(run, case, 1, "c2")
    err, printed = _s3(ctx)
    check_detail_on_fail(
        "S3 passes for the candidate with an overlay",
        err is None and ctx.marker("s3").exists(),
        f"{err!r}"[:240] + " · " + printed[-300:],
    )
    check_detail_on_fail(
        "the checker is asked once",
        [r for r, _c in ctx.calls] == ["assembly_verification"],
        str([r for r, _c in ctx.calls]),
    )
    asked = ctx.calls[0][1] if ctx.calls else {}
    shared = (rnd(run, 1) / "shared_assembly").get()
    before = shared["noise"][0]
    check_detail_on_fail(
        "it is shown the changed noise entry only, before and after, and the overlay",
        asked.get("changed_entries")
        == {
            "noise": [
                {"before": before, "after": {**before, "distribution": "laplace"}}
            ]
        }
        and [a.get("patch") for a in asked.get("overlay") or []] == LAPLACE
        and "Audit ONLY the changed entries" in str(asked.get("audit_scope")),
        json.dumps(asked.get("changed_entries"))[:300],
    )
    check_detail_on_fail(
        "and nothing of the shared assembly's tables beyond the observables",
        "conditions_tsv" not in asked
        and "parameters_tsv" not in asked
        and "observables_tsv" in asked,
        str(sorted(asked)),
    )
    rec = (ctx.gates / "assembly_verification").get(None) or {}
    check_detail_on_fail(
        "the delta's verdict is recorded among the candidate's gate verdicts, advisory",
        rec.get("gate_id") == "assembly_verification"
        and rec.get("blocking") is False
        and "overlay delta: noise: laplace on obs_A" in str(rec.get("detail")),
        str(rec)[:240],
    )
    ctx_again = _ctx(run, case, 1, "c2")
    with contextlib.redirect_stdout(io.StringIO()):
        lines = S3._audit_overlay_delta(
            ctx_again, ctx_again.work / "petab", {"flags": []}
        )
    check_detail_on_fail(
        "its lines name the concern and the clean aspect",
        lines
        == [
            "checker[noise]: CONCERN — laplace on obs_A has no replicate",
            "checker[scaling]: ok",
        ],
        str(lines),
    )
    reused = [
        e
        for e in ctx_again.ledger.entries()
        if e.get("overlay_audit_reused") == "c2" and e.get("round") == 1
    ]
    check_detail_on_fail(
        "the identical question asked again reuses the stored verdict, with no call",
        ctx_again.calls == [] and len(reused) == 1,
        f"{len(ctx_again.calls)} call(s), {len(reused)} reuse row(s)",
    )


def main() -> int:
    with temp_record("run") as run:
        case = run.store.path.parent / "input"
        case.mkdir()
        (case / "testcase.yaml").write_text(
            "name: carried_audit\nt_end: 4\nholdout:\n  condition_labels: []\n"
        )
        (run / "intent").put({"question": "how fast is A cleared?"})
        sbml = _sbml()
        _round0(run, sbml)
        seed = round_seed.seed_round(
            _ctx(run, case, 0, None),
            rnd(run, 1),
            candidate="w",
            why="the criterion winner w",
        )
        for marker in ("s1", "s2"):
            (rnd(run, 1) / "status/markers" / marker).put({})
        test_the_carried_audit_is_found(run, case, seed)
        test_a_candidate_without_overlay_is_not_rechecked(run, case, sbml)
        test_an_overlay_delta_is_audited_alone(run, case, sbml)
    return finish(
        "\nCARRIED AUDIT",
        "\nCARRIED AUDIT UNIT OK — a seeded round's S3 inherits the checker's audit "
        "while the assembly is the seeded one, and an overlay is audited on its "
        "delta alone, once",
    )


if __name__ == "__main__":
    sys.exit(main())
