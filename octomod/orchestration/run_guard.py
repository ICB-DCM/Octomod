"""Run-id safety: an existing run is never silently reused.

A run whose ledger closes with `run_end` is finished and its id is refused,
unless re-entered with `--from-module` (which writes a new `run_start` and makes
it live again). A paused run resumes only while its spec and inputs are the ones
it started with: the `input` group of its own record, or, for a run without
one, its testcase folder under the `testcase_sha` key.

The run is one record, `runs/<id>.h5`; what the guard reads is its
ledger and its `run` record, and what it deletes on `--overwrite` is the
record, its checkpoint and its rendered documents (`RunStore.remove`).
"""

from __future__ import annotations

from pathlib import Path

from octomod import config
from octomod.orchestration import run_folder
from octomod.orchestration.ledger import sha256_file, sha256_text
from octomod.result.node import Node, RecordMissing


class RunIdRefused(Exception):
    """The run-id names a finished run, or the run has drifted from its inputs.

    Carries the whole operator-facing message: the caller prints it and exits
    non-zero rather than reformatting it.
    """


def manifest(inputs) -> dict[str, str]:
    """Every file a run reads, with its content sha, keyed by path.

    The files are `run_folder.inputs_read`: what the snapshot copies is what
    the identity hashes, and nothing else under the case moves it.
    `inputs` is a folder (a staged testcase, a legacy run's inputs) or a record
    `Node` (its `input` group is hashed — the same list and digests, so a
    snapshot's identity is the folder's). Recorded in the `run` record so a
    refused resume can name the file that moved.
    """
    if isinstance(inputs, Node):
        return run_folder.manifest(inputs)
    inputs_dir = Path(inputs)
    return {
        rel.as_posix(): sha256_file(inputs_dir / rel)
        for rel in run_folder.inputs_read(inputs_dir)
    }


def sha_of(man: dict[str, str]) -> str:
    return sha256_text("\n".join(f"{rel}:{sha}" for rel, sha in sorted(man.items())))


def input_sha(inputs) -> str:
    """One hash over the inputs: every path with its content sha, so a renamed
    file drifts as loudly as an edited one."""
    return sha_of(manifest(inputs))


# The name older runs recorded their input digest under; same walk, same digest.
testcase_sha = input_sha


def drifted(was: dict[str, str], now: dict[str, str]) -> list[str]:
    """Which files moved, as lines a person can act on."""
    lines = []
    for rel in sorted(set(was) | set(now)):
        if rel not in now:
            lines.append(f"{rel} — removed")
        elif rel not in was:
            lines.append(f"{rel} — added")
        elif was[rel] != now[rel]:
            lines.append(f"{rel} — edited")
    return lines


def ended_outcome(root: Node) -> str | None:
    """The outcome of the `run_end` that closes this run's ledger, else None.

    A `run_end` counts only while no `run_start` or live event follows it: a
    `--from-module` re-entry makes the run live again, while a refused invocation
    writes nothing, so an ended run stays ended. A malformed line is skipped
    rather than raising: the guard must not stop a run from being cleaned up.
    """
    from octomod.result.access import store_of

    store = store_of(root)
    if not store.exists_on_disk():
        return None
    outcome = None
    for row in store.ledger_rows():
        event = row.get("event")
        if event == "run_start":
            outcome = None
        elif event == "run_end":
            # a crash, or a stop the engine declared resumable (e.g. the
            # agent-call byte cap), is not an ending: the run resumes from its
            # markers as after a kill
            out = str(row.get("outcome") or "ended")
            outcome = None if (out == "crashed" or row.get("resumable")) else out
        elif outcome is not None and event in _LIVE_AGAIN_EVENTS:
            # a live event after a run_end means a `--from-module` re-entry
            # brought the run back: the run_end is history and a plain resume
            # is allowed
            outcome = None
    return outcome


# ledger events that only a live run writes; any of them after the last run_end
# means the run was re-entered and is paused or running again
_LIVE_AGAIN_EVENTS = frozenset({"gate_pending", "marker", "agent_call", "human_gate"})


