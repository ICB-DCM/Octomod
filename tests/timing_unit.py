"""Where the wall clock went — the account in the record closes.

    uv run python tests/timing_unit.py

Three parts. The arithmetic on hand-made rows (sessions + gaps tile the run;
leaves + engine tile a session; a parent span is not counted twice; a killed
session is said to be). A stub toy run: its record carries `timing`, the
run's wall is explained to the second, every agent call is an `agent` span,
and the compute blocks the design names (compile, cost probe, multistart,
profiles) are there with the time they took. And a file-gate run that
pauses: two sessions, and the gap between them is `waiting_for_human_s`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from octomod.orchestration import timing as T  # noqa: E402
from octomod.result import completeness  # noqa: E402
from octomod.result.runstore import RunStore  # noqa: E402
from tests._record import ledger_rows, pending_gate, run_root  # noqa: E402

PY = str(config.VENV_PYTHON)
CASE = REPO / "testcase" / "toy_phos"


def _env() -> dict:
    env = os.environ.copy()
    env.setdefault(
        "OCTOMOD_SPEC_OVERLAY", str(REPO / "workflows" / "overlays" / "quick.yaml")
    )
    return env


def _cmd(run_id: str, *extra: str) -> list[str]:
    return [
        PY,
        "-m",
        "octomod",
        "run",
        "--testcase",
        str(CASE),
        "--backend",
        "stub",
        "--run-id",
        run_id,
        *extra,
    ]


# ------------------------------------------------------------ arithmetic
def _row(event: str, t: float, **kw) -> dict:
    return {"ts": "", "t": t, "round": 0, "module": "", "event": event, **kw}


def _span(cat: str, name: str, t0: float, t1: float, **kw) -> dict:
    return _row(
        "span",
        t1,
        category=cat,
        name=name,
        t0=t0,
        t1=t1,
        wall_s=round(t1 - t0, 3),
        **kw,
    )


def test_the_account_closes_on_hand_made_rows() -> None:
    rows = [
        _row("run_start", 1000.0),
        _span("module", "model", 1001.0, 1010.0, module="model"),
        _span("agent", "construction", 1002.0, 1008.0, module="model", api_s=5.0),
        _span("compute", "compile", 1008.0, 1009.5, module="model"),
        _row("gate_pending", 1010.5, cpu_s=0.0),
        # the human takes 30 s at the gate, then the answer starts a new process
        _row("run_start", 1040.5),
        _span("module", "estimation", 1041.0, 1050.0, module="estimation"),
        _span(
            "compute",
            "multistart",
            1041.5,
            1049.0,
            module="estimation",
            cpu_s=30.0,
            n_starts=10,
            n_fval=1500,
            n_procs=4,
        ),
        # a parent compute span with a child: only the child is a leaf
        _span("compute", "averaged_holdout", 1050.0, 1053.0, module="evaluation"),
        _span("compute", "holdout", 1050.5, 1052.5, module="evaluation"),
        _row("run_end", 1054.0, outcome="completed", cpu_s=33.0),
    ]
    acc = T.summarize(rows)
    # CPU and work: the multistart kept 4 cores busy, cost 3 s per start and
    # 0.02 s per objective evaluation; the session's CPU beyond its leaves
    # is the engine's
    ms = acc["compute"]["multistart"]
    assert ms["cpu_s"] == 30.0 and ms["parallelism"] == 4.0, ms
    assert ms["n_starts"] == 10 and ms["n_fval"] == 1500 and ms["n_procs"] == 4, ms
    assert ms["cpu_s_per_start"] == 3.0 and ms["cpu_s_per_fval"] == 0.02, ms
    assert acc["sessions"][1]["cpu_s"] == 33.0
    assert acc["sessions"][1]["engine_cpu_s"] == 3.0, acc["sessions"][1]
    assert acc["run_cpu_s"] == 33.0 and acc["by_category"]["engine"]["cpu_s"] == 3.0
    assert acc["by_category"]["compute"]["cpu_s"] == 30.0
    assert acc["n_sessions"] == 2, acc["n_sessions"]
    s0, s1 = acc["sessions"]
    assert s0["wall_s"] == 10.5 and s0["ended_by"] == "gate_pending", s0
    assert s1["wall_s"] == 13.5 and s1["ended_by"] == "run_end:completed", s1
    assert acc["waiting_for_human_s"] == 30.0, acc["waiting_for_human_s"]
    assert acc["run_wall_s"] == 54.0 and acc["residual_s"] == 0.0, acc
    # leaves: agent 6, compile 1.5, multistart 7.5, holdout 2 (not the parent 3)
    cats = acc["by_category"]
    assert cats["agent"]["wall_s"] == 6.0 and cats["agent"]["api_s"] == 5.0, cats
    assert cats["compute"]["wall_s"] == 11.0, cats["compute"]
    # engine = each session's wall minus its leaves: (10.5-7.5) + (13.5-9.5)
    assert cats["engine"]["wall_s"] == 7.0, cats["engine"]
    assert s0["engine_s"] == 3.0 and s1["engine_s"] == 4.0, (s0, s1)
    assert acc["compute"]["holdout"]["wall_s"] == 2.0
    # an old-style parent row (no children counts): its time is its children's
    assert acc["compute"]["averaged_holdout"]["wall_s"] == 0.0, "a parent was summed"
    assert acc["by_module"]["model"]["agent_s"] == 6.0, acc["by_module"]
    # the session tiles: self time + engine == wall, both sessions; and the
    # categories tile the run
    for ses in acc["sessions"]:
        assert abs(ses["timed_s"] + ses["engine_s"] - ses["wall_s"]) < 1e-6, ses
    assert _tiles(acc), acc["by_category"]
    print("  hand-made rows: sessions + waiting = wall; self time + engine = session")


def _tiles(acc: dict) -> bool:
    """The closing check: every category's wall, summed, is the run's."""
    total = sum(float(v.get("wall_s") or 0.0) for v in acc["by_category"].values())
    return abs(total - float(acc["run_wall_s"])) < 0.01


def test_parentage_is_the_stack_not_the_clock() -> None:
    """A parent contributes its self time (its wall minus its children's) —
    known from the stack when it closed, so two spans with equal times, or a
    zero-length span on a boundary, cannot fool the account."""
    rows = [
        _row("run_start", 1000.0),
        # a parent (model-averaged holdout, 3 s) with two children (1 s each)
        _span(
            "compute",
            "averaged_holdout",
            1001.0,
            1004.0,
            n_children=2,
            children_wall_s=2.0,
            children_cpu_s=2.0,
            cpu_s=3.0,
            depth=0,
        ),
        _span(
            "compute",
            "holdout",
            1001.5,
            1002.5,
            n_children=0,
            children_wall_s=0.0,
            children_cpu_s=0.0,
            cpu_s=1.0,
            depth=1,
        ),
        _span(
            "compute",
            "holdout",
            1002.5,
            1003.5,
            n_children=0,
            children_wall_s=0.0,
            children_cpu_s=0.0,
            cpu_s=1.0,
            depth=1,
        ),
        # two leaves with IDENTICAL times, and a zero-length stub call on a
        # boundary: all three count, nothing is demoted
        _span(
            "compute",
            "a",
            1005.0,
            1006.0,
            n_children=0,
            children_wall_s=0.0,
            children_cpu_s=0.0,
            cpu_s=1.0,
        ),
        _span(
            "compute",
            "b",
            1005.0,
            1006.0,
            n_children=0,
            children_wall_s=0.0,
            children_cpu_s=0.0,
            cpu_s=1.0,
        ),
        _span(
            "agent",
            "stub",
            1006.0,
            1006.0,
            n_children=0,
            children_wall_s=0.0,
            children_cpu_s=0.0,
            cpu_s=0.0,
        ),
        _row("run_end", 1008.0, outcome="completed", cpu_s=7.0),
    ]
    acc = T.summarize(rows)
    comp = acc["compute"]
    assert comp["averaged_holdout"]["wall_s"] == 1.0, comp["averaged_holdout"]
    assert comp["holdout"]["wall_s"] == 2.0 and comp["holdout"]["n"] == 2
    assert comp["a"]["wall_s"] == 1.0 and comp["b"]["wall_s"] == 1.0
    assert acc["by_category"]["agent"]["n"] == 1
    assert acc["by_category"]["compute"]["wall_s"] == 5.0, acc["by_category"]
    assert acc["sessions"][0]["engine_s"] == 3.0 and _tiles(acc), acc["sessions"]
    assert acc["by_category"]["compute"]["cpu_s"] == 5.0
    assert acc["sessions"][0]["engine_cpu_s"] == 2.0
    print(
        "  parentage from the stack: equal intervals and zero-length spans count once"
    )


def test_a_paused_session_keeps_its_late_spans_on_resume() -> None:
    """The checkpoint after `gate_pending` is the paused session's; on resume
    it must stay there (extending that session), not fall into the human's
    gap and ALSO into the category sums."""
    pause_rows = [
        _row("run_start", 1000.0, cpu_s=0.1),
        _span(
            "compute",
            "compile",
            1001.0,
            1004.0,
            cpu_s=3.0,
            n_children=0,
            children_wall_s=0.0,
            children_cpu_s=0.0,
        ),
        _row("gate_pending", 1004.5, cpu_s=3.3),
    ]
    late = _span(
        "record",
        "checkpoint",
        1004.6,
        1006.6,
        cpu_s=0.5,
        n_children=0,
        children_wall_s=0.0,
        children_cpu_s=0.0,
        late=True,
    )
    at_pause = T.summarize(
        pause_rows, extra_spans=[late], ended_at=1006.7, cpu_at_end=3.9
    )
    assert at_pause["sessions"][0]["wall_s"] == 6.7 and _tiles(at_pause)
    resumed = pause_rows + [
        _row("run_start", 1030.0, cpu_s=0.1),
        _span(
            "compute",
            "multistart",
            1031.0,
            1035.0,
            cpu_s=4.0,
            n_children=0,
            children_wall_s=0.0,
            children_cpu_s=0.0,
        ),
        _row("run_end", 1036.0, outcome="completed", cpu_s=4.4),
    ]
    final = T.rebuild(at_pause, resumed)
    s0 = final["sessions"][0]
    assert s0["wall_s"] == 6.7 and s0["ended_by"] == "gate_pending", s0
    assert final["waiting_for_human_s"] == round(1030.0 - 1006.7, 3), final[
        "waiting_for_human_s"
    ]
    assert final["by_category"]["record"]["wall_s"] == 2.0
    assert _tiles(final), (final["by_category"], final["run_wall_s"])
    # a resume launched while the paused process was still checkpointing
    early = pause_rows + [
        _row("run_start", 1005.0, cpu_s=0.1),
        _row("run_end", 1010.0, outcome="completed", cpu_s=1.0),
    ]
    acc = T.rebuild(at_pause, early)
    assert acc["sessions"][1]["started"] >= acc["sessions"][0]["ended"], acc["sessions"]
    assert acc["residual_s"] == 0.0 and _tiles(acc)
    # and a stored account that the ledger ran past is stale
    assert T.is_stale(at_pause, resumed) and not T.is_stale(final, resumed)
    print(
        "  paused session: its late checkpoint stays its own on resume; the account tiles"
    )


def test_a_killed_session_is_said_to_be() -> None:
    rows = [
        _row("run_start", 1000.0),
        _span("compute", "compile", 1001.0, 1004.0),
        _row("note", 1005.0),
        # no end row: the process died; the next invocation starts later
        _row("run_start", 1100.0),
        _row("run_end", 1105.0, outcome="completed"),
    ]
    acc = T.summarize(rows)
    assert acc["sessions"][0]["ended_by"] == "killed", acc["sessions"][0]
    assert acc["sessions"][0]["wall_s"] == 5.0, "a killed session ends at its last row"
    # nobody was asked anything: the gap after a killed session is not a
    # human's, it is what the account cannot explain
    assert acc["waiting_for_human_s"] == 0.0, acc["waiting_for_human_s"]
    assert acc["unaccounted_s"] == 95.0 and acc["residual_s"] == 95.0, acc
    assert acc["by_category"]["unaccounted"]["wall_s"] == 95.0
    assert "unaccounted" in T.one_line(acc)
    # a legacy record has only `ts` strings: still an account
    old = [
        {"ts": "2026-09-01T10:00:00", "event": "run_start"},
        {"ts": "2026-09-01T10:01:00", "event": "run_end", "outcome": "completed"},
    ]
    acc = T.summarize(old)
    assert acc["run_wall_s"] == 60.0 and acc["by_category"]["engine"]["wall_s"] == 60.0
    print("  killed session and legacy rows: still an account, honestly bounded")


def test_a_span_records_nothing_unattached() -> None:
    T.detach()
    with T.span("compute", "probe") as s:
        s["n"] = 1
    with T.span("compute", "nested"):
        with T.span("compute", "inner"):
            pass
    try:
        with T.span("nonsense", "x"):
            pass
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown category was accepted")
    print("  unattached: a span is a plain timer")


# ---------------------------------------------------------------- a run
def _assert_record_complete(run_id: str) -> None:
    """The record holds what each finished step left (`completeness.py`):
    this suite removes its runs, so the battery cannot read them for it."""
    gaps = completeness.gaps(RunStore.for_run(config.RUNS_DIR, run_id).path)
    assert not gaps, f"the record lacks what its steps left: {gaps[:5]}"


def test_a_stub_run_explains_its_wall() -> None:
    run_id = "timing_suite_run"
    t0 = time.time()
    rc = subprocess.run(
        _cmd(
            run_id,
            "--auto-approve",
            "--overwrite",
            # profiles run only on request; the account must time them
            "--profiles",
            "timing suite: the profiles span is part of the account",
        ),
        cwd=REPO,
        env=_env(),
        capture_output=True,
        text=True,
    )
    wall = time.time() - t0
    assert rc.returncode == 0, rc.stderr[-800:]
    root = run_root(run_id)
    try:
        acc = (root / "timing").get()
        rows = ledger_rows(root)
        assert acc["n_sessions"] == 1, acc["n_sessions"]
        assert acc["residual_s"] == 0.0, acc["residual_s"]
        # the account's wall is the process's wall, less its start-up and exit
        assert 0 < acc["run_wall_s"] <= wall, (acc["run_wall_s"], wall)
        assert (
            wall - acc["run_wall_s"] < 5.0
        ), f"{wall - acc['run_wall_s']:.1f}s of the process is outside the account"
        cats = acc["by_category"]
        calls = [r for r in rows if r.get("event") == "agent_call"]
        # every call that delivered is one `agent` span; a call that raised
        # (a stub with no reply for that role, an exhausted re-ask) is a span
        # too, `ok: false`, because its time was spent all the same
        agent_spans = [s for s in acc["spans"] if s.get("category") == "agent"]
        delivered = [s for s in agent_spans if s.get("ok")]
        assert len(delivered) == len(calls), (
            [(s["name"], s.get("ok")) for s in agent_spans],
            len(calls),
        )
        assert cats["agent"]["n"] == len(agent_spans)
        assert all(isinstance(r.get("t"), float) for r in rows), "a row without `t`"
        comp = acc["compute"]
        for name in ("cost_probe", "multistart", "profiles"):
            assert name in comp and comp[name]["wall_s"] > 0, (name, comp.keys())
        assert "compile" in comp, "the AMICI build (or its cache load) was not timed"
        assert "estimation" in acc["by_module"] and "evaluation" in acc["by_module"]
        assert (acc["by_category"].get("render") or {}).get("wall_s", 0) > 0
        assert (acc["by_category"].get("record") or {}).get("n", 0) >= 3, "checkpoints"
        assert _tiles(acc), (acc["by_category"], acc["run_wall_s"])
        assert (acc["by_category"].get("render") or {}).get(
            "n", 0
        ) >= 3, "analysis render"
        # across machines: CPU beside wall, the work done, and what it ran on
        assert acc["run_cpu_s"] and acc["run_cpu_s"] > 0, acc.get("run_cpu_s")
        assert acc["machine"]["cpu_count"] and acc["machine"]["cpu_model"], acc[
            "machine"
        ]
        ms = comp["multistart"]
        assert ms["cpu_s"] > 0 and ms["n_fval"] > 0 and ms["n_procs"] >= 1, ms
        assert ms["cpu_s_per_start"] > 0 and ms["cpu_s_per_fval"] > 0, ms
        pf = comp["profiles"]
        assert pf["n_points"] > 0 and pf["n_fval"] > 0, pf
        assert all(
            s.get("cpu_s") is not None for s in acc["spans"]
        ), "a span without cpu"
        run_meta = (root / "run").get()
        assert (
            run_meta["provenance"]["machine"]["cpu_count"]
            == acc["machine"]["cpu_count"]
        )
        # the session's CPU covers its leaves: the engine's CPU is a residual
        ses = acc["sessions"][0]
        assert ses["cpu_s"] >= ses["timed_cpu_s"] - 0.05, (
            ses["cpu_s"],
            ses["timed_cpu_s"],
        )
        # the account is a group of the record AND what `status` prints
        st = subprocess.run(
            [PY, "-m", "octomod", "status", "--run-id", run_id],
            cwd=REPO,
            env=_env(),
            capture_output=True,
            text=True,
        ).stdout
        assert "time:" in st and "compute" in st, st[:400]
        # the module spans are parents, never summed as leaves
        assert "module" not in cats, cats.keys()
        # no span follows the run_end row: late spans went to the group (the
        # tried-models note the engine writes after run_end is not ours)
        last_end = max(i for i, r in enumerate(rows) if r["event"] == "run_end")
        after = [r["event"] for r in rows[last_end + 1 :]]
        assert "span" not in after, after
        assert any(s.get("late") for s in acc["spans"]), "no late span (analysis)"
        print(
            f"  stub run: {T.one_line(acc)}\n"
            f"    process wall {wall:.1f}s; compute "
            + ", ".join(
                f"{k} {v['wall_s']:.1f}s/{v['cpu_s']:.1f}cpu" for k, v in comp.items()
            )
            + f"\n    multistart: {ms['n_starts']} starts on {ms['n_procs']} procs, "
            f"{ms['n_fval']} fval, {ms['cpu_s_per_start']:.3f} cpu-s/start; "
            f"profiles: {pf['n_points']} points, {pf['cpu_s_per_point']:.4f} cpu-s/point"
            f"\n    machine: {acc['machine']['cpu_model']} x{acc['machine']['cpu_count']}"
        )
        _assert_record_complete(run_id)
    finally:
        RunStore.for_run(config.RUNS_DIR, run_id).remove()


def test_a_paused_run_counts_the_wait_between_sessions() -> None:
    run_id = "timing_suite_gate"
    rc = subprocess.run(
        _cmd(run_id, "--gate-mode", "file", "--overwrite"),
        cwd=REPO,
        env=_env(),
        capture_output=True,
        text=True,
    )
    root = run_root(run_id)
    try:
        assert rc.returncode == 3, rc.stderr[-600:]
        assert pending_gate(root)["module"] == "intent"
        acc = (root / "timing").get()
        assert (
            acc["n_sessions"] == 1 and acc["sessions"][0]["ended_by"] == "gate_pending"
        )
        assert acc["residual_s"] == 0.0
        assert ledger_rows(root)[-1]["event"] == "gate_pending"
        time.sleep(2.0)  # the human reads the card
        rc = subprocess.run(
            _cmd(run_id, "--gate-mode", "file", "--gate-answer", "n"),
            cwd=REPO,
            env=_env(),
            capture_output=True,
            text=True,
        )
        assert rc.returncode == 1, rc.stderr[-600:]  # declined: the run stops
        acc = (root / "timing").get()
        assert acc["n_sessions"] == 2, acc["sessions"]
        assert acc["waiting_for_human_s"] >= 2.0, acc["waiting_for_human_s"]
        assert acc["sessions"][1]["ended_by"].startswith("run_end:"), acc["sessions"]
        assert acc["residual_s"] == 0.0
        assert (
            abs(
                sum(s["wall_s"] for s in acc["sessions"])
                + acc["waiting_for_human_s"]
                - acc["run_wall_s"]
            )
            < 1e-6
        )
        print(f"  paused run: {T.one_line(acc)}")
        _assert_record_complete(run_id)
    finally:
        RunStore.for_run(config.RUNS_DIR, run_id).remove()


def main() -> int:
    test_the_account_closes_on_hand_made_rows()
    test_a_killed_session_is_said_to_be()
    test_parentage_is_the_stack_not_the_clock()
    test_a_paused_session_keeps_its_late_spans_on_resume()
    test_a_span_records_nothing_unattached()
    test_a_stub_run_explains_its_wall()
    test_a_paused_run_counts_the_wait_between_sessions()
    print("TIMING OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
