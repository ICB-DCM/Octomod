"""The engine writes the run record as it runs.

Every artifact that has a record class is validated against it on the way
into the record (`result.write.write_record`), so a payload that does not
fit its declared shape stops the module with the field named. The run IS
one file, `runs/<id>.h5`, written group by group as the modules run — there is
no directory of artifacts and nothing to commit or rebuild.

What this asserts, on a real stub run under the quick overlay:

  1. the run ends with `runs/<id>.h5` present and loadable as a `RunResult`
     whose rounds, decisions and outcome are the run's;
  2. the engine wrote NOTHING else under runs/ for that id — no `runs/<id>/`
     directory; only the record, its checkpoint and the rendered documents
     beside it (`runs/<id>_reports/`);
  3. in file-gate mode the record exists at the FIRST pause, holds the pending
     gate, and grows with the run across resumes — the resume contract, held
     by the record;
  4. `write_record` refuses a payload that does not fit, naming the field, and
     `_missing_keys` reports a typed contract failure for an agent reply;
  5. the readings `derive` fills on load never make the record unloadable (a
     non-numeric cost) and never resurrect a decision a redraft withdrew.

    uv run python tests/result_writes_unit.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from octomod.orchestration.artifacts import ArtifactError  # noqa: E402
from octomod.result.runstore import RunStore  # noqa: E402
from octomod.result.slots import EstimationRecord  # noqa: E402
from octomod.result.write import write_record  # noqa: E402
from tests._record import (  # noqa: E402
    ledger_rows,
    pending_gate,
    rnd,
    run_root,
    temp_record,
    work,
)

PY = str(config.VENV_PYTHON)
CASE = REPO / "testcase" / "toy_phos"


def _env() -> dict:
    env = os.environ.copy()
    env.setdefault(
        "OCTOMOD_SPEC_OVERLAY", str(REPO / "workflows" / "overlays" / "quick.yaml")
    )
    return env


def _run(args: list[str]) -> int:
    return subprocess.run(
        [PY, "-m", "octomod", *args], cwd=REPO, env=_env(), capture_output=True
    ).returncode


def _footprint(run_id: str) -> list[str]:
    """Everything under runs/ that carries this run id."""
    return sorted(p.name for p in config.RUNS_DIR.glob(f"{run_id}*"))


def test_auto_run_ends_with_the_record() -> None:
    run_id = f"record_writes_{time.strftime('%H%M%S')}"
    rc = _run(
        [
            "run",
            "--testcase",
            str(CASE),
            "--backend",
            "stub",
            "--auto-approve",
            "--run-id",
            run_id,
        ]
    )
    assert rc == 0, f"stub run exited {rc}"
    store = RunStore.for_run(config.RUNS_DIR, run_id)
    assert store.exists_on_disk(), "the run did not leave runs/<id>.h5 behind"
    record = store.load()
    assert record.outcome and record.outcome.outcome == "completed"
    r0 = record.round(0)
    assert r0.shape == "single" and r0.candidates["_single"].estimation is not None
    assert r0.evaluation and r0.evaluation.t2prime_passed is not None
    assert set(r0.decisions) >= {"model_scope", "evaluation_verdict"}, set(r0.decisions)
    # the cost boundary (the compile card, `compile_gate.ask`) is the ROUND's
    # decision: `decisions/assembly_cost_boundary`
    boundary = r0.decisions.get("assembly_cost_boundary")
    assert (
        boundary is not None and boundary.module == "assembly_cost_boundary"
    ), r0.decisions
    assert r0.status and set(r0.status.markers) >= {
        "s1",
        "s3",
        "s6",
        "s7",
    }, r0.status and set(r0.status.markers)
    # the file is the run — nothing else is written under runs/ for it
    footprint = _footprint(run_id)
    assert not (
        config.RUNS_DIR / run_id
    ).exists(), (
        f"the engine wrote a directory runs/{run_id}/ — the run must be one file"
    )
    allowed = {f"{run_id}.h5", f"{run_id}.h5.bak", f"{run_id}_reports"}
    assert set(footprint) <= allowed, f"unexpected footprint under runs/: {footprint}"
    rows = ledger_rows(run_root(run_id))
    assert any(r["event"] == "run_end" for r in rows), "no run_end row"
    assert not [
        r for r in rows if r["event"] == "result_commit"
    ], "nothing is committed or rebuilt; the record is written directly"
    assert len(record.ledger) == len(rows), "the record's ledger is the ledger"
    print(
        f"  auto run      runs/{run_id}.h5 loads: {len(record.rounds)} round(s), "
        f"{len(rows)} ledger rows, {store.path.stat().st_size / 1e6:.1f} MB; "
        f"footprint {footprint}"
    )


def test_file_gate_pause_leaves_a_valid_record() -> None:
    run_id = f"record_pause_{time.strftime('%H%M%S')}"
    root = run_root(run_id)
    store = root.store
    base = [
        "run",
        "--testcase",
        str(CASE),
        "--backend",
        "stub",
        "--run-id",
        run_id,
        "--gate-mode",
        "file",
    ]
    rc = _run(base)
    assert rc == 3, f"expected a pause at the intent gate (exit 3), got {rc}"
    assert store.exists_on_disk(), "no record at the very first pause"
    paused = store.load()
    assert paused.outcome is None and paused.rounds == {}, "nothing has run yet"
    gate = pending_gate(root)
    assert gate and gate["module"] == "intent", gate
    rows = ledger_rows(root)
    assert rows[-1]["event"] == "gate_pending", rows[-1]
    assert len(paused.ledger) == len(rows), "the record holds the pause row itself"
    assert store.backup_path.exists(), "no checkpoint copy at the pause"
    rc = _run([*base, "--gate-answer", "y"])
    assert rc == 3, f"expected a pause at the scope gate, got {rc}"
    first = store.load()
    assert first.outcome is None, "a paused run is open, not ended"
    assert first.intent and first.intent.question
    assert first.round(0).model is not None, "S1 has built by the scope gate"
    keys_first = set(k for k, _ in store.walk(""))
    rc = _run([*base, "--gate-answer", "y"])
    assert rc == 3, f"expected a pause at the compile gate, got {rc}"
    second = store.load()
    keys_second = set(k for k, _ in store.walk(""))
    assert keys_first < keys_second, "the record did not grow with the run"
    assert len(second.ledger) > len(first.ledger)
    r0 = second.round(0)
    assert r0.model is not None and r0.data is not None, "S1 and S2 are in the record"
    assert pending_gate(root) is not None, "the compile gate is pending in the record"
    print(
        f"  file gate     record present and valid at each pause; "
        f"{len(keys_first)} → {len(keys_second)} keys across resumes"
    )


def test_export_refuses_to_prune_the_record_in_place() -> None:
    """`export --tiers core` without --out would overwrite the
    run's own record with a copy; it is refused (exit 2) and the file kept."""
    stores = [
        RunStore(p)
        for p in config.RUNS_DIR.glob("record_writes_*.h5")
        if not p.name.endswith(".bak")
    ]
    if not stores:
        print("  SKIP: no record_writes run with a record on this machine yet")
        return
    store = max(stores, key=lambda s: s.mtime_ns() or 0)
    before = store.mtime_ns()
    rc = _run(["export", "--run-id", store.run_id, "--tiers", "core"])
    assert rc == 2, f"expected a refusal (exit 2), got {rc}"
    assert store.mtime_ns() == before, "the record was rewritten"
    with tempfile.TemporaryDirectory() as d:
        rc = _run(
            [
                "export",
                "--run-id",
                store.run_id,
                "--tiers",
                "core",
                "--out",
                f"{d}/copy.h5",
            ]
        )
        assert rc == 0 and Path(d, "copy.h5").exists()
        copy = RunStore(Path(d, "copy.h5")).load()
        assert copy.round_indices == store.load().round_indices
    print("  export        a pruned copy needs --out; the run's record is left alone")


