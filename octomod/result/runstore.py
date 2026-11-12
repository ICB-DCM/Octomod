"""The run IS the file: `runs/<id>.h5`, written and read one group at a time.

There is no run directory: every module writes its record straight into the
HDF5 file, every reader takes it from there, and the file's group tree is the
`RunResult` tree (`model.py`) exactly — so
`mkstd.Hdf5Standard(RunResult).load_data` reads the whole run, and a partial
reader opens one group.

Every `put` opens the file, writes ONE group, and closes it. There is no long-lived
handle in the engine process, so between two writes the file is a complete
HDF5 file. A process dying inside a write damages at most that one group
write, and is covered by `checkpoint()`, which verifies the file and copies
it to `<id>.h5.bak` at every marker, decision, pause and at run end; a
damaged file is replaced by that copy.

Space. HDF5 does not reuse the space of a deleted object once the file is
closed — unless the file tracks its free space persistently. Every record is
created that way (`fs_persist`), so replacing a group reuses what the old one
held, and the ledger is an appendable byte stream (one JSON row per line), so
a row costs its own bytes, not a rewrite of every row before it. `compact()`
reclaims what is left at run end.

Keys are record paths, `rounds/round_0/candidates/base/estimation`; each
segment is escaped the way mkstd escapes dict keys, so an id containing `/`
is one group, not two.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml
from mkstd.standards.hdfdict import hdfdict
from pydantic import BaseModel

from octomod.result.model import RunResult

SUFFIX = ".h5"
BACKUP_SUFFIX = ".h5.bak"
REPORTS_SUFFIX = "_reports"
LEDGER_KEY = "ledger"
LEDGER_FORMAT = "jsonl-bytes"  # the ledger dataset's `format` attribute
BLOB_FORMAT = "bytes"  # an opaque value's (`put_bytes`) `format` attribute

# A group is written under this sibling name and moved over the old one at
# the end (`_write`). `%t` cannot occur in an escaped key (`%` is followed by
# `25`, `2F`, `2E` or is the whole key `%00`), so it never names real data.
_TMP_SUFFIX = "%tmp"

# Every file the store creates tracks its free space persistently, so the
# space of a replaced group is reused after the file was closed and reopened
# (measured: 300 rewrites of a 40 KB group, 647 KB → 47 KB). HDF5 ≥ 1.10.
_CREATE = {"fs_strategy": "fsm", "fs_persist": True, "libver": ("v110", "latest")}

# Groups iterate in INSERTION order, not name order: a dict written into the
# record must read back with its keys where the writer put them. h5py takes
# that from a process-wide setting when a group is created (hdfdict creates
# the nested ones), so it is switched on for the length of OUR writes only —
# never at import, where it would change every other HDF5 file the process
# writes (pyPESTO's, AMICI's) behind their backs.


@contextlib.contextmanager
def _ordered() -> Iterator[None]:
    cfg = h5py.get_config()
    was = cfg.track_order
    cfg.track_order = True
    try:
        yield
    finally:
        cfg.track_order = was


# Another process may hold the file for the length of one group write (the
# front end's `pending`, a test polling a paused run); HDF5's file lock makes
# that an OSError for the short overlap. Retry it away rather than fail — and
# NEVER read it as damage.
_OPEN_TRIES = 40
_OPEN_WAIT_S = 0.05


def key(*segments: Any) -> str:
    """A record key from segments; each segment escaped as a dict key is."""
    return "/".join(hdfdict.escape_key(str(s)) for s in segments if s is not None)


def unescape(segment: str) -> str:
    return hdfdict.unescape_key(segment)


def round_key(round_idx: int) -> str:
    return key("rounds", f"round_{round_idx}")


def candidate_key(round_idx: int, candidate: str | None) -> str:
    """The workdir of a candidate, or of the single model (`_single`)."""
    return key("rounds", f"round_{round_idx}", "candidates", candidate or "_single")


class RecordDamaged(OSError):
    """The record file does not read back."""


class RunStore:
    """One run's HDF5 record, addressed by record keys."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.recovered = False  # set when a damaged file was replaced by .bak
        self.dropped: list[str] = []  # what the last `load` had to leave out
        self._reader: h5py.File | None = None  # an open `reading()` session
        self._depth = 0

    # ------------------------------------------------------------ paths
    @classmethod
    def for_run(cls, runs_dir: Path, run_id: str) -> RunStore:
        return cls(Path(runs_dir) / f"{run_id}{SUFFIX}")

    @property
    def run_id(self) -> str:
        name = self.path.name
        return name[: -len(SUFFIX)] if name.endswith(SUFFIX) else name

    @property
    def backup_path(self) -> Path:
        return self.path.with_name(self.run_id + BACKUP_SUFFIX)

    @property
    def reports_dir(self) -> Path:
        """Rendered documents (HTML) live beside the file, not in it."""
        return self.path.with_name(self.run_id + REPORTS_SUFFIX)

    @property
    def _damaged_path(self) -> Path:
        """Where a restore keeps the damaged file."""
        return self.path.with_name(self.path.name + ".damaged")

    @property
    def _tmp_path(self) -> Path:
        """The checkpoint's and the restore's intermediate copy."""
        return self.path.with_name(self.path.name + ".tmp")

    @property
    def _compact_tmp_path(self) -> Path:
        return self.path.with_suffix(".compact.tmp")

    def _transient_paths(self) -> list[Path]:
        """What an interrupted checkpoint, restore, compaction or whole-file
        write (`write_all`'s `<id>.h5.<random>.tmp`) can leave beside the
        record."""
        return [
            self._damaged_path,
            self._tmp_path,
            self._compact_tmp_path,
            *sorted(self.path.parent.glob(self.path.name + ".*.tmp")),
        ]

    @property
    def _wid(self) -> Path:
        return self.path.resolve()

    def exists_on_disk(self) -> bool:
        return self.path.exists()

    def mtime_ns(self) -> int | None:
        try:
            return self.path.stat().st_mtime_ns
        except OSError:
            return None

    def stamp(self) -> tuple | None:
        """What a cache of this file's content is keyed on: the file's mtime,
        size and inode, and this process's count of its own writes — so two
        writes within one tick of a coarse clock still change the stamp."""
        try:
            st = self.path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size, st.st_ino, _GENERATION.get(self._wid, 0))

    def create(self) -> None:
        """A new, empty record file (refuses to clobber an existing one), and
        its first checkpoint: a record has a checkpoint beside it from the
        moment it exists, so a process killed inside a write BEFORE the first
        marker (the first seconds of a run) leaves something to restore from
        rather than a file no mode can open and no `--overwrite` was asked
        for."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            raise FileExistsError(self.path)
        with _ordered(), h5py.File(self.path, "w", **_CREATE):
            pass
        shutil.copyfile(self.path, self._tmp_path)
        os.replace(self._tmp_path, self.backup_path)
        _WRITERS.add(self._wid)  # a new file needs no verification
        _bump(self._wid)

    # ------------------------------------------------------- open / close
    def _open(self, mode: str) -> h5py.File:
        if mode != "r":
            self._close_reader()
            if not self.path.exists():
                self._create_or_restore()
            self._verify_once_for_writing()
        try:
            return _open_retrying(self.path, mode)
        except FileNotFoundError:
            raise
        except OSError as e:
            if not (_is_damage(e) and self.backup_path.exists()):
                raise
            if mode == "r" and self._wid not in _WROTE:
                # a reader gets the last consistent state rather than nothing
                return h5py.File(self.backup_path, "r")
            self._recover(e)
            return _open_retrying(self.path, mode)

    @contextlib.contextmanager
    def _file(self, mode: str) -> Iterator[h5py.File]:
        """The file for one operation: the open `reading()` handle when there
        is one and this is a read, else a fresh open that is closed after."""
        if mode == "r" and self._reader is not None:
            yield self._reader
            return
        f = self._open(mode)
        try:
            if mode == "r":
                yield f
            else:
                with _ordered():
                    yield f
        finally:
            f.close()
            if mode != "r":
                _WROTE.add(self._wid)
                _bump(self._wid)

    @contextlib.contextmanager
    def reading(self) -> Iterator[RunStore]:
        """Hold ONE read handle for a block of reads (a renderer, the slot
        state): every `get`/`exists`/`keys` inside uses it. A write inside the
        block closes it first (HDF5 will not open a file for writing that the
        same process holds for reading); the next read reopens it."""
        self._depth += 1
        try:
            yield self
        finally:
            self._depth -= 1
            if self._depth == 0:
                self._close_reader()

    def _read(self, fn):
        """Run `fn(file)` for a read. A file that OPENS but whose groups do
        not read (a process killed inside a group write) is detected
        here: a reader is given the checkpoint instead; the run's writer
        restores it and stops (`_recover`)."""
        if self._depth and self._reader is None and self.path.exists():
            self._reader = self._open("r")
        try:
            with self._file("r") as f:
                return fn(f)
        except (OSError, RuntimeError, KeyError, ValueError) as e:
            if isinstance(e, FileNotFoundError) or not self._damaged():
                raise
            self._close_reader()
            if not self.backup_path.exists():
                raise RecordDamaged(
                    f"{self.path} is damaged ({_first_line(e)}) and has no "
                    f"checkpoint to restore from"
                ) from e
            if self._wid in _WROTE:
                self._recover(e)  # raises: the run must not go on silently
            print(
                f"  ⚑ {self.path.name} is damaged ({_first_line(e)}); reading "
                f"its checkpoint {self.backup_path.name}",
                file=sys.stderr,
            )
            with h5py.File(self.backup_path, "r") as f:
                return fn(f)

    def _close_reader(self) -> None:
        if self._reader is not None:
            try:
                self._reader.close()
            finally:
                self._reader = None

    # ------------------------------------------------------------ damage
    def verify(self, path: Path | None = None) -> str | None:
        """None when every group, dataset and attribute of the file reads;
        else what failed. Datasets are read in full: headers alone miss a
        fifth of the damage a full read finds (measured on 300 random
        corruptions of a run record: 105 of 134), and the full read costs
        only ~20% more than walking the headers (~0.2 s for a toy run's
        record). Bytes that decode to wrong VALUES are not detectable here.

        A file another process holds (HDF5's lock) is NOT damage: the open is
        retried like any other, and an open that still fails for a reason
        other than damage raises instead of returning a verdict."""
        target = Path(path or self.path)

        def visit(_name, obj):
            dict(obj.attrs)
            if isinstance(obj, h5py.Dataset):
                obj[()]

        try:
            f = _open_retrying(target, "r")
        except FileNotFoundError:
            raise
        except OSError as e:
            if _is_damage(e):
                return _first_line(e)
            raise
        try:
            f.visititems(visit)
        except (OSError, RuntimeError, KeyError, ValueError) as e:
            return _first_line(e)
        finally:
            f.close()
        return None

    def _damaged(self) -> bool:
        try:
            return self.path.exists() and self.verify() is not None
        except OSError:
            return False  # held by another process, or gone: not damage

    def _verify_once_for_writing(self) -> None:
        """The first write of a process (a resume) checks the whole file: a
        run killed inside a group write can leave a file that opens, and
        writing on into it would bury the damage under the next checkpoint.
        Restoring HERE is the resume contract: nothing of this process's own
        is lost, it has not written yet."""
        if self._wid in _WRITERS:
            return
        if not self.path.exists():
            _WRITERS.add(self._wid)
            return
        try:
            problem = self.verify()
        except OSError:
            return  # held by another process: verify on the next write
        _WRITERS.add(self._wid)
        if problem is None:
            return
        if not self.backup_path.exists():
            raise RecordDamaged(
                f"{self.path} is damaged ({problem}) and has no checkpoint to "
                f"restore from"
            )
        # through `_recover`: a process whose first verify was skipped (the
        # file was held) may have written since, and then must not go on
        self._recover(RecordDamaged(problem))

    def _create_or_restore(self) -> None:
        """A write to a path with no file. A checkpoint beside it means a
        restore was interrupted between its two renames (or the main file
        went missing): it is restored, and a process that has written since
        stops (`_recover`). Otherwise the file is created with the record's
        own settings (`_CREATE`), which a bare `h5py.File(path, "a")` would
        not give it."""
        if self.backup_path.exists():
            self._recover(RecordDamaged(f"{self.path.name} is missing"))
        else:
            self.create()

    def _recover(self, error: Exception) -> None:
        """Damage met by a process that has ALREADY written: restore the
        checkpoint, then stop — everything this process wrote since the last
        checkpoint is gone, and carrying on would leave it believing it is
        recorded. A process that has not written yet (a resume) restores and
        carries on."""
        self._restore_from_checkpoint(error)
        if self._wid in _WROTE:
            raise RecordDamaged(
                f"{self.path.name} was damaged ({_first_line(error)[:120]}); "
                f"restored from {self.backup_path.name} — resume the run to "
                f"continue from its last marker"
            )

    def _restore_from_checkpoint(self, error: Exception) -> None:
        self._close_reader()
        damaged = self._damaged_path
        gone = not self.path.exists()
        # the copy first, then two renames: at no moment is there no `<id>.h5`
        # (a kill between them leaves the copy, which the next write finishes)
        shutil.copyfile(self.backup_path, self._tmp_path)
        if not gone:
            os.replace(self.path, damaged)
        os.replace(self._tmp_path, self.path)
        self.recovered = True
        _WRITERS.add(self._wid)
        _bump(self._wid)
        why = "is missing" if gone else f"is damaged ({_first_line(error)[:80]})"
        kept = "" if gone else f" — the damaged file is kept as {damaged.name}"
        print(
            f"  ⚑ {self.path.name} {why}; restored from {self.backup_path.name}"
            f"{kept}",
            file=sys.stderr,
        )
        was = "missing" if gone else f"damaged ({_first_line(error)[:160]})"
        row = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "round": 0,
            "module": "record",
            "event": "note",
            "note": (
                f"record restored from checkpoint {self.backup_path.name}: the "
                f"main file was {was}"
            ),
            "recovered": True,
        }
        with _ordered(), _open_retrying(self.path, "a") as f:
            _ledger_append(f, [row])

    # ----------------------------------------------------------- writing
    def put(self, k: str, value: BaseModel | dict | list | Any) -> Any:
        """Replace the group (or dataset) at `k` with `value`. Returns the
        value as it reads back — what HDF5 made of it (a mixed list
        `[0, 10.0]` is `[0.0, 10.0]`), so a writer's sha is the reader's."""
        with self._file("a") as f:
            _write(f, k, value)
            return _value(f[k])

    def put_bytes(self, k: str, data: bytes) -> None:
        """Opaque bytes at `k`, as ONE opaque HDF5 value (a cached paper, a
        PDF): written directly, never element by element."""
        with self._file("a") as f:
            _write(f, k, bytes(data))

    def put_many(self, items: dict[str, Any]) -> None:
        """Several keys in one open/close."""
        with self._file("a") as f:
            for k, value in items.items():
                _write(f, k, value)

    def delete(self, k: str) -> bool:
        with self._file("a") as f:
            if k in f:
                del f[k]
                return True
        return False

    def copy(self, k: str, dst: RunStore, dst_key: str) -> None:
        """Copy the object at `k` to `dst_key` in `dst` (the same store or
        another), replacing what is there. HDF5 copies it natively."""
        if dst.path == self.path:
            with self._file("a") as f:
                if dst_key in f:
                    del f[dst_key]
                parent = dst_key.rpartition("/")[0]
                if parent:
                    f.require_group(parent)
                f.copy(f[k], dst_key)
            return
        with self._file("r") as src:
            with dst._file("a") as f:
                if dst_key in f:
                    del f[dst_key]
                parent = dst_key.rpartition("/")[0]
                if parent:
                    f.require_group(parent)
                src.copy(src[k], f, name=dst_key)

    # ----------------------------------------------------------- reading
    def exists(self, k: str) -> bool:
        if not self.path.exists():
            return False
        return self._read(lambda f: k in f)

    def get(
        self,
        k: str,
        cls: type[BaseModel] | None = None,
        default: Any = None,
        raw: bool = False,
    ) -> Any:
        """The group at `k` as a dict (or validated as `cls`), a dataset as its
        value, `default` when absent. `raw` returns a dataset's stored value
        without turning arrays into lists (opaque bytes)."""
        if not self.path.exists():
            return default

        def read(f):
            if k not in f:
                return _ABSENT
            obj = f[k]
            if raw and not isinstance(obj, h5py.Group):
                return obj[()]
            return _value(obj)

        data = self._read(read)
        if data is _ABSENT:
            return default
        if cls is not None:
            return cls.model_validate(data)
        return data

    def keys(self, k: str = "") -> list[str]:
        """Child names under `k` (unescaped), sorted."""
        if not self.path.exists():
            return []

        def read(f):
            if k and k not in f:
                return []
            grp = f[k] if k else f
            if not isinstance(grp, h5py.Group):
                return []
            return sorted(unescape(n) for n in grp.keys() if not _is_tmp(n))

        return self._read(read)

    def walk(self, k: str = "") -> Iterable[tuple[str, str]]:
        """(key, 'group'|'dataset') for everything under `k`, depth first."""
        if not self.path.exists():
            return

        def read(f):
            out: list[tuple[str, str]] = []
            root = f[k] if k else f

            def rec(g, prefix):
                for raw, obj in g.items():
                    if _is_tmp(raw):
                        continue
                    name = unescape(raw)
                    kk = f"{prefix}/{name}" if prefix else name
                    if isinstance(obj, h5py.Group):
                        out.append((kk, "group"))
                        rec(obj, kk)
                    else:
                        out.append((kk, "dataset"))

            if isinstance(root, h5py.Group):
                rec(root, k)
            return out

        yield from self._read(read)

    # ------------------------------------------------------------ ledger
    def append_ledger(self, row: dict) -> None:
        """Append one row: its JSON line is added to the ledger's byte stream,
        nothing before it is rewritten."""
        with self._file("a") as f:
            _ledger_append(f, [row])

    def ledger_text(self) -> str:
        """The rows as JSON lines (what `ledger.jsonl` held)."""
        if not self.path.exists():
            return ""
        return "".join(
            json.dumps(r, ensure_ascii=True) + "\n" for r in self.ledger_rows()
        )

    def ledger_rows(self) -> list[dict]:
        """Every row, parsed as the JSON it is."""
        if not self.path.exists():
            return []
        return self._read(_ledger_rows)

    def replace_ledger(self, rows: list[dict]) -> None:
        """The whole ledger at once (fixtures, the legacy importer)."""
        with self._file("a") as f:
            if LEDGER_KEY in f:
                del f[LEDGER_KEY]
            _ledger_append(f, rows)

    # ------------------------------------------------- whole-record forms
    def load(self) -> RunResult:
        """The whole run, validated.

        A malformed entry in one optional part (a parameter row that is not a
        mapping, an axis without an id, a gate file without a `gate_id`) is
        LEFT OUT, named in `self.dropped` and on stderr — not allowed to make
        every reader of the run fail. The record is what the engine wrote;
        one bad entry in it is a finding about that entry, not about the run.
        The readings no module writes (a call's ledger rows, a slot's producer,
        a dropped candidate…) are filled in by `derive.derive`.
        """

        def read(f):
            # the ledger is parsed as the byte stream it is, not turned into
            # a list of a million ints first
            data = {
                unescape(raw): _value(obj)
                for raw, obj in f.items()
                if unescape(raw) != LEDGER_KEY and not _is_tmp(raw)
            }
            if LEDGER_KEY in f:
                data[LEDGER_KEY] = _ledger_rows(f)
            return data

        rr, self.dropped = validate_lenient(self._read(read))
        from octomod.result.derive import derive

        derive(rr)
        if self.dropped:
            print(
                f"  ⚑ {self.path.name}: left out {len(self.dropped)} malformed "
                f"entr{'y' if len(self.dropped) == 1 else 'ies'} on load: "
                + "; ".join(self.dropped[:5]),
                file=sys.stderr,
            )
        return rr

    def write_all(self, record: RunResult) -> Path:
        """Replace the whole file with `record`, atomically (export copies,
        the legacy import). The ledger is written as the engine writes it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent
        )
        os.close(fd)
        try:
            data = record.model_dump()
            rows = data.pop("ledger", None) or []
            with _ordered(), h5py.File(tmp, "w", **_CREATE) as f:
                hdfdict.dump(data, f, packer=_pack, escape_keys=True)
                if rows:
                    _ledger_append(f, rows)
            with open(tmp, "rb") as fh:
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
            _bump(self._wid)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return self.path

    # --------------------------------------------------- safety, hygiene
    def checkpoint(self) -> Path | None:
        """A consistent copy beside the file. Called at every marker,
        decision, pause and at run end; reads fall back to it.

        The file is VERIFIED first: copying a damaged file over the last good
        checkpoint would leave nothing to recover. A damaged file is replaced
        by the checkpoint instead and `RecordDamaged` raised, so the run stops
        here and its resume starts from the last good marker. A file another
        process holds is not damage; the checkpoint waits for it like any
        open does, and raises `OSError` if it never frees."""
        if not self.path.exists():
            return None
        self._close_reader()
        self._verify_for_copy()
        shutil.copyfile(self.path, self._tmp_path)
        os.replace(self._tmp_path, self.backup_path)
        return self.backup_path

    def _verify_for_copy(self) -> None:
        """Before the whole file is copied (a checkpoint, a compaction): a
        damaged file is replaced by the checkpoint and `RecordDamaged` raised,
        so the run stops here rather than copying the damage on."""
        problem = self.verify()
        if problem is None:
            return
        if self.backup_path.exists():
            self._restore_from_checkpoint(RecordDamaged(problem))
            raise RecordDamaged(
                f"{self.path.name} was damaged ({problem}); restored from "
                f"{self.backup_path.name} — resume the run to continue "
                f"from its last marker"
            )
        raise RecordDamaged(f"{self.path.name} is damaged ({problem})")

    def compact(self) -> None:
        """Rewrite the file so the space deleted groups left behind is
        reclaimed. Atomic replace. Verified first, as a checkpoint is: a
        damaged file would fail half-way through the copy, and the failure
        must be the restore, not a stray `.compact.tmp`."""
        if not self.path.exists():
            return
        self._close_reader()
        self._verify_for_copy()
        tmp = self._compact_tmp_path
        try:
            with (
                _ordered(),
                _open_retrying(self.path, "r") as src,
                h5py.File(tmp, "w", **_CREATE) as dst,
            ):
                for name in src:
                    src.copy(name, dst, name=name)
                for k, v in src.attrs.items():
                    dst.attrs[k] = v
            os.replace(tmp, self.path)
        finally:
            if tmp.exists():  # only when the replace did not happen
                tmp.unlink()
        _bump(self._wid)

    def remove(self) -> list[str]:
        """Delete the record, its checkpoint, what an interrupted restore or
        copy left beside them, and its rendered documents. Returns what was
        removed, for the `--overwrite` message."""
        self._close_reader()
        removed = []
        for p in (self.path, self.backup_path, *self._transient_paths()):
            if p.exists():
                p.unlink()
                removed.append(p.name)
        if self.reports_dir.exists():
            n = sum(1 for q in self.reports_dir.rglob("*") if q.is_file())
            shutil.rmtree(self.reports_dir)
            removed.append(f"{self.reports_dir.name}/ ({n} file(s))")
        _WRITERS.discard(self._wid)
        _WROTE.discard(self._wid)
        _bump(self._wid)
        return removed

    @classmethod
    def all_in(cls, runs_dir: Path) -> list[RunStore]:
        """Every run record under `runs_dir`, oldest first."""
        base = Path(runs_dir)
        if not base.exists():
            return []
        stores = [cls(p) for p in base.glob(f"*{SUFFIX}")]
        return sorted(stores, key=lambda s: s.mtime_ns() or 0)