def remove(root: Node, *, keep_input: bool = False) -> list[str]:
    """Delete a run — its record, checkpoint and rendered documents —
    returning what was removed for printing.

    Refuses anything that is not inside RUNS_DIR, so a surprising run-id can
    never turn `--overwrite` into a delete somewhere else on the disk.
    `keep_input` leaves the record's `input` group (and `input_source`) behind
    in a fresh record, e.g. the inputs of a run the user authored in place,
    which are the only copy of those inputs.
    """
    import shutil
    import tempfile

    from octomod.result.access import store_of
    from octomod.result.runstore import RunStore

    store = store_of(root)
    runs = config.RUNS_DIR.resolve()
    target = store.path.resolve()
    if target.parent != runs:
        raise RunIdRefused(
            f"refusing to delete {target}: --overwrite only ever removes a "
            f"run record inside {runs}"
        )
    if not store.exists_on_disk():
        return []
    stash_dir = None
    stash = None
    if keep_input and run_folder.input_node(root).exists():
        # the inputs are carried across the delete in a scratch record, since
        # the file they live in is what is being removed
        stash_dir = Path(tempfile.mkdtemp(prefix="octomod_keep_"))
        stash = Node(RunStore(stash_dir / "keep.h5"))
        stash.store.create()
        run_folder.input_node(root).copy_to(run_folder.input_node(stash))
        (root / run_folder.SOURCE_KEY).copy_to(stash / run_folder.SOURCE_KEY)
    try:
        removed = store.remove()
        if stash is not None:
            store.create()
            run_folder.input_node(stash).copy_to(run_folder.input_node(root))
            (stash / run_folder.SOURCE_KEY).copy_to(root / run_folder.SOURCE_KEY)
    finally:
        if stash_dir is not None:
            shutil.rmtree(stash_dir, ignore_errors=True)
    return removed


def check(
    root: Node,
    inputs,
    workflow_sha: str,
    *,
    overwrite: bool = False,
    from_module: str | None = None,
    keep_input: bool = False,
) -> None:
    """Raise RunIdRefused unless this run-id may be started or resumed.

    `inputs` is the folder the run reads (a legacy run's testcase), or None
    when the run's inputs are the record's own `input` group. Called before
    the record is created, and therefore before its `run` record is
    rewritten — the recorded shas it compares against would otherwise already
    be the new ones.

    `from_module` re-enters a run on purpose (entry-anywhere), naming the
    module and invalidating what follows it, so a finished run is a legitimate
    target and the ended-run refusal does not apply. What the guard refuses is
    SILENT reuse, and `--from-module` is the opposite of silent. The drift
    check still applies: re-entering with a spec that has moved is the second
    case the guard exists to catch.
    """
    from octomod.result.access import store_of

    store = store_of(root)
    run_id = store.run_id
    if overwrite:
        removed = remove(root, keep_input=keep_input)
        if removed:
            print(
                f"--overwrite: removed run {run_id} "
                f"({len(removed)} file(s), including "
                f"{', '.join(removed[:3])}{' …' if len(removed) > 3 else ''})"
                + (f"; kept {run_folder.INPUT_KEY}/" if keep_input else "")
            )
        return
    if not store.exists_on_disk():
        return

    outcome = ended_outcome(root)
    if outcome is not None and from_module is None:
        raise RunIdRefused(
            f"run {run_id} already ended ({outcome}) — choose a new id, or "
            f"pass --overwrite to delete it.\n"
            f"  to re-run part of it in place instead, name the module: "
            f"--from-module model|data|assembly|estimation|evaluation\n"
            f"  the run is at {store.path}"
        )

    try:
        meta = (Node(store) / "run").get(None)
    except (RecordMissing, ValueError):  # no `run` record yet is no drift
        return  # a DAMAGED record (RecordDamaged) is not swallowed here
    if not isinstance(meta, dict):
        return

    drift = []
    was = meta.get("workflow_sha")
    if was and was != workflow_sha:
        drift.append(
            f"workflow_sha: started with {was}, now {workflow_sha} "
            f"(the spec or its overlay changed)"
        )
    # checked against whichever key the run recorded (older runs: testcase_sha)
    key = "input_sha" if meta.get("input_sha") else "testcase_sha"
    was_in = meta.get(key)
    if was_in:
        source = inputs if inputs is not None else Node(store)
        now_man = manifest(source)
        now_in = sha_of(now_man)
        if was_in != now_in:
            where = (
                f"in the record's {run_folder.INPUT_KEY}/ group"
                if inputs is None
                else f"under {Path(inputs).name}/"
            )
            moved = drifted(meta.get("input_files") or {}, now_man)
            drift.append(
                f"{key}: started with {was_in}, now {now_in} "
                f"(an input {where} changed)"
                # the files that moved, when the run recorded a manifest
                + "".join(f"\n      - {m}" for m in moved[:12])
                + (f"\n      - … and {len(moved) - 12} more" if len(moved) > 12 else "")
            )
    if drift:
        raise RunIdRefused(
            f"run {run_id} is paused mid-run, but its inputs have drifted "
            f"since it started:\n"
            + "".join(f"  · {d}\n" for d in drift)
            + "  put them back as they were, pass --overwrite to start it "
            "again, or use a new run-id."
        )
