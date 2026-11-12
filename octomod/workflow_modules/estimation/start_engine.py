"""Where a multistart's starts run, and what each one cost.

`pypesto.optimize.minimize` builds one task per start and hands the list to
its engine. `StartEngine` is that engine for every multistart this workflow
runs (the cost probe, S6's estimation, S7's re-run of a fit). It runs the
tasks in this process or in worker processes, and times each start on its
own: wall and CPU, and whether it ran ALONE (nothing else of this multistart
running beside it).

Two numbers come out of that, for two different uses:

- **what one start costs** — `start_s`: its wall when it ran alone, its CPU
  when others ran beside it (a start sharing the machine with its siblings
  takes longer on the clock for work that did not grow). This is the
  serial-equivalent cost that projections, the engine decision and every
  comparison with a serially timed number (the optimiser comparison, the
  adjoint re-probe, a later candidate's probe) read, so a parallel probe and
  a serial one give the same kind of number;
- **whether dispatching paid** — `wall_s` of the whole multistart against
  `serial_equivalent_s` (the sum of `start_s`): `speedup` is how many times
  faster than one at a time it actually ran, pool start-up included.

Three modes:

- `serial`: every start here, in order.
- `parallel`: every start dispatched to `min(n_procs, n_starts)` workers.
- `adaptive` (the cost probe under `estimation.engine: auto`): starts run
  here one at a time; the moment one has used `min_start_cpu_s` of CPU and is
  still running, the rest are dispatched and it finishes beside them. A toy
  whose starts finish under the floor never starts a pool; a start that
  fails at its start point finishes at once and the next one decides. CPU,
  not wall, so a loaded machine does not tip the decision.

Every start is seeded from (seed, start index) before it runs, wherever it
runs, so an optimiser that draws from NumPy's global generator gives the
same result serially and dispatched. Workers are forked where that is safe
and spawned where it is not (`_context`): either way each is this process's
own child, so its CPU is in `timing.cpu_now()` once the pool is joined
(`process_cpu_s`, pool start-up included). Each worker unpickles the task list once, not once per start. A
pool that breaks (a worker killed for memory, a crash in native code) does
not lose the starts that finished: the rest run here, and `fallback` says why.
"""

from __future__ import annotations

import multiprocessing
import sys
import threading
import time

import numpy as np

# how often an adaptive wait looks at the CPU clock
POLL_S = 0.05

_TASKS: list | None = None  # a worker's copy of the task list


def start_seed(seed: int, index: int) -> int:
    """The NumPy seed of start `index` of a multistart seeded with `seed`."""
    seq = np.random.SeedSequence([abs(int(seed)), int(index)])
    return int(seq.generate_state(1)[0])


def _run(task, seed: int, capture: bool, clock) -> tuple[object, dict]:
    """Execute one task seeded, timed, and (in a worker) with its messages counted."""
    np.random.seed(seed)
    counted = None
    c0, t0 = clock(), time.perf_counter()
    if capture:
        from octomod.workflow_modules.cost_probe.solver_messages import Capture

        with Capture() as captured:
            result = task.execute()
        counted = captured.counted()
    else:
        result = task.execute()
    return result, {
        "wall_s": time.perf_counter() - t0,
        "cpu_s": max(0.0, clock() - c0),
        "counted": counted,
    }


def _init_worker(payload: bytes) -> None:
    import cloudpickle

    global _TASKS
    _TASKS = cloudpickle.loads(payload)


def _work(index: int, seed: int, capture: bool):
    # a worker runs one start at a time: the process clock is that start's
    return _run(_TASKS[index], seed, capture, time.process_time)


def _context(start_running: bool):
    """`fork` where it is safe and cheap, else `spawn`; never `forkserver`,
    whose workers are the server's children, so their CPU would never reach
    this process's account (`timing.cpu_now`).

    A fork copies a process mid-whatever: with a start simulating on a thread
    (an adaptive dispatch) the copy can inherit a lock that thread held, and
    on macOS system libraries do not survive a fork at all. A spawned worker
    imports pyPESTO and AMICI afresh (seconds of CPU each), which is why a
    plain parallel multistart on Linux forks, as pyPESTO's own engine does.
    """
    methods = multiprocessing.get_all_start_methods()
    if not start_running and sys.platform != "darwin" and "fork" in methods:
        return multiprocessing.get_context("fork")
    return multiprocessing.get_context("spawn")