# What HDF5 says of a file it cannot open because its bytes are wrong — and of
# one whose writer DIED while it was open: the record's superblock (v3, from
# `libver` in `_CREATE`) carries a "open for write" consistency flag that only
# a clean close clears, and a file left with it set opens in NO mode
# ("file is already open for write (may use <h5clear file> to clear file
# consistency flags)"). That is a process killed inside a write, and its
# answer is the checkpoint: the flag says the metadata cache was never flushed,
# so the bytes behind it are not to be trusted either.
_DAMAGE = (
    "truncated file",
    "bad byte number",
    "file signature",
    "superblock",
    "file consistency flags",
)

# Paths this process has VERIFIED for writing (its first write checks the whole
# file), paths it has actually WRITTEN, and a per-path count of its writes.
_WRITERS: set[Path] = set()
_WROTE: set[Path] = set()
_GENERATION: dict[Path, int] = {}

_ABSENT = object()


def _bump(wid: Path) -> None:
    _GENERATION[wid] = _GENERATION.get(wid, 0) + 1


def _open_retrying(path: Path, mode: str) -> h5py.File:
    """`h5py.File`, retried through another process's lock; damage and a
    missing file are raised at once."""
    last: OSError | None = None
    for _ in range(_OPEN_TRIES):
        try:
            return h5py.File(path, mode)
        except FileNotFoundError:
            raise
        except OSError as e:
            last = e
            if mode == "r" and not Path(path).exists():
                raise FileNotFoundError(str(path)) from e
            if _is_damage(e):
                raise
            time.sleep(_OPEN_WAIT_S)
    raise last if last else OSError(f"cannot open {path} ({mode})")


