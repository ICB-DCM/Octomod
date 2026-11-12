"""The profile projection is a range, measured as it runs, and remembered.

  a. step count: a walk of 0 is the optimum alone; a short walk takes a handful
     of points; a long one grows geometrically, then linearly at the maximum
     step; more points for a longer walk and for a smaller maximum step;
  b. projection: a sharp parameter (large FIM_pp) walks less on the low end
     than on the high; a flat one (FIM_pp 0, or none) walks to both bounds on
     both ends; the per-point range and the workers enter as declared; the
     record says what the low end stood on and where the per-point cost came
     from; the FIM screen carries the diagonal, agents do not see it;
  c. the batch loop, on pyPESTO itself and on a fake profiler with a fake
     clock: batches accumulate into ONE profile list and equal a single call;
     each batch is a progress row whose remainder is re-projected from the
     measured per-point cost; the round's timing file is written; on the
     automatic path the cap stops profiling after the finished batches, keeps
     them, names the rest, and the verdict card's `profiles` continues with the
     rest only; a projection whose low end only is under the cap asks the gate
     with both ends;
  d. a later round projects from the timing file an earlier round wrote;
  e. a parameter is two direction tasks, so a batch of b parameters keeps up to
     2b processes busy, and the measured per-point cost agrees with the wall
     projection on every batch size; the ratio of measured to projected points
     on the finished parameters scales the rest's projection, and is ledgered
     and timed.

    uv run python tests/profile_projection_unit.py
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod.orchestration.interaction import humangate  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.orchestration.run_context import ModuleFailure, RunContext  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.workflow_modules.estimation import estimation_settings  # noqa: E402
from octomod.workflow_modules.estimation.problem import lr_threshold  # noqa: E402
from octomod.workflow_modules.evaluation import engine as s7  # noqa: E402
from octomod.workflow_modules.evaluation import profile_projection as pp  # noqa: E402
from tests._record import record_at  # noqa: E402

THR = lr_threshold(0.05)


class _Spec:
    def __init__(self, **kv):
        self.kv = kv

    def get(self, key, default=None):
        return self.kv.get(key, default)

    def require(self, key):
        if key not in self.kv:
            raise KeyError(key)
        return self.kv[key]


# ------------------------------------------------------------ a. step count


def test_step_count() -> None:
    import pypesto.profile

    opts = pypesto.profile.ProfileOptions()
    sched = pp.schedule()
    check(
        "the schedule is the installed pyPESTO's ProfileOptions",
        sched.as_dict()
        == {
            "default_step_size": opts.default_step_size,
            "min_step_size": opts.min_step_size,
            "max_step_size": opts.max_step_size,
            "step_size_factor": opts.step_size_factor,
        },
        str(sched.as_dict()),
    )
    check(
        "no declared step sizes: pyPESTO's defaults (no options object)",
        pp.profile_options(_Spec()) is None,
    )
    declared = pp.profile_options(
        _Spec(**{"uncertainty.profile_step_sizes": {"max_step_size": 0.2}})
    )
    check(
        "a declared size is taken, the others keep pyPESTO's",
        declared is not None
        and declared.max_step_size == 0.2
        and declared.default_step_size == opts.default_step_size,
        str(dict(declared or {})),
    )
    check("a walk of 0 is no point", pp.walk_points(0.0, sched) == 0)
    check(
        "a profile with no walk is the optimum: 1 point",
        pp.profile_points(0, 0, sched) == 1,
    )
    small = pp.walk_points(0.05, sched)
    check("a short walk (0.05) takes a handful of points", 2 <= small <= 6, str(small))
    # geometric: covering exactly the first k steps takes k points
    k, covered, step = 0, 0.0, sched.default_step
    while step * sched.factor < sched.max_step:
        covered += step
        k += 1
        step *= sched.factor
    check(
        "the geometric phase: the first k steps cover their own sum in k points",
        pp.walk_points(covered, sched) == k,
        f"k={k}, covered={covered:.4f}",
    )
    d2, d3 = pp.walk_points(2.0, sched), pp.walk_points(3.0, sched)
    check(
        "the linear phase: one more unit of walk is 1/max_step more points",
        d3 - d2 == round(1.0 / sched.max_step),
        f"{d2} -> {d3}",
    )
    grid = np.linspace(0, 6, 241)
    counts = [pp.walk_points(float(d), sched) for d in grid]
    check(
        "monotone in the distance",
        all(b >= a for a, b in zip(counts, counts[1:], strict=False)),
    )
    finer = pp.Schedule(
        sched.default_step, sched.min_step, sched.max_step / 2, sched.factor
    )
    check(
        "monotone in 1/max_step: a smaller maximum step takes more points",
        all(
            pp.walk_points(float(d), finer) >= pp.walk_points(float(d), sched)
            for d in grid
        )
        and pp.walk_points(3.0, finer) > pp.walk_points(3.0, sched),
        f"{pp.walk_points(3.0, sched)} vs {pp.walk_points(3.0, finer)} at 3.0",
    )


# ------------------------------------------------------------ b. projection


def test_projection() -> None:
    sched = pp.schedule()
    check(
        "the threshold is in -log(L) units: chi2(0.95, 1) / 2",
        abs(THR - 1.920729) < 1e-4,
        f"{THR:.6f}",
    )
    sharp = pp.Box("sharp", 0.0, -3.0, 3.0, fim_pp=1.0e4)
    flat = pp.Box("flat", 1.0, -3.0, 3.0, fim_pp=0.0)
    unknown = pp.Box("unknown", 0.0, -2.0, 2.0, fim_pp=None)
    edge = pp.Box("edge", 2.99, -3.0, 3.0, fim_pp=1.0)
    rows = {r["name"]: r for r in pp.plan([sharp, flat, unknown, edge], sched, THR)}
    half = math.sqrt(2 * THR / 1.0e4)
    check(
        "sharp: the low walk is the quadratic half-width, the high the bounds",
        rows["sharp"]["walk_low"] == [round(half, 6)] * 2
        and rows["sharp"]["walk_high"] == [3.0, 3.0]
        and rows["sharp"]["points_low"] < rows["sharp"]["points_high"]
        and rows["sharp"]["basis"] == "FIM at the MLE",
        str(rows["sharp"]),
    )
    check(
        "flat (FIM_pp 0): low == high == the walk to both bounds",
        rows["flat"]["walk_low"] == rows["flat"]["walk_high"] == [4.0, 2.0]
        and rows["flat"]["points_low"]
        == rows["flat"]["points_high"]
        == pp.profile_points(4.0, 2.0, sched)
        and rows["flat"]["basis"] == "bounds only",
        str(rows["flat"]),
    )
    check(
        "no FIM for a parameter: its low walk is its high walk",
        rows["unknown"]["walk_low"] == rows["unknown"]["walk_high"]
        and rows["unknown"]["basis"] == "bounds only",
    )
    check(
        "the low walk is capped at the bound",
        rows["edge"]["walk_low"][1] == 0.01 and rows["edge"]["walk_low"][0] > 1.0,
        str(rows["edge"]["walk_low"]),
    )
    spec = _Spec(**{"gates.profiles_auto.point_cost_range": [1.0, 2.0]})
    cost = pp.point_cost(spec, 3.06)
    check(
        "before any profiling: the declared range times the probe's median start",
        cost["low_s"] == 3.06 and cost["high_s"] == 6.12 and cost["source"] == pp.PROBE,
        str(cost),
    )
    two = [rows["sharp"], rows["flat"]]
    rec = pp.project(two, cost, pp.workers(9, len(two)))
    lo_pts = rows["sharp"]["points_low"] + rows["flat"]["points_low"]
    hi_pts = rows["sharp"]["points_high"] + rows["flat"]["points_high"]
    check(
        "workers: the engine's processes, or two per parameter (one walk per "
        "direction), whichever is fewer",
        pp.workers(9, 2) == 4
        and pp.workers(3, 2) == 3
        and pp.workers(9, 32) == 9
        and pp.workers(1, 5) == 1
        and pp.workers(4, 0) == 1,
        str([pp.workers(9, 2), pp.workers(3, 2), pp.workers(9, 32)]),
    )
    check(
        "a batch holds as many parameters as the engine has processes",
        pp.batch_size(4, 6) == 4
        and pp.batch_size(8, 3) == 3
        and pp.batch_size(0, 5) == 1,
    )
    check(
        "seconds = points x per-point / workers, for the low and the high end",
        rec["points_low"] == lo_pts
        and rec["points_high"] == hi_pts
        and rec["workers"] == 4
        and rec["low_s"] == round(lo_pts * 3.06 / 4, 1)
        and rec["high_s"] == round(hi_pts * 6.12 / 4, 1)
        and rec["low_s"] < rec["high_s"],
        json.dumps(pp.summary(rec)),
    )
    check(
        "the record carries its basis and its per-point source",
        rec["basis"] == "FIM at the MLE for 1 of 2 parameters, bounds only for the rest"
        and rec["per_point_source"] == pp.PROBE
        and set(rec["parameters"]) == {"sharp", "flat"},
        f"{rec['basis']!r} {rec['per_point_source']!r}",
    )
    text = pp.describe(rec)
    check(
        "one sentence shows the range, the points and the per-point range",
        text.startswith("profiles projected ~")
        and f"{lo_pts:,}–{hi_pts:,} points over 2 parameters" in text
        and "3.1–6.1 s per point from the cost probe" in text
        and "on 4 processes" in text,
        text,
    )
    check(
        "no per-point cost on file: points, and no seconds",
        pp.project(two, None, 2)["low_s"] is None
        and "no seconds" in pp.describe(pp.project(two, None, 2)),
    )
    same = pp.point_cost(spec, 3.06, {"per_point_s": 5.9, "round": 0}, same_model=True)
    check(
        "a measurement on this model replaces the range",
        same["low_s"] == same["high_s"] == 5.9 and same["source"] == pp.MEASURED,
        str(same),
    )
    carried = pp.point_cost(
        _Spec(**{"gates.profiles_auto.carried_point_band": 0.25}),
        2.0,
        {"per_point_s": 5.9, "per_point_starts": 1.9, "round": 0},
    )
    check(
        "another model's measurement is carried as starts per point, within the band",
        abs(carried["low_s"] - 1.9 * 2.0 * 0.75) < 1e-9
        and abs(carried["high_s"] - 1.9 * 2.0 * 1.25) < 1e-9
        and "round 0" in carried["detail"],
        str(carried),
    )
    check(
        "durations read in their unit",
        pp.span(40, 75) == "~40–75 s"
        and pp.span(180, 720) == "~3–12 min"
        and pp.duration(246) == "4.1 min"
        and pp.span(600, 600) == "~10 min",
        f"{pp.span(40, 75)} {pp.span(180, 720)} {pp.duration(246)}",
    )


def test_fim_diagonal() -> None:
    import pypesto

    from octomod.agents import payload
    from octomod.workflow_modules.evaluation import identifiability

    a = np.array([[2.0, 0.0, 1.0], [0.0, 3.0, 0.0], [1.0, 0.0, 0.5], [0.0, 1.0, 0.0]])
    b = np.array([1.0, 2.0, 0.0, 1.0])
    obj = pypesto.Objective(res=lambda x: a @ x - b, sres=lambda x: a)
    prob = pypesto.Problem(obj, lb=[-5.0] * 3, ub=[5.0] * 3, x_names=["p", "q", "r"])
    ident = identifiability.fim_at_mle(prob, np.zeros(3), ["p", "q", "r"])
    want = np.diag(a.T @ a)
    got = [(ident.get("diagonal_scaled") or {}).get(n) for n in ("p", "q", "r")]
    check(
        "the FIM screen carries the diagonal of J^T J, in the problem's scaled space",
        ident.get("available")
        and None not in got
        and np.allclose(np.asarray(got, dtype=float), want),
        f"{got} vs {want.tolist()}",
    )
    view = payload.core_for_agents(
        {
            "identifiability": ident,
            "profiles_projection": {"available": True, "parameters": {"p": {}}},
        }
    )
    check(
        "agents read the spectrum and the totals, not the diagonal or per-parameter rows",
        "diagonal_scaled" not in view["identifiability"]
        and "parameters" not in view["profiles_projection"],
    )


# --------------------------------------------------------- c. the batch loop

NAMES = ["k1", "k2", "k3", "k4", "k5", "k6"]
X_HAT = np.array([0.0, 0.5, -0.5, 1.0, -1.0, 2.0])
FIM = {"k1": 1e4, "k2": 1e3, "k3": 0.0, "k4": 50.0, "k5": 5.0, "k6": 1e5}
# points each fake profile takes, as `profile_points` counts them
FAKE_POINTS = {"k1": 9, "k2": 15, "k3": 61, "k4": 25, "k5": 40, "k6": 7}


def _toy_problem():
    import pypesto

    obj = pypesto.Objective(
        fun=lambda x: float(0.5 * np.sum((x - X_HAT) ** 2 * 10.0)),
        grad=lambda x: (x - X_HAT) * 10.0,
    )
    return pypesto.Problem(obj, lb=[-3.0] * 6, ub=[3.0] * 6, x_names=NAMES)


def _optimum_result():
    import pypesto
    import pypesto.result as res

    result = pypesto.Result()
    result.optimize_result = res.OptimizeResult()
    result.optimize_result.append(
        res.OptimizerResult(
            id="0", x=X_HAT.copy(), fval=0.0, grad=np.zeros(6), exitflag=0, time=0.1
        )
    )
    return result


def _new_run() -> Node:
    """A throwaway run record."""
    root = record_at(Path(tempfile.mkdtemp(prefix="octomod_test_")) / "run.h5")
    root.store.create()
    return root


def _stage(run: Node, round_idx: int = 0, median: float = 1.0) -> Node:
    """Round `round_idx`'s fitted problem: its parameter table and the probe's
    `cost` record (`median_start_s`). Returns the round's group."""
    import pandas as pd

    rd = tree.round_node(run, round_idx)
    wk = tree.work_node(rd, None)
    (wk / "petab/parameters").put_table(
        pd.DataFrame(
            [
                {
                    "parameterId": n,
                    "parameterScale": "log10",
                    "lowerBound": 0.001,
                    "upperBound": 1000,
                    "nominalValue": 1,
                    "estimate": 1,
                }
                for n in NAMES
            ]
        )
    )
    (wk / "cost").put({"median_start_s": median})
    return rd


