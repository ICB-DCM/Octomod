"""The AMICI cache key lock: processes that need the same model never both compile it.

  1. N processes race on one cleared cache key; exactly one compiles;
  2. every process returns a usable problem, and the module is in the cache.

    uv run python tests/amici_cache_lock_unit.py

Not part of `run_all`: it deletes a cache key to force a cold compile, which
would pull the module out from under a suite running beside it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
N_PROC = 3

CHILD = """
import json, sys
sys.path.insert(0, {repo!r})
from octomod.workflow_modules.assembly import petab_io
from octomod.workflow_modules.estimation.problem import build_problem
from tests._record import record_at, rnd, work
root = record_at({record!r})
inp = petab_io.from_work(work(root, 0), rnd(root, 0) / "model")
prob, _petab, compile_s = build_problem(inp, {{}})
print(json.dumps({{"compile_s": compile_s, "n_free": len(prob.x_free_indices)}}))
"""


def main() -> int:
    # any finished golden run supplies a real PEtab problem to compile — from
    # the battery's directory or the user's, whichever has one: one record
    # file per run, its problem at rounds/round_0/candidates/_single
    sys.path.insert(0, str(REPO))
    from octomod.config import AMICI_CACHE_DIR, RUNS_DIR, USER_RUNS_DIR
    from octomod.workflow_modules.assembly import petab_io
    from tests._record import record_at, rnd, work

    pattern = "golden_toy_phos_*.h5"
    runs = sorted(
        p
        for p in {
            p for d in dict.fromkeys((RUNS_DIR, USER_RUNS_DIR)) for p in d.glob(pattern)
        }
        if (work(record_at(p), 0) / "petab/measurements").exists()
    )
    if not runs:
        print(
            "no golden run on disk to borrow a PEtab problem from — run "
            "tests/golden_path.py toy_phos first"
        )
        return 1
    record = runs[-1]
    root = record_at(record)
    inp = petab_io.from_work(work(root, 0), rnd(root, 0) / "model")

    # the COMPILE key names the folder and the lock; the problem key would name
    # a directory that does not exist, and the race would never happen
    from octomod.workflow_modules.estimation.problem import compile_content_hash

    key = compile_content_hash(inp)
    cache_dir = AMICI_CACHE_DIR / f"amici_{key}"
    if cache_dir.exists():
        shutil.rmtree(cache_dir)  # force a genuine cold compile
    (AMICI_CACHE_DIR / f".lock_{key}").unlink(missing_ok=True)
    print(f"racing {N_PROC} processes on a cold cache key {key}")

    code = CHILD.format(repo=str(REPO), record=str(record))
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", code],
            cwd=REPO,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(N_PROC)
    ]
    outs = []
    for p in procs:
        out, err = p.communicate()
        assert p.returncode == 0, f"a racing process failed:\n{err[-1500:]}"
        line = [ln for ln in out.splitlines() if ln.startswith("{")][-1]
        outs.append(json.loads(line))
    times = sorted(o["compile_s"] for o in outs)
    print(f"build_problem wall per process: {[round(t, 1) for t in times]}")
    assert all(o["n_free"] > 0 for o in outs), "a process got an unusable problem"
    assert cache_dir.exists(), "no compiled module in the cache afterwards"
    # the winner compiles; the waiters block on the lock and then LOAD, so their
    # wall time is a small fraction of the compile they would have duplicated
    assert times[0] < 0.5 * times[-1], (
        f"every process paid compile-like time {times} — the lock is not "
        f"serialising the first compile"
    )
    print("AMICI CACHE LOCK OK — one compile, the rest loaded; no corrupted module")
    return 0


if __name__ == "__main__":
    sys.exit(main())
