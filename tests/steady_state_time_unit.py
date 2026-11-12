"""Steady-state measurements (PEtab `time = inf`), from the data table to the report.

PEtab reads a measurement at `time = inf` as the model's steady state under its
condition (v1: `TIME_STEADY_STATE = inf`; v2: a measurement time is finite or
`inf`); AMICI post-equilibrates to it and pyPESTO's objective passes it through.
The engine lets such a row through every module:

  1. S2: `data_rows_well_formed` passes `inf` and counts the steady-state rows;
     a blank, `-inf` and a negative time still fail, each by name; a time cell
     written `inf` is a number, and a time cell in words is refused with the
     spelling that works;
  2. the roadrunner path (S3 screens, S7 metrics, report figures) reads a
     time-inf point at the state the condition settles to: the analytic steady
     state of the toy cycle, with the finite points unchanged; a slow system
     is followed past t = 1e5 until it settles, and one that grows without
     bound keeps its t = 1e5 read;
  3. the S3 battery passes a problem with steady-state rows;
  4. the data signals keep a steady-state point off the time-course shapes, a
     series measured at steady state only is named (on the card too) rather
     than called flat, and the raw-file reading takes a file with time-inf
     cells;
  5. held-out coverage at time inf is scored against the band's steady state;
  6. the residual statistics read the time course only: S7's autocorrelation
     screen and the expansion agent's series report are unchanged by a
     steady-state row, which the report carries beside the time course;
  7. the figures draw steady-state rows in a column marked ∞, right of the time
     course and of a band that runs past the last measurement;
  8. the budget card reports AMICI's post-equilibration beside the
     pre-equilibration, and a failed Newton step that simulation recovered is
     not a failure;
Full tier (an AMICI compile, and a run):
  9. AMICI reads the same steady state as roadrunner, and settles every
     post-equilibration;
 10. a supplied PEtab problem with time-inf rows (a copy of toy_phos_petab)
     enters at estimation, fits, evaluates and renders its report, token-free.

    uv run python tests/steady_state_time_unit.py
"""

from __future__ import annotations

import atexit
import json
import logging
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.WARNING)
# the end-to-end check runs the CLI in this process; `runs/` is the user's
if not os.environ.get("OCTOMOD_RUNS_DIR"):
    os.environ["OCTOMOD_RUNS_DIR"] = tempfile.mkdtemp(prefix="steady_runs_")
    atexit.register(shutil.rmtree, os.environ["OCTOMOD_RUNS_DIR"], True)

from _harness import (  # noqa: E402
    RecordingLedger,
    check,
    finish,
    quick_tier,
    run_cli_captured,
)
from _record import (  # noqa: E402
    ledger_rows,
    reports_dir,
    rnd,
    run_root,
    temp_record,
    work,
)

from octomod import config  # noqa: E402
from octomod.gates import run_gate_set  # noqa: E402
from octomod.gates.petab_gates import PetabTables, make_petab_gates  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import petab_io  # noqa: E402

SOURCE = REPO / "testcase" / "toy_phos_petab"
SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
DOSES = {"dose_0p3": 0.3, "dose_1": 1.0, "dose_3": 3.0}
NOMINAL = {"k_phos": 0.02, "k_dephos": 0.2}
# the generator's truth (testcase/toy_phos/make_data.py): y = 3.7 Rp
TRUTH = {"k_phos": 0.05, "k_dephos": 0.1, "sc_obs_pR": 3.7}
RUN_ID = "steady_state_cli"


def _rp_steady(s: float, k_phos: float = 0.02, k_dephos: float = 0.2) -> float:
    """The toy cycle R <-> Rp (R + Rp = 10) at steady state under ligand `s`."""
    return 10.0 * k_phos * s / (k_phos * s + k_dephos)


def _true_steady(s: float) -> float:
    """What the assay reads at steady state under ligand `s`, noise-free."""
    rp = _rp_steady(s, TRUTH["k_phos"], TRUTH["k_dephos"])
    return round(TRUTH["sc_obs_pR"] * rp, 4)


