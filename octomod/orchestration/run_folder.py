"""The run record carries its own inputs: the `input/` group of `runs/<id>.h5`.

A run reads its inputs only from that snapshot, which gets there by
**snapshot** (`run --testcase` copies the staged case into the record before
S0 and never reads the source again), **in the record** (`run --run-id` alone
runs on an `input` group already in the record — authored with the user, or
copied from a previous run with `--from-run`, whose `input_source` records
`started_from`). A snapshot carries what a run reads from the case
(`inputs_read`) and nothing else, and the same list is the run's input
identity (`run_guard.manifest`): raw instrument files, provenance scripts,
notes and `truth/` stay in the staging folder.

There is no run directory. The snapshot lives in the record as
`input/<relative path>` (text files as text, everything else as bytes, the
path's separators kept as key segments) beside `input_source` (what a legacy
run folder keeps in `input/source.json`). The engine's readers are file-based, so a
run that starts from the record MATERIALISES the group into a temporary
directory (`materialise_dir`), which becomes `ctx.testcase_dir` for the
process: read-only, and gone at exit.
"""

from __future__ import annotations

import atexit
import datetime
import hashlib
import json
import posixpath
import re
import shutil
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from octomod import config
from octomod.result.node import Node
from octomod.workflow_modules.knowledge import supplied_literature as _lit

INPUT_DIRNAME = "input"  # the record group, and the name in messages
INPUT_KEY = "input"
SOURCE_KEY = "input_source"  # what `input/source.json` was
SOURCE_FILE = "source.json"
PENDING_KEY = "input_pending"  # set while a snapshot or copy is being written  # never snapshotted: it lives at SOURCE_KEY

# What a run reads from a case whatever the case says (`inputs_read`): these
# top-level files, when present, and every file under these folders —
# `knowledge/` is the knowledge module's output (its json, the documents it
# cached, its calls, the intent it saw).
READ_FILES = ("description.md", "intent.yaml", "testcase.yaml", "blocklist.txt")
READ_DIRS = ("data", "supplied", "stubs", "knowledge")
# Never an input at any depth: benchmark ground truth, and build detritus.
_NEVER_DIRS = frozenset({"truth", "__pycache__", ".git"})
_NEVER_FILES = frozenset({".DS_Store"})

# Stored as text (readable with `show`), when they decode as UTF-8; anything
# else is stored as opaque bytes. The bytes read back are identical either way.
TEXT_SUFFIXES = frozenset(
    {
        ".md",
        ".txt",
        ".yaml",
        ".yml",
        ".json",
        ".tsv",
        ".csv",
        ".py",
        ".ant",
        ".xml",
        ".sbml",
        ".toml",
        ".cfg",
        ".ini",
        ".html",
        ".htm",
        ".bib",
        ".tex",
        ".rst",
        ".mmd",
        ".sh",
        ".r",
        ".jl",
    }
)

# `<project>_<YYYYMMDD_HHMMSS>`: the default run id, from which a project name
# is recovered.
_STAMP = re.compile(r"_\d{8}_\d{6}$")


class InputsMissing(Exception):
    """Neither `--testcase` nor an `input` group in the record: there is
    nothing to run on.

    Raised before the record is created and before a single token is spent,
    and carries the whole operator-facing message.
    """


def stamp(now: datetime.datetime | None = None) -> str:
    return (now or datetime.datetime.now()).strftime("%Y%m%d_%H%M%S")


def default_run_id(project: str, now: datetime.datetime | None = None) -> str:
    return f"{project}_{stamp(now)}"


def project_of(run_id: str, testcase_dir: Path | None) -> str:
    """The project a run belongs to: the testcase's name, else the run id
    without its timestamp suffix, else the run id itself."""
    if testcase_dir is not None:
        return Path(testcase_dir).name
    return _STAMP.sub("", run_id) or run_id


def archive_dir(project: str) -> Path:
    """Where a project's cross-run tried-models archive lives.

    Keyed by project, not by input hash: a follow-up run always edits
    something, so it would always start blind.
    """
    return config.PROJECTS_DIR / project


def input_node(root: Node) -> Node:
    """The record's `input` group."""
    return root / INPUT_KEY


def is_complete(root: Node) -> bool:
    """The record holds a WHOLE `input` group: present, and no snapshot or copy
    of it still pending (`input_pending` is set before the first file and
    cleared after the last). A pending one is what a kill cut short — neither
    a run's inputs nor an edit to compare a testcase against — and is taken
    again."""
    return input_node(root).exists() and not (root / PENDING_KEY).exists()


