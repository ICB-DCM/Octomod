"""How long a live agent call usually takes, from this engine's own ledgers.

`agent_call` ledger rows carry `duration_s`, so the console quotes measured
history instead of a guess, and says so when there is none. Nothing here is a
threshold or a gate. The walk over the ledger of every run record (`runs/*.h5`)
is cached for the process; it covers every run on disk and its answer does not
change mid-run. Also: `Heartbeat`, the progress line printed while a live call
is in flight.
"""

from __future__ import annotations

import statistics
from functools import lru_cache
from pathlib import Path

MIN_SAMPLES = 3  # below this, a range is anecdote rather than history


def _fmt(seconds: float) -> str:
    """Duration a person can read: seconds under a minute, else m/s."""
    s = int(round(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s" if s % 60 else f"{s // 60}m"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


@lru_cache(maxsize=1)
def history(runs_dir: str | None = None) -> dict[str, dict]:
    """{role: {n, median, p10, p90}} of `duration_s` over every live call ledgered.

    Stub calls are excluded: they return in milliseconds and would drag every
    median to zero.
    """
    from octomod import config

    base = Path(runs_dir) if runs_dir else config.RUNS_DIR
    by_role: dict[str, list[float]] = {}
    if not base.exists():
        return {}
    from octomod.result.runstore import RunStore

    for store in RunStore.all_in(base):
        try:
            rows = store.ledger_rows()
        except Exception:
            continue
        for row in rows:
            if (
                row.get("event") != "agent_call"
                or row.get("backend") != "llm"
                or not row.get("duration_s")
            ):
                continue
            by_role.setdefault(str(row.get("role")), []).append(
                float(row["duration_s"])
            )
    out: dict[str, dict] = {}
    for role, xs in by_role.items():
        xs.sort()
        out[role] = {
            "n": len(xs),
            "median": statistics.median(xs),
            "p10": xs[max(0, int(len(xs) * 0.1) - (1 if len(xs) % 10 == 0 else 0))],
            "p90": xs[min(len(xs) - 1, int(len(xs) * 0.9))],
        }
    return out


def typical(role: str, backend: str = "llm") -> str:
    """A typical-duration phrase for `role`, e.g. "typically 5m-18m (n=7)".

    Returns "" for a non-live backend; with fewer than MIN_SAMPLES measured
    calls it says in words that there is no typical time yet.
    """
    if backend != "llm":
        return ""
    h = history().get(role)
    if not h or h["n"] < MIN_SAMPLES:
        if h:
            return f"no typical time yet, {h['n']} call(s) measured"
        return "never called live before, so no typical time"
    lo, hi = h["p10"], h["p90"]
    if _fmt(lo) == _fmt(hi):
        return f"typically {_fmt(h['median'])} (n={h['n']})"
    return f"typically {_fmt(lo)}-{_fmt(hi)} (n={h['n']})"


# What each role is doing, in the user's terms rather than the contract's.
DOING = {
    "knowledge": "gathering what is known about the system: reactions, facts and their sources",
    "knowledge_verification": "re-reading each source's own text around its quote",
    "construction": "drafting the model and the alternatives it is unsure about",
    "expansion": "writing each candidate as a difference from the tested base",
    "data_extraction": "reading the data files and mapping their columns",
    "observation": "deciding what each measured column observes",
    "condition": "encoding the experimental conditions",
    "assembly_verification": "checking the assembled problem against the lab note",
    "interpretation": "reading the fits and the residuals",
    "revision": "reading the residuals to say what the model space missed",
    "revision_proposal": "proposing one change to the model",
    "entity_glossary": "naming the entities in the modeller's own words",
}


def doing(role: str) -> str:
    return DOING.get(role, f"working on {role.replace('_', ' ')}")


class Heartbeat:
    """A progress line (elapsed time, what the agent is doing) during a live call.

    On a TTY one line is rewritten in place every `interval` seconds and erased
    when the call returns; otherwise plain lines are appended, because captured
    stdout turns carriage returns into one smear. With `live=False` nothing is
    printed, so the stub backend's console output (parsed by several suites)
    stays byte-identical. The ticker is a daemon thread and every write is
    guarded: a broken pipe or closed stream must not take down a run.
    """

    def __init__(
        self,
        label: str,
        detail: str = "",
        interval: float = 15.0,
        stream=None,
        live: bool = True,
    ) -> None:
        import sys as _sys

        self.label = label
        self.detail = detail
        # a floor against a busy loop, low enough for a test to watch it tick
        self.interval = max(0.05, float(interval))
        self.stream = stream if stream is not None else _sys.stdout
        self.live = live
        self._thread = None
        self._stop = None
        self._t0 = 0.0
        self._wrote = False

    def _tty(self) -> bool:
        try:
            return bool(self.stream.isatty())
        except Exception:
            return False

    def _write(self, text: str, rewrite: bool) -> None:
        try:
            if rewrite:
                self.stream.write("\r\x1b[2K" + text)
            else:
                self.stream.write(text + "\n")
            self.stream.flush()
            self._wrote = True
        except Exception:
            pass

    def _line(self) -> str:
        import time as _time

        elapsed = _fmt(_time.perf_counter() - self._t0)
        parts = [self.label, self.detail, f"{elapsed} elapsed"]
        return "  " + " · ".join(x for x in parts if x)

    def __enter__(self):
        import threading
        import time as _time

        self._t0 = _time.perf_counter()
        if not self.live:
            return self
        self._stop = threading.Event()
        tty = self._tty()

        def loop() -> None:
            while not self._stop.wait(self.interval):
                self._write(self._line(), rewrite=tty)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        # erase the rewritten line so the reply lands on a clean row (TTY only)
        if self._wrote and self._tty():
            try:
                self.stream.write("\r\x1b[2K")
                self.stream.flush()
            except Exception:
                pass
