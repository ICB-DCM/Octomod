"""A multistart's starts run where they pay, and every start is timed for its use.

  1. `make_probe_engine` follows `estimation.engine` (`singlecore` serial,
     `auto` adaptive at `parallel_min_start_s`, `multiprocess` parallel, and
     parallel up front when an earlier probe measured a slow start);
     `estimation.n_procs` takes an integer or null/`auto`, anything else is
     refused by name; a pool of one is no pool (`make_engine`);
  2. adaptive: starts that finish under the CPU floor never start a pool; a
     start that fails at once does not decide — the next one does; a start
     still running at the floor dispatches the rest, results in task order;
  3. every start is timed: `start_s` is its wall when it ran alone and its
     CPU when others ran beside it; the summary carries the multistart's wall,
     CPU, serial-equivalent work and `speedup`, and resets between runs;
  4. each start is seeded by its index, so a start draws the same numbers
     serially, dispatched and adaptively;
  5. a pool that breaks keeps what it returned and runs the rest here, saying so;
  6. AMICI's messages from the workers reach the parent's `Capture` with the
     same counts AND the same examples as a serial run, and an example is
     compared as it is kept (truncated);
  7. on a real AMICI problem, dispatched starts begin at the serial run's
     start points and reach its optima;
  8. the budget card's lines name how the probe ran — one at a time,
     dispatched with its speedup, or a saved probe from before engines
     recorded, read from `estimation.engine`.

    uv run python tests/probe_engine_unit.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402
from _start_fakes import Start  # noqa: E402

from octomod.workflow_modules.cost_probe import solver_messages as sm  # noqa: E402
from octomod.workflow_modules.estimation.problem import (  # noqa: E402
    make_engine,
    make_probe_engine,
    resolve_n_procs,
    run_multistart,
)
from octomod.workflow_modules.estimation.start_engine import (  # noqa: E402
    StartEngine,
    start_seed,
)


class Spec:
    def __init__(self, **values):
        self.values = {f"estimation.{k}": v for k, v in values.items()}

    def get(self, key, default=None):
        return self.values.get(key, default)


def test_engine_choice() -> None:
    import pypesto.engine

    serial = make_probe_engine(Spec(engine="singlecore"), 1)
    auto = make_probe_engine(Spec(parallel_min_start_s=3.0, n_procs=4), 1)
    multi = make_probe_engine(Spec(engine="multiprocess", n_procs=4), 1)
    known = make_probe_engine(Spec(n_procs=4), 1, known_start_s=5.0)
    check(
        "the probe engine follows estimation.engine",
        (serial.mode, auto.mode, multi.mode, known.mode)
        == ("serial", "adaptive", "parallel", "parallel")
        and auto.min_start_cpu_s == 3.0
        and auto.n_procs == 4
        and "forward probe measured 5.00s" in known.decided,
        f"{serial.mode} {auto.mode} {multi.mode} {known.mode}",
    )
    cpu = max(1, (os.cpu_count() or 2) - 1)
    good = [resolve_n_procs(Spec(n_procs=v)) for v in (None, "auto", 3, "3")]
    refused = []
    for bad in ("many", 0, -2, True):
        try:
            resolve_n_procs(Spec(n_procs=bad))
        except ValueError as e:
            refused.append("estimation.n_procs" in str(e))
    check(
        "estimation.n_procs: an integer, or null/auto; anything else refused by name",
        good == [cpu, cpu, 3, 3] and refused == [True] * 4,
        f"{good} {refused}",
    )
    try:
        make_probe_engine(Spec(engine="threads"), 1)
        unknown = False
    except ValueError:
        unknown = True
    check("an unknown engine is refused", unknown)
    one = make_engine(Spec(engine="multiprocess", n_procs=1))
    check(
        "a pool of one process is no pool",
        isinstance(one, pypesto.engine.SingleCoreEngine),
        type(one).__name__,
    )


def test_adaptive() -> None:
    me = os.getpid()
    fast = StartEngine("adaptive", 3, seed=1, min_start_cpu_s=0.3)
    out = fast.execute([Start(i, cpu_s=0.01) for i in range(4)])
    s = fast.summary()
    check(
        "starts under the CPU floor never start a pool",
        [r.id for r in out] == ["0", "1", "2", "3"]
        and all(r.pid == me for r in out)
        and s["kind"] == "serial"
        and s["n_dispatched"] == 0
        and "every start finished under 0.3s" in s["decided"],
        str({k: s[k] for k in ("kind", "n_here", "decided")}),
    )

    tasks = [Start(0, fail=True)] + [Start(i, cpu_s=0.8) for i in range(1, 5)]
    slow = StartEngine("adaptive", 3, seed=1, min_start_cpu_s=0.3)
    out = slow.execute(tasks)
    s = slow.summary()
    where = [st["where"] for st in s["starts"]]
    check(
        "a start that fails at once does not decide; one still running at the "
        "floor dispatches the rest, results in task order",
        [r.id for r in out] == ["0", "1", "2", "3", "4"]
        and where == ["here", "here", "worker", "worker", "worker"]
        and out[0].pid == me
        and out[1].pid == me
        and all(r.pid != me for r in out[2:])
        and s["n_workers"] == 3
        and "start 1 had used 0.3s of CPU" in s["decided"],
        f"{where} {s['decided']}",
    )
    st = s["starts"]
    check(
        "each start is timed for its use: alone -> wall, beside others -> CPU",
        st[0]["alone"]
        and st[0]["start_s"] == st[0]["wall_s"]
        and not st[1]["alone"]
        and st[1]["start_s"] == st[1]["cpu_s"]
        and all(x["start_s"] == x["cpu_s"] for x in st[2:])
        and all(0.7 < x["cpu_s"] < 2.0 for x in st[1:])
        and not st[0]["finite"]
        and all(x["finite"] for x in st[1:]),
        str([(x["alone"], x["wall_s"], x["cpu_s"]) for x in st]),
    )
    check(
        "the summary says whether dispatching paid: wall, CPU, "
        "serial-equivalent work, speedup",
        # the engine rounds its ratio of unrounded times (≤ 0.005 off), the
        # test divides times rounded to 3 decimals (< 0.001 more here)
        abs(s["speedup"] - s["serial_equivalent_s"] / s["wall_s"]) <= 1e-2
        and abs(s["serial_equivalent_s"] - sum(x["start_s"] for x in st)) < 1e-2
        and s["cpu_s"] >= 3.0,
        str({k: s[k] for k in ("wall_s", "cpu_s", "serial_equivalent_s", "speedup")}),
    )
    slow.execute([Start(i, cpu_s=0.01) for i in range(3)])
    s = slow.summary()
    check(
        "a second run of the same engine reports only itself",
        s["kind"] == "serial" and s["n_dispatched"] == 0 and s["n_starts"] == 3,
        str({k: s[k] for k in ("kind", "n_dispatched", "n_starts")}),
    )


def test_parallel_single_and_seeds() -> None:
    me = os.getpid()
    every = StartEngine("parallel", 2, seed=7)
    par = every.execute([Start(i) for i in range(4)])
    check(
        "parallel dispatches every start, however fast",
        all(r.pid != me for r in par)
        and every.summary()["n_dispatched"] == 4
        and every.summary()["n_workers"] == 2,
        str(every.summary()["decided"]),
    )
    one = StartEngine("parallel", 1, seed=7)
    ser = one.execute([Start(i) for i in range(4)])
    check(
        "a single-worker engine runs everything here",
        all(r.pid == me for r in ser) and one.summary()["n_dispatched"] == 0,
        one.summary()["decided"],
    )
    ada = StartEngine("adaptive", 2, seed=7, min_start_cpu_s=0.2)
    mixed = ada.execute([Start(i, cpu_s=0.4) for i in range(4)])
    want = [_draw(start_seed(7, i)) for i in range(4)]
    check(
        "each start is seeded by its index: the same draws serially, "
        "dispatched and adaptively",
        [r.draw for r in ser] == [r.draw for r in par] == [r.draw for r in mixed]
        and [r.draw for r in ser] == want
        and ada.summary()["n_dispatched"] == 3,
        f"{[r.draw for r in ser]} {[r.draw for r in par]} {[r.draw for r in mixed]}",
    )


def test_macos_start_method() -> None:
    """macOS spawns every worker; the stand-ins' results must come back there."""
    from octomod.workflow_modules.estimation import start_engine as se

    saved = se.sys.platform
    se.sys.platform = "darwin"
    try:
        ctx = se._context(start_running=False)
        eng = StartEngine("parallel", 2, seed=7)
        out = eng.execute([Start(i) for i in range(3)])
    finally:
        se.sys.platform = saved
    check(
        "with macOS's start method (spawn), dispatched results come back",
        ctx.get_start_method() == "spawn"
        and [r.id for r in out] == ["0", "1", "2"]
        and all(r.pid != os.getpid() for r in out),
        ctx.get_start_method(),
    )


