"""Whole-record forms: export copies pruned by tier, and the schema.

The run's record is `runs/<id>.h5`, written group by group by the
engine (`runstore.RunStore`). This module keeps the whole-record operations
— load it validated, write a copy atomically, prune a copy by tier, keep a
subset of rounds, emit the JSON Schema.

HDF5 through `mkstd.Hdf5Standard` and nothing else is produced by a run.
mkstd can serialise the same model to
JSON or YAML; that is a skill's business, on request, and not done here.

What `commit` guarantees: the file on disk is always a COMPLETE, valid record
— written to a temporary file beside the target, flushed, renamed over the old
one — so a process that dies between two commits leaves the previous complete
state, which is what a resume starts from.

What `prune` guarantees: a copy with fewer tiers is valid against the same
schema, and every record that lost a field lists it in `elided`.

The module uses mkstd's `Hdf5Standard` as is, which is why mkstd is pinned
(0.0.13): its HDF5 path escapes a `/` in a dict key instead of reading it as
a nested group, loads eagerly, keeps an empty string a string rather than
`[]`, and returns `str` for stored strings rather than ASCII-decoded ones.
`tests/result_roundtrip_unit.py` pins each of those cases.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from octomod.result.model import RunResult
from octomod.result.records import TIERS

try:  # mkstd is a declared dependency (pyproject.toml)
    import mkstd as _mkstd

    RunResultStandard = _mkstd.Hdf5Standard(model=RunResult)
except Exception as _e:  # pragma: no cover - the environment says so loudly
    _mkstd = None
    RunResultStandard = None
    _MKSTD_ERROR = _e


def _require_mkstd() -> None:
    if RunResultStandard is None:
        raise RuntimeError(
            f"mkstd is not importable in this environment ({_MKSTD_ERROR!r}); "
            "it is pinned in pyproject.toml — run `uv sync`."
        )


def schema_json() -> str:
    """The JSON Schema of the HDF5 record, as mkstd generates it."""
    _require_mkstd()
    return RunResultStandard.get_schema()


# ------------------------------------------------------------ write / read
def result_path(run) -> Path:
    """The run's file: `runs/<id>.h5`."""
    from octomod.result.access import store_of

    return store_of(run).path


def commit(result: RunResult, target) -> Path:
    """Write a whole record atomically to `target` (an export copy, a legacy
    import). A target without the `.h5` suffix gets it — `runs/foo` is
    written as `runs/foo.h5`, the same file `load("runs/foo")` reads.

    A PRUNED record (anything `elided`) is never written over an existing
    file: the file could be a run's own record, and a copy with fewer tiers
    replacing it is the loss this guards against. The caller
    deletes the old copy first, so the guard is not the CLI's alone."""
    from octomod.result.runstore import SUFFIX, RunStore

    t = Path(target)
    if not t.name.endswith(SUFFIX):
        t = t.with_name(t.name + SUFFIX)
    if t.exists() and is_pruned(result):
        raise FileExistsError(
            f"refusing to write a pruned record over {t} — it may be a run's "
            f"own record; delete the file first if it is only an old copy"
        )
    return RunStore(t).write_all(result)


def is_pruned(result: RunResult) -> bool:
    """Whether any record in the tree lists an `elided` field."""
    return _any_elided(result)


def _any_elided(value: Any) -> bool:
    if isinstance(value, BaseModel):
        if getattr(value, "elided", None):
            return True
        return any(
            _any_elided(getattr(value, name)) for name in type(value).model_fields
        )
    if isinstance(value, dict):
        return any(_any_elided(v) for v in value.values())
    if isinstance(value, list):
        return any(_any_elided(v) for v in value)
    return False


def load(path) -> RunResult:
    """Read and validate a record: the run's file, a `RunStore`, a record
    `Node`, or `runs/<id>`."""
    from octomod.result.access import store_of

    store = store_of(path)
    if not store.exists_on_disk():
        raise FileNotFoundError(f"no result file at {store.path}")
    return store.load()


# ------------------------------------------------------------------ tiers
def _tier_of(model_cls: type[BaseModel], name: str) -> str:
    info = model_cls.model_fields[name]
    extra = info.json_schema_extra
    if isinstance(extra, dict):
        return str(extra.get("tier", "core"))
    return "core"


def _empty_for(model_cls: type[BaseModel], name: str, value: Any) -> Any:
    """What a removed field becomes: None when the field allows it, else the
    empty container of its kind — so the pruned record still validates."""
    info = model_cls.model_fields[name]
    if info.default is None or _allows_none(info.annotation):
        return None
    if isinstance(value, list):
        return []
    if isinstance(value, dict):
        return {}
    return None


def _allows_none(annotation: Any) -> bool:
    import types
    import typing

    if annotation is type(None):
        return True
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        return any(_allows_none(a) for a in typing.get_args(annotation))
    return False


def _prune_model(obj: BaseModel, keep: set[str]) -> None:
    for name in list(type(obj).model_fields):
        if name == "elided":
            continue
        value = getattr(obj, name)
        t = _tier_of(type(obj), name)
        if t not in keep and value not in (None, [], {}):
            object.__setattr__(obj, name, _empty_for(type(obj), name, value))
            if hasattr(obj, "elided"):
                obj.elided.append(name)
            continue
        _prune_value(value, keep)


def _prune_value(value: Any, keep: set[str]) -> None:
    if isinstance(value, BaseModel):
        _prune_model(value, keep)
    elif isinstance(value, dict):
        for v in value.values():
            _prune_value(v, keep)
    elif isinstance(value, list):
        for v in value:
            _prune_value(v, keep)


def prune(result: RunResult, tiers: Iterable[str]) -> RunResult:
    """A deep copy keeping only the named tiers; `core` is always kept."""
    keep = {str(t) for t in tiers} | {"core"}
    unknown = keep - set(TIERS)
    if unknown:
        raise ValueError(f"unknown tier(s) {sorted(unknown)}; tiers are {TIERS}")
    copy = result.model_copy(deep=True)
    _prune_model(copy, keep)
    return copy


def select_rounds(result: RunResult, rounds: Iterable[int]) -> RunResult:
    """A deep copy holding only the named rounds in full; every other round is
    reduced to its index, shape, selection and decisions, and says so."""
    want = {int(k) for k in rounds}
    copy = result.model_copy(deep=True)
    for _key, rec in list(copy.rounds.items()):
        if rec.index in want:
            continue
        kept = {"index", "shape", "selection", "decisions", "revision", "expansion"}
        for name in list(type(rec).model_fields):
            if name in kept or name == "elided":
                continue
            value = getattr(rec, name)
            if value not in (None, [], {}):
                object.__setattr__(rec, name, _empty_for(type(rec), name, value))
                rec.elided.append(name)
    return copy
