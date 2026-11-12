"""How a test reaches a run, which is one file.

    from tests._record import run_root, temp_record, ledger_rows, rnd

    root = run_root(run_id)                  # the record of runs/<id>.h5
    r0 = rnd(root, 0)                        # rounds/round_0
    (r0 / "evaluation").exists()
    report = (r0 / "evaluation").get()
    rows = ledger_rows(root)                 # the ledger as dicts

    with temp_record() as root:              # a throwaway record for a fixture
        (rnd(root, 0) / "model/antimony").put_text("model m\\nend")

    saved = save_run(run_id)                 # a paused run, set aside ...
    ...                                      # ... answer its gate one way ...
    restore_run(saved, run_id)               # ... and back to the same pause
                                             # (file_gate_loop.drive(resume=True)
                                             # answers it on the first call)

A record `Node` is addressed by record key — the `RunResult` tree of
`octomod/result/model.py` — and reads and writes record data (`get`/
`put`), text (`text`/`put_text`) and tables (`table`/`put_table`). Where each
part of a round lives is in `octomod.result.node` (`work_node`,
`model_node`, `gates_node`, `markers_node`, `candidate_ids`).
"""

from __future__ import annotations

import atexit
import contextlib
import shutil
import tempfile
from pathlib import Path

from octomod import config
from octomod.result import node as tree
from octomod.result.node import Node
from octomod.result.runstore import RunStore

REPO = Path(__file__).resolve().parents[1]


def run_store(run_id: str, runs_dir: Path | None = None) -> RunStore:
    return RunStore.for_run(runs_dir or config.RUNS_DIR, run_id)


def run_root(run_id: str, runs_dir: Path | None = None) -> Node:
    """The record of a run under runs/ (or `runs_dir`)."""
    return Node(run_store(run_id, runs_dir))


def record_at(path: Path) -> Node:
    """A record at an explicit file path (created on first write)."""
    p = Path(path)
    if p.suffix != ".h5":
        p = p.with_suffix(".h5") if p.suffix else p.parent / f"{p.name}.h5"
    return Node(RunStore(p))


@contextlib.contextmanager
def temp_record(name: str = "fixture"):
    """A throwaway record in a temporary directory, removed afterwards."""
    tmp = Path(tempfile.mkdtemp(prefix="octomod_test_"))
    try:
        root = Node(RunStore(tmp / f"{name}.h5"))
        root.store.create()
        yield root
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def save_run(run_id: str, runs_dir: Path | None = None) -> Path:
    """Set a run aside — its record, checkpoint and rendered documents — in a
    temporary directory, so a suite can answer one pause two ways without
    running the modules before it twice. `restore_run` puts it back."""
    store = run_store(run_id, runs_dir)
    saved = Path(tempfile.mkdtemp(prefix="octomod_saved_"))
    atexit.register(shutil.rmtree, saved, ignore_errors=True)
    for p in (store.path, store.backup_path):
        if p.exists():
            shutil.copy2(p, saved / p.name)
    if store.reports_dir.exists():
        shutil.copytree(store.reports_dir, saved / store.reports_dir.name)
    return saved


def restore_run(saved: Path, run_id: str, runs_dir: Path | None = None) -> None:
    """Replace the run with what `save_run` set aside (the copy is kept, so a
    third answer can start from it too). Answer the restored pause on the
    first call (`drive(..., resume=True)`): a resume without an answer
    re-enters the paused module."""
    store = run_store(run_id, runs_dir)
    store.remove()
    for p in (store.path, store.backup_path):
        if (saved / p.name).exists():
            shutil.copy2(saved / p.name, p)
    if (saved / store.reports_dir.name).exists():
        shutil.copytree(saved / store.reports_dir.name, store.reports_dir)


def rnd(root: Node, k: int) -> Node:
    """`rounds/round_<k>`."""
    return tree.round_node(root, k)


def work(root: Node, k: int, cid: str | None = None) -> Node:
    """The fitted problem's group: a candidate's, or `_single`."""
    return tree.work_node(tree.round_node(root, k), cid)


def ledger_rows(root: Node) -> list[dict]:
    return root.store.ledger_rows()


def pending_gate(root: Node) -> dict | None:
    """The paused gate's payload, or None when nothing is pending."""
    return (root / "pending_gate").get(None)


def reports_dir(root: Node) -> Path:
    """Where the run's rendered HTML lives (`runs/<id>_reports/`)."""
    return root.store.reports_dir