def _timing_node(rd: Node) -> Node:
    """The round's profiling timing record (`WK/profiles_timing`)."""
    return tree.work_node(rd, None) / pp.TIMING_KEY


def _summary() -> dict:
    return {
        "x_names": NAMES,
        "best_x_unscaled": {n: float(10**x) for n, x in zip(NAMES, X_HAT, strict=True)},
        "n_starts": 1,
        "seed": 0,
    }


def _ident() -> dict:
    return {"available": True, "diagonal_scaled": dict(FIM)}


def _ctx(run: Node, round_idx: int = 0, n_procs: int = 2, **spec) -> RunContext:
    (run / "intent").put({})  # an empty intent
    kv = {
        "estimation.engine": "multiprocess",
        "estimation.n_procs": n_procs,
        "uncertainty.profile_next_guess": "adaptive_step_order_1",
        "gates.profiles_auto.point_cost_range": [1.0, 2.0],
        "gates.profiles_auto.carried_point_band": 0.25,
        "gates.profiles_auto.max_projected_s": 600,
        "gates.profiles.on_request": True,
        "estimation.optimizer": "scipy",
    }
    kv.update(spec)
    ctx = RunContext(
        root=run,
        testcase_dir=run.store.path.parent / "input",
        spec=_Spec(**kv),
        ledger=Ledger(run.store),
        backend="stub",
        auto=False,
        round_idx=round_idx,
    )
    ctx.cache[ctx.candidate_key("pypesto_result")] = _optimum_result()
    return ctx