# ------------------------------------------------------ what a run reads


def _never(rel: PurePosixPath) -> bool:
    return (
        bool(_NEVER_DIRS.intersection(rel.parts))
        or rel.name in _NEVER_FILES
        or rel.suffix == ".pyc"
    )


def _fixed(rel: PurePosixPath) -> bool:
    """`rel` is read by every run: a `READ_FILES` file or one under a
    `READ_DIRS` folder."""
    if _never(rel):
        return False
    if len(rel.parts) == 1:
        return rel.name in READ_FILES
    return rel.parts[0] in READ_DIRS


def _file_urls(
    fixed: Iterable[PurePosixPath], text_of: Callable[[PurePosixPath], str | None]
) -> list[str]:
    """The `file:` urls of the evidence items a run is handed: the intent's
    `supplied_literature`, the evidence of a stub reply — a research reply's
    `evidence_items`, the per-reaction and per-fact `evidence` of a knowledge
    reply (a fixture's reply may name a case document; a live one never
    does) — and the same of the knowledge module's `knowledge/knowledge.json`.
    Unreadable or malformed files name nothing here — S0 refuses a bad intent
    by name."""
    import yaml

    urls: list[str] = []

    def add(items) -> None:
        for it in items if isinstance(items, list) else []:
            if isinstance(it, dict) and str(it.get("url") or "").startswith("file:"):
                urls.append(str(it["url"]))

    try:
        intent = yaml.safe_load(text_of(PurePosixPath("intent.yaml")) or "")
    except Exception:  # a malformed intent is S0's refusal, not this list's
        intent = None
    if isinstance(intent, dict):
        add(_lit.items(intent))
    for rel in fixed:
        is_stub = rel.parts[0] == "stubs" and rel.suffix == ".json"
        if not is_stub and rel.as_posix() != "knowledge/knowledge.json":
            continue
        try:
            reply = json.loads(text_of(rel) or "null")
        except Exception:  # a malformed stub is the stub backend's error
            continue
        if isinstance(reply, dict):
            add(reply.get("evidence_items"))
            for key in ("reactions", "facts"):
                for entry in reply.get(key) or []:
                    if isinstance(entry, dict):
                        add(entry.get("evidence"))
    return urls


def _documents(
    fixed: Iterable[PurePosixPath],
    text_of: Callable[[PurePosixPath], str | None],
    locate: Callable[[PurePosixPath], PurePosixPath | None],
) -> set[PurePosixPath]:
    """The case files the evidence items' `file:` urls name, each read as the
    source cache reads it (`supplied_literature.case_document`) and kept only
    when `locate` finds it inside the case."""
    out = set()
    for url in _file_urls(fixed, text_of):
        named = _lit.case_document(url)
        found = locate(named) if named is not None else None
        if found is not None and not _never(found):
            out.add(found)
    return out


def inputs_read(case_dir: Path) -> list[Path]:
    """Exactly what a run reads from a case, as sorted relative paths (files
    only). What the snapshot copies, what `run_guard.manifest` hashes as the
    run's input identity, and what the legacy importer transcribes:

    1. `description.md`, `intent.yaml`, `testcase.yaml`, `blocklist.txt`,
       each when present;
    2. every file under `data/`, `supplied/`, `stubs/` and `knowledge/` (the
       knowledge module's json, the documents it cached — stored as text or
       bytes by the snapshot's own rule — its calls, and the intent it saw);
    3. every case file an evidence item names by a `file:` url — the intent's
       `supplied_literature` (`file:./paper/x.pdf`), a stub reply's
       `evidence_items` or per-reaction and per-fact `evidence`, and the
       knowledge module's — resolved against the case as the source cache
       resolves it. A named file that does not exist is left out here; the
       cache records it as unreachable, as it would anyway.

    Nothing else. Not `truth/` (benchmark ground truth, which no run may
    read), nor build detritus. Not `curation/` or `notes/`: staging notes no
    run reads, which may be appended while a run is live, so a paused run
    stays resumable. Not `make_data.py`: it generates the data, and the data
    is what is hashed. Not `tried_models.json`: the engine appends to it after
    every run, so hashing it would make a case drift from itself, and when a
    run consumes it the snapshot's own sha goes in the run's `run` record.
    Not raw instrument files, preprocessing, a `paper/` beyond what an item
    names, or any other provenance: the run never reads them, so they stay in
    the staging folder, out of the record and out of the identity.
    """
    case = Path(case_dir)
    fixed: set[PurePosixPath] = set()
    for name in READ_FILES:
        if (case / name).is_file():
            fixed.add(PurePosixPath(name))
    for folder in READ_DIRS:
        if not (case / folder).is_dir():
            continue
        for path in (case / folder).rglob("*"):
            if path.is_file():
                rel = PurePosixPath(path.relative_to(case).as_posix())
                if _fixed(rel):
                    fixed.add(rel)
    root = case.resolve()

    def text_of(rel: PurePosixPath) -> str | None:
        path = case / rel
        return path.read_text(errors="replace") if path.is_file() else None

    def locate(named: PurePosixPath) -> PurePosixPath | None:
        # the source cache's own resolution: joined to the case, then resolved
        path = (root / named).resolve()
        if not path.is_file() or not path.is_relative_to(root):
            return None
        return PurePosixPath(path.relative_to(root).as_posix())

    found = fixed | _documents(fixed, text_of, locate)
    return [Path(rel) for rel in sorted(found)]


