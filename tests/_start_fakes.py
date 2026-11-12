"""Stand-in start tasks for `tests/probe_engine_unit.py`.

In their own importable module, not the test script: a worker started with
`spawn` or `forkserver` (macOS's default, and what `StartEngine` uses) must
import the classes a result is rebuilt from, and a class defined in the
script's `__main__` is not the same class there.
"""

from __future__ import annotations

import os
import time
from types import SimpleNamespace

import numpy as np


def burn(cpu_s: float) -> None:
    """Use `cpu_s` of this thread's CPU."""
    c0 = time.thread_time()
    while time.thread_time() - c0 < cpu_s:
        sum(i * i for i in range(2000))


class Start:
    """Uses `cpu_s` of CPU; fails (fval inf) when `fail`; draws from NumPy's
    global generator, so the result shows the seed it ran under. With
    `die_in_worker` set to the parent's pid it kills any other process that
    runs it, as a worker the OS killed for memory would die."""

    def __init__(self, i, cpu_s=0.0, fail=False, die_in_worker=None):
        self.id, self.cpu_s, self.fail = str(i), cpu_s, fail
        self.die_in_worker = die_in_worker

    def execute(self):
        if self.die_in_worker is not None and os.getpid() != self.die_in_worker:
            os._exit(1)
        burn(self.cpu_s)
        return SimpleNamespace(
            id=self.id,
            fval=float("inf") if self.fail else 1.0,
            draw=float(np.random.random()),
            pid=os.getpid(),
        )