class _FakeProfiler:
    """`pypesto.profile.parameter_profile` without optimising, on a fake clock.

    It keeps pyPESTO's list semantics — no `profile_list` appends a new list,
    a named one is filled at the called indices only — and each call advances
    the clock by its points times `per_point_s`, over the processes its tasks
    occupy: pyPESTO's two per parameter (one walk per direction), at most
    `n_procs`. Written out here rather than read from `pp.workers`, so the
    fixture holds the engine to pyPESTO's task model, not to its own.
    """

    def __init__(
        self,
        clock: list[float],
        per_point_s: float,
        n_procs: int,
        points: dict | None = None,
    ):
        self.clock, self.per_point_s, self.n_procs = clock, per_point_s, n_procs
        self.points = dict(points or FAKE_POINTS)
        self.calls: list[tuple[list[int], int | None]] = []

    def __call__(self, *, problem, result, profile_index, profile_list=None, **_kw):
        from pypesto.result import ProfilerResult

        self.calls.append((list(profile_index), profile_list))
        if profile_list is None:
            result.profile_result.append_empty_profile_list()
            result.profile_result.list[-1].extend([None] * problem.dim_full)
        target = result.profile_result.list[
            -1 if profile_list is None else profile_list
        ]
        points = 0
        for i in profile_index:
            n = self.points[problem.x_names[i]]
            walked = n - 1
            down, up = walked // 2, walked - walked // 2
            xs = np.concatenate(
                [
                    np.linspace(X_HAT[i] - 0.8, X_HAT[i], down + 1),
                    np.linspace(X_HAT[i], X_HAT[i] + 0.8, up + 1),
                ]
            )
            x_path = np.tile(X_HAT[:, None], (1, len(xs)))
            x_path[i] = xs
            fval = 5.0 * (xs - X_HAT[i]) ** 2
            target[i] = ProfilerResult(
                x_path=x_path, fval_path=fval, ratio_path=np.exp(-fval)
            )
            points += pp.points_in(target[i])
        busy = min(self.n_procs, 2 * len(profile_index))
        self.clock[0] += points * self.per_point_s / busy
        return result


