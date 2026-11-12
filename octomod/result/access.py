"""The record as the readers' source.

Every reader — the analysis report, the tried-models memory, the decision
record, the truth scorer, the CLI — asks for the run's `RunResult` here and
reads the artifact it needs OFF the record.
Two things this module settles once:

* **Which record.** `record_for(run)` loads the run's HDF5 file (the run
  IS the file, so there is nothing else it could be). `run` may be any
  record `Node` a module holds, the `RunStore`, or a `Path` — to the file, or
  `runs/<id>`. Cached on the file's mtime, so one reader building a document
  asks once per state of the run and a later state is never served an older
  record.

* **Artifact views.** A reader wants the dict a module wrote, not a record
  with `elided` and defaulted fields. The `*_dict` helpers return that dict:
  extras verbatim, declared fields only when set. A reader may still use
  `.get` for a key the module did not write.
"""

from __future__ import annotations

import functools
from pathlib import Path

from pydantic import BaseModel

from octomod.result.model import RoundRecord, RunResult
from octomod.result.runstore import SUFFIX, RunStore

# fields a record class declares that the module writing it never sets (a
# legacy import filled them from elsewhere), which the view leaves out
_ADDED = {
    "revision": {"config_hash", "best_fval"},
}


def store_of(run) -> RunStore:
    """The `RunStore` behind whatever a caller holds for a run."""
    if isinstance(run, RunStore):
        return run
    if hasattr(run, "store"):  # a record Node (any depth: the store is the run)
        return run.store
    p = Path(run)
    if p.name.endswith(SUFFIX):
        return RunStore(p)
    return RunStore.for_run(p.parent, p.name)


@functools.lru_cache(maxsize=1)
def _cached(path: str, stamp: tuple | None) -> RunResult:
    return RunStore(Path(path)).load()


def record_for(run) -> RunResult:
    """The run's record, validated, current as of the file's last write."""
    store = store_of(run)
    return _cached(str(store.path.resolve()), store.stamp())


def as_artifact(rec: BaseModel | None, added: set[str] = frozenset()) -> dict | None:
    """The dict an artifact held, read back off its record."""
    if rec is None:
        return None
    fields = type(rec).model_fields
    out = rec.model_dump(exclude_unset=True, exclude={"elided", *added})
    return {k: v for k, v in out.items() if not (v is None and k in fields)}


def report_dict(rnd: RoundRecord) -> dict | None:
    """The round's evaluation (S7's report)."""
    return as_artifact(rnd.evaluation)


def expansion_dict(rnd: RoundRecord) -> dict | None:
    """The round's expansion decision (None when the round never reached it)."""
    if rnd.expansion is None:
        return None
    return as_artifact(rnd.expansion)


def revision_dict(rnd: RoundRecord) -> dict | None:
    """The round's revision decision."""
    if rnd.revision is None:
        return None
    return as_artifact(rnd.revision, _ADDED["revision"])


def axes_declared(rnd: RoundRecord) -> list[dict]:
    """Every axis dict the round declared: `space/axes` then `space/declared`,
    in that order, as `tried_models` always read them."""
    if rnd.space is None:
        return []
    out: list[dict] = []
    for a in rnd.space.axes:
        d = as_artifact(a) or {}
        if d.get("id"):
            out.append(d)
    out += [a for a in rnd.space.declared if isinstance(a, dict) and a.get("id")]
    return out


def ledger_rows(rr: RunResult) -> list[dict]:
    """The ledger as the list of dicts `load_ledger` returned."""
    return [e.model_dump(exclude_unset=True, exclude={"elided"}) for e in rr.ledger]


def run_meta(rr: RunResult) -> dict:
    """The run's metadata as the engine wrote it."""
    return as_artifact(rr.run, {"started_at", "n_invocations", "research_fence"}) or {}


def intent(rr: RunResult) -> dict:
    """The frozen intent."""
    return as_artifact(rr.intent) or {}


def rounds_with_reports(rr: RunResult) -> list[tuple[int, dict]]:
    """(index, evaluation) for every round that has one, in order. An EMPTY
    evaluation is still a report; a round whose S7 died after writing only
    `evaluation_core` has none — the core is its own group,
    so it cannot make the evaluation appear."""
    out = []
    for k in rr.round_indices:
        if rr.round(k).evaluation is not None:
            out.append((k, report_dict(rr.round(k))))
    return out


def round_of(rr: RunResult, rnd) -> RoundRecord | None:
    """The RoundRecord of a round node (`rounds/round_k`)."""
    return rr.rounds.get(rnd.name)


def candidate_assembly(rnd: RoundRecord) -> dict | None:
    """The assembly of a single-model round, else the shared base."""
    single = rnd.candidates.get("_single")
    if single is not None and single.assembly is not None:
        return as_artifact(single.assembly)
    return as_artifact(rnd.shared_assembly)