def _recorded_inputs_read(root: Node) -> list[str]:
    """`inputs_read` over the record's `input` group: the same rule applied
    to its entries, so a record's input identity is the one its staging
    folder has. A snapshot holds exactly this list; a group authored in
    place, or written by a whole-case snapshot, may hold more, which the run
    never reads."""
    present = {PurePosixPath(rel) for rel in entries(root)}
    fixed = {rel for rel in present if _fixed(rel)}

    def text_of(rel: PurePosixPath) -> str | None:
        if rel not in present:
            return None
        return read_bytes(root, rel.as_posix()).decode("utf-8", errors="replace")

    def locate(named: PurePosixPath) -> PurePosixPath | None:
        # the group holds no links, so the resolution is the lexical one
        rel = PurePosixPath(posixpath.normpath(named.as_posix()))
        if rel.is_absolute() or rel.parts[:1] == ("..",):
            return None
        return rel if rel in present else None

    found = fixed | _documents(fixed, text_of, locate)
    return sorted(rel.as_posix() for rel in found)


# ------------------------------------------------------------ the snapshot


def _entry(inp: Node, rel: Path) -> Node:
    """`input/<segment>/<segment>/…`: each path part is one key segment."""
    node = inp
    for part in rel.parts:
        node = node.child(part)
    return node


def _put_file(inp: Node, rel: Path, data: bytes) -> None:
    node = _entry(inp, rel)
    if rel.suffix.lower() in TEXT_SUFFIXES and b"\x00" not in data:
        try:
            # bytes, not `read_text`: no newline translation, so the sha of
            # what reads back is the sha of the file
            node.put_text(data.decode("utf-8"))
            return
        except UnicodeDecodeError:
            pass
    node.put_blob(data)


def snapshot(source: Path, dest: Node) -> list[str]:
    """Copy a staged testcase into a record's `input` group. Returns what was
    copied (relative posix paths).

    What a run reads (`inputs_read`) and nothing else: the engine reads every
    input only from the snapshot, and everything else in the staging folder
    stays there.
    """
    source = Path(source)
    inp = dest if dest.name == INPUT_KEY else input_node(dest)
    # a snapshot is whole or visibly unfinished: the pending mark goes in
    # before the first file and comes out after the last (`is_complete`), so
    # a kill in between is never mistaken for inputs, or for an edit
    root = Node(inp.store)
    (root / PENDING_KEY).put({"from": str(source)})
    inp.delete()
    copied = []
    for rel in inputs_read(source):
        _put_file(inp, rel, (source / rel).read_bytes())
        copied.append(rel.as_posix())
    (root / PENDING_KEY).delete()
    return copied


def entries(root: Node) -> list[str]:
    """Every file of the record's `input` group, as relative posix paths."""
    inp = input_node(root)
    if not inp.exists():
        return []
    prefix = inp.key + "/"
    return sorted(
        k[len(prefix) :]
        for k, kind in inp.store.walk(inp.key)
        if kind == "dataset" and k.startswith(prefix)
    )


def read_bytes(root: Node, rel: str) -> bytes:
    """One input file's bytes, as it was staged."""
    return _entry(input_node(root), Path(rel)).blob()


def manifest(root: Node) -> dict[str, str]:
    """{relative path: sha256} of what a run reads of the record's `input`
    group — the same list and digest `run_guard.manifest` computes over a
    directory, so a run's input identity is one number whether it is read
    from the record or from a folder."""
    # sha16, as `ledger.sha256_file` hashes a folder's files
    return {
        rel: hashlib.sha256(read_bytes(root, rel)).hexdigest()[:16]
        for rel in _recorded_inputs_read(root)
    }