def _with_steady_rows(meas: pd.DataFrame) -> pd.DataFrame:
    """The measurement table plus one row per condition at time inf, at the
    generator's true steady state: a steady-state readout biased toward no
    sample, and one value per cell, so the replicate noise floor is the time
    course's own."""
    first = meas.groupby("simulationConditionId", sort=False).head(1)
    steady = first.assign(
        time=np.inf,
        measurement=[_true_steady(DOSES[c]) for c in first["simulationConditionId"]],
    )
    return pd.concat([meas, steady], ignore_index=True)


def _toy_input():
    """The toy problem, every condition in the measurement table, with one
    steady-state row per condition."""
    inp = petab_io.from_dir(SOURCE / "supplied" / "petab")
    return inp.with_tables(measurements=_with_steady_rows(inp.measurements))


def _frame(inp) -> pd.DataFrame:
    """The measurements as the report reads them, dose_3 held out."""
    m = inp.measurements
    return pd.DataFrame(
        {
            "observable": m["observableId"].astype(str),
            "condition": m["simulationConditionId"].astype(str),
            "time": m["time"].astype(float),
            "value": m["measurement"].astype(float),
            "heldout": m["simulationConditionId"].astype(str) == "dose_3",
        }
    )


# ------------------------------------------------------------------ S2


def _rows_gate(times):
    """`data_rows_well_formed` on one series at `times`."""
    from octomod.workflow_modules.data.engine import make_data_gates

    n = len(times)
    long_df = pd.DataFrame(
        {
            "observable_label": "pR_au",
            "condition_label": "dose=1",
            "condition_key": "dose=1",
            "time": times,
            "value": np.linspace(1.0, 2.0, n),
            "replicate": list(range(1, n + 1)),
        }
    )
    report = {
        "mappings": [],
        "observable_labels": [
            {"label": "pR_au", "units": "arbitrary", "error_type": "replicates"}
        ],
        "flags": [],
    }
    ctx = SimpleNamespace(testcase={"holdout": {"condition_labels": []}})
    return make_data_gates(long_df, report, ctx)[0]()


def test_the_data_gate_lets_steady_state_through() -> None:
    r = _rows_gate([0.0, 5.0, 60.0, np.inf, np.inf])
    check(
        "S2 passes time inf, the steady-state measurement, and counts its rows",
        r.passed and "or inf (2 steady-state row(s))" in r.detail,
        r.detail,
    )
    plain = _rows_gate([0.0, 5.0, 60.0])
    check(
        "a table without one reads as it did",
        plain.passed and plain.detail.endswith("keys unique, times finite"),
        plain.detail,
    )
    for label, times, want in (
        ("a blank time", [0.0, np.nan, 60.0], "non-numeric or non-finite times"),
        ("time -inf", [0.0, -np.inf, 60.0], "time -inf in 1 row(s)"),
        ("a negative time", [0.0, -5.0, 60.0], "negative time points"),
    ):
        r = _rows_gate(times)
        check(
            f"{label} still fails, by name",
            not r.passed and want in r.detail,
            r.detail,
        )


def test_a_time_cell_written_inf_is_a_number() -> None:
    from octomod.orchestration.run_context import ModuleFailure
    from octomod.workflow_modules.data.engine import _numeric_cells

    got = _numeric_cells(
        pd.DataFrame({"t": ["0", "5", "inf", "Inf"]}), "t", "data.csv", "time"
    )
    check(
        "a time cell written inf, in either case, is the number inf",
        got[:2] == [0.0, 5.0] and all(math.isinf(v) and v > 0 for v in got[2:]),
        str(got),
    )
    said = ""
    try:
        _numeric_cells(
            pd.DataFrame({"t": ["0", "steady state"]}), "t", "data.csv", "time"
        )
    except ModuleFailure as e:
        said = str(e)
    check(
        "a time cell in words is refused, and the refusal says how a steady "
        "state is written",
        "holds text where a number belongs" in said and "`inf`" in said,
        said[-240:],
    )


# ------------------------------------------------------------- roadrunner