def _first_line(e: BaseException) -> str:
    text = str(e) or type(e).__name__
    return text.splitlines()[0]


def validate_lenient(data: dict) -> tuple[RunResult, list[str]]:
    """`RunResult.model_validate(data)`, leaving out what does not validate.

    Each validation error names a location; the deepest part of it that
    exists in `data` is removed (the bad value, or — when a required key is
    missing — the entry that lacks it) and validation is repeated. Returns
    the record and the locations removed."""
    from pydantic import ValidationError

    dropped: list[str] = []
    for _ in range(500):
        try:
            return RunResult.model_validate(data), dropped
        except ValidationError as e:
            progressed = False
            for err in e.errors():
                where = _drop_at(data, list(err["loc"]))
                if where is not None:
                    dropped.append(f"{where} ({err['msg']})")
                    progressed = True
                    break  # locations shift once a list entry goes; revalidate
            if not progressed:
                raise
    raise RuntimeError("record validation did not settle")


def _drop_at(data: Any, loc: list) -> str | None:
    """Remove the deepest existing element along `loc`; its path, or None."""
    trail: list[tuple[Any, Any]] = []
    obj = data
    for part in loc:
        if isinstance(obj, dict) and part in obj:
            trail.append((obj, part))
            obj = obj[part]
        elif isinstance(obj, list) and isinstance(part, int) and 0 <= part < len(obj):
            trail.append((obj, part))
            obj = obj[part]
        else:
            break
    if not trail:
        return None
    # the full location is the bad value itself; a shorter one is the entry
    # that lacks a required key (a list entry, a dict-of-records value)
    container, part = trail[-1]
    del container[part]
    return "/".join(str(t[1]) for t in trail)


