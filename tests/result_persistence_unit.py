"""The multistart result is an artifact: S6 writes it into the record, S7 reads it.

The unit of work's `multistart` (e.g. `rounds/round_0/candidates/_single/multistart`,
rebuilt by `estimation.result_from_record`).

  1. the round trip keeps every fval, the best x, and the order (the best is list[0]);
  2. a missing multistart returns None, so the caller can recompute;
  3. so does a corrupt one;
  4. S6 writes it and S7 reads it before falling back to re-running.

    uv run python tests/result_persistence_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.workflow_modules.estimation.problem import (  # noqa: E402
    read_optimize_result,
    write_optimize_result,
)
from tests._record import rnd, temp_record, work  # noqa: E402


def _toy_result():
    """A pypesto Result with a few starts, built without fitting anything."""
    import pypesto
    import pypesto.result

    problem = pypesto.Problem(
        objective=pypesto.Objective(fun=lambda x: float(np.sum(np.asarray(x) ** 2))),
        lb=[-5.0, -5.0],
        ub=[5.0, 5.0],
        x_names=["a", "b"],
    )
    result = pypesto.Result(problem=problem)
    rng = np.random.default_rng(3)
    for i in range(5):
        x = rng.normal(size=2)
        result.optimize_result.append(
            pypesto.result.OptimizerResult(
                id=str(i),
                x=x,
                fval=float(np.sum(x**2)),
                grad=np.zeros(2),
                exitflag=0,
                x0=x,
                fval0=float(np.sum(x**2)),
            )
        )
    result.optimize_result.sort()
    return result


def test_round_trip_preserves_what_is_read(node):
    res = _toy_result()
    write_optimize_result(res, node)
    assert node.exists(), node
    back = read_optimize_result(node)
    assert back is not None, "wrote a multistart and could not read it"
    a = [float(o.fval) for o in res.optimize_result.list]
    b = [float(o.fval) for o in back.optimize_result.list]
    assert len(a) == len(b) == 5, (len(a), len(b))
    assert np.allclose(a, b, rtol=0, atol=0), list(zip(a, b, strict=False))
    assert a == sorted(a), "order lost: the report's best is list[0]"
    xa = np.asarray(res.optimize_result.list[0].x, dtype=float)
    xb = np.asarray(back.optimize_result.list[0].x, dtype=float)
    assert np.allclose(xa, xb, rtol=0, atol=0), (xa, xb)
    # what profiling and a refit read besides fval and x
    o0, b0 = res.optimize_result.list[0], back.optimize_result.list[0]
    assert b0.id == o0.id and b0.exitflag == o0.exitflag
    assert np.allclose(b0.x0, o0.x0) and b0.fval0 == o0.fval0
    print("  round trip    5 starts, every fval and the best x exact, order kept")


def test_missing_is_none_not_an_exception(root):
    # a record key nothing has been written to: another round's slot
    nowhere = work(root, 7) / "multistart"
    assert read_optimize_result(nowhere) is None
    print("  missing       returns None, so the caller can recompute")


def test_corrupt_is_none_not_an_exception(root):
    # garbage where the arrays should be: a group that is not a multistart
    bad = rnd(root, 0) / "candidates/bad/multistart"
    bad.put({"n_starts": "x"})
    assert read_optimize_result(bad) is None
    print("  corrupt       returns None rather than killing the evaluation module")


def test_the_modules_are_wired_to_it():
    s6 = (
        REPO / "octomod" / "workflow_modules" / "estimation" / "engine.py"
    ).read_text()
    s7 = (
        REPO / "octomod" / "workflow_modules" / "evaluation" / "engine.py"
    ).read_text()
    assert "write_optimize_result" in s6, "S6 does not persist the result"
    assert "read_optimize_result" in s7, "S7 does not read the persisted result"
    i_read = s7.index("read_optimize_result")
    i_rerun = s7.index("result = run_multistart(")
    assert i_read < i_rerun, "S7 re-runs before it tries to read the file"
    print("  wiring        S6 writes it; S7 reads it BEFORE falling back to re-running")


if __name__ == "__main__":
    with temp_record() as root:
        test_round_trip_preserves_what_is_read(work(root, 0) / "multistart")
        test_missing_is_none_not_an_exception(root)
        test_corrupt_is_none_not_an_exception(root)
    test_the_modules_are_wired_to_it()
    print(
        "RESULT PERSISTENCE UNIT OK — the multistart survives the process that "
        "made it, and an unreadable one degrades to recomputation, not to a crash"
    )