def test_the_roadrunner_path_reads_the_steady_state() -> None:
    tables = PetabTables.from_input(_toy_input())
    t = np.array([0.0, 5.0, 60.0, np.inf])
    got, ok = {}, True
    for cid, s in DOSES.items():
        y = tables.simulate_observables(cid, t)["obs_pR"]
        y_finite = tables.simulate_observables(cid, t[:3])["obs_pR"]
        want = _rp_steady(s)
        got[cid] = (round(float(y[-1]), 6), round(want, 6))
        ok = ok and abs(float(y[-1]) - want) <= 1e-4 * want
        ok = ok and bool(np.allclose(y[:3], y_finite, rtol=1e-6, atol=1e-9))
    check(
        "a time-inf point reads the analytic steady state of the toy cycle, and "
        "the finite points are those of the same call without it",
        ok,
        str(got),
    )
    only = tables.simulate_observables(
        "dose_1", np.array([np.inf]), param_override={"k_phos": 0.05}
    )["obs_pR"]
    check(
        "a steady-state-only call reads the steady state at the caller's parameters",
        abs(float(only[0]) - _rp_steady(1.0, k_phos=0.05)) <= 1e-4,
        f"{float(only[0])} vs {_rp_steady(1.0, k_phos=0.05)}",
    )
    sd = tables.sigma_series("obs_pR", "dose_1", t)
    check(
        "sigma is read at a time-inf point too",
        len(sd) == 4 and bool(np.all(np.isfinite(sd))),
        str(sd),
    )


def _rr_model(src: str):
    """A roadrunner model from Antimony source."""
    import antimony

    from octomod.workflow_modules.model.simwrap import RRModel

    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(src) >= 0, antimony.getLastError()
    return RRModel(antimony.getSBMLString(antimony.getMainModuleName()))


def test_a_slow_system_is_read_where_it_settles() -> None:
    # time constant 5e4: at t = 1e5 the product has reached only 1 - e^-2
    slow = _rr_model("model slow\n  J1: A -> B; k*A\n  k = 2e-5\n  A = 1; B = 0\nend\n")
    at_probe = float(slow.simulate(1e5, n_points=51)["B"][-1])
    got = slow.settled_values()
    check(
        "a system still moving at t = 1e5 is followed until it settles, where "
        "AMICI's post-equilibration reads it",
        abs(got["B"] - 1.0) <= 1e-4 and abs(got["A"]) <= 1e-4,
        f"B = {got['B']:.6f} (analytic 1; the t = 1e5 point is {at_probe:.4f})",
    )
    grow = _rr_model("model grow\n  J1: -> A; r*A\n  r = 1e-3\n  A = 1\nend\n")
    at_probe = float(grow.simulate(1e5, n_points=51)["A"][-1])
    got_a = grow.settled_values()["A"]
    check(
        "a state that grows without bound keeps the t = 1e5 read: the longer "
        "run fails and replaces nothing",
        bool(np.isclose(got_a, at_probe, rtol=1e-12)),
        f"{got_a:.4e} vs {at_probe:.4e}",
    )


def test_the_s3_battery_passes_with_steady_state_rows() -> None:
    with temp_record() as root:
        ok, results = run_gate_set(
            make_petab_gates(PetabTables.from_input(_toy_input()), SPEC),
            rnd(root, 0) / "gates",
            RecordingLedger(),
            "assembly",
        )
    res = {r.gate_id: r for r in results}
    check(
        "the S3 battery passes a problem with time-inf rows, petablint included",
        ok and "assembly_petablint" in res and res["assembly_petablint"].passed,
        "; ".join(f"{g}: {r.passed} {r.detail[:70]}" for g, r in res.items()),
    )
    mag = res.get("assembly_magnitude_reconciliation")
    check(
        "the magnitude check simulates the steady-state rows instead of failing "
        "on them",
        mag is not None and mag.passed and "simulation failed" not in mag.detail,
        mag.detail if mag else str(sorted(res)),
    )
    sens = res.get("assembly_sensitivity_coverage")
    check(
        "the sensitivity screen runs over them",
        sens is not None and "screen unavailable" not in sens.detail,
        sens.detail if sens else str(sorted(res)),
    )


# ------------------------------------------------------------------ signals


def _rise(t: float, scale: float) -> float:
    """A first-order rise to `scale`, which is its value at time inf."""
    return scale * (1.0 - math.exp(-t / 8.0)) if math.isfinite(t) else scale