def _is_damage(e: OSError) -> bool:
    """A file HDF5 cannot open because its bytes are wrong, or because the
    process writing it died with it open (`_DAMAGE`), as opposed to one
    another process holds — that is a lock error, and is retried."""
    text = str(e).lower()
    return any(w in text for w in _DAMAGE)


# ----------------------------------------------------------------- ledger
# The ledger is a 1-D, chunked, resizable uint8 dataset holding JSON lines
# (`format` = LEDGER_FORMAT). Rows are serialised with `ensure_ascii`, so a row
# is exactly one line whatever it quotes (an unescaped U+2028 in an agent's
# note would split a row in two and drop both halves); readers split on "\n"
# only.
# `RunResult.ledger` accepts the bytes as they are, so mkstd's whole-record
# load reads it too. A legacy record (a YAML string of `- {json}` lines) is
# read too, and converted on its first append.


def _row_line(row: dict) -> str:
    return json.dumps(row, default=str, ensure_ascii=True) + "\n"


def _ledger_append(f: h5py.File, rows: list[dict]) -> None:
    if not rows:
        if LEDGER_KEY not in f:
            _new_ledger(f, b"")
        return
    data = np.frombuffer("".join(_row_line(r) for r in rows).encode("ascii"), "u1")
    if LEDGER_KEY in f and _is_stream(f[LEDGER_KEY]):
        ds = f[LEDGER_KEY]
        n = ds.shape[0]
        ds.resize((n + data.shape[0],))
        ds[n:] = data
        return
    old = _legacy_rows(f) if LEDGER_KEY in f else []
    if old is None:  # a ledger that does not parse is never replaced
        raise RecordDamaged(f"the ledger of {f.filename} does not parse as rows")
    if LEDGER_KEY in f:
        del f[LEDGER_KEY]
    prefix = "".join(_row_line(r) for r in old).encode("ascii")
    _new_ledger(f, prefix + data.tobytes())