def listing(root_or_dir) -> list[str]:
    """The input files, for the record and for the report's Inputs block:
    the record's `input` group, or (a legacy run) what a run reads of the
    folder."""
    if isinstance(root_or_dir, Node):
        return entries(root_or_dir)
    inp = Path(root_or_dir)
    if not inp.is_dir():
        return []
    return [rel.as_posix() for rel in inputs_read(inp)]


MATERIALISED_PREFIX = "octomod_input_"
STALE_AFTER_S = 24 * 3600


def sweep_stale(max_age_s: float = STALE_AFTER_S) -> list[Path]:
    """Remove materialised input directories (`octomod_input_*` in the temp
    dir) older than `max_age_s` — left behind by a process that was killed
    before its `finally` or `atexit` ran. Never raises."""
    import time

    removed = []
    cutoff = time.time() - max_age_s
    try:
        candidates = list(Path(tempfile.gettempdir()).glob(MATERIALISED_PREFIX + "*"))
    except OSError:
        return removed
    for path in candidates:
        try:
            if path.is_dir() and path.stat().st_mtime < cutoff:
                shutil.rmtree(path, ignore_errors=True)
                removed.append(path)
        except OSError:
            continue
    return removed


def release(inputs: Inputs | None) -> None:
    """Remove the temporary directory `materialise` extracted the inputs into
    (not a legacy run's testcase folder, which is read in place). Called when
    the run's process is done with it; `atexit` stays as the fallback."""
    if inputs is None or inputs.legacy or inputs.dir is None:
        return
    d = Path(inputs.dir)
    if d.name.startswith(MATERIALISED_PREFIX) and d.parent == Path(
        tempfile.gettempdir()
    ):
        shutil.rmtree(d, ignore_errors=True)


def materialise_dir(root: Node) -> Path:
    """Extract the record's `input` group into a temporary directory
    (`octomod_input_*`) and return it — what `ctx.testcase_dir` is for a
    run started from the record. Removed when the run finishes
    (`release`, from `Orchestrator.run`) or, failing that, when the process
    exits; stale ones from killed processes are swept here. The engine never
    writes into it."""
    sweep_stale()
    tmp = Path(tempfile.mkdtemp(prefix=MATERIALISED_PREFIX))
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    for rel in entries(root):
        target = tmp / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(read_bytes(root, rel))
    return tmp


def copy_inputs(src_root: Node, dst_root: Node) -> list[str]:
    """A follow-up run: copy a previous record's `input` group (and its
    `input_source`, whose `run_id` then becomes the new run's `started_from`)
    into a new record. Returns what was copied."""
    if not input_node(src_root).exists():
        raise InputsMissing(
            f"run {src_root.store.run_id} has no input group to start from "
            f"(a run from before records carried their inputs); name a staged "
            f"case with --testcase instead"
        )
    if not dst_root.store.exists_on_disk():
        dst_root.store.create()
    (dst_root / PENDING_KEY).put({"from": src_root.store.run_id})
    input_node(src_root).copy_to(input_node(dst_root))
    (src_root / SOURCE_KEY).copy_to(dst_root / SOURCE_KEY)
    (dst_root / PENDING_KEY).delete()
    return entries(dst_root)


# --------------------------------------------------------------- the source


def read_source(root: Node) -> dict | None:
    """`input_source`, or None. Never raises: an `input` group with no source
    record is the authored-in-place case, not an error, and a malformed one
    must not be the thing that stops a run."""
    try:
        got = (root / SOURCE_KEY).get(None)
    except Exception:
        return None
    return got if isinstance(got, dict) else None


def _source_file(folder: Path | None) -> dict | None:
    """A staged folder's own `source.json`, or None (never raises)."""
    import json

    if folder is None:
        return None
    path = Path(folder) / SOURCE_FILE
    try:
        got = json.loads(path.read_text()) if path.is_file() else None
    except Exception:
        return None
    return got if isinstance(got, dict) else None