def _signal_rows() -> pd.DataFrame:
    """Two time courses with a steady-state point each, and a third condition
    measured at steady state only."""
    rows = []
    times = [0.0, 5.0, 10.0, 20.0, 40.0, 60.0, np.inf]
    for key, scale in (("dose=1", 1.0), ("dose=3", 3.0)):
        for rep in (1, 2):
            for t in times:
                level = _rise(t, scale)
                rows.append(
                    {
                        "observable_label": "pR",
                        "condition_label": key,
                        "condition_key": key,
                        "time": t,
                        "value": level + 0.01 * rep,
                        "replicate": rep,
                    }
                )
    for rep in (1, 2):
        rows.append(
            {
                "observable_label": "pR",
                "condition_label": "dose=10",
                "condition_key": "dose=10",
                "time": np.inf,
                "value": 10.0 + 0.01 * rep,
                "replicate": rep,
            }
        )
    return pd.DataFrame(rows)


def test_the_signals_keep_steady_state_off_the_curves() -> None:
    from octomod.workflow_modules.data import data_signals, phenomenology

    out = data_signals.compute(_signal_rows())
    shape = out["per_observable"]["pR"]["shape_per_condition"]["dose=1"]
    check(
        "a series' raw shape is read off its time course: the steady-state "
        "point is not its last sample",
        shape.get("n_points") == 6 and math.isfinite(shape.get("time_of_max", 0.0)),
        str(shape),
    )
    cd = out["curve_descriptors"]
    fitted = {r["condition"]: r["fit"] for r in cd.get("per_series") or []}
    check(
        "a series measured at steady state only is named, not fitted and called "
        "flat",
        cd.get("steady_state_only") == [{"observable": "pR", "condition": "dose=10"}]
        and "dose=10" not in fitted
        and "dose=1" in fitted,
        str(cd.get("steady_state_only")),
    )
    check(
        "a fitted time course uses the finite samples only",
        fitted.get("dose=1", {}).get("n") == 12
        and (fitted.get("dose=1", {}).get("window") or [None, None])[1] == 60.0,
        str(fitted.get("dose=1", {}).get("window")),
    )
    ph = phenomenology.build(out)
    sentences = ph["sentences"]
    check(
        "the sentences construction reads say nothing about the steady-state-only "
        "series",
        bool(sentences) and not any("dose=10" in s for s in sentences),
        " | ".join(sentences),
    )
    lines = phenomenology.card_lines(ph)
    check(
        "the card names the series measured at steady state only instead",
        ph.get("steady_state_only") == [{"observable": "pR", "condition": "dose=10"}]
        and any(
            "(measured at steady state only, not described: pR@dose=10)" in s
            for s in lines
        ),
        " | ".join(lines),
    )


def test_the_raw_reading_takes_a_time_inf_cell(root: Path) -> None:
    from octomod.workflow_modules.data import raw_phenomenology

    data = root / "raw_data"
    data.mkdir(parents=True, exist_ok=True)
    rows = [
        {"time": t, "dose": dose, "pR": _rise(t, dose)}
        for dose in (1.0, 3.0)
        for t in (0.0, 5.0, 10.0, 20.0, 40.0, 60.0, np.inf)
    ]
    pd.DataFrame(rows).to_csv(data / "timecourse.csv", index=False)
    rec = raw_phenomenology.derive(data, [])
    check(
        "the raw-file reading takes a file with time-inf rows, and describes the "
        "time courses",
        rec.get("available") is True and bool(rec.get("sentences")),
        f"{rec.get('rule')}: {rec.get('why')}",
    )


# -------------------------------------------------------------- evaluation


def test_held_out_coverage_reads_the_band_at_steady_state() -> None:
    from octomod.workflow_modules.evaluation.engine import (
        _holdout_from_cr,
        _steady_state_conditions,
    )

    tables = PetabTables.from_input(_toy_input())
    check(
        "the conditions with a time-inf row are found",
        _steady_state_conditions(tables) == set(DOSES),
        str(_steady_state_conditions(tables)),
    )
    # the band sits at 0 on the time course and at 100 at steady state: a
    # held-out row at 100 is inside it only if time inf reads the last entry
    band = {
        "time": [0.0, 60.0, np.inf],
        "best": [0.0, 0.0, 100.0],
        "lo95": [0.0, 0.0, 100.0],
        "hi95": [0.0, 0.0, 100.0],
    }
    core = {
        "prediction_uncertainty": {"bands": {"obs_pR@dose_3": band}},
        "holdout": {"groups": [{"label": "obs_pR@dose_3"}]},
    }
    hold = pd.DataFrame(
        {
            "observableId": ["obs_pR"],
            "simulationConditionId": ["dose_3"],
            "time": [np.inf],
            "measurement": [100.0],
        }
    )
    _holdout_from_cr(core, hold, tables, {"best_x_unscaled": {}}, SPEC)
    g = core["holdout"]["groups"][0]
    check(
        "a held-out time-inf row is scored against the band's steady state, not "
        "its last time point",
        g.get("band_coverage") == 1.0,
        str(g),
    )