def _draw(seed: int) -> float:
    np.random.seed(seed)
    return float(np.random.random())


def test_broken_pool() -> None:
    me = os.getpid()
    eng = StartEngine("parallel", 2, seed=3)
    out = eng.execute([Start(i, die_in_worker=me) for i in range(3)])
    s = eng.summary()
    check(
        "a pool that breaks runs the starts it did not return here, and says so",
        [r.id for r in out] == ["0", "1", "2"]
        and all(r.pid == me for r in out)
        and s["fallback"]
        and "BrokenProcessPool" in s["fallback"]
        and s["n_here"] == 3,
        str(s["fallback"]),
    )


def test_examples() -> None:
    long_a = "Steady state computation failed. " + "x" * 200 + " tail A"
    long_b = "Steady state computation failed. " + "x" * 200 + " tail B"
    t = sm.Tally()
    for text in (long_a, long_b, "equilibration failed at t=3"):
        t.add(text)
    check(
        "an example is compared as it is kept: two long messages that differ "
        "past the cut are one example",
        t.examples["equilibration"]
        == [long_a[: sm.EXAMPLE_CHARS], "equilibration failed at t=3"],
        str(t.examples),
    )


def _proportional_noise_problem(tmp: Path):
    from solver_messages_unit import _proportional_noise_problem as build

    return build(tmp)