def test_load_survives_an_unpriced_agent_call() -> None:
    """`derive` sums the ledger's `cost_usd` per role on every load. The value
    is whatever the backend reported, unvalidated, so only numbers count: one
    `"n/a"` row raised in `float()` would make the record unloadable — status,
    inspect, export and every reader would fail for the run."""
    with temp_record() as root:
        (rnd(root, 0) / "agent_calls/construction/reply").put({"ok": True})
        row = {
            "ts": "t",
            "round": 0,
            "module": "model",
            "event": "agent_call",
            "role": "construction",
        }
        root.store.append_ledger({**row, "cost_usd": "n/a"})
        root.store.append_ledger({**row, "cost_usd": 0.25})
        root.store.append_ledger({**row, "cost_usd": None})
        record = root.store.load()
        call = record.round(0).agent_calls["construction"]
    assert len(call.calls) == 3 and call.cost_usd == 0.25, (call.cost_usd, call.calls)
    print("  cost          a non-numeric cost_usd row is skipped; the numbers sum")


def test_derive_does_not_resurrect_a_redrafted_decision() -> None:
    """A `redraft:` answer at the scope gate makes S1 delete
    `decisions/model_scope` so the resume asks again; the `human_gate` row
    stays in the ledger. `derive` must not recreate the decision from that
    row on every load (the run would look decided while the gate is open),
    and once the module is asked again the decision's mode and time are the
    LATEST answer's, not the first row's."""
    gate = {
        "round": 0,
        "module": "model_scope",
        "event": "human_gate",
        "question": "Accept this model scope?",
    }
    with temp_record() as root:
        (rnd(root, 0) / "model/antimony").put_text("model m\nend\n")
        root.store.append_ledger(
            {
                **gate,
                "ts": "t1",
                "approved": False,
                "mode": "file",
                "note": "redraft: split it",
            }
        )
        decisions = root.store.load().round(0).decisions
        assert (
            "model_scope" not in decisions
        ), "the withdrawn decision was resurrected from its redraft row"
        # re-asked and answered; `ask_once` writes the decision without a mode
        root.store.append_ledger(
            {**gate, "ts": "t2", "approved": True, "mode": "interactive", "note": ""}
        )
        (rnd(root, 0) / "decisions/model_scope").put(
            {"module": "model_scope", "approved": True, "note": ""}
        )
        # a gate answered plainly without a decision record is still a decision
        root.store.append_ledger(
            {
                **gate,
                "ts": "t3",
                "module": "evaluation_verdict",
                "approved": True,
                "mode": "file",
            }
        )
        decisions = root.store.load().round(0).decisions
    scope = decisions["model_scope"]
    assert scope.mode == "interactive" and scope.at == "t2", (scope.mode, scope.at)
    assert (
        decisions["evaluation_verdict"].mode == "file"
        and decisions["evaluation_verdict"].approved
    )
    print(
        "  decisions     a redraft row invents no decision; mode/at from the last answer"
    )