class _Patched:
    """The toy problem for the module, the fake profiler and the fake clock."""

    def __init__(self, fake):
        self.fake = fake

    def __enter__(self):
        import pypesto.profile

        self.saved = (
            estimation_settings.build,
            pypesto.profile.parameter_profile,
            pp.now,
        )
        estimation_settings.build = lambda ctx: (_toy_problem(), None, 0.0)
        if self.fake is not None:
            pypesto.profile.parameter_profile = self.fake
            pp.now = lambda: self.fake.clock[0]
        return self

    def __exit__(self, *exc):
        import pypesto.profile

        (
            estimation_settings.build,
            pypesto.profile.parameter_profile,
            pp.now,
        ) = self.saved
        return False


def _read(node: Node) -> dict:
    """A record, or {} when it was not written."""
    return node.get(None) or {}


def _profiles_section(rd: Node) -> str:
    """The round report's profile section, rendered from what is in the record."""
    from octomod.reporting import round_report

    return round_report._s8_profiles(round_report.Round(rd))


def _rows(ledger: Ledger, event: str) -> list[dict]:
    return [r for r in ledger.entries() if r.get("event") == event]


def test_batches_accumulate_on_pypesto_itself() -> None:
    """Two calls into one list give the profiles one call gives (real pyPESTO)."""
    import pypesto.engine
    import pypesto.optimize
    import pypesto.profile

    def run(batches):
        result, problem = _optimum_result(), _toy_problem()
        idx = None
        for batch in batches:
            pypesto.profile.parameter_profile(
                problem=problem,
                result=result,
                optimizer=pypesto.optimize.ScipyOptimizer(method="L-BFGS-B"),
                engine=pypesto.engine.SingleCoreEngine(),
                profile_index=batch,
                profile_list=idx,
                progress_bar=False,
            )
            if idx is None:
                idx = len(result.profile_result.list) - 1
        return result.profile_result.list

    one = run([[0, 1, 2]])
    split = run([[0, 1], [2]])
    same = len(split) == 1 and all(
        np.allclose(one[0][i].fval_path, split[0][i].fval_path)
        and np.allclose(one[0][i].x_path, split[0][i].x_path)
        for i in (0, 1, 2)
    )
    check(
        "pyPESTO: a second call with profile_list=0 fills the same list, and "
        "equals one call",
        same and all(split[0][i] is None for i in (3, 4, 5)),
        f"{len(split)} list(s)",
    )