def test_on_amici(tmp: Path) -> None:
    problem, _ = _proportional_noise_problem(tmp)
    spec = Spec(optimizer="fides", engine="serial")
    with sm.Capture() as serial_cap:
        serial = run_multistart(problem, 3, 0, spec)
    with sm.Capture() as par_cap:
        engine = StartEngine("parallel", 2, capture=par_cap)
        parallel = run_multistart(problem, 3, 0, spec, engine=engine)

    def x0s(result):
        return sorted(tuple(np.round(o.x0, 10)) for o in result.optimize_result.list)

    check(
        "dispatched starts begin at the serial run's start points",
        engine.summary()["n_dispatched"] == 3 and x0s(serial) == x0s(parallel),
        str(engine.summary()["decided"]),
    )
    check(
        "AMICI's messages from the workers reach the parent's Capture: the "
        "same counts and the same examples as a serial run",
        par_cap.n_messages == serial_cap.n_messages > 0
        and par_cap.tally.counts == serial_cap.tally.counts
        and par_cap.tally.examples == serial_cap.tally.examples,
        f"serial {serial_cap.tally.counts} parallel {par_cap.tally.counts}",
    )
    rec = sm.probe_record(problem, parallel.optimize_result.list, par_cap)
    check(
        "the probe record reads the dispatched messages as captured",
        (rec["table"] or [{}])[0].get("kind") == "sigma_nonpositive"
        and "over every simulation of the probe's starts" in rec["source"],
        str(rec["source"]),
    )


def test_same_optima() -> None:
    from octomod.workflow_modules.assembly import petab_io
    from octomod.workflow_modules.estimation.problem import build_problem

    src = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"
    problem, _, _ = build_problem(petab_io.from_dir(src), {}, None)
    spec = Spec(optimizer="fides", engine="serial")
    serial = run_multistart(problem, 4, 7, spec)
    engine = StartEngine("parallel", 2)
    parallel = run_multistart(problem, 4, 7, spec, engine=engine)

    def by_id(result):
        return {o.id: (tuple(o.x0), float(o.fval)) for o in result.optimize_result.list}

    s, p = by_id(serial), by_id(parallel)
    check(
        "on a problem that fits, every dispatched start reaches the serial "
        "run's optimum",
        engine.summary()["n_dispatched"] == 4
        and s.keys() == p.keys()
        and all(np.isfinite(v[1]) for v in s.values())
        and all(
            np.allclose(s[k][0], p[k][0]) and np.isclose(s[k][1], p[k][1], rtol=1e-6)
            for k in s
        ),
        f"{sorted(v[1] for v in s.values())} vs {sorted(v[1] for v in p.values())}",
    )


def test_card_lines() -> None:
    from octomod.workflow_modules.cost_probe import engine as cp

    ser = StartEngine("serial")
    ser.execute([Start(i) for i in range(3)])
    lines = cp._probe_timing_lines(ser.summary(), 0.5, 3)
    check(
        "a serial probe reads 'run one at a time'",
        len(lines) == 1 and "run one at a time" in lines[0],
        str(lines),
    )
    par = StartEngine("adaptive", 2, min_start_cpu_s=0.2)
    par.execute([Start(i, cpu_s=0.4) for i in range(4)])
    lines = cp._probe_timing_lines(par.summary(), 0.4, 4)
    check(
        "a dispatched probe says where its starts ran, what the median means, "
        "and how much faster it ran",
        "one at a time" not in lines[0]
        and "1 here, 3 dispatched to 2 workers" in lines[0]
        and "its CPU when others ran beside it" in lines[0]
        and ("x faster dispatched" in lines[1] or "x SLOWER dispatched" in lines[1])
        and "start 0 had used 0.2s of CPU" in lines[1],
        str(lines),
    )

    class Ctx:
        spec = Spec(engine="multiprocess", n_procs=4)

    legacy = cp._saved_probe_engine(Ctx(), {"probe_wall_s": 3.0}, 5)
    lines = cp._probe_timing_lines(legacy, 1.2, 5)
    check(
        "a probe saved before engines recorded is read from estimation.engine",
        legacy["kind"] == "parallel"
        and legacy["n_workers"] == 4
        and "saved before per-start CPU was recorded" in lines[0],
        str(lines),
    )


def main() -> int:
    test_engine_choice()
    test_adaptive()
    test_parallel_single_and_seeds()
    test_macos_start_method()
    test_broken_pool()
    test_examples()
    tmp = Path(tempfile.mkdtemp())
    try:
        test_on_amici(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    test_same_optima()
    test_card_lines()
    return finish(
        "START ENGINE",
        "START ENGINE OK — a multistart's starts run where they pay, each timed "
        "for its use, seeded by index, and AMICI's messages kept",
    )


if __name__ == "__main__":
    sys.exit(main())
