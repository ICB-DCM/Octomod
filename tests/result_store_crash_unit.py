"""Crash safety of the single-file record.

A directory of small files cannot be left half-written by a process that
dies: each artifact is its own file. One HDF5 file can be — a process killed
inside a write can leave a file HDF5 refuses to open. What the record does
about it, and what this suite measures:

  * every `RunStore.put` is open → write one group → close, so the window
    is one group write, never the run;
  * the record is copied to `<id>.h5.bak` at every marker and decision (the
    points a resume replays from) and at every pause and run end;
  * a READER is given the checkpoint when the main file is damaged, and the
    WRITER restores the checkpoint over the damaged file, so a resume
    continues from the last marker — whether the damage stops the file from
    OPENING (a truncation; or the "open for write" consistency flag a killed
    writer leaves in the superblock, which refuses every mode until cleared)
    or only from READING (a group broken inside a write, which opens fine and
    fails on first touch);
  * `checkpoint()` verifies the file before copying it, so a damaged file
    never replaces the last good checkpoint.

The suite kills a stub toy run with SIGKILL at random moments, N times, and
checks after every kill that (a) the record or its checkpoint opens and
validates, and (b) the same run-id RESUMES to completion (exit 0) with its
outcome recorded. It prints how often the main file was damaged and how often
the checkpoint was needed — that number is the honest measurement of what the
design promises. It also truncates a record by hand to check the restore path
deterministically, because random kills rarely land inside a write.

    uv run python tests/result_store_crash_unit.py [--trials N]
"""

from __future__ import annotations

import argparse
import os
import random
import signal
import subprocess
import sys
import time
from pathlib import Path

import h5py

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from octomod.result.runstore import RunStore  # noqa: E402

PY = str(config.VENV_PYTHON)
CASE = REPO / "testcase" / "toy_phos"


def _env() -> dict:
    env = os.environ.copy()
    env.setdefault(
        "OCTOMOD_SPEC_OVERLAY", str(REPO / "workflows" / "overlays" / "quick.yaml")
    )
    return env


def _cmd(run_id: str, overwrite: bool = False) -> list[str]:
    return [
        PY,
        "-m",
        "octomod",
        "run",
        "--testcase",
        str(CASE),
        "--backend",
        "stub",
        "--auto-approve",
        "--run-id",
        run_id,
        *(["--overwrite"] if overwrite else []),
    ]


def _opens(path: Path) -> bool:
    try:
        with h5py.File(path, "r"):
            return True
    except OSError:
        return False


