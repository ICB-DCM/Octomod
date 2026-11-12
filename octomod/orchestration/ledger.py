"""Append-only run ledger. Written by the engine, never by an agent.

The rows live in the run record (`RunStore.append_ledger`), one JSON object
per row, the same objects a legacy run's `ledger.jsonl` holds. `entries()` is what every
reader calls — the gate signature, the stub call counter, the decision record
— so the rows are cached in the process and re-read only when the record file
has changed underneath (another process wrote it).

A `run_end` row is also the run's outcome: `RunResult.outcome` is written
from it here, so the record says how the run ended without a reader having to
find the last row.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    """sha16 of a file's bytes — a REAL file (the testcase, the spec); a
    record node hashes its content with `Node.sha`."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _cpu_now() -> float:
    from octomod.orchestration.timing import cpu_now

    return cpu_now()


def read_rows(source, *, strict: bool = True) -> list[dict]:
    """The rows of a run's ledger ([] when there is no record).

    `source` is the run's `RunStore`, any record `Node` of it, a `Ledger`, or
    the path of the record file (`runs/<id>.h5`); a path to a legacy
    `ledger.jsonl` is read line by line, for the importer and legacy
    fixtures. `strict` raises on a torn row (a damaged record, a torn line);
    otherwise such a row is skipped, which is right for a reader that renders
    and wrong for one that counts.
    """
    store = getattr(source, "store", source)
    if isinstance(store, (str, Path)):
        path = Path(store)
        if path.suffix != ".h5":
            return _read_jsonl(path, strict=strict)
        from octomod.result.runstore import RunStore

        store = RunStore(path)
    try:
        return list(store.ledger_rows())
    except Exception:
        if strict:
            raise
        return []


def _read_jsonl(path: Path, *, strict: bool) -> list[dict]:
    """The rows of a JSON-lines ledger file ([] when it does not exist)."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if strict:
                raise
    return rows


class Ledger:
    def __init__(self, store_or_run):
        """`store_or_run` is the run's `RunStore`, or any record `Node` of it."""
        self.store = getattr(store_or_run, "store", store_or_run)
        self._rows: list[dict] | None = None
        self._stamp: int | None = None

    @property
    def path(self):
        """Where the rows are, for messages (the record file)."""
        return self.store.path

    def append(self, event: str, module: str = "", round_idx: int = 0, **data) -> None:
        now = datetime.datetime.now()
        entry = {
            "ts": now.isoformat(timespec="seconds"),
            # the same instant to the millisecond, as an epoch float —
            # what the time account (`octomod/orchestration/timing.py`) is built from
            "t": round(now.timestamp(), 3),
            "round": round_idx,
            # the process's CPU so far at its boundary rows, so a session's
            # CPU (self + children) is a difference of two numbers
            **(
                {"cpu_s": round(_cpu_now(), 3)}
                if event in ("run_start", "run_end", "gate_pending")
                else {}
            ),
            "module": module,
            "event": event,
            **data,
        }
        if not self.store.exists_on_disk():
            self.store.create()
        self.store.append_ledger(entry)
        if self._rows is not None:
            self._rows.append(entry)
        self._stamp = self.store.stamp()
        if event == "run_end":
            self._write_outcome(entry)

    def entries(self) -> list[dict]:
        stamp = self.store.stamp()
        if self._rows is None or stamp != self._stamp:
            self._rows = self.store.ledger_rows()
            self._stamp = stamp
        return list(self._rows)

    def _write_outcome(self, row: dict) -> None:
        from octomod.result.model import RunOutcome

        outcome = RunOutcome(
            outcome=row.get("outcome"),
            reason=row.get("reason"),
            winner=row.get("winner"),
            decisive=row.get("decisive"),
            at=row.get("ts"),
            final_round=row.get("round"),
        )
        try:
            self.store.put("outcome", outcome.model_dump(exclude_none=True))
        except Exception:  # noqa: BLE001 - the row is the record; this is a copy
            pass