class StartEngine:
    """A pyPESTO engine that times every start; see the module docstring.

    `n_procs` caps the workers; `capture` (a `solver_messages.Capture` the
    caller holds open) receives the AMICI messages counted in the workers,
    since a handler only sees its own process. After `execute`, `summary()`
    says what happened. `progress_bar` is accepted and ignored.
    """

    def __init__(
        self,
        mode: str = "serial",
        n_procs: int = 1,
        *,
        seed: int = 0,
        min_start_cpu_s: float | None = None,
        capture=None,
        decided: str = "",
    ):
        if mode not in ("serial", "parallel", "adaptive"):
            raise ValueError(f"unknown StartEngine mode {mode!r}")
        if mode == "adaptive" and min_start_cpu_s is None:
            raise ValueError("an adaptive StartEngine needs min_start_cpu_s")
        self.mode = mode
        self.n_procs = max(1, int(n_procs))
        self.seed = int(seed)
        self.min_start_cpu_s = min_start_cpu_s
        self.capture = capture
        self._why = decided
        self._reset()

    def _reset(self) -> None:
        self.starts: list[dict | None] = []
        self.results: list = []
        self.n_workers = 1
        self.decided = self._why
        self.fallback: str | None = None
        self.wall_s = 0.0
        self.process_cpu_s = 0.0
        self._counted: list[tuple[int, dict]] = []

    # ------------------------------------------------------------ running

    def execute(self, tasks, progress_bar=None) -> list:
        self._reset()
        tasks = list(tasks)
        n = len(tasks)
        self.starts, self.results = [None] * n, [None] * n
        from octomod.orchestration.timing import cpu_now

        t0, p0 = time.perf_counter(), cpu_now()
        try:
            can_dispatch = self.n_procs > 1 and n >= 2
            if self.mode == "parallel" and can_dispatch:
                self._dispatch(tasks, 0)
            elif self.mode == "adaptive" and can_dispatch:
                self._adaptive(tasks)
            else:
                if self.mode != "serial" and not self.decided:
                    self.decided = (
                        "one worker allowed (estimation.n_procs)"
                        if self.n_procs == 1
                        else "a single start"
                    )
                for i in range(len(tasks)):
                    self._here(tasks, i)
        finally:
            self.wall_s = time.perf_counter() - t0
            self.process_cpu_s = max(0.0, cpu_now() - p0)
            # in start order, as a serial run would have logged them: the
            # examples kept are then the same whichever way the starts ran
            for _i, counted in sorted(self._counted, key=lambda c: c[0]):
                self.capture.absorb(counted)
            self._counted = []
        return list(self.results)

    def _store(self, tasks, i: int, result, meta: dict, where: str, alone: bool):
        if meta.get("counted") and self.capture is not None:
            self._counted.append((i, meta["counted"]))
        fval = getattr(result, "fval", None)
        try:
            finite = fval is not None and bool(np.isfinite(float(fval)))
        except (TypeError, ValueError):
            finite = False
        wall, cpu = float(meta["wall_s"]), float(meta["cpu_s"])
        self.results[i] = result
        self.starts[i] = {
            "id": str(getattr(tasks[i], "id", i)),
            "where": where,
            "alone": alone,
            "wall_s": round(wall, 4),
            "cpu_s": round(cpu, 4),
            # what this start costs by itself: the clock when nothing ran
            # beside it, its CPU when something did
            "start_s": round(wall if alone else cpu, 4),
            "finite": finite,
        }

    def _here(self, tasks, i: int) -> None:
        result, meta = _run(
            tasks[i], start_seed(self.seed, i), False, time.process_time
        )
        self._store(tasks, i, result, meta, "here", alone=True)

    def _adaptive(self, tasks) -> None:
        import cloudpickle

        n = len(tasks)
        # pickled before any start runs: once a start is simulating on a
        # thread, the objective is not read from another one
        payload = cloudpickle.dumps(tasks)
        floor = float(self.min_start_cpu_s)
        for i in range(n):
            if n - i - 1 < 2:  # one start left is not worth a pool
                self._here(tasks, i)
                continue
            box: dict = {}

            def target(i=i, box=box):
                try:
                    box["out"] = _run(
                        tasks[i], start_seed(self.seed, i), False, time.thread_time
                    )
                except BaseException as e:  # noqa: BLE001 - re-raised below
                    box["error"] = e

            thread = threading.Thread(target=target, daemon=True)
            c0 = time.process_time()
            thread.start()
            while thread.is_alive():
                thread.join(POLL_S)
                if thread.is_alive() and time.process_time() - c0 >= floor:
                    self.decided = (
                        f"start {i} had used {floor:g}s of CPU "
                        f"(estimation.parallel_min_start_s) and was still running"
                    )
                    self._dispatch(
                        tasks, i + 1, payload=payload, pending=(i, thread, box)
                    )
                    return
            if "error" in box:
                raise box["error"]
            self._store(tasks, i, *box["out"], "here", alone=True)
        self.decided = (
            f"every start finished under {floor:g}s of CPU "
            f"(estimation.parallel_min_start_s)"
        )

    def _dispatch(self, tasks, j0: int, *, payload=None, pending=None) -> None:
        """Run tasks[j0:] on workers; `pending` is a start still running here."""
        from concurrent.futures import ProcessPoolExecutor, as_completed
        from concurrent.futures.process import BrokenProcessPool

        import cloudpickle

        if payload is None:
            payload = cloudpickle.dumps(tasks)
        if not self.decided:
            self.decided = "estimation.engine dispatches every start"
        todo = list(range(j0, len(tasks)))
        self.n_workers = min(self.n_procs, len(todo))
        capture = self.capture is not None
        futures: dict = {}
        try:
            with ProcessPoolExecutor(
                max_workers=self.n_workers,
                mp_context=_context(start_running=pending is not None),
                initializer=_init_worker,
                initargs=(payload,),
            ) as pool:
                futures = {
                    pool.submit(_work, j, start_seed(self.seed, j), capture): j
                    for j in todo
                }
                if pending is not None:
                    self._finish_pending(tasks, pending)
                    pending = None
                for fut in as_completed(futures):
                    self._store(tasks, futures[fut], *fut.result(), "worker", False)
        except (BrokenProcessPool, OSError) as e:
            self.fallback = (
                f"the worker pool broke ({type(e).__name__}: {str(e)[:160]}); "
                "the starts it had not returned ran here, one at a time"
            )
            if pending is not None:
                self._finish_pending(tasks, pending)
            for fut, j in futures.items():
                if self.results[j] is None and fut.done() and not fut.exception():
                    self._store(tasks, j, *fut.result(), "worker", False)
            for j in todo:
                if self.results[j] is None:
                    self._here(tasks, j)

    def _finish_pending(self, tasks, pending) -> None:
        i, thread, box = pending
        thread.join()
        if "error" in box:
            raise box["error"]
        self._store(tasks, i, *box["out"], "here", alone=False)

    # ------------------------------------------------------------ reading

    def summary(self) -> dict:
        """What ran where, and whether dispatching paid, for the record."""
        starts = [s for s in self.starts if s is not None]
        n_disp = sum(1 for s in starts if s["where"] == "worker")
        serial_eq = sum(s["start_s"] for s in starts)
        return {
            "kind": "parallel" if n_disp else "serial",
            "mode": self.mode,
            "n_starts": len(starts),
            "n_here": len(starts) - n_disp,
            "n_dispatched": n_disp,
            "n_workers": self.n_workers if n_disp else 1,
            "min_start_cpu_s": self.min_start_cpu_s,
            "decided": self.decided,
            "fallback": self.fallback,
            "wall_s": round(self.wall_s, 3),
            # the starts' own CPU, and everything the processes used over the
            # multistart (this one and its workers: pool start-up included)
            "cpu_s": round(sum(s["cpu_s"] for s in starts), 3),
            "process_cpu_s": round(self.process_cpu_s, 3),
            "serial_equivalent_s": round(serial_eq, 3),
            # > 1: dispatching was faster than one at a time would have been
            "speedup": (
                round(serial_eq / self.wall_s, 2)
                if n_disp and self.wall_s > 0
                else None
            ),
            "starts": starts,
        }


def serial_summary(n_starts: int = 0, decided: str = "") -> dict:
    """The summary of a multistart known to have run here, one at a time,
    without an engine's timings (a record saved before engines recorded)."""
    out = StartEngine("serial", decided=decided).summary()
    out.update(n_starts=n_starts, n_here=n_starts)
    return out