def kill_and_resume(run_id: str, kill_after_s: float) -> dict:
    """One trial: start, SIGKILL after `kill_after_s`, inspect, resume."""
    store = RunStore.for_run(config.RUNS_DIR, run_id)
    proc = subprocess.Popen(
        _cmd(run_id, overwrite=True),
        cwd=REPO,
        env=_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        proc.wait(timeout=kill_after_s)  # returns at once if the run ends first
        finished_early = True
    except subprocess.TimeoutExpired:
        finished_early = False
        proc.send_signal(signal.SIGKILL)
        proc.wait()
    out = {
        "kill_after_s": round(kill_after_s, 1),
        "finished_before_kill": finished_early,
        "file_exists": store.path.exists(),
        "file_opens": store.path.exists() and _opens(store.path),
        "bak_exists": store.backup_path.exists(),
        "bak_opens": store.backup_path.exists() and _opens(store.backup_path),
        "markers_before": None,
        "resumed_rc": None,
        "outcome": None,
        "recovered_row": False,
    }
    if out["file_opens"] or out["bak_opens"]:
        try:
            out["markers_before"] = sorted(
                store.keys("rounds/round_0/status/markers")
            ) + sorted(store.keys("rounds/round_0/candidates/_single/markers"))
        except Exception as e:  # noqa: BLE001 - report, do not fail, here
            out["markers_before"] = f"unreadable: {e}"
    if finished_early:
        return out
    # Killed AFTER `run_end`: the run had finished and was doing what follows
    # it (the analysis document, the tried-models archive, the time account).
    # A resume is then refused as "already ended" — correctly — so there is
    # nothing to resume; what must hold is that the finished record reads and
    # says how it ended. (The post-run work is long enough for a random kill
    # to land in it — at 16 s on the toy run.)
    try:
        ended = [r for r in store.ledger_rows() if r.get("event") == "run_end"]
    except Exception:  # noqa: BLE001 - an unreadable record is judged below
        ended = []
    if ended:
        out["ended_before_kill"] = True
        out["outcome"] = ended[-1].get("outcome")
        out["markers_after"] = out["markers_before"]
        return out
    # the resume: same id, no --overwrite; the run must continue from its markers
    rc = subprocess.run(
        _cmd(run_id), cwd=REPO, env=_env(), capture_output=True, text=True
    )
    out["resumed_rc"] = rc.returncode
    if rc.returncode != 0:
        out["stderr_tail"] = rc.stderr[-600:]
    rows = store.ledger_rows()
    ends = [r for r in rows if r.get("event") == "run_end"]
    out["outcome"] = ends[-1].get("outcome") if ends else None
    out["recovered_row"] = any(r.get("recovered") for r in rows)
    out["markers_after"] = _markers(store)
    return out


def kill_after_run_end(run_id: str) -> dict:
    """A kill after `run_end`, placed on purpose: SIGKILL the
    run as soon as its ledger holds `run_end`, while it is still writing what
    follows (the analysis document, the tried-models archive, the time
    account). The finished record must read and say how it ended; a resume
    is refused as ended (nothing to resume); the analysis the kill may have
    cut short is regenerated from the record."""
    store = RunStore.for_run(config.RUNS_DIR, run_id)
    proc = subprocess.Popen(
        _cmd(run_id, overwrite=True),
        cwd=REPO,
        env=_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    t0 = time.time()
    landed = False
    while proc.poll() is None and time.time() - t0 < 180:
        try:
            if any(r.get("event") == "run_end" for r in store.ledger_rows()):
                proc.send_signal(signal.SIGKILL)
                proc.wait()
                landed = True
                break
        except Exception:  # noqa: BLE001 - held by the writer: look again
            pass
        time.sleep(0.02)
    if not landed and proc.poll() is None:
        proc.kill()
        proc.wait()
    out = {"landed": landed}
    if not landed:
        return out
    out["readable"] = _opens(store.path) or (
        store.backup_path.exists() and _opens(store.backup_path)
    )
    out["outcome"] = _outcome(store)
    rc = subprocess.run(
        _cmd(run_id), cwd=REPO, env=_env(), capture_output=True, text=True
    )
    out["resume_rc"], out["resume_says"] = rc.returncode, rc.stderr + rc.stdout
    rep = subprocess.run(
        [PY, "-m", "octomod", "report", "--run-id", run_id, "--analysis"],
        cwd=REPO,
        env=_env(),
        capture_output=True,
        text=True,
    )
    out["report_rc"] = rep.returncode
    out["analysis"] = (store.reports_dir / "ANALYSIS.html").exists()
    return out


def kill_inside_a_write(run_id: str) -> dict:
    """The trial random kills rarely land (write windows are ~3% of a toy run,
    ≤80 ms each): start the run and SIGKILL it the moment the record is held
    open for writing — HDF5's lock refuses a reader while a writer has it —
    so the file is left with its "open for write" flag set."""
    store = RunStore.for_run(config.RUNS_DIR, run_id)
    proc = subprocess.Popen(
        _cmd(run_id, overwrite=True),
        cwd=REPO,
        env=_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    t0 = time.time()
    landed = False
    while proc.poll() is None and time.time() - t0 < 120:
        # only once a checkpoint exists: the kill must test the restore path,
        # not the first second of a run
        if store.backup_path.exists():
            try:
                with h5py.File(store.path, "r"):
                    pass
            except OSError as e:
                if "lock" in str(e):
                    proc.send_signal(signal.SIGKILL)
                    proc.wait()
                    landed = True
                    break
        time.sleep(0.002)
    out = {"landed": landed, "killed_at_s": round(time.time() - t0, 2)}
    if not landed:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        return out
    out["file_opens"] = _opens(store.path)
    out["bak_opens"] = store.backup_path.exists() and _opens(store.backup_path)
    rc = subprocess.run(
        _cmd(run_id), cwd=REPO, env=_env(), capture_output=True, text=True
    )
    out["resumed_rc"] = rc.returncode
    if rc.returncode != 0:
        out["stderr_tail"] = rc.stderr[-600:]
    rows = store.ledger_rows()
    out["outcome"] = _outcome(store)
    out["recovered_row"] = any(r.get("recovered") for r in rows)
    out["damaged_kept"] = store.path.with_name(store.path.name + ".damaged").exists()
    return out


def _markers(store: RunStore) -> list[str]:
    return sorted(store.keys("rounds/round_0/status/markers")) + sorted(
        store.keys("rounds/round_0/candidates/_single/markers")
    )


def _outcome(store: RunStore) -> str | None:
    ends = [r for r in store.ledger_rows() if r.get("event") == "run_end"]
    return ends[-1].get("outcome") if ends else None


def test_a_truncated_record_is_restored_from_its_checkpoint() -> tuple[float, str]:
    """Deterministic: damage the file by hand, then read and write.

    Its unkilled run is also the trials' reference: returns how long it took
    less any AMICI compile (a later run loads the cached model, so a cold
    compile would stretch the kill window past the end of every run), and the
    outcome it recorded, before any damage."""
    run_id = "crash_truncated"
    store = RunStore.for_run(config.RUNS_DIR, run_id)
    t0 = time.perf_counter()
    rc = subprocess.run(
        _cmd(run_id, overwrite=True), cwd=REPO, env=_env(), capture_output=True
    ).returncode
    t_run = time.perf_counter() - t0
    assert rc == 0, rc
    try:
        outcome = _outcome(store)
        assert outcome, "the unkilled run recorded no outcome"
        compile_s = ((store.get("timing") or {}).get("compute") or {}).get("compile")
        t_run -= float((compile_s or {}).get("wall_s") or 0.0)
        assert store.backup_path.exists(), "no checkpoint after a finished run"
        size = store.path.stat().st_size
        with open(store.path, "r+b") as fh:
            fh.truncate(size // 2)
        assert not _opens(store.path), "the truncated file should not open"
        # a reader is served the checkpoint
        rr = store.load()
        assert rr.outcome and rr.outcome.outcome == "completed", rr.outcome
        # a writer restores the checkpoint over the damaged file, keeps the damage
        store.put("probe", {"after": "restore"})
        assert _opens(store.path), "the main file was not restored"
        assert store.path.with_name(store.path.name + ".damaged").exists()
        rows = store.ledger_rows()
        assert any(r.get("recovered") for r in rows), "the restore was not ledgered"
        assert store.get("probe") == {"after": "restore"}
    finally:
        store.remove()  # takes the .damaged file too
    print("  truncated record: reader served the checkpoint, writer restored it")
    return t_run, outcome


def _corrupt_inside(path: Path, n: int = 40) -> None:
    """Overwrite bytes throughout the file past the superblock: the file still
    OPENS, and its groups fail when read — what a kill inside a group write
    leaves (measured: 16 of 40 random 64-byte corruptions of a record open
    and then fail on visit)."""
    data = bytearray(path.read_bytes())
    rng = random.Random(3)
    for _ in range(n):
        off = rng.randint(2048, len(data) - 128)
        data[off : off + 64] = os.urandom(64)
    path.write_bytes(bytes(data))


def test_a_record_that_opens_but_does_not_read_is_restored() -> None:
    """Deterministic, in-process: damage that `h5py.File` does not notice."""
    import tempfile

    from octomod.result.runstore import RecordDamaged

    with tempfile.TemporaryDirectory() as d:
        store = RunStore(Path(d) / "damaged.h5")
        for k in range(30):
            store.put(f"rounds/round_{k}/model/parameters", [{"id": f"k{k}"}] * 5)
        store.append_ledger({"ts": "", "event": "run_start", "round": 0})
        store.checkpoint()
        good = store.backup_path.read_bytes()
        _corrupt_inside(store.path)
        assert _opens(store.path), "the damage should leave the file openable"
        assert store.verify() is not None, "verify() did not see the damage"
        # 1. the checkpoint refuses to copy the damage over the good copy
        try:
            store.checkpoint()
        except RecordDamaged:
            pass
        else:
            raise AssertionError("checkpoint() copied a damaged file")
        assert store.backup_path.read_bytes() == good, "the good checkpoint was lost"
        assert store.verify() is None, "the checkpoint was not restored"
        # 2. a resuming WRITER (a fresh process) restores before its first write
        _corrupt_inside(store.path)
        _as_fresh_process(store.path)
        fresh = RunStore(store.path)
        fresh.put("probe", {"after": "restore"})
        assert fresh.recovered and fresh.verify() is None
        assert any(r.get("recovered") for r in fresh.ledger_rows())
        fresh.checkpoint()
        # 3. a READER (a process that has written nothing) gets the checkpoint
        _corrupt_inside(store.path)
        _as_fresh_process(store.path)
        rr = RunStore(store.path).load()
        assert "round_29" in rr.rounds, "the reader was not served the checkpoint"
        # 4. a WRITER that meets damage after it has written restores and STOPS:
        # what it wrote since the checkpoint is gone, and it must not go on
        # believing otherwise
        writer = RunStore(store.path)
        writer.put("probe2", {"x": 1})
        _corrupt_inside(store.path)
        try:
            writer.get("rounds/round_3/model/parameters")
            writer.load()
        except RecordDamaged:
            pass
        else:
            raise AssertionError("a writer carried on over a restored record")
        assert writer.verify() is None and writer.get("probe2") is None
    print(
        "  damaged but openable: checkpoint refused to overwrite the good copy; "
        "a resuming writer restored; a reader was served the checkpoint; a "
        "writer mid-run restored and stopped"
    )


def _as_fresh_process(path: Path) -> None:
    """Forget that this process verified or wrote `path`, as a new one would."""
    from octomod.result import runstore as rs_mod

    rs_mod._WRITERS.discard(path.resolve())
    rs_mod._WROTE.discard(path.resolve())


def test_a_run_end_compaction_meets_damage_as_a_checkpoint_does() -> None:
    """`compact()` verifies before it copies, as `checkpoint()` does: copied
    unverified, a damaged record at run end fails INSIDE the copy — swallowed
    by `commit_run` as a 'checkpoint failed' note, exit 0, no restore, a
    `.compact.tmp` left."""
    import tempfile

    from octomod.result.autocommit import commit_run
    from octomod.result.runstore import RecordDamaged

    with tempfile.TemporaryDirectory() as d:
        store = RunStore(Path(d) / "end.h5")
        for k in range(30):
            store.put(f"rounds/round_{k}/model/parameters", [{"id": f"k{k}"}] * 5)
        store.append_ledger({"ts": "", "event": "run_start", "round": 0})
        store.checkpoint()
        good = store.backup_path.read_bytes()
        _corrupt_inside(store.path)
        assert store.verify() is not None, "verify() did not see the damage"
        try:
            commit_run(store, None, why="run_end")
        except RecordDamaged:
            pass
        else:
            raise AssertionError("a damaged record was compacted at run end")
        assert store.backup_path.read_bytes() == good, "the good checkpoint was lost"
        assert store.verify() is None, "the checkpoint was not restored"
        assert not store.path.with_suffix(".compact.tmp").exists(), "tmp left"
    print("  damaged at run end: compact restored and stopped, no .compact.tmp")


def test_a_half_restored_record_is_finished_by_the_next_write() -> None:
    """A kill between the restore's two steps (the damaged file renamed away,
    the checkpoint not yet copied in) leaves no `<id>.h5`; the next write
    finishes the restore, where `h5py.File(path, "a")` would make a fresh,
    empty file without the record's own settings."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        store = RunStore(Path(d) / "half.h5")
        store.put("a", {"v": 1})
        store.checkpoint()
        # what a kill between the two renames leaves: .bak and .damaged, no .h5
        os.replace(store.path, store.path.with_name(store.path.name + ".damaged"))
        _as_fresh_process(store.path)
        fresh = RunStore(store.path)
        fresh.put("probe", {"after": "restore"})
        assert fresh.recovered and fresh.get("a") == {"v": 1}, "not restored"
        assert fresh.get("probe") == {"after": "restore"}
        assert any(r.get("recovered") for r in fresh.ledger_rows())
        # a first write to a path with nothing beside it creates the record
        # with its own settings (persistent free space), not h5py's defaults
        bare = RunStore(Path(d) / "bare.h5")
        bare.put("a", {"v": 1})
        with h5py.File(bare.path, "r") as f:
            _, persist, _ = f.id.get_create_plist().get_file_space_strategy()
        assert persist, "the file does not track its free space persistently"
    print("  half-restored record: the next write finished the restore")


def test_a_writer_whose_first_verify_was_skipped_still_stops_on_damage() -> None:
    """`_verify_once_for_writing` gives no verdict while
    another process holds the file; the verify happens on a later write — by
    which time THIS process may have written, and a restore must then stop
    it, not let it carry on over a record that lost its writes."""
    import tempfile

    from octomod.result import runstore as rs_mod
    from octomod.result.runstore import RecordDamaged

    with tempfile.TemporaryDirectory() as d:
        store = RunStore(Path(d) / "skipped.h5")
        for k in range(30):
            store.put(f"rounds/round_{k}/model/parameters", [{"id": f"k{k}"}] * 5)
        store.checkpoint()
        store.put("b", {"v": 2})
        _corrupt_inside(store.path)
        # the state after a skipped verify: has written, not verified
        _as_fresh_process(store.path)
        rs_mod._WROTE.add(store.path.resolve())
        writer = RunStore(store.path)
        try:
            writer.put("c", {"v": 3})
        except RecordDamaged:
            pass
        else:
            raise AssertionError("a writer carried on over a restored record")
        assert writer.verify() is None and writer.get("b") is None
    print("  skipped verify: a writer that had written restored and stopped")


_HOLD = """
import sys, time, h5py
with h5py.File(sys.argv[1], "a"):
    print("held", flush=True)
    time.sleep(float(sys.argv[2]))
"""


def test_a_writer_killed_inside_a_write_leaves_a_file_only_the_checkpoint_opens() -> (
    None
):
    """A writer killed inside a write, made deterministic.

    The record's superblock (v3, `libver` in `_CREATE`) carries an "open for
    write" consistency flag that only a clean close clears. A process
    SIGKILLed while it holds the file open for writing leaves the flag set,
    and HDF5 then refuses EVERY open — `r` and `a`, with or without its file
    lock — with "file is already open for write (may use <h5clear file> to
    clear file consistency flags)". `_is_damage` must read that message as
    damage: read as a lock, the reader retries it, the resuming writer's
    verify gives up on it as "held by another process", its first write fails
    the same way, and the run dies with the checkpoint untouched beside it."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        store = RunStore(Path(d) / "killed.h5")
        store.put("a", {"v": 1})
        store.append_ledger({"ts": "", "event": "run_start", "round": 0})
        store.checkpoint()
        _as_fresh_process(store.path)
        writer = subprocess.Popen(
            [PY, "-c", _HOLD, str(store.path), "30"],
            stdout=subprocess.PIPE,
            text=True,
        )
        assert writer.stdout.readline().strip() == "held"
        writer.kill()
        writer.wait()
        assert not _opens(store.path), "a killed writer's file should not open"
        # a reader gets the checkpoint
        assert RunStore(store.path).get("a") == {"v": 1}, "reader not served .bak"
        # a resuming writer restores it, keeps the flagged file, and carries on
        fresh = RunStore(store.path)
        fresh.put("probe", {"after": "restore"})
        assert fresh.recovered and _opens(store.path), "the file was not restored"
        assert store.path.with_name(store.path.name + ".damaged").exists()
        assert fresh.get("a") == {"v": 1} and fresh.get("probe") == {"after": "restore"}
        assert any(r.get("recovered") for r in fresh.ledger_rows())
        fresh.checkpoint()
    print("  killed inside a write: the flagged file was restored from the checkpoint")


def test_a_file_another_process_holds_is_not_damage() -> None:
    """HDF5's lock error is not damage: read as damage by `verify()`, the
    first write of a process would restore the checkpoint over a HEALTHY file
    that another process simply has open."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        store = RunStore(Path(d) / "held.h5")
        store.put("a", {"v": 1})
        store.checkpoint()
        store.put("b", {"v": 2})  # after the checkpoint: a restore would lose it
        _as_fresh_process(store.path)
        holder = subprocess.Popen(
            [PY, "-c", _HOLD, str(store.path), "1.0"],
            stdout=subprocess.PIPE,
            text=True,
        )
        assert holder.stdout.readline().strip() == "held"
        other = RunStore(store.path)
        other.put("c", {"v": 3})  # waits for the lock; must NOT restore
        holder.wait()
        assert not other.recovered, "a held file was taken for a damaged one"
        assert other.get("b") == {"v": 2} and other.get("c") == {"v": 3}
        assert not store.path.with_name(store.path.name + ".damaged").exists()
    print("  held by another process: waited for the lock, restored nothing")


def main(trials: int, seed: int) -> int:
    random.seed(seed)
    test_a_record_that_opens_but_does_not_read_is_restored()
    test_a_file_another_process_holds_is_not_damage()
    test_a_run_end_compaction_meets_damage_as_a_checkpoint_does()
    test_a_half_restored_record_is_finished_by_the_next_write()
    test_a_writer_whose_first_verify_was_skipped_still_stops_on_damage()
    test_a_writer_killed_inside_a_write_leaves_a_file_only_the_checkpoint_opens()
    # a failed earlier run leaves its records in this suite's runs folder, and
    # a fixed id that already exists would fail the next run for that reason
    for left in RunStore.all_in(config.RUNS_DIR):
        if left.run_id.startswith("crash_"):
            left.remove()
    # the truncation test's unkilled run says how long a run takes, so the
    # kill times cover it — kills fall in [1 s, 0.9 * that] — and the outcome
    # a clean run ends with, which every resume must reach
    t_run, expected_outcome = test_a_truncated_record_is_restored_from_its_checkpoint()
    print(f"  unkilled run: {t_run:.1f} s, outcome {expected_outcome}")
    results = []
    for i in range(trials):
        run_id = f"crash_{i}"
        kill_after = random.uniform(1.0, max(2.0, 0.9 * t_run))
        r = kill_and_resume(run_id, kill_after)
        results.append(r)
        print(
            f"  trial {i}: killed at {r['kill_after_s']}s "
            f"({'finished first' if r['finished_before_kill'] else 'mid-run'}); "
            f"file opens={r['file_opens']} bak={r['bak_exists']} "
            f"markers={r['markers_before']}; resumed rc={r['resumed_rc']} "
            f"outcome={r['outcome']}{' RECOVERED' if r['recovered_row'] else ''}"
            f"{' (killed after run_end)' if r.get('ended_before_kill') else ''}"
        )
        RunStore.for_run(config.RUNS_DIR, run_id).remove()  # .damaged too
    # one kill placed AFTER run_end, in the post-run work
    e = kill_after_run_end("crash_after_end")
    RunStore.for_run(config.RUNS_DIR, "crash_after_end").remove()
    if e["landed"]:
        print(
            f"  kill after run_end: readable={e['readable']} outcome={e['outcome']}; "
            f"resume rc={e['resume_rc']}; analysis regenerated={e['analysis']}"
        )
        assert e["readable"], "a kill after run_end left no readable record"
        assert e["outcome"] == expected_outcome, (e["outcome"], expected_outcome)
        assert e["resume_rc"] == 1 and "already ended" in e["resume_says"], e[
            "resume_says"
        ][-400:]
        assert e["report_rc"] == 0 and e["analysis"], "the analysis was not regenerated"
    else:
        print("  kill after run_end: the run ended before the poll saw run_end")
    # one kill placed INSIDE a write, since the random ones seldom land there
    for _attempt in range(3):
        w = kill_inside_a_write("crash_in_write")
        RunStore.for_run(config.RUNS_DIR, "crash_in_write").remove()
        if w["landed"]:
            break
    assert w["landed"], "no kill landed inside a write in three runs"
    print(
        f"  kill inside a write at {w['killed_at_s']}s: file opens="
        f"{w['file_opens']} bak opens={w['bak_opens']}; resumed rc="
        f"{w['resumed_rc']} outcome={w['outcome']}"
        f"{' RECOVERED' if w['recovered_row'] else ''}"
        f"{' (.damaged kept)' if w['damaged_kept'] else ''}"
    )
    assert w["bak_opens"], "the checkpoint of a run killed inside a write is unreadable"
    assert w["resumed_rc"] == 0, w.get("stderr_tail")
    assert w["outcome"] == expected_outcome, (w["outcome"], expected_outcome)
    if not w["file_opens"]:  # the flagged file: restored, ledgered, kept
        assert w["recovered_row"] and w["damaged_kept"], "restore not ledgered/kept"

    killed = [r for r in results if not r["finished_before_kill"]]
    damaged = [r for r in killed if r["file_exists"] and not r["file_opens"]]
    unreadable = [r for r in damaged if not r["bak_opens"]]
    after_end = [r for r in killed if r.get("ended_before_kill")]
    failed_resume = [
        r for r in killed if not r.get("ended_before_kill") and r["resumed_rc"] != 0
    ]
    print(
        f"\nCRASH REPORT — {len(killed)} kill(s): main file damaged in "
        f"{len(damaged)}, of which the checkpoint was also unreadable in "
        f"{len(unreadable)}; {len(after_end)} landed after run_end (nothing "
        f"to resume); resume failed in {len(failed_resume)}"
    )
    for r in failed_resume:
        print("  resume failure:", r.get("stderr_tail", "")[-400:])
    assert not unreadable, "a kill left neither the record nor its checkpoint readable"
    assert not failed_resume, "a killed run did not resume to completion"
    for r in killed:
        # a resume ends where a clean run ends, and loses no marker it had
        assert r["outcome"] == expected_outcome, (r["outcome"], expected_outcome)
        if isinstance(r["markers_before"], list):
            lost = set(r["markers_before"]) - set(r["markers_after"])
            assert not lost, f"markers lost across the kill and resume: {lost}"
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=6)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    sys.exit(main(a.trials, a.seed))