def test_the_module_on_pypesto_itself() -> None:
    """`_profiles` in batches of one (serial engine) gives one call's CIs."""
    import pypesto.engine
    import pypesto.optimize
    import pypesto.profile

    run = _new_run()
    _stage(run)
    ctx = _ctx(run, **{"estimation.engine": "serial"})
    with _Patched(None):
        out = s7._profiles(ctx, _summary(), fim=_ident())
    progress = _rows(ctx.ledger, "profiles_progress")
    direct = _optimum_result()
    pypesto.profile.parameter_profile(
        problem=_toy_problem(),
        result=direct,
        optimizer=pypesto.optimize.ScipyOptimizer(method="L-BFGS-B"),
        engine=pypesto.engine.SingleCoreEngine(),
        progress_bar=False,
    )
    ok = True
    for i, n in enumerate(NAMES):
        fv = np.asarray(direct.profile_result.list[0][i].fval_path)
        xs = np.asarray(direct.profile_result.list[0][i].x_path[i])
        inside = fv <= fv.min() + THR
        want = [float(10 ** xs[inside].min()), float(10 ** xs[inside].max())]
        ok &= np.allclose(out[n]["ci95"], want)
    check(
        "the module's batches (one parameter each, serial) give one call's CIs",
        ok and len(progress) == 6 and set(NAMES) <= set(out),
        f"{len(progress)} progress rows",
    )


def test_batch_loop_progress_and_timing() -> None:
    run = _new_run()
    rd = _stage(run)
    ctx = _ctx(run)
    ctx.request_profiles = "the final model"
    clock = [100.0]
    fake = _FakeProfiler(clock, per_point_s=5.0, n_procs=2)
    core = {"identifiability": _ident()}
    with _Patched(fake):
        s7._profiles_for(ctx, core, _summary(), "prediction", 6)
    check(
        "batches of `workers` parameters, accumulated into one list",
        fake.calls == [([0, 1], None), ([2, 3], 0), ([4, 5], 0)],
        str(fake.calls),
    )
    prof = core.get("profiles") or {}
    check(
        "every parameter's profile reaches the report",
        [k for k in prof if not k.startswith("_")] == NAMES
        and not pp.not_profiled(prof),
        str(list(prof)),
    )
    rows = _rows(ctx.ledger, "profiles_progress")
    check(
        "one progress row per batch, counting the parameters done",
        [r["parameters_done"] for r in rows] == [2, 4, 6]
        and all(r["parameters_total"] == 6 for r in rows),
        str([r.get("parameters_done") for r in rows]),
    )
    check(
        "the per-point cost is measured, not the probe's range",
        all(abs(r["per_point_s"] - 5.0) < 1e-9 for r in rows),
        str([r.get("per_point_s") for r in rows]),
    )
    sched = pp.schedule()
    plan = {
        r["name"]: r
        for r in pp.plan(
            [
                pp.Box(n, float(x), -3.0, 3.0, FIM[n])
                for n, x in zip(NAMES, X_HAT, strict=True)
            ],
            sched,
            THR,
        )
    }
    rest = ["k3", "k4", "k5", "k6"]
    # the midpoint of the projection's low and high end, written out
    ratio = (FAKE_POINTS["k1"] + FAKE_POINTS["k2"]) / sum(
        0.5 * (plan[n]["points_low"] + plan[n]["points_high"]) for n in ("k1", "k2")
    )
    scaled = pp.calibrated([plan[n] for n in rest], ratio)
    want_lo = round(sum(r["points_low"] for r in scaled) * 5.0 / 2, 1)
    want_hi = round(sum(r["points_high"] for r in scaled) * 5.0 / 2, 1)
    check(
        "the remainder is re-projected from the measured per-point cost and "
        "the measured points ratio",
        rows[0]["remaining_low_s"] == want_lo
        and rows[0]["remaining_high_s"] == want_hi
        and abs(rows[0]["points_ratio"] - round(ratio, 4)) < 1e-12,
        f"{rows[0].get('remaining_low_s')}/{rows[0].get('remaining_high_s')} vs "
        f"{want_lo}/{want_hi}, ratio {rows[0].get('points_ratio')} vs {ratio:.4f}",
    )
    first = rows[0]["note"]
    check(
        "the progress line says done, elapsed, measured and remaining",
        first.startswith("profiles: 2/6 parameters done, ")
        and "elapsed; 5 s per point measured; remaining ~" in first,
        first,
    )
    timing = _read(_timing_node(rd))
    points = sum(FAKE_POINTS.values())
    check(
        "the round's timing file: per-point cost, points, wall, workers, parameters",
        abs((timing.get("per_point_s") or 0) - 5.0) < 1e-9
        and timing.get("points") == points
        and timing.get("parameters_done") == 6
        and timing.get("workers") == 2
        and abs(timing.get("wall_s", 0) - points * 5.0 / 2) < 1e-6
        and timing.get("per_point_starts") == 5.0,
        json.dumps({k: v for k, v in timing.items() if k != "batches"}),
    )
    started = [
        r
        for r in ctx.ledger.entries()
        if "profiles run at the human's request" in str(r.get("note"))
    ]
    check(
        "the projection before the run shows the probe's range",
        started
        and "s per point from the cost probe" in started[0]["note"]
        and "–" in started[0]["note"],
        started[0]["note"] if started else "no row",
    )

    # one batch is the single call it replaces
    run1 = _new_run()
    _stage(run1)
    ctx1 = _ctx(run1, n_procs=8)
    ctx1.request_profiles = "all at once"
    fake1 = _FakeProfiler([0.0], per_point_s=5.0, n_procs=8)
    core1 = {"identifiability": _ident()}
    with _Patched(fake1):
        s7._profiles_for(ctx1, core1, _summary(), "prediction", 6)
    check(
        "workers >= parameters: one call over every free index, a new list",
        fake1.calls == [([0, 1, 2, 3, 4, 5], None)],
        str(fake1.calls),
    )