def test_write_record_refuses_a_misfit() -> None:
    bad = {"optimizer": "fides", "seed": "not-an-int", "n_starts": 3}
    with temp_record() as root:
        node = work(root, 0) / "estimation"
        try:
            write_record(node, EstimationRecord, bad)
        except ArtifactError as e:
            assert "seed" in str(e), str(e)
            assert node.key in str(e), f"the refusal does not name the key: {e}"
        else:
            raise AssertionError(
                "a misfit payload must be refused before it is written"
            )
        assert not node.exists(), "the refused payload was written anyway"
    from octomod.agents import ROLES, _missing_keys

    failures = _missing_keys(
        {"move": "add_reaction", "motivated_by": "x", "expected_effect": "y"},
        ROLES["revision_proposal"],
    )
    assert any("move" in f for f in failures), failures
    print(
        "  contracts     a misfit artifact and a mistyped agent reply are both refused by name"
    )


if __name__ == "__main__":
    for fn in (
        test_write_record_refuses_a_misfit,
        test_load_survives_an_unpriced_agent_call,
        test_derive_does_not_resurrect_a_redrafted_decision,
        test_auto_run_ends_with_the_record,
        test_file_gate_pause_leaves_a_valid_record,
        test_export_refuses_to_prune_the_record_in_place,
    ):
        fn()
    print("RESULT WRITES OK — the record is written by the run, validated, one file")