def test_the_residual_statistics_read_the_time_course() -> None:
    from octomod.workflow_modules.assembly import petab_io
    from octomod.workflow_modules.evaluation.engine import _fit_metrics
    from octomod.workflow_modules.evaluation.residuals import series_report

    t = np.array([0.0, 5.0, 10.0, 20.0, 40.0, 60.0, np.inf])
    meas = np.array([0.0, 1.0, 1.6, 2.1, 2.3, 2.35, 2.9])
    sim = np.array([0.1, 0.9, 1.7, 2.0, 2.4, 2.3, 2.4])
    with_ss = series_report(t, meas, sim, 0.1)
    course = series_report(t[:-1], meas[:-1], sim[:-1], 0.1)
    shape = (
        "fit_over_time",
        "n_timepoints",
        "residual_sign_pattern_over_time",
        "n_sign_runs",
        "lag1_autocorr",
        "monotone_trend_with_time",
        "largest_deviation",
    )
    moved = {k: (with_ss.get(k), course.get(k)) for k in shape}
    check(
        "the residual shape the expansion agent reads is the time course's: a "
        "steady-state row changes none of it",
        all(a == b for a, b in moved.values()),
        str({k: v for k, v in moved.items() if v[0] != v[1]}),
    )
    check(
        "the steady-state row is reported beside the time course, and the report "
        "is plain JSON",
        with_ss.get("steady_state")
        == {"measured": 2.9, "simulated": 2.4, "residual_in_noise_units": 5.0}
        and "steady_state" not in course
        and bool(json.dumps(with_ss, allow_nan=False)),
        str(with_ss.get("steady_state")),
    )
    only = series_report(
        np.array([np.inf, np.inf]), np.array([2.9, 3.0]), np.array([2.4, 2.4]), 0.1
    )
    check(
        "a series measured at steady state only has no time-course shape",
        only["n_timepoints"] == 0
        and only["largest_deviation"] is None
        and "steady_state" in only,
        str(only),
    )
    best = {**NOMINAL, "sc_obs_pR": 3.7, "sigma_obs_pR": 1.0}
    plain = petab_io.from_dir(SOURCE / "supplied" / "petab")
    with_rows = _fit_metrics(PetabTables.from_input(_toy_input()), best)
    without = _fit_metrics(PetabTables.from_input(plain), best)
    got = {
        a["condition"]: (a["residual_lag1_autocorr"], b["residual_lag1_autocorr"])
        for a, b in zip(with_rows, without, strict=True)
    }
    check(
        "the residual autocorrelation S7 screens for misfit reads the time course "
        "only",
        len(got) == 3
        and all(math.isclose(a, b, rel_tol=1e-12) for a, b in got.values()),
        str(got),
    )


def _svg(html: str) -> str:
    start = html.find("<svg")
    return html[start : html.find("</svg>", start)] if start >= 0 else ""