def _cap_run(per_point_s: float):
    run = _new_run()
    rd = _stage(run)
    ctx = _ctx(run)
    proj = s7._profile_projection(ctx, _summary(), _ident())
    cap = float(proj["high_s"]) + 1.0
    ctx.spec.kv["gates.profiles_auto.max_projected_s"] = cap
    fake = _FakeProfiler([0.0], per_point_s=per_point_s, n_procs=2)
    return run, rd, ctx, proj, cap, fake


def test_cap_stops_the_automatic_path() -> None:
    # the probe says a point costs 1-2 s; it costs 20
    run, rd, ctx, proj, cap, fake = _cap_run(per_point_s=20.0)
    core = {"identifiability": _ident()}
    with _Patched(fake):
        s7._profiles_for(ctx, core, _summary(), "parameter_values", 6)
    started = [r for r in ctx.ledger.entries() if "auto-profiles" in str(r.get("note"))]
    check(
        "profiles start unasked when the HIGH projection is under the cap",
        bool(started) and proj["high_s"] <= cap,
        f"high {proj['high_s']} cap {cap}",
    )
    prof = core.get("profiles") or {}
    left = pp.not_profiled(prof)
    check(
        "the cap stops after the finished batch: its profiles are kept",
        fake.calls == [([0, 1], None)]
        and [k for k in prof if not k.startswith("_")] == ["k1", "k2"],
        f"{fake.calls} {list(prof)}",
    )
    stop = (prof.get("_meta") or {}).get("not_profiled") or {}
    check(
        "the rest are named: not profiled, time cap",
        left == ["k3", "k4", "k5", "k6"]
        and stop.get("reason") == "time cap"
        and stop.get("cap_s") == cap
        and (stop.get("remaining") or {}).get("per_point_source") == pp.MEASURED,
        json.dumps(stop)[:300],
    )
    capped = [r for r in ctx.ledger.entries() if r.get("profiles_time_cap")]
    check(
        "the stop is ledgered with its numbers",
        len(capped) == 1
        and capped[0]["not_profiled"] == left
        and capped[0]["elapsed_s"] + capped[0]["remaining"]["low_s"] > cap,
        str(capped[0] if capped else "no row")[:300],
    )
    timing = _read(_timing_node(rd))
    check(
        "the timing file says it stopped",
        timing.get("stopped") == "time cap" and timing.get("parameters_done") == 2,
        str({k: timing.get(k) for k in ("stopped", "parameters_done")}),
    )
    lines, forms = s7._profiles_card_lines(core)
    check(
        "the verdict card asks: the stop, the names, and `profiles` to continue",
        lines
        and "stopped at the" in lines[0]
        and "not profiled: time cap — k3, k4, k5, k6" in lines[0]
        and "continues with the remaining 4" in lines[0]
        and "per point measured" in lines[0]
        and forms
        and forms[0].startswith("profiles "),
        f"{lines} {forms}",
    )
    # the report reads `RK/evaluation_core`
    (rd / "evaluation_core").put(core)
    html = _profiles_section(rd)
    check(
        "the round report names what the cap left, and how to continue",
        "not profiled: time cap — k3, k4, k5, k6" in html
        and "`profiles` at the verdict card continues" in html,
        html[-400:],
    )
    took = s7._take_profiles_request(ctx, core, "profiles")
    decision = _read(rd / s7.PROFILE_REQUEST)
    check(
        "`profiles` at the card is taken for profiles the cap stopped",
        took and decision.get("continues") == left,
        str(decision),
    )
    fake2 = _FakeProfiler(fake.clock, per_point_s=20.0, n_procs=2)
    core2 = {"identifiability": _ident()}
    with _Patched(fake2):
        s7._profiles_for(ctx, core2, _summary(), "parameter_values", 6)
    prof2 = core2.get("profiles") or {}
    cached = ctx.cache[ctx.candidate_key("pypesto_result")].profile_result.list
    check(
        "the continuation profiles the rest only, never stopped by the cap",
        [c[0] for c in fake2.calls] == [[2, 3], [4, 5]]
        and [k for k in prof2 if not k.startswith("_")] == NAMES
        and not pp.not_profiled(prof2),
        f"{fake2.calls} {list(prof2)}",
    )
    check(
        "… into a new list beside the stopped one, and read from it",
        len(cached) == 2 and [c[1] for c in fake2.calls] == [None, 1],
        f"{len(cached)} lists, calls {fake2.calls}",
    )
    cont = [
        r
        for r in ctx.ledger.entries()
        if "profiles continue at the human's request" in str(r.get("note"))
    ]
    check(
        "… on its measured projection",
        cont and "s per point measured" in cont[0]["note"],
        cont[0]["note"] if cont else "no row",
    )
    (rd / "evaluation_core").put(core2)
    html2 = _profiles_section(rd)
    check(
        "… and, once finished, what was measured beside what was projected",
        f"measured: {sum(FAKE_POINTS.values())} profile points" in html2
        and "before it ran, profiles projected ~" in html2
        and "not profiled" not in html2,
        html2[-500:],
    )
    rows = _rows(ctx.ledger, "profiles_progress")
    timing2 = _read(_timing_node(rd))
    check(
        "progress counts the kept profiles, and the timing covers both parts",
        [r["parameters_done"] for r in rows] == [2, 4, 6]
        and timing2.get("parameters_done") == 6
        and timing2.get("points") == sum(FAKE_POINTS.values())
        and timing2.get("stopped") is None,
        f"{[r.get('parameters_done') for r in rows]} {timing2.get('parameters_done')}",
    )


