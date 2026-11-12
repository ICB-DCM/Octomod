"""A location in the run record, addressed by its record key.

The run is one HDF5 file and its
group tree IS the `RunResult` tree (model.py): `rounds/round_0/candidates/
base/estimation` is where candidate `base`'s fit summary lives, and nowhere
else. A `Node` is one such key on one `RunStore`. Modules write and read
through nodes, so what a module names is the record's own vocabulary — there
is no second, file-shaped name for anything (the file names of a legacy run
directory appear only in the legacy importer, `importer.py`).

The rule that keeps the tree sound: every group is EITHER written whole by
one writer (`put` replaces it) OR is a pure container whose children are
written independently (`model/`, `petab/`, `gates/`, `agent_calls/<role>/`).
Nothing a writer owns is nested inside a group another writer replaces, so a
write never has to "keep" children it does not own, and a reader never sees
a record appear because only a neighbour was written.

What a node holds is plain record data — a dict (a group), a list, a string,
a number — or one of three typed forms with their own accessors: a `Table`
(`table`/`put_table`, a DataFrame in and out), text (`text`/`put_text`), and
opaque bytes (`blob`/`put_blob`). Libraries never see a node: they get the
DataFrame, the string, the `petab.Problem` built from them (`petab_io.py`).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel

from octomod.orchestration.artifacts import ArtifactError
from octomod.result.runstore import RunStore, key, unescape

_RAISE = object()
_ABSENT = object()


class RecordMissing(ArtifactError, KeyError):
    """A node read that has no data — an `ArtifactError` (a module's missing
    input), and a `KeyError` (a missing key)."""

    def __str__(self) -> str:  # KeyError quotes its argument; this is prose
        return str(self.args[0]) if self.args else "missing record data"


class Node:
    __slots__ = ("store", "key")

    def __init__(self, store: RunStore, key_: str = ""):
        self.store = store
        self.key = key_.strip("/")

    # ------------------------------------------------------------ address
    def __truediv__(self, segments: str) -> Node:
        """`node / "model/parameters"`: one or more `/`-separated segments.
        An id that may itself contain `/` goes through `child`."""
        parts = [s for s in str(segments).split("/") if s]
        return self._join(key(*parts))

    def child(self, name: str) -> Node:
        """One segment, escaped whole (a candidate id, a gate id)."""
        return self._join(key(name))

    def _join(self, tail: str) -> Node:
        return Node(self.store, f"{self.key}/{tail}" if self.key else tail)

    @property
    def name(self) -> str:
        return unescape(self.key.rsplit("/", 1)[-1]) if self.key else ""

    @property
    def parent(self) -> Node:
        return Node(self.store, self.key.rpartition("/")[0])

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, Node)
            and other.store.path == self.store.path
            and other.key == self.key
        )

    def __hash__(self) -> int:
        return hash((str(self.store.path), self.key))

    def __repr__(self) -> str:
        return f"Node({self.store.path.name}, {self.key!r})"

    def __str__(self) -> str:
        """For messages: `runs/x.h5::rounds/round_0/data/report`."""
        return f"{self.store.path}::{self.key}" if self.key else str(self.store.path)

    # ---------------------------------------------------------- existence
    def exists(self) -> bool:
        if not self.key:
            return self.store.exists_on_disk()
        return self.store.exists(self.key)

    def children(self) -> list[str]:
        """Child names (unescaped), sorted — ONE read of the file."""
        return self.store.keys(self.key)

    def child_nodes(self) -> list[Node]:
        return [self.child(n) for n in self.children()]

    # ------------------------------------------------------------ reading
    def get(self, default: Any = _RAISE) -> Any:
        """The data at this key; `RecordMissing` (or `default`) when absent."""
        data = self.store.get(self.key, default=_RAISE)
        if data is _RAISE:
            if default is _RAISE:
                raise RecordMissing(f"nothing in the record at {self}")
            return default
        return data

    def _data(self, default: Any) -> Any:
        """`get`, with `_ABSENT` for "absent and a default was given"."""
        return self.get(default=_RAISE if default is _RAISE else _ABSENT)

    def text(self, default: Any = _RAISE) -> str:
        data = self._data(default)
        if data is _ABSENT:
            return default
        if isinstance(data, bytes):
            return data.decode("utf-8", "replace")
        return data if isinstance(data, str) else str(data)

    def table(self, default: Any = _RAISE):
        """A stored `Table` as a DataFrame."""
        from octomod.result.records import Table

        data = self._data(default)
        if data is _ABSENT:
            return default
        return Table.model_validate(data).to_dataframe()

    def blob(self, default: Any = _RAISE) -> bytes:
        import numpy as np

        data = self.store.get(self.key, default=_RAISE, raw=True)
        if data is _RAISE:
            if default is _RAISE:
                raise RecordMissing(f"nothing in the record at {self}")
            return default
        if isinstance(data, np.void):
            return data.tobytes()
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            return data.encode("utf-8")
        return np.asarray(data, dtype=np.uint8).tobytes()

    def sha(self) -> str:
        """sha16 of the content, in a canonical form (sorted JSON): what a
        marker stamps and `check_intact` compares."""
        return content_sha(self.get())

    # ------------------------------------------------------------ writing
    def put(self, data: Any) -> str:
        """Replace whatever is at this key with `data`. Returns the sha16 of
        what reads back — `sha()` of this node — not of `data`: HDF5 stores a
        mixed list `[0, 10.0]` as `[0.0, 10.0]`, and a marker's sha must be
        the one a later reader computes.

        A dict becomes a group; a list, string or number a dataset. Values
        pass through a JSON round trip first (numpy scalars, paths and other
        objects become what `json.dumps(default=str)` makes of them), which
        is the form every JSON artifact takes in the record."""
        payload = data.model_dump() if isinstance(data, BaseModel) else data
        payload = _no_nul(json.loads(json.dumps(payload, default=str)))
        return content_sha(self.store.put(self.key, payload))

    def put_text(self, text: str) -> str:
        return content_sha(self.store.put(self.key, _no_nul(str(text))))

    def put_table(self, df) -> str:
        from octomod.result.records import Table

        payload = Table.from_dataframe(df).model_dump()
        return content_sha(self.store.put(self.key, payload))

    def put_blob(self, data: bytes) -> str:
        """Opaque bytes, stored as one opaque HDF5 value."""
        self.store.put_bytes(self.key, bytes(data))
        return hashlib.sha256(bytes(data)).hexdigest()[:16]

    def put_raw(self, data: Any) -> None:
        """Write `data` as is (arrays stay arrays): the multistart."""
        self.store.put(self.key, data)

    def delete(self) -> bool:
        """Remove this key and everything under it. True when it existed."""
        if not self.store.exists_on_disk():
            return False
        return self.store.delete(self.key)

    def copy_to(self, dst: Node) -> bool:
        """Copy this group or dataset to `dst` (replacing it) — inside one
        file or across two, arrays and all, without a decode. False when
        there was nothing to copy."""
        if not self.exists():
            return False
        self.store.copy(self.key, dst.store, dst.key)
        return True


def _no_nul(data: Any) -> Any:
    """Strings with `\\x00` replaced by the escaped literal `\\x00`,
    recursively (keys too): HDF5's variable-length strings cannot hold the
    character, and a write that meets an unescaped one fails half-way."""
    if isinstance(data, str):
        return data.replace("\x00", "\\x00")
    if isinstance(data, dict):
        return {_no_nul(k): _no_nul(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_no_nul(v) for v in data]
    return data


def content_sha(data: Any) -> str:
    """sha16 of record data in a canonical form."""
    if isinstance(data, str):
        text = data
    else:
        text = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def root(store: RunStore) -> Node:
    return Node(store, "")


# ------------------------------------------------------------ the tree
# Where the parts of a round live, for code that holds a round node rather
# than a RunContext (renderers, readers). The single-model round keeps its
# model, gates and markers at ROUND level and its fitted problem under the
# candidate `_single`; a candidate-set round keeps all four per candidate.

SINGLE = "_single"
PENDING_GATE = "pending_gate"


def pending_node(root_: Node) -> Node:
    """Where a file-mode gate's pending question lives."""
    return root_ / PENDING_GATE


def round_node(root_: Node, k: int) -> Node:
    return root_ / "rounds" / f"round_{int(k)}"


def round_index(rnd: Node) -> int:
    return int(rnd.name.split("_", 1)[1])


def round_indices(root_: Node) -> list[int]:
    """Every round in the record, in order."""
    out = []
    for name in (root_ / "rounds").children():
        if name.startswith("round_") and name[6:].isdigit():
            out.append(int(name[6:]))
    return sorted(out)


def candidate_ids(rnd: Node) -> list[str]:
    """The candidates of a candidate-set round, in name order; [] for a
    single-model round (whose one workdir is `_single`, not a candidate)."""
    return [c for c in (rnd / "candidates").children() if c != SINGLE]


def work_node(rnd: Node, cid: str | None) -> Node:
    return (rnd / "candidates").child(cid or SINGLE)


def model_node(rnd: Node, cid: str | None) -> Node:
    return work_node(rnd, cid) / "model" if cid else rnd / "model"


def gates_node(rnd: Node, cid: str | None) -> Node:
    return work_node(rnd, cid) / "gates" if cid else rnd / "gates"


def markers_node(rnd: Node, cid: str | None) -> Node:
    return work_node(rnd, cid) / "markers" if cid else rnd / "status/markers"