def test_the_figures_draw_a_steady_state_column() -> None:
    from octomod.reporting import figures, round_report

    inp = _toy_input()
    tables = PetabTables.from_input(inp)
    frame = _frame(inp)
    best = {**NOMINAL, "sc_obs_pR": 10.0, "sigma_obs_pR": 1.0}
    band = {
        "time": [0.0, 30.0, 60.0, np.inf],
        "best": [0.0, 8.0, 9.0, 9.1],
        "lo95": [0.0, 7.0, 8.0, 8.1],
        "hi95": [0.0, 9.0, 10.0, 10.1],
        "lo90": [0.0, 7.5, 8.5, 8.6],
        "hi90": [0.0, 8.5, 9.5, 9.6],
    }
    fake_round = SimpleNamespace(
        petab_tables=lambda: tables,
        measurement_frame=lambda: frame,
        summary={"best_x_unscaled": best, "ensemble": []},
        report={},
        core={},
        _band_note_shown=False,
    )
    drawn = {
        "data figure": figures.data_figure("obs_pR", frame),
        "fit grid": figures.fit_grid_figure(tables, best, [best], frame),
        "fit grid with a confidence band": figures.fit_grid_figure(
            tables, best, [], frame, {"obs_pR@dose_1": band}
        ),
        "held-out figure": round_report._holdout_figure(
            fake_round, [{"label": "obs_pR@dose_3"}]
        ),
    }
    for label, html in drawn.items():
        check(
            f"the {label} draws, with the steady-state rows in a column marked ∞",
            figures.STEADY_STATE_TICK in _svg(html) and "unavailable" not in html,
            html[:300],
        )
    plain = figures.data_figure("obs_pR", frame[np.isfinite(frame["time"])])
    check(
        "a figure without steady-state rows has no such column",
        "<svg" in plain and figures.STEADY_STATE_TICK not in plain,
        plain[:200],
    )
    # the band runs to t_end, 100 for a case that declares none, past the last
    # measurement at 60: the column goes right of the band, not inside it
    dense = np.linspace(0.0, 100.0, 61)
    long_band = {
        "time": [*dense, np.inf],
        "best": [*np.full(61, 9.0), 9.1],
        "lo95": [*np.full(61, 8.0), 8.1],
        "hi95": [*np.full(61, 10.0), 10.1],
    }
    import matplotlib.pyplot as plt

    drawn_fig: dict = {}

    def keep(build, **_kw):
        drawn_fig["fig"] = build(plt)
        return ""

    real_figure = figures.figure
    figures.figure = keep
    try:
        figures.fit_grid_figure(tables, best, [], frame, {"obs_pR@dose_1": long_band})
    finally:
        figures.figure = real_figure
    ax = next(a for a in drawn_fig["fig"].axes if a.get_title().endswith("dose_1"))
    labels = [t.get_text() for t in ax.get_xticklabels()]
    x_ss = (
        float(ax.get_xticks()[labels.index(figures.STEADY_STATE_TICK)])
        if figures.STEADY_STATE_TICK in labels
        else None
    )
    plt.close(drawn_fig["fig"])
    check(
        "a band that runs past the last measurement keeps the ∞ column right of it",
        x_ss is not None and x_ss > 100.0,
        f"∞ at x = {x_ss}; band to 100, data to 60",
    )


# ------------------------------------------------------------------ probe


def _probe_row(i: int, cid: str, pre: dict, post: dict) -> dict:
    return {"condition_index": i, "condition": cid, **pre, "posteq": post}


_IDLE = {"status": [0, 0, 0], "ran": False, "wrms": None, "cpu_time_s": 0.0}


def test_the_budget_card_reports_post_equilibration() -> None:
    from octomod.workflow_modules.cost_probe.engine import _steady_state_lines

    def ran(status, wrms):
        return {"status": status, "ran": True, "wrms": wrms, "cpu_time_s": 0.01}

    lines = _steady_state_lines(
        {
            "available": True,
            "used": False,
            "posteq_used": True,
            "per_condition": [
                _probe_row(0, "dose_1+", _IDLE, ran([0, 1, 0], 1e-3)),
                # Newton failed on the singular Jacobian, simulation settled it
                _probe_row(1, "dose_0p3+", _IDLE, ran([-3, 1, 0], 2e-3)),
                _probe_row(2, "dose_3+", _IDLE, ran([0, -2, 0], 3.0)),
            ],
        }
    )
    check(
        "the budget card names the post-equilibration of the time-inf rows, and "
        "the one condition AMICI did not settle",
        len(lines) == 2
        and lines[0].startswith(
            "post-equilibration (steady-state measurements, time inf): ran for "
            "3 condition(s)"
        )
        and "AMICI did not settle 1 post-equilibration(s): dose_3+" in lines[1],
        " || ".join(lines),
    )
    settled = {"status": [1, 0, 0], "ran": True, "wrms": 2e-4, "cpu_time_s": 0.0}
    pre_only = _steady_state_lines(
        {
            "available": True,
            "used": True,
            "posteq_used": False,
            "per_condition": [_probe_row(0, "dose_1+preeq_dose_1", settled, _IDLE)],
        }
    )
    as_it_was = (
        "pre-equilibration: ran for 1 condition(s), worst steady-state wrms "
        "2.00e-04 (dose_1+preeq_dose_1) (AMICI calls it settled below 1), "
        "0.00s total"
    )
    check(
        "a problem that only pre-equilibrates reads as it did",
        pre_only == [as_it_was],
        " || ".join(pre_only),
    )
    neither = {"available": True, "used": False, "posteq_used": False}
    check(
        "a problem that does neither says nothing",
        _steady_state_lines({**neither, "per_condition": []}) == [],
    )