def _new_ledger(f: h5py.File, payload: bytes) -> None:
    ds = f.create_dataset(
        LEDGER_KEY,
        data=np.frombuffer(payload, "u1"),
        maxshape=(None,),
        chunks=(16384,),
        dtype="u1",
    )
    ds.attrs["format"] = LEDGER_FORMAT


def _is_stream(ds) -> bool:
    return (
        isinstance(ds, h5py.Dataset)
        and ds.ndim == 1
        and ds.dtype == np.uint8
        and ds.attrs.get("format", b"") in (LEDGER_FORMAT, LEDGER_FORMAT.encode())
    )


def _ledger_rows(f: h5py.File) -> list[dict]:
    if LEDGER_KEY not in f:
        return []
    ds = f[LEDGER_KEY]
    if _is_stream(ds):
        return parse_jsonl(ds[()].tobytes().decode("utf-8", "replace"))
    return _legacy_rows(f) or []


def _legacy_rows(f: h5py.File) -> list[dict] | None:
    """The rows of a legacy ledger, one not stored as the byte stream: a text
    of `- {json}` lines, or — hdfdict's own form of a list of dicts, as a
    legacy `write_all` wrote it — block YAML, marked `yaml`. None when the
    text is not empty and no row came out of it."""
    ds = f[LEDGER_KEY]
    raw = ds[()]
    text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    if not text.strip():
        return []
    if ds.attrs.get(hdfdict.TYPE, b"") in ("yaml", b"yaml"):
        try:
            rows = yaml.safe_load(text)
        except yaml.YAMLError:
            return None
    else:
        lines = [line[2:] for line in text.split("\n") if line.startswith("- ")]
        rows = parse_jsonl("\n".join(lines)) or None
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        return None
    return rows


