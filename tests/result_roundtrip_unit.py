"""The result record survives HDF5 unchanged.

mkstd's HDF5 path goes through hdfdict, and three habits of a stock packer
are ones a record cannot live with: an empty string coming back as `[]`, a
non-ASCII string failing on load, and a dict key containing '/' becoming a
nested group. The pinned mkstd (0.0.13) has none of them; this suite pins
every one of those cases so a version bump of mkstd, h5py or pydantic that
breaks the round trip fails HERE, not in a run. The whole-record write is
`RunStore.write_all` (export copies, the legacy import); the engine itself
writes the record one group at a time.

Also asserted: `prune` keeps only the named tiers and records what it removed,
`select_rounds` reduces the other rounds and says so, the schema names every
record, a whole-record write over an existing file leaves no temporary file
behind, and a pruned copy is a separate file that is never the run's record.

    uv run python tests/result_roundtrip_unit.py
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.result import (  # noqa: E402
    AgentCallRecord,
    CandidateRecord,
    DecisionRecord,
    GateRecord,
    LedgerEvent,
    RoundRecord,
    RunMeta,
    RunOutcome,
    RunResult,
    Table,
    commit,
    load,
    prune,
    schema_json,
)
from octomod.result.records import AttemptRecord  # noqa: E402
from octomod.result.runstore import RunStore  # noqa: E402
from octomod.result.slots import (  # noqa: E402
    DataRecord,
    EstimationRecord,
    EvaluationRecord,
    ModelRecord,
)
from octomod.result.store import select_rounds  # noqa: E402


def _diffs(x, y, path=""):
    if isinstance(x, dict) and isinstance(y, dict):
        for k in set(x) | set(y):
            if k not in x or k not in y:
                yield f"{path}/{k}: only on one side"
                continue
            yield from _diffs(x[k], y[k], f"{path}/{k}")
    elif isinstance(x, (list, tuple)) and isinstance(y, (list, tuple)):
        if len(x) != len(y):
            yield f"{path}: length {len(x)} vs {len(y)}"
            return
        for i, (u, v) in enumerate(zip(x, y, strict=False)):
            yield from _diffs(u, v, f"{path}[{i}]")
    else:
        if (
            isinstance(x, float)
            and isinstance(y, float)
            and math.isnan(x)
            and math.isnan(y)
        ):
            return
        if x != y:
            yield f"{path}: {x!r} != {y!r}"


def _fixture() -> RunResult:
    """Every awkward value the real runs contain, in one small record."""
    gate_a = GateRecord(
        gate_id="estimation_waterfall_plateau",
        tier="T2",
        passed=True,
        value=100,
        threshold=">=3 starts within 0.5 of best",
        detail="best −209.59; plateau 100/100 — non-ASCII on purpose",
        module="estimation",
        round=0,
    )
    gate_b = GateRecord(
        gate_id="model_required_entities",
        tier="T0",
        passed=True,
        blocking=False,
        value={"missing": ["KinA_p", "RegB_p"]},
        threshold=None,
        advisory_findings=[{"aspect": "naming", "text": "µM units"}],
    )
    gate_c = GateRecord(
        gate_id="evaluation_t2prime_holdout",
        tier="T2prime",
        passed=False,
        value=0.0,
        threshold="p >= 0.01",
        detail="",
    )
    est = EstimationRecord(
        optimizer="fides",
        seed=20260914,
        n_starts=3,
        n_data=192,
        x_names=["k_act", "k_deg"],
        best_fval=-169.143,
        best_x_unscaled={"k_act": 0.0776, "k_deg": 0.0204},
        fvals=[-169.143, -169.1, -100.5],
        ensemble=[0, 1],
        at_bounds=[],
        near_bounds=[{"id": "k_deg", "log10_distance": 0.3}],
    )
    # the multistart's per-start table and arrays are the candidate's own
    # siblings of `estimation`, not fields of it
    starts = Table(
        columns=["id", "fval", "time_s", "n_grad", "note"],
        data={
            "id": [0, 1, 2],
            "fval": [-169.143, -169.1, float("nan")],
            "time_s": [0.5, 0.6, 0.7],
            "n_grad": [10, 11, 12],
            "note": ["", "ok", None],
        },
    )
    multistart = {
        "x": [[0.1, 0.2], [0.11, 0.21], [0.5, 0.9]],
        "x0": [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]],
        "fval": [-169.143, -169.1, -100.5],
    }
    data = DataRecord(
        measurements=Table(
            columns=["observable_label", "time", "value"],
            data={
                "observable_label": ["A", "A", "B"],
                "time": [0, 5, 10],
                "value": [0.0, 1.5, 2.5],
            },
        ),
        report={"observable_labels": ["A", "B"], "flags": [], "notes": ""},
        n_rows=3,
    )
    cand = CandidateRecord(
        id="product_feedback",
        axes_on=["product_feedback"],
        model=ModelRecord(
            antimony="A -> B; k*A;", sbml="<sbml/>", producer="agent:construction"
        ),
        estimation=est,
        starts=starts,
        multistart=multistart,
        refit={"bought": True, "why": "σ 1.58× — a refit"},
        gates={g.gate_id: g for g in (gate_a, gate_c)},
        markers={"s6": {"best_fval": -169.143, "n_ensemble": 2}},
    )
    round0 = RoundRecord(
        index=0,
        shape="candidate_set",
        model=ModelRecord(
            antimony="A -> B; k*A;", sbml="<sbml/>", producer="agent:construction"
        ),
        data=data,
        candidates={"base": CandidateRecord(id="base"), cand.id: cand},
        evaluation=EvaluationRecord(
            goal="prediction",
            best_fval=-169.143,
            fit=[{"observable": "A", "rmse": 0.05}],
            misfit_evidence={"open": True, "reasons": ["σ 1.58× over the floor"]},
            t2prime_passed=False,
        ),
        evaluation_core={"best_fval": -169.143, "fit": []},
        attribution={"per_observable": {"A": {"share": 0.5}}},
        decisions={
            "evaluation_verdict": DecisionRecord(
                module="evaluation_verdict",
                approved=True,
                note="",
                mode="file",
                signed="human",
            ),
            "model_scope": DecisionRecord(
                module="model_scope", approved=True, note="axes: product_feedback"
            ),
        },
        agent_calls={
            "construction": AgentCallRecord(
                role="construction",
                reply={"antimony": "A -> B; k*A;", "model_space": []},
                prompt="# Inputs\n\n## intent — with a dash — and µ\n",
                attempts=[AttemptRecord(attempt=1, text="{}", gate_failures=[])],
                calls=[
                    LedgerEvent(
                        ts="2026-09-20T17:00:00", event="agent_call", cost_usd=0.0
                    )
                ],
            )
        },
        gates={gate_b.gate_id: gate_b},
        decisions_md="# decisions\n",
    )
    round1 = RoundRecord(index=1, shape="single", directive="Add a reaction: …")
    return RunResult(
        run=RunMeta(
            run_id="fixture", backend="stub", provenance={"git": {"dirty": True}}
        ),
        rounds={"round_0": round0, "round_1": round1},
        ledger=[
            LedgerEvent(
                ts="2026-09-20T17:00:00", event="run_start", workflow_sha="abc"
            ),
            LedgerEvent(
                ts="2026-09-20T17:05:00",
                round=0,
                module="estimation",
                event="gate",
                gate_id="x",
            ),
        ],
        outcome=RunOutcome(outcome="completed", final_round=1),
        analysis={
            "models_assessed": [{"model": "base", "path/with/slash": 1}],
            "n_rounds": 2,
            "by_label": {"": "an empty label", "a/b": 2, "100%": 3},
        },
    )


def test_roundtrip_is_lossless() -> None:
    rr = _fixture()
    with tempfile.TemporaryDirectory() as d:
        path = commit(rr, Path(d) / "fixture.h5")
        assert path.name == "fixture.h5" and path.exists()
        back = load(path)
    # `load` derives the time account from the ledger when the record
    # carries none; a reading filled on load is not a change in what was
    # stored, so it is left out of the comparison on both sides
    before, after = rr.model_dump(), back.model_dump()
    before.pop("timing", None), after.pop("timing", None)
    diffs = list(_diffs(before, after))
    assert not diffs, "the HDF5 round trip changed the record:\n  " + "\n  ".join(
        diffs[:20]
    )
    # the three hdfdict habits, each named
    r0 = back.round(0)
    assert (
        r0.decisions["evaluation_verdict"].note == ""
    ), "an empty string came back as something else"
    assert (
        "−209.59"
        in r0.candidates["product_feedback"]
        .gates["estimation_waterfall_plateau"]
        .detail
    )
    assert (
        "path/with/slash" in back.analysis["models_assessed"][0]
    ), "a '/' key was not restored"
    cand = r0.candidates["product_feedback"]
    assert cand.multistart["x"] == [[0.1, 0.2], [0.11, 0.21], [0.5, 0.9]]
    assert cand.starts.data["note"] == ["", "ok", None]
    assert math.isnan(cand.starts.data["fval"][2])
    assert cand.refit["why"].startswith("σ"), "a candidate sibling survives"
    assert r0.attribution["per_observable"]["A"]["share"] == 0.5
    assert r0.gates["model_required_entities"].value == {
        "missing": ["KinA_p", "RegB_p"]
    }
    assert r0.candidates["base"].model is None
    print(
        "  roundtrip     lossless, including '', non-ASCII, '/' keys, NaN, None, nested lists"
    )


def test_commit_is_atomic_and_overwrites() -> None:
    rr = _fixture()
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "copy.h5"
        commit(rr, target)
        rr.outcome = RunOutcome(outcome="stopped", reason="second commit")
        commit(rr, target)
        leftovers = [p.name for p in Path(d).iterdir() if p.name != "copy.h5"]
        assert not leftovers, f"temporary files left behind: {leftovers}"
        assert load(target).outcome.outcome == "stopped"
        # the ledger written whole reads back row by row, as the engine's does
        assert [r["event"] for r in RunStore(target).ledger_rows()] == [
            "run_start",
            "gate",
        ]
    print("  commit        atomic: second write replaces the first, no .tmp left")


def test_prune_drops_tiers_and_says_so() -> None:
    rr = _fixture()
    core = prune(rr, ["core"])
    assert core.ledger == [] and "ledger" in core.elided
    assert core.analysis is None and "analysis" in core.elided
    cand = core.round(0).candidates["product_feedback"]
    est = cand.estimation
    assert est.fvals == [] and "fvals" in est.elided
    assert cand.multistart is None and cand.starts is None
    assert {"multistart", "starts"} <= set(cand.elided)
    assert est.best_fval == -169.143, "core fields must survive"
    assert cand.refit is not None, "the refit record is core"
    r0 = core.round(0)
    assert r0.attribution is None and "attribution" in r0.elided
    assert r0.evaluation_core is not None, "the computed core is core"
    call = core.round(0).agent_calls["construction"]
    assert call.prompt is None and call.attempts == [] and "prompt" in call.elided
    assert call.reply is not None, "the accepted reply is core"
    assert (
        core.round(0).data.measurements is None
        and core.round(0).data.report is not None
    )
    # the original is untouched
    assert rr.ledger and rr.round(0).candidates["product_feedback"].estimation.fvals
    bulk = prune(rr, ["core", "bulk"])
    assert bulk.round(0).candidates["product_feedback"].multistart is not None
    assert bulk.round(0).attribution is not None
    assert bulk.round(0).agent_calls["construction"].prompt is None
    try:
        prune(rr, ["everything"])
    except ValueError as e:
        assert "unknown tier" in str(e)
    else:
        raise AssertionError("an unknown tier must be refused")
    with tempfile.TemporaryDirectory() as d:
        p = commit(core, Path(d) / "core.h5")
        assert load(p).round(0).elided == core.round(0).elided
    print(
        "  prune         core copy drops bulk+audit, lists every removed field, still valid"
    )


def test_select_rounds_reduces_the_others() -> None:
    rr = _fixture()
    only1 = select_rounds(rr, [1])
    r0 = only1.round(0)
    assert r0.candidates == {} and r0.model is None and r0.data is None
    assert {"candidates", "model", "data", "evaluation"} <= set(r0.elided)
    assert r0.decisions, "decisions are kept on a reduced round"
    assert only1.round(1).directive == "Add a reaction: …"
    print(
        "  select_rounds the other round keeps index, decisions, selection; the rest elided"
    )


def test_a_pruned_copy_is_never_served_as_the_record() -> None:
    """A pruned copy is a SEPARATE file. The CLI refuses to prune the run's
    own record in place (exit 2, record untouched), refuses an `--out` that
    names the record itself — `runs/<id>.h5`, or `runs/<id>`, which names it
    too because `commit` appends `.h5` — and `commit` itself refuses a pruned record
    over any existing file, so the guard is not the CLI's alone. The CLI runs
    in-process against a throwaway `RUNS_DIR`: nothing under runs/ is made."""
    import contextlib
    import io

    from octomod import config
    from octomod.cli import main
    from octomod.result.access import record_for

    def cli(*argv: str) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            rc = main(list(argv))
        return rc, err.getvalue()

    rr = _fixture()
    export = ("export", "--run-id", "fixture", "--tiers", "core")
    with tempfile.TemporaryDirectory() as d:
        runs_dir, config.RUNS_DIR = config.RUNS_DIR, Path(d)
        try:
            live = RunStore.for_run(Path(d), "fixture")
            live.write_all(rr)
            before = live.path.read_bytes()
            rc, err = cli(*export)
            assert rc == 2 and "never pruned in place" in err, (rc, err)
            # --out naming the record, with or without .h5, or its checkpoint
            for out in (live.path, live.path.with_suffix(""), live.backup_path):
                rc, err = cli(*export, "--out", str(out))
                assert rc == 2 and "own record" in err, (out, rc, err)
                assert live.path.read_bytes() == before, f"--out {out} rewrote the run"
            copy = Path(d) / "core_copy.h5"
            rc, err = cli(*export, "--out", str(copy))
            assert rc == 0, err
            assert load(copy).ledger == [] and "ledger" in load(copy).elided
            assert record_for(live).ledger, "the copy did not replace the record"
            # the store's own guard: a pruned record never lands on an existing
            # file — the caller deletes an old copy first
            try:
                commit(prune(rr, ["core"]), live.path)
            except FileExistsError as e:
                assert "pruned" in str(e), str(e)
            else:
                raise AssertionError("commit wrote a pruned record over a file")
            assert live.path.read_bytes() == before
            rc, err = cli(*export, "--out", str(copy))
            assert rc == 2 and "pruned" in err, (rc, err)
            commit(rr, copy)  # a whole record may still replace a file
            assert load(copy).ledger
        finally:
            config.RUNS_DIR = runs_dir
    print(
        "  whole record  a pruned copy needs --out, never the record's own path; "
        "commit refuses a pruned record over an existing file"
    )


def test_schema_names_every_record() -> None:
    schema = json.loads(schema_json())
    defs = set(schema.get("$defs", {}))
    for name in (
        "RoundRecord",
        "CandidateRecord",
        "GateRecord",
        "EstimationRecord",
        "EvaluationRecord",
        "DecisionRecord",
        "AgentCallRecord",
        "LedgerEvent",
        "Table",
        "RunMeta",
        "RunOutcome",
    ):
        assert name in defs, f"{name} missing from the schema's $defs"
    gate_value = schema["$defs"]["GateRecord"]["properties"]["value"]
    assert gate_value.get(
        "anyOf"
    ), "GateValue must be a typed union, not an empty schema"
    # the multistart's arrays and table are the candidate's siblings,
    # and the estimation summary does not declare them
    est_props = schema["$defs"]["EstimationRecord"]["properties"]
    assert not {"start_x", "start_x0", "pypesto_result", "refit"} & set(est_props)
    cand_props = schema["$defs"]["CandidateRecord"]["properties"]
    assert {"starts", "multistart", "attempts", "refit"} <= set(cand_props)
    fvals = schema["$defs"]["EstimationRecord"]["properties"]["fvals"]
    assert fvals.get("tier") == "bulk", "the tier must be visible in the schema"
    print(
        f"  schema        {len(defs)} records in $defs; GateValue typed; tiers present"
    )


if __name__ == "__main__":
    for fn in (
        test_roundtrip_is_lossless,
        test_commit_is_atomic_and_overwrites,
        test_prune_drops_tiers_and_says_so,
        test_select_rounds_reduces_the_others,
        test_a_pruned_copy_is_never_served_as_the_record,
        test_schema_names_every_record,
    ):
        print(fn.__name__)
        fn()
    print("OK")