# ------------------------------------------------------------ full effort


def test_amici_reads_the_same_steady_state() -> None:
    from octomod.workflow_modules.cost_probe import solver_probe
    from octomod.workflow_modules.cost_probe.engine import _steady_state_lines
    from octomod.workflow_modules.estimation import problem as estimation

    inp = _toy_input()
    problem, petab_problem, _ = estimation.build_problem(inp, {}, SPEC)
    scales = estimation.parameter_scales(inp)
    par = petab_problem.parameter_df
    nominal = {p: float(par.loc[p, "nominalValue"]) for p in problem.x_names}
    to_scale = {"log10": math.log10, "log": math.log}
    x = np.array([to_scale.get(scales[p], float)(v) for p, v in nominal.items()])
    x_free = x[problem.x_free_indices]
    out = problem.objective(x_free, return_dict=True, sensi_orders=(0,))
    tables = PetabTables.from_input(inp)
    got, ok = {}, math.isfinite(float(out["fval"]))
    for r in out["rdatas"]:
        cid = str(r.id).split("+")[0]
        t = np.asarray(r.ts, dtype=float)
        y = np.asarray(r.y, dtype=float)[:, 0]
        at_inf = np.isposinf(t)
        sim = tables.simulate_observables(cid, t, param_override=nominal)["obs_pR"]
        want = _rp_steady(DOSES[cid])
        amici_ss = float(y[at_inf][0]) if at_inf.any() else float("nan")
        rr_ss = float(sim[at_inf][0]) if at_inf.any() else float("nan")
        got[cid] = (round(amici_ss, 5), round(rr_ss, 5), round(want, 5))
        ok = ok and bool(at_inf.any()) and abs(amici_ss - want) <= 1e-2 * want
        ok = ok and float(np.max(np.abs(y - sim))) <= 1e-2 * max(want, 1e-12)
    check(
        "AMICI post-equilibrates each time-inf row to the analytic steady state, "
        "and agrees with roadrunner along the whole series",
        ok and set(got) == set(DOSES),
        str(got),
    )
    report = solver_probe.steady_state_report(problem, x_free)
    posteq = [r["posteq"] for r in report.get("per_condition") or []]
    settled = [
        p["ran"] and 1 in p["status"] and (p["wrms"] or 0.0) < 1.0 for p in posteq
    ]
    lines = _steady_state_lines(report)
    check(
        "the probe reads AMICI's post-equilibration for every condition, each "
        "settled (success, wrms below 1), and the card says so in one line",
        report.get("posteq_used") is True
        and len(posteq) == 3
        and all(settled)
        and len(lines) == 1
        and lines[0].startswith("post-equilibration"),
        json.dumps(posteq),
    )


def _cli_case(root: Path) -> Path:
    """toy_phos_petab, copied, with one time-inf row per condition at the true
    steady state; dose_3 stays held out, its steady-state row with it."""
    case = root / "toy_phos_petab_steady"
    shutil.copytree(SOURCE, case, ignore=shutil.ignore_patterns("truth"))
    path = case / "supplied" / "petab" / "measurements.tsv"
    _with_steady_rows(pd.read_csv(path, sep="\t")).to_csv(path, sep="\t", index=False)
    return case