def parse_jsonl(text: str) -> list[dict]:
    """JSON rows, one per "\\n"-separated line (never `splitlines`, which also
    splits on the line separators JSON allows inside a string)."""
    out = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _write(f: h5py.File, k: str, value: Any) -> None:
    """Replace what is at `k` with `value` inside an open file. The new
    content is written under a temporary sibling name and moved over the old
    one at the very end, so a write that fails half-way (a value neither
    h5py nor yaml can store) leaves the old content as it was."""
    payload = value.model_dump() if isinstance(value, BaseModel) else value
    parent, _, name = k.rpartition("/")
    grp = f.require_group(parent) if parent else f
    tmp = name + _TMP_SUFFIX
    if tmp in grp:  # a write killed before its move
        del grp[tmp]
    try:
        if isinstance(payload, dict):
            hdfdict.dump(
                payload, grp.require_group(tmp), packer=_pack, escape_keys=True
            )
        else:
            _pack(grp, tmp, payload)
    except BaseException:
        if tmp in grp:
            del grp[tmp]
        raise
    if name in grp:
        del grp[name]
    grp.move(tmp, name)


def _pack(grp: h5py.Group, name: str, value: Any) -> None:
    """hdfdict's packer, with bytes stored as ONE opaque value — hdfdict
    would hand them to h5py as a string, which cannot hold a NUL."""
    if isinstance(value, (bytes, bytearray)):
        data = bytes(value)
        # np.void refuses a zero size: the empty blob is a zero-length array
        ds = grp.create_dataset(name, data=np.void(data) if data else np.zeros(0, "u1"))
        ds.attrs["format"] = BLOB_FORMAT
        return
    hdfdict.pack_dataset(grp, name, value)