def test_human_requested_profiling_is_never_stopped() -> None:
    run, rd, ctx, proj, cap, fake = _cap_run(per_point_s=20.0)
    ctx.request_profiles = "I want all of them"
    core = {"identifiability": _ident()}
    with _Patched(fake):
        s7._profiles_for(ctx, core, _summary(), "parameter_values", 6)
    check(
        "a profiling the human asked for runs past the cap",
        len(fake.calls) == 3 and not pp.not_profiled(core.get("profiles")),
        str(fake.calls),
    )


def test_gate_asked_with_both_ends() -> None:
    run = _new_run()
    _stage(run)
    ctx = _ctx(run)
    proj = s7._profile_projection(ctx, _summary(), _ident())
    ctx.spec.kv["gates.profiles_auto.max_projected_s"] = (
        float(proj["low_s"]) + float(proj["high_s"])
    ) / 2
    asked: list[dict] = []
    real = humangate.ask_once

    def recorder(_ctx, _path, question, lines, **kw):
        asked.append({"question": question, "lines": lines, "module": kw.get("module")})
        return False, "no"

    humangate.ask_once = recorder
    try:
        with _Patched(_FakeProfiler([0.0], 5.0, 2)):
            try:
                s7._profiles_for(
                    ctx,
                    {"identifiability": _ident()},
                    _summary(),
                    "parameter_values",
                    6,
                )
            except ModuleFailure:
                pass
    finally:
        humangate.ask_once = real
    lines = asked[0]["lines"] if asked else []
    check(
        "only the low end under the cap: the profiling gate asks, with both ends",
        asked
        and asked[0]["module"] == "evaluation_profiling_gate"
        and lines[0].startswith("profiles projected ~")
        and "the high end is over the" in lines[1]
        and "the low end under it" in lines[1],
        str(lines[:2]),
    )


# ------------------------------------------------- d. a later round reads it


def test_later_round_reads_the_timing() -> None:
    run = _new_run()
    _stage(run, 0, median=1.0)
    ctx0 = _ctx(run)
    ctx0.request_profiles = "round 0"
    with _Patched(_FakeProfiler([0.0], per_point_s=5.0, n_procs=2)):
        s7._profiles_for(
            ctx0,
            {"identifiability": _ident()},
            _summary(),
            "prediction",
            6,
        )
    _stage(run, 1, median=2.0)
    ctx1 = _ctx(run, round_idx=1)
    cost, median = s7._per_point_cost(ctx1)
    check(
        "round 1 prices a point from round 0's measurement, in starts, within the band",
        cost is not None
        and cost["source"] == pp.MEASURED
        and median == 2.0
        and abs(cost["low_s"] - 5.0 * 2.0 * 0.75) < 1e-9
        and abs(cost["high_s"] - 5.0 * 2.0 * 1.25) < 1e-9
        and "round 0" in cost["detail"],
        str(cost),
    )
    proj = s7._profile_projection(ctx1, _summary(), _ident())
    check(
        "… and its projection says the per-point cost was measured in this run",
        proj.get("per_point_source") == pp.MEASURED
        and "s per point measured" in pp.describe(proj),
        pp.describe(proj),
    )
    # a round after the one asking is not read
    rd3 = _stage(run, 3, median=1.0)
    _timing_node(rd3).put({"per_point_s": 99.0, "round": 3})
    later = pp.latest_timing(run, 1)
    check(
        "only rounds up to the one projecting are read",
        later is not None and later.get("round") == 0,
        str(later and later.get("round")),
    )