def test_a_supplied_problem_with_steady_state_rows_runs(root: Path) -> None:
    run = run_root(RUN_ID, config.RUNS_DIR)
    run.store.remove()
    rc, out = run_cli_captured(
        [
            "run",
            "--testcase",
            str(_cli_case(root)),
            "--backend",
            "stub",
            "--auto-approve",
            "--run-id",
            RUN_ID,
        ]
    )
    rows = ledger_rows(run) if run.store.exists_on_disk() else []

    def gate_row(gate_id: str) -> dict | None:
        """The last verdict of `gate_id` in the run's ledger."""
        hits = [
            r for r in rows if r.get("event") == "gate" and r.get("gate_id") == gate_id
        ]
        return hits[-1] if hits else None

    t2 = gate_row("evaluation_t2prime_holdout") or {}
    check(
        "a supplied PEtab problem with time-inf rows runs to its end: entry at "
        "estimation, fit, evaluation, report",
        rc == 0,
        f"rc={rc}; T2': {t2.get('passed')} {t2.get('detail')}\n{out[-1500:]}",
    )
    gate = gate_row("data_rows_well_formed")
    check(
        "the data slot's entry check passed the steady-state rows and counted them",
        gate is not None
        and gate.get("passed") is True
        and "(3 steady-state row(s))" in str(gate.get("detail")),
        str(gate),
    )
    if rc != 0:
        return
    petab = work(run, 0) / "petab"
    n_train = np.isposinf((petab / "measurements").table()["time"].to_numpy(float))
    n_hold = np.isposinf(
        (petab / "holdout_measurements").table()["time"].to_numpy(float)
    )
    check(
        "the fitted problem carries them, training and held out",
        int(n_train.sum()) == 2 and int(n_hold.sum()) == 1,
        f"{int(n_train.sum())} training, {int(n_hold.sum())} held out",
    )
    steady = ((work(run, 0) / "cost").get(None) or {}).get("steady_state") or {}
    posteq = [
        r["posteq"]
        for r in steady.get("per_condition") or []
        if (r.get("posteq") or {}).get("ran")
    ]
    check(
        "the probe read AMICI's post-equilibration for both training conditions, "
        "each settled",
        steady.get("posteq_used") is True
        and len(posteq) == 2
        and all(1 in p["status"] for p in posteq),
        json.dumps(steady.get("per_condition")),
    )
    ev = (rnd(run, 0) / "evaluation").get(None) or {}
    fit = ev.get("fit") or []
    check(
        "the fit metrics are finite over every training series",
        len(fit) == 2 and all(math.isfinite(float(f["rmse"])) for f in fit),
        str(fit),
    )
    groups = (ev.get("holdout") or {}).get("groups") or []
    check(
        "the held-out condition is scored with its steady-state row",
        len(groups) == 1
        and groups[0].get("n") == 13
        and math.isfinite(float(groups[0].get("nrmse"))),
        str(groups),
    )
    html = reports_dir(run) / "round_0" / "report" / "report.html"
    text = html.read_text() if html.exists() else ""
    check(
        "the round report renders its data and fit figures with them",
        bool(text)
        and "fit grid unavailable" not in text
        and "data figure for obs_pR unavailable" not in text,
        str(html),
    )
    run.store.remove()


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        test_the_data_gate_lets_steady_state_through()
        test_a_time_cell_written_inf_is_a_number()
        test_the_roadrunner_path_reads_the_steady_state()
        test_a_slow_system_is_read_where_it_settles()
        test_the_s3_battery_passes_with_steady_state_rows()
        test_the_signals_keep_steady_state_off_the_curves()
        test_the_raw_reading_takes_a_time_inf_cell(root)
        test_held_out_coverage_reads_the_band_at_steady_state()
        test_the_residual_statistics_read_the_time_course()
        test_the_figures_draw_a_steady_state_column()
        test_the_budget_card_reports_post_equilibration()
        if quick_tier():
            print(
                "  (reduced effort: the AMICI compile and the end-to-end run "
                "are full-effort steps)"
            )
        else:
            test_amici_reads_the_same_steady_state()
            test_a_supplied_problem_with_steady_state_rows_runs(root)
    return finish(
        "\nSTEADY STATE",
        "\nSTEADY STATE OK — a time-inf measurement passes S2, is read at the "
        "condition's steady state by roadrunner and by AMICI, is scored against "
        "the band's steady state, is drawn in its own column, and a supplied "
        "problem with such rows runs to its report",
    )


if __name__ == "__main__":
    sys.exit(main())
