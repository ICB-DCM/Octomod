"""Run-id safety, checked on fabricated run records without running the pipeline.

  1. finished: a ledger with run_end means the id is spent; refuse, naming the remedy;
  2. paused: no run_end means the run waits at a gate; resume;
  3. drifted: a paused run whose spec or testcase moved is refused, naming the sha;
  4. overwrite: delete the run record and start clean, never outside runs/;
  5. damaged: a record that does not read back is an error, not "no record".

A run is one record, `runs/<id>.h5`, fabricated here in a throwaway
runs dir (never the repo's runs/); the guard fires before a record is created,
so the pipeline never starts. That a real paused run still resumes is held by
the `filegate` suite.

    uv run python tests/run_id_unit.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from octomod.orchestration import run_guard  # noqa: E402
from tests._record import run_root  # noqa: E402

TESTCASE = REPO / "testcase" / "toy_phos"
SPEC_SHA = "0123456789abcdef"


def fabricate(run_id: str, *, ended: str | None, meta: dict | None = None):
    """A run record (one file under runs/) with just enough in it for
    the guard to judge it."""
    root = run_root(run_id)
    root.store.remove()
    root.store.create()
    rows = [{"event": "run_start", "ts": "now", "workflow_sha": SPEC_SHA}]
    if ended:
        rows.append({"event": "run_end", "ts": "now", "outcome": ended})
    root.store.replace_ledger(rows)
    base = {
        "workflow_sha": SPEC_SHA,
        "testcase_sha": run_guard.testcase_sha(TESTCASE),
    }
    base.update(meta or {})
    (root / "run").put(base)
    return root


def remove(root) -> None:
    root.store.remove()


def refusal(root, **kw) -> str:
    try:
        run_guard.check(root, TESTCASE, SPEC_SHA, **kw)
    except run_guard.RunIdRefused as e:
        return str(e)
    raise AssertionError(f"expected {root.store.run_id} to be refused, it was allowed")


def test_finished_is_refused() -> None:
    for outcome in ("completed", "stopped", "completed_t2prime_unmet"):
        root = fabricate(f"runid_end_{outcome}", ended=outcome)
        msg = refusal(root)
        assert "already ended" in msg and outcome in msg, msg
        assert "--overwrite" in msg and "new id" in msg, (
            "a refusal must say what to do instead: " + msg
        )
        assert str(root) in msg, "the refusal must name where the run is"
        remove(root)
    print(
        "  finished  refused for completed / stopped / t2prime_unmet, "
        "each naming the remedy"
    )


def test_paused_resumes() -> None:
    root = fabricate("runid_paused", ended=None)
    run_guard.check(root, TESTCASE, SPEC_SHA)  # must not raise
    remove(root)

    # a fresh id, and an id whose record holds no ledger at all
    run_guard.check(run_root("runid_never_existed"), TESTCASE, SPEC_SHA)
    bare = run_root("runid_bare")
    bare.store.remove()
    bare.store.create()
    run_guard.check(bare, TESTCASE, SPEC_SHA)
    remove(bare)
    print("  paused    resumes; a fresh or empty run record is allowed")


def test_reentered_after_end_resumes() -> None:
    """A gate_pending after a run_end (a re-entry) makes the run live again."""
    root = fabricate("runid_reentered", ended="stopped")
    root.store.append_ledger({"event": "marker", "ts": "later", "module": "s3"})
    root.store.append_ledger(
        {
            "event": "gate_pending",
            "ts": "later",
            "module": "cost_boundary_estimation",
        }
    )
    run_guard.check(root, TESTCASE, SPEC_SHA)  # must not raise
    assert run_guard.ended_outcome(root) is None
    remove(root)
    # but a run_end AFTER the re-entry ends it again
    root = fabricate("runid_reentered_ended", ended="stopped")
    root.store.append_ledger({"event": "gate_pending", "ts": "later", "module": "x"})
    root.store.append_ledger(
        {"event": "run_end", "ts": "latest", "outcome": "completed"}
    )
    assert "already ended" in refusal(root)
    remove(root)
    print(
        "  re-entered a run_end followed by live events resumes; a later run_end ends it again"
    )


def test_drift_is_refused() -> None:
    root = fabricate("runid_spec_drift", ended=None, meta={"workflow_sha": "deadbeef"})
    msg = refusal(root)
    assert "drifted" in msg and "deadbeef" in msg and SPEC_SHA in msg, msg
    assert "workflow_sha" in msg, "the refusal must name WHICH sha moved: " + msg
    remove(root)

    root = fabricate("runid_tc_drift", ended=None, meta={"testcase_sha": "0badc0de"})
    msg = refusal(root)
    assert "testcase_sha" in msg and "0badc0de" in msg, msg
    assert TESTCASE.name in msg, "name the testcase whose input moved: " + msg
    remove(root)

    # an older run with no testcase_sha recorded must still resume
    root = fabricate("runid_legacy", ended=None)
    meta = (root / "run").get()
    del meta["testcase_sha"]
    (root / "run").put(meta)
    run_guard.check(root, TESTCASE, SPEC_SHA)  # must not raise
    remove(root)
    print(
        "  drifted   refused for spec and for testcase, each naming the sha; "
        "a run from before shas were recorded still resumes"
    )


def test_explicit_reentry_is_allowed_on_a_finished_run() -> None:
    """Naming a module re-enters a finished run on purpose; drift is still refused."""
    root = fabricate("runid_reentry", ended="completed")
    run_guard.check(root, TESTCASE, SPEC_SHA, from_module="evaluation")
    msg = refusal(root)  # without --from-module it is still refused
    assert "already ended" in msg and "--from-module" in msg, (
        "the refusal should name re-entry as a remedy: " + msg
    )
    remove(root)

    drifted = fabricate(
        "runid_reentry_drift", ended="completed", meta={"workflow_sha": "deadbeef"}
    )
    try:
        run_guard.check(drifted, TESTCASE, SPEC_SHA, from_module="evaluation")
    except run_guard.RunIdRefused as e:
        assert "deadbeef" in str(e)
    else:
        raise AssertionError("re-entry with a drifted spec must still be refused")
    remove(drifted)
    print(
        "  re-entry  --from-module allowed on a finished run; still refused "
        "when the spec has drifted"
    )


def test_a_reentered_run_that_paused_resumes() -> None:
    """A run_start after run_end (a re-entry) is live again, so a plain resume works."""
    root = fabricate("runid_reentered_paused", ended="stopped")
    root.store.append_ledger({"event": "run_start", "ts": "later"})
    run_guard.check(root, TESTCASE, SPEC_SHA)  # must not raise
    root.store.append_ledger({"event": "run_end", "ts": "end", "outcome": "completed"})
    msg = refusal(root)  # and once it ends again, it is spent again
    assert "already ended" in msg and "completed" in msg, msg
    remove(root)
    print("  re-entered a run_start after run_end is live; the next run_end ends it")


def test_overwrite() -> None:
    root = fabricate("runid_overwrite", ended="completed")
    removed = run_guard.remove(root)
    assert not root.exists(), "--overwrite must delete the run record"
    assert any(name.endswith(".h5") for name in removed), removed

    # and it starts clean rather than refusing
    root = fabricate("runid_overwrite2", ended="completed")
    run_guard.check(root, TESTCASE, SPEC_SHA, overwrite=True)
    assert not root.exists()
    run_guard.check(run_root("runid_absent"), TESTCASE, SPEC_SHA, overwrite=True)
    print(
        f"  overwrite deleted {len(removed)} file(s) and started clean; "
        f"absent id is a no-op"
    )


def test_overwrite_never_escapes_runs() -> None:
    """The one destructive path in the engine, fenced."""
    for outside in (
        REPO,
        REPO / "testcase" / "toy_phos",
        config.RUNS_DIR,
        Path("/tmp"),
    ):
        try:
            run_guard.remove(outside)
        except run_guard.RunIdRefused as e:
            assert "only ever removes" in str(e)
        else:
            raise AssertionError(f"remove({outside}) was NOT refused")
    assert (REPO / "testcase" / "toy_phos").exists(), "testcase/ must be untouched"
    print("  overwrite refuses the repo, a testcase, runs/ itself and /tmp")


def test_truth_is_not_part_of_the_identity() -> None:
    """The identity is what a run reads (`run_folder.inputs_read`): truth/,
    which the engine never reads, and every staging file beside the inputs
    stay out of the testcase sha."""
    tmp = config.RUNS_DIR / f"runid_tc_copy_{time.strftime('%H%M%S')}"
    shutil.copytree(TESTCASE, tmp)
    base = run_guard.testcase_sha(tmp)
    # a truth/ is planted in the COPY, so the real one is never written to and
    # the assertion does not depend on which testcase happens to carry one
    (tmp / "truth").mkdir(exist_ok=True)
    (tmp / "truth" / "true_parameters.json").write_text('{"k_phos": 0.7}')
    assert run_guard.testcase_sha(tmp) == base, (
        "truth/ changed the testcase sha — the engine would be pinning a run "
        "to ground truth it is not allowed to read"
    )
    with_truth = base
    gen = tmp / "make_data.py"
    if gen.exists():
        gen.write_text(gen.read_text() + "\n# a comment\n")
        assert run_guard.testcase_sha(tmp) == with_truth, (
            "make_data.py changed the sha — reformatting a generator would "
            "fail a resume it cannot affect"
        )
    # curation/ and notes/ are outside the identity, so a staging log appended
    # while a run is paused cannot make it unresumable
    for d in ("curation", "notes"):
        (tmp / d).mkdir(exist_ok=True)
        (tmp / d / "STAGING-LOG.md").write_text("# log\n- appended while paused\n")
    assert run_guard.testcase_sha(tmp) == with_truth, (
        "curation/ or notes/ changed the sha — a staging note appended while a "
        "run is paused would make that run unresumable"
    )
    # nor does anything else a run never reads: raw files, a paper no
    # supplied-literature item names, a provenance script
    for rel in ("raw_fcs/A01.fcs", "paper/unreferenced.pdf", "preprocessing/gate.py"):
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp / rel).write_bytes(b"not an input\n")
    assert run_guard.testcase_sha(tmp) == with_truth, (
        "a file no run reads changed the sha — the identity must be what the "
        "run reads, nothing else"
    )
    data = sorted((tmp / "data").glob("*"))
    assert data, "expected staged data to perturb"
    data[0].write_text(data[0].read_text() + "\n")
    assert (
        run_guard.testcase_sha(tmp) != with_truth
    ), "editing a staged data file did NOT change the sha — the check is blind"
    (tmp / "intent.yaml").rename(tmp / "intent_renamed.yaml")
    renamed = run_guard.testcase_sha(tmp)
    assert renamed != with_truth, "a rename must drift too"
    shutil.rmtree(tmp)
    print(
        "  identity  what a run reads: excludes truth/, make_data.py, curation/, "
        "notes/ and raw files; catches an edited file and a renamed one"
    )


def test_damaged_record_is_not_swallowed() -> None:
    """A damaged `run` record is not "no record": swallowed, the damage would
    let the run go ahead over it. Only a missing record is nothing to compare
    against; damage propagates."""
    from octomod.result.runstore import RecordDamaged

    root = fabricate("runid_damaged", ended=None)

    def damaged(*_a, **_k):
        raise RecordDamaged("runid_damaged.h5 is damaged (truncated file)")

    root.store.get = damaged  # the ledger still reads; only `run` is damaged
    try:
        run_guard.check(root, TESTCASE, SPEC_SHA)
    except RecordDamaged:
        pass
    else:
        raise AssertionError("a damaged record was read as no record and allowed")
    finally:
        del root.store.get
        remove(root)
    # and the real thing: a truncated file
    root = fabricate("runid_truncated", ended=None)
    root.store.path.write_bytes(root.store.path.read_bytes()[:200])
    try:
        run_guard.check(root, TESTCASE, SPEC_SHA)
    except RecordDamaged:
        pass
    else:
        raise AssertionError("a truncated record was allowed")
    finally:
        remove(root)
    print("  damaged   RecordDamaged propagates from the guard; the run does not start")


def test_cli_refuses_with_exit_1() -> None:
    """End to end through the CLI, still without starting the pipeline."""
    from octomod.cli import main

    root = fabricate("runid_cli", ended="completed")
    rc = main(
        [
            "run",
            "--testcase",
            str(TESTCASE),
            "--backend",
            "stub",
            "--auto-approve",
            "--run-id",
            root.store.run_id,
        ]
    )
    assert rc == 1, f"expected exit 1 from a refused run-id, got {rc}"
    assert root.exists(), "a refusal must not delete the run it refused"
    remove(root)
    print("  cli       exit 1, and the refused run is left on disk untouched")


if __name__ == "__main__":
    # every record this suite fabricates lives in a throwaway runs dir: the
    # repo's runs/ is never written
    config.RUNS_DIR = Path(tempfile.mkdtemp(prefix="octomod_runid_"))
    try:
        test_finished_is_refused()
        test_paused_resumes()
        test_reentered_after_end_resumes()
        test_drift_is_refused()
        test_explicit_reentry_is_allowed_on_a_finished_run()
        test_a_reentered_run_that_paused_resumes()
        test_overwrite()
        test_overwrite_never_escapes_runs()
        test_truth_is_not_part_of_the_identity()
        test_damaged_record_is_not_swallowed()
        test_cli_refuses_with_exit_1()
    finally:
        shutil.rmtree(config.RUNS_DIR, ignore_errors=True)
    print(
        "RUN ID UNIT OK — a spent run-id is refused, a paused one resumes, "
        "drift is named, a damaged record is refused, "
        "and --overwrite cannot leave runs/"
    )