def _plan_rows() -> dict:
    return {
        r["name"]: r
        for r in pp.plan(
            [
                pp.Box(n, float(x), -3.0, 3.0, FIM[n])
                for n, x in zip(NAMES, X_HAT, strict=True)
            ],
            pp.schedule(),
            THR,
        )
    }


def test_the_running_projection_learns() -> None:
    """Walks longer than the high estimate raise the rest's projection."""
    plan = _plan_rows()
    many = {n: 2 * plan[n]["points_high"] for n in NAMES}
    run = _new_run()
    rd = _stage(run)
    ctx = _ctx(run)
    ctx.request_profiles = "calibrate"
    fake = _FakeProfiler([0.0], per_point_s=5.0, n_procs=2, points=many)
    with _Patched(fake):
        s7._profiles_for(
            ctx,
            {"identifiability": _ident()},
            _summary(),
            "prediction",
            6,
        )
    rows = _rows(ctx.ledger, "profiles_progress")

    def ratio_of(names):
        return sum(many[n] for n in names) / sum(
            0.5 * (plan[n]["points_low"] + plan[n]["points_high"]) for n in names
        )

    want = [ratio_of(NAMES[:2]), ratio_of(NAMES[:4]), ratio_of(NAMES)]
    check(
        "each progress row carries the ratio over every parameter finished so far",
        [r.get("points_ratio") for r in rows] == [round(w, 4) for w in want],
        f"{[r.get('points_ratio') for r in rows]} vs {[round(w, 4) for w in want]}",
    )
    rest = NAMES[2:]
    plain_lo = round(sum(plan[n]["points_low"] for n in rest) * 5.0 / 2, 1)
    plain_hi = round(sum(plan[n]["points_high"] for n in rest) * 5.0 / 2, 1)
    check(
        "points above the high estimate lift the rest's projection above its "
        "uncalibrated high end",
        want[0] > 1.0
        and rows[0]["remaining_low_s"] > plain_lo
        and rows[0]["remaining_high_s"] > plain_hi,
        f"ratio {want[0]:.2f}: {rows[0].get('remaining_low_s')}–"
        f"{rows[0].get('remaining_high_s')} vs uncalibrated {plain_lo}–{plain_hi}",
    )
    check(
        "the progress line says the ratio it applied",
        f"points so far {want[0]:.2g}× the projected midpoint, applied to the rest"
        in rows[0]["note"],
        rows[0]["note"],
    )
    timing = _read(_timing_node(rd))
    check(
        "the round's timing record carries the final ratio",
        timing.get("points_ratio") == round(want[-1], 4),
        str(timing.get("points_ratio")),
    )


def test_two_tasks_per_parameter() -> None:
    """A batch smaller than the engine still measures the true per-point cost."""
    run = _new_run()
    rd = _stage(run)
    ctx = _ctx(run, n_procs=4)
    ctx.request_profiles = "two tasks each"
    fake = _FakeProfiler([0.0], per_point_s=5.0, n_procs=4)
    with _Patched(fake):
        s7._profiles_for(
            ctx,
            {"identifiability": _ident()},
            _summary(),
            "prediction",
            6,
        )
    check(
        "four processes: batches of four parameters, then the two left",
        [c[0] for c in fake.calls] == [[0, 1, 2, 3], [4, 5]],
        str(fake.calls),
    )
    rows = _rows(ctx.ledger, "profiles_progress")
    check(
        "the two-parameter batch ran on four processes, and the measured "
        "per-point cost stays the true one",
        [r.get("per_point_s") for r in rows] == [5.0, 5.0],
        str([r.get("per_point_s") for r in rows]),
    )
    timing = _read(_timing_node(rd))
    check(
        "the timing record's batches are timed on the processes they used",
        [b.get("workers") for b in timing.get("batches") or []] == [4, 4],
        str([b.get("workers") for b in timing.get("batches") or []]),
    )


def main() -> int:
    test_step_count()
    test_projection()
    test_fim_diagonal()
    test_batches_accumulate_on_pypesto_itself()
    test_the_module_on_pypesto_itself()
    test_batch_loop_progress_and_timing()
    test_cap_stops_the_automatic_path()
    test_human_requested_profiling_is_never_stopped()
    test_gate_asked_with_both_ends()
    test_later_round_reads_the_timing()
    test_the_running_projection_learns()
    test_two_tasks_per_parameter()
    return finish(
        "PROFILE PROJECTION",
        "PROFILE PROJECTION OK — a low and a high end, measured while it runs, "
        "stopped at the cap only when nobody asked, and remembered for later rounds",
    )


if __name__ == "__main__":
    sys.exit(main())
