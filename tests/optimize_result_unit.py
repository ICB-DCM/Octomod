"""The multistart survives the record as pyPESTO produced it.

`estimation.write_optimize_result` stores the optimize result as one array
per `OptimizerResult` field under the candidate's `multistart`, and
`read_optimize_result` rebuilds the `pypesto.Result` that profiling and the
refits consume. Two things are pinned here:

  NaN      a start whose fval is NaN (the integrator failed) reads back as
           NaN, not None: the first version mapped NaN to None, pyPESTO's
           `sort` then raised `TypeError` on `np.isnan(None)`, the reader
           swallowed it and returned None — so S7 re-ran the whole multistart
           on EVERY resume of a run with one failed start. The record also
           tells a None apart from a NaN (`fval_present`), as pyPESTO's own
           HDF5 writer does, and a record written before the flag existed
           still reads its NaN as NaN.
  fields   the per-start arrays pyPESTO's writer keeps — `hess`, `res`,
           `sres`, `free_indices`, `inner_parameters` — round-trip with their
           shapes (the 2-D ones are stored flat and reshaped on read).

    uv run python tests/optimize_result_unit.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.workflow_modules.estimation.problem import (  # noqa: E402
    read_optimize_result,
    result_from_record,
    result_to_record,
    write_optimize_result,
)
from tests._record import temp_record, work  # noqa: E402

HESS = np.array([[2.0, 0.1], [0.1, 4.0]])
SRES = np.arange(6.0).reshape(3, 2)


def _two_starts():
    """One failed start (NaN fval, no gradient) and one converged start."""
    import pypesto
    from pypesto.result import OptimizerResult

    failed = OptimizerResult(
        id="0",
        x=np.array([1.0, 2.0]),
        fval=float("nan"),
        x0=np.array([0.5, 0.5]),
        fval0=float("nan"),
        exitflag=-1,
        n_fval=3,
        message="integration failed",
        optimizer="fides",
    )
    good = OptimizerResult(
        id="1",
        x=np.array([0.1, 0.2]),
        fval=3.5,
        grad=np.array([1e-3, -2e-3]),
        hess=HESS,
        res=np.array([0.1, -0.2, 0.3]),
        sres=SRES,
        x0=np.array([0.0, 0.0]),
        fval0=12.0,
        exitflag=0,
        n_fval=40,
        n_grad=40,
        time=1.25,
        message="converged",
        optimizer="fides",
    )
    good.free_indices = np.array([0, 1])
    good.inner_parameters = np.array([7.0])
    result = pypesto.Result()
    result.optimize_result.list = [failed, good]  # NaN first: `sort` must move it
    return result


def test_nan_fval_reads_back_and_sorts_last() -> None:
    with temp_record() as root:
        node = work(root, 0) / "multistart"
        write_optimize_result(_two_starts(), node)
        stored = node.get()
        back = read_optimize_result(node)
    assert back is not None, (
        "read_optimize_result returned None for a record with one NaN fval — "
        "the resume would re-run the multistart"
    )
    starts = back.optimize_result.list
    assert len(starts) == 2, len(starts)
    assert starts[0].id == "1" and starts[0].fval == 3.5, "the finite start sorts first"
    nan = starts[1]
    assert math.isnan(nan.fval) and math.isnan(nan.fval0), (nan.fval, nan.fval0)
    assert nan.time is None and nan.grad is None and nan.hess is None
    assert stored["fval_present"] == [True, True] and stored["time_present"] == [
        False,
        True,
    ], "None and NaN are told apart by the flag, not by the value"
    print("  nan fval      2 starts read back, NaN kept as NaN, finite start first")


def test_record_without_present_flags_still_reads() -> None:
    """A legacy record without `fval_present`: NaN is NaN, not None."""
    data = result_to_record(_two_starts())
    for f in ("fval", "fval0", "time"):
        data.pop(f + "_present")
    back = result_from_record(data)
    assert [s.id for s in back.optimize_result.list] == ["1", "0"]
    assert math.isnan(back.optimize_result.list[1].fval)
    print("  legacy record without the flags a NaN fval still reads and sorts")


def test_per_start_arrays_round_trip() -> None:
    with temp_record() as root:
        node = work(root, 0) / "multistart"
        write_optimize_result(_two_starts(), node)
        stored = node.get()
        good = read_optimize_result(node).optimize_result.list[0]
    assert {"hess", "res", "sres", "free_indices", "inner_parameters"} <= set(
        stored["fields"]
    )
    assert good.hess.shape == (2, 2) and np.allclose(good.hess, HESS), good.hess
    assert np.allclose(good.res, [0.1, -0.2, 0.3]), good.res
    assert good.sres.shape == (3, 2) and np.allclose(good.sres, SRES), good.sres
    assert list(good.free_indices) == [0, 1], good.free_indices
    assert good.free_indices.dtype.kind == "i", "indices come back as ints"
    assert np.allclose(good.inner_parameters, [7.0]), good.inner_parameters
    assert good.time == 1.25 and good.exitflag == 0 and good.n_fval == 40
    assert np.allclose(good.grad, [1e-3, -2e-3]) and np.allclose(good.x0, [0, 0])
    print("  fields        hess (2×2), res, sres (3×2), free_indices, inner_parameters")


if __name__ == "__main__":
    for fn in (
        test_nan_fval_reads_back_and_sorts_last,
        test_record_without_present_flags_still_reads,
        test_per_start_arrays_round_trip,
    ):
        print(fn.__name__)
        fn()
    print("OPTIMIZE RESULT OK — the multistart reads back as pyPESTO wrote it")