def _is_blob(ds: h5py.Dataset) -> bool:
    return ds.attrs.get("format", b"") in (BLOB_FORMAT, BLOB_FORMAT.encode())


def _unpack(ds: h5py.Dataset) -> Any:
    """hdfdict's unpacker, with an opaque value (`_pack`) read as bytes: the
    empty blob would otherwise read as `[]`, and an opaque dataset written
    before the `format` attribute (`np.void`, no compound fields) as bytes
    already — kept so."""
    if _is_blob(ds) or (ds.dtype.kind == "V" and ds.dtype.names is None):
        return ds[()].tobytes()
    return hdfdict.unpack_dataset(ds)


def _value(obj: h5py.Group | h5py.Dataset) -> Any:
    """A group as a plain dict, a dataset as its value. A `%tmp` sibling a
    killed write left behind (`_write`) is not part of the record and is
    skipped here as in `keys` and `walk`; the next write of its key removes
    it."""
    if isinstance(obj, h5py.Group):
        return {
            unescape(raw): _value(child)
            for raw, child in obj.items()
            if not _is_tmp(raw)
        }
    return _plain(_unpack(obj))


def _is_tmp(raw: str) -> bool:
    """A raw (escaped) child name `_write` uses for its half-written group.
    Exact at this level: an escaped real name spells `%` as `%25`."""
    return raw.endswith(_TMP_SUFFIX)


def _plain(obj: Any) -> Any:
    """hdfdict's mappings → plain dicts; numpy scalars and arrays → Python
    values, so what comes out of the record is what JSON put in. An opaque
    value (`put_bytes`) comes out as bytes — never decoded: text datasets
    arrive as `str` already, so bytes here ARE opaque."""
    if isinstance(obj, np.void):
        return obj.tobytes()
    if isinstance(obj, np.ndarray):
        return _plain(obj.tolist())
    if isinstance(obj, np.generic):
        return obj.item()
    if (
        hasattr(obj, "keys")
        and hasattr(obj, "__getitem__")
        and not isinstance(obj, (str, dict))
    ):
        return {k: _plain(obj[k]) for k in obj.keys()}
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return obj