def write_source(
    root: Node,
    *,
    run_id: str,
    project: str,
    source: Path | None,
    started_from: str | None,
) -> dict:
    """Record, in the record, where these inputs came from.

    Beside the `input` group rather than inside it, so the group holds only
    the staged files; `copy_inputs` carries both, and the new run reads its
    `started_from` from the `run_id`.
    """
    record = {
        "run_id": run_id,
        "project": project,
        "source": str(source) if source else "authored in place",
        "started_from": started_from,
        "written_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    (root / SOURCE_KEY).put(record)
    return record


# ---------------------------------------------------------------- the plan


@dataclass
class Plan:
    """How this invocation will get its inputs — decided before anything is
    written, so a refusal costs nothing."""

    mode: str  # "snapshot" | "in_record" | "copy" | "legacy"
    source: Path | None  # the testcase it came from, when there is one
    project: str
    from_run: str | None = None  # "copy": the run whose inputs are copied
    # "in_record" with `--testcase`: the testcase was compared with the
    # record's `input` group and matched it (a differing one is refused)
    matched: Path | None = None

    @property
    def inputs_dir(self) -> Path | None:
        """What `run_guard.check` hashes: a folder for a legacy run, else None
        (the record's `input` group)."""
        return self.source if self.mode == "legacy" else None


@dataclass
class Inputs:
    """The resolved answer, after the snapshot (if any) has been taken."""

    dir: Path  # where the engine reads its inputs from (`ctx.testcase_dir`)
    source: Path | None
    project: str
    mode: str
    started_from: str | None = None
    copied: list[str] = field(default_factory=list)
    matched: Path | None = None  # see `Plan.matched`

    @property
    def legacy(self) -> bool:
        """A run from before records carried their inputs: no `input` group,
        so inputs are read from the testcase folder and a paused run still
        resumes."""
        return self.mode == "legacy"

    @property
    def source_label(self) -> str:
        if self.mode == "legacy":
            return f"{self.source} (a run from before input snapshots: inputs read in place)"
        return str(self.source) if self.source else "authored in place"


def plan(
    root: Node,
    testcase_dir: Path | None,
    *,
    overwrite: bool = False,
    from_run: str | None = None,
) -> Plan:
    """Decide where inputs come from. Pure: reads the record, writes nothing.

    In order:

    1. `--from-run`: a follow-up run — the previous record's `input` group is
       copied into this one (`--testcase` is not read).
    2. `--testcase` with `--overwrite`: the record is about to be deleted, so
       any `input` group in it is the old snapshot. Take a fresh one.
    3. an `input` group already there: authored in place, or a resume. Used as
       is. `--testcase`, if passed, is compared with it and must match: an
       edited testcase is refused (`run_guard.RunIdRefused`), never silently
       ignored. The project and the source case are the ones the
       record's `input_source` holds, not this command line's.
    4. a `run` record but no `input` group: a legacy run resumed or
       re-entered. Read the testcase as it always has; a snapshot would change
       its identity.
    5. `--testcase`: a fresh start. Snapshot it.
    6. nothing: raise `InputsMissing` before the record exists.
    """
    store = root.store
    run_id = store.run_id
    tc = Path(testcase_dir).resolve() if testcase_dir is not None else None
    if tc is not None and not tc.is_dir():
        raise InputsMissing(
            f"no such testcase: {tc}\n"
            f"  --testcase names a staged problem folder (intent.yaml, "
            f"description.md, testcase.yaml, data/)"
        )
    project = project_of(run_id, tc)
    exists = store.exists_on_disk()
    # an `input` group without its `input_source` is an interrupted snapshot
    # (a kill during the first second of a run): not the run's inputs, so it
    # is taken again from --testcase rather than compared against it
    partial = exists and (root / PENDING_KEY).exists()
    has_input = exists and is_complete(root)
    if partial and tc is not None and not from_run:
        return Plan("snapshot", tc, project)

    if from_run:
        prev = Node(store.for_run(store.path.parent, from_run))
        if not prev.store.exists_on_disk():
            raise InputsMissing(
                f"--from-run names no run: {prev.store.path} does not exist"
            )
        if not input_node(prev).exists():
            raise InputsMissing(
                f"run {from_run} has no input group to start from (a run from "
                f"before records carried their inputs); name a staged case "
                f"with --testcase instead"
            )
        if has_input and not overwrite:
            raise InputsMissing(
                f"run {run_id} already holds an input group; --from-run "
                f"starts a NEW run from {from_run}'s inputs — choose a new "
                f"--run-id, or pass --overwrite"
            )
        return Plan("copy", tc, project_of(run_id, None), from_run=from_run)
    if tc is not None and overwrite:
        return Plan("snapshot", tc, project)
    if has_input:
        return _plan_in_record(root, tc)
    if exists and (root / "run").exists() and tc is not None:
        return Plan("legacy", tc, project)
    if tc is not None:
        return Plan("snapshot", tc, project)
    raise InputsMissing(
        f"run {run_id} has no inputs to run on: neither --testcase nor an "
        f"`{INPUT_KEY}` group in {store.path}\n"
        f"  a run reads its inputs from its OWN record. Either name a staged "
        f"case with --testcase, start from a previous run's inputs with "
        f"--from-run <id>, or put an `{INPUT_KEY}/` group into the record\n"
        f"  holding description.md, intent.yaml, testcase.yaml and data/ "
        f"(supplied/ and blocklist.txt are optional)\n"
        f"  and run again with the same --run-id. Nothing was written and "
        f"nothing was spent."
    )


def _stored_source_dir(stored: dict | None) -> Path | None:
    """The source case `input_source` names, when it is still a folder on
    disk ("authored in place", a moved case: None)."""
    src = str((stored or {}).get("source") or "")
    if not src or src == "authored in place":
        return None
    path = Path(src)
    return path if path.is_dir() else None


def _plan_in_record(root: Node, tc: Path | None) -> Plan:
    """Plan step 3: the record already holds its `input` group.

    The project and the source case come from the stored `input_source`, so a
    `--run-id`-only resume keeps appending to the same tried-models archive
    and S0 still sees the source case (its `truth/`, its declarations). A
    `--testcase` given as well is compared file by file with the snapshot —
    the same manifest `run_guard` hashes — and a difference is refused.
    """
    from octomod.orchestration import run_guard  # run_guard imports this module

    run_id = root.store.run_id
    stored = read_source(root)
    if tc is not None:
        now = run_guard.manifest(tc)
        was = run_guard.manifest(root)
        if now != was:
            moved = run_guard.drifted(was, now)
            raise run_guard.RunIdRefused(
                f"run {run_id} already holds its inputs (the record's "
                f"`{INPUT_KEY}` group), and --testcase {tc} does not match "
                f"them:\n"
                + "".join(f"      - {m}\n" for m in moved[:12])
                + (f"      - … and {len(moved) - 12} more\n" if len(moved) > 12 else "")
                + f"  the run reads only its record's inputs, so these edits "
                f"would be ignored. Pass --overwrite to start it again from the "
                f"edited case, or start a new run from it with a new --run-id "
                f"(or --from-run {run_id} to reuse this run's inputs).\n"
                f"  Nothing was written and nothing was spent."
            )
    stored_project = str((stored or {}).get("project") or "")
    stored_dir = _stored_source_dir(stored)
    # authored in place (or a moved case): only a matching --testcase names one
    source = stored_dir if stored_dir is not None else tc
    project = stored_project or project_of(run_id, source)
    return Plan("in_record", source, project, matched=tc)


def materialise(p: Plan, root: Node, *, run_id: str) -> Inputs:
    """Carry out the plan: take the snapshot (or the copy) if there is one to
    take, settle `started_from` from the `input_source` the inputs arrived
    with, and extract the `input` group into the directory the engine reads.

    The record is created here when it does not exist yet."""
    if p.mode == "legacy":
        return Inputs(dir=p.source, source=p.source, project=p.project, mode=p.mode)

    if not root.store.exists_on_disk():
        root.store.create()
    copied: list[str] = []
    if p.mode == "snapshot":
        copied = snapshot(p.source, root)
        (root / SOURCE_KEY).delete()
        # a staged folder that carries a `source.json` (a copied run folder's
        # `input/`, staged as a follow-up) brings its provenance along, so
        # `started_from` is recorded as it was when the file was snapshotted
        carried = _source_file(p.source)
        if carried is not None:
            (root / SOURCE_KEY).put(carried)
    elif p.mode == "copy":
        prev = Node(root.store.for_run(root.store.path.parent, p.from_run))
        copied = copy_inputs(prev, root)

    previous = read_source(root)
    started_from = None
    if previous:
        was = str(previous.get("run_id") or "")
        if was and was != run_id:
            # these inputs were written for a different run and copied here
            started_from = was
        elif was == run_id:
            # a resume: keep what this run recorded the first time
            started_from = previous.get("started_from") or None
    if not previous or str(previous.get("run_id") or "") != run_id:
        write_source(
            root,
            run_id=run_id,
            project=p.project,
            source=p.source,
            started_from=started_from,
        )
    return Inputs(
        dir=materialise_dir(root),
        source=p.source,
        project=p.project,
        mode=p.mode,
        started_from=started_from,
        copied=copied,
        matched=p.matched,
    )
