"""What the compiled model costs and whether the integrator has converged.

Measured at the compile+probe module, before the budget gate: trajectories at
the declared tolerance against `tighten_factor` tighter (is the ODE solution
right?), residual against sensitivity timings (the forward-vs-adjoint
proposal), and pre- and post-equilibration per condition (reporting only). Nothing here
decides; the engine measures and proposes, and the human approves at the gate.
"""

from __future__ import annotations

import time

import numpy as np


def _states(rdatas) -> list[np.ndarray]:
    return [np.asarray(r.x, dtype=float) for r in rdatas]


def _worst_rel_diff(a: list[np.ndarray], b: list[np.ndarray]) -> tuple[float, str]:
    """Worst |Δ| / scale over every state, time point and condition.

    Scaled by the LOOSER run's own magnitude, floored by its largest value so a
    state that passes through zero does not manufacture an infinite relative
    difference out of a rounding-level absolute one.
    """
    worst, where = 0.0, "no comparable trajectory"
    for i, (xa, xb) in enumerate(zip(a, b, strict=False)):
        if xa.shape != xb.shape or xa.size == 0:
            continue
        scale = np.maximum(np.abs(xa), np.max(np.abs(xa)) * 1e-6)
        scale[scale == 0] = 1.0
        rel = np.abs(xa - xb) / scale
        k = int(np.argmax(rel))
        if float(rel.flat[k]) > worst:
            t_i, s_i = np.unravel_index(k, rel.shape)
            worst = float(rel.flat[k])
            where = f"condition {i}, state {s_i}, time index {t_i}"
    return worst, where


def tolerance_agreement(problem, spec, x_free) -> dict:
    """Simulate twice — declared, then `tighten_factor` tighter — and compare.

    Always restores the declared settings afterwards, so the estimation that
    follows runs on what the card described.
    """
    from octomod.workflow_modules.estimation import solver_settings as _ss

    objective = getattr(problem, "objective", None)
    solver = getattr(objective, "amici_solver", None)
    model = getattr(objective, "amici_model", None)
    if solver is None:
        return {"available": False, "why": "no AMICI solver on this objective"}

    declared = _ss.flatten_spec(spec)
    factor = float(spec.get("simulation.tighten_factor", 100) or 100)
    limit = float(spec.get("simulation.traj_rel_agree", 1e-3) or 1e-3)
    atol = float(declared.get("atol") or solver.get_absolute_tolerance())
    rtol = float(declared.get("rtol") or solver.get_relative_tolerance())

    def _sim() -> tuple[list[np.ndarray], list[int]]:
        out = objective(x_free, return_dict=True, sensi_orders=(0,))
        rd = out.get("rdatas") or []
        return _states(rd), [int(r.status) for r in rd]

    try:
        _ss.apply_amici(solver, model, {"atol": atol, "rtol": rtol})
        t0 = time.perf_counter()
        loose, st_loose = _sim()
        loose_s = time.perf_counter() - t0
        _ss.apply_amici(solver, model, {"atol": atol / factor, "rtol": rtol / factor})
        t0 = time.perf_counter()
        tight, st_tight = _sim()
        tight_s = time.perf_counter() - t0
    except Exception as e:
        return {"available": False, "why": f"{type(e).__name__}: {e}"}
    finally:
        # the estimation that follows must run on what the card described
        _ss.apply_amici(solver, model, {"atol": atol, "rtol": rtol})

    if not loose or not tight:
        return {"available": False, "why": "the objective returned no rdatas"}
    worst, where = _worst_rel_diff(loose, tight)
    agrees = worst <= limit
    return {
        "available": True,
        "declared": {"atol": atol, "rtol": rtol},
        "tightened": {"atol": atol / factor, "rtol": rtol / factor},
        "tighten_factor": factor,
        "worst_rel_diff": float(worst),
        "worst_at": where,
        "threshold": limit,
        "agrees": bool(agrees),
        "declared_s": round(loose_s, 4),
        "tightened_s": round(tight_s, 4),
        "all_integrated": bool(
            all(s == 0 for s in st_loose) and all(s == 0 for s in st_tight)
        ),
        "reading": (
            f"declared and {factor:g}x-tighter trajectories agree to "
            f"{worst:.2e} (limit {limit:.0e})"
            if agrees
            else f"THE DECLARED TOLERANCE IS WRONG FOR THIS MODEL: tightening "
            f"by {factor:g}x moves the trajectory by {worst:.2e}, over the "
            f"{limit:.0e} limit, worst at {where}. Every gate verdict and "
            f"every fit below this point inherits that error. Proposed: "
            f"atol {atol / factor:.1e}, rtol {rtol / factor:.1e}."
        ),
        "proposal": (
            None if agrees else {"atol": atol / factor, "rtol": rtol / factor}
        ),
    }


# What `adjoint` costs beside what it saves: it removes the per-residual
# sensitivities the FIM Hessian is built from, so Fides falls back to BFGS.
# Quoted by the probe's proposal and by the budget card's note form.
ADJOINT_CONSEQUENCE = (
    "adjoint also removes the FIM Hessian (no per-residual sensitivities), so "
    "Fides falls back to BFGS — starts can be several times SLOWER on a small "
    "model; worth it only when the sensitivity ratio exceeds ~20x or the model "
    "has more than ~50 estimated parameters. The 5-start probe is re-run WITH "
    "adjoint before any projection is trusted."
)


def sensitivity_probe(problem, x_free, spec) -> dict:
    """Time `sensi_orders=(0,)` and `(0,1)`; propose forward vs adjoint.

    Forward sensitivities cost roughly one extra solve per estimated
    parameter, so on a large model the gradient, not the residual, is what
    makes a fit unaffordable; the proposal is made from the timing ratio.
    """
    objective = getattr(problem, "objective", None)
    if objective is None:
        return {"available": False, "why": "no objective"}
    n_par = int(len(x_free))

    def _time(orders) -> tuple[float, dict | None, str | None]:
        t0 = time.perf_counter()
        try:
            out = objective(x_free, return_dict=True, sensi_orders=orders)
        except Exception as e:
            return time.perf_counter() - t0, None, f"{type(e).__name__}: {e}"
        return time.perf_counter() - t0, out, None

    res_s, res_out, res_err = _time((0,))
    sen_s, sen_out, sen_err = _time((0, 1))

    grad_ok, grad_note = False, None
    if sen_out is not None:
        g = np.asarray(sen_out.get("grad", []), dtype=float)
        grad_ok = bool(g.size and np.all(np.isfinite(g)))
        if g.size and not grad_ok:
            grad_note = "the gradient integrated but is not finite"
        elif not g.size:
            grad_note = "no gradient was returned"
    ratio = (sen_s / res_s) if res_s > 0 and sen_err is None else None

    threshold = float(spec.get("simulation.adjoint_when_ratio_over", 8.0) or 8.0)
    declared = spec.get("simulation.amici.sensi_method")
    proposal, why = None, None
    if declared:
        why = f"`simulation.amici.sensi_method` is declared {declared!r}; not proposing"
    elif ratio is None:
        why = "no ratio to propose from"
    elif ratio > threshold:
        proposal = "adjoint"
        why = (
            f"forward sensitivities cost {ratio:.1f}x the residual, over the "
            f"declared {threshold:g}x. Forward scales with the {n_par} "
            f"estimated parameters; adjoint does not. NOTE: adjoint removes "
            f"per-residual sensitivities (`sres`), so the FIM in "
            f"identifiability falls back to finite differences. {ADJOINT_CONSEQUENCE}"
        )
    else:
        proposal = "forward"
        why = (
            f"forward sensitivities cost {ratio:.1f}x the residual, under the "
            f"declared {threshold:g}x — forward is affordable and keeps "
            f"per-residual sensitivities for the FIM"
        )
    return {
        "available": res_err is None,
        "n_estimated": n_par,
        "residual_s": round(res_s, 4),
        "sensi_s": round(sen_s, 4),
        "ratio": round(ratio, 3) if ratio is not None else None,
        "gradient_computable": grad_ok,
        "gradient_note": grad_note,
        "residual_error": res_err,
        "sensi_error": sen_err,
        "adjoint_threshold": threshold,
        "proposed_sensi_method": proposal,
        "why": why,
    }


def _rdata_id(rdata) -> str | None:
    try:
        rid = str(getattr(rdata, "id", "") or "").rstrip("+")
        return rid or None
    except Exception:
        return None


def _equilibration(rdata, prefix: str) -> dict:
    """One condition's pre- or post-equilibration, from AMICI's `<prefix>_*`
    fields: status flags, whether it ran, the weighted residual it reached
    (below 1 is settled) and its time."""
    status = getattr(rdata, f"{prefix}_status", None)
    flags = [int(s) for s in status] if status is not None else []
    wrms = getattr(rdata, f"{prefix}_wrms", None)
    steps = getattr(rdata, f"{prefix}_numsteps", None)
    return {
        "status": flags,
        "ran": bool(any(f != 0 for f in flags)),
        "wrms": float(wrms) if wrms is not None and np.isfinite(wrms) else None,
        "cpu_time_s": float(getattr(rdata, f"{prefix}_cpu_time", 0.0) or 0.0) / 1e3,
        "numsteps": (
            [int(v) for v in np.asarray(steps).ravel()] if steps is not None else []
        ),
    }


def steady_state_report(problem, x_free) -> dict:
    """Did each steady state settle, per condition? Reporting only.

    Read from AMICI's own fields: `preeq_status` per condition, `preeq_wrms`
    (the weighted residual it reached) and `preeq_cpu_time` for the
    pre-equilibration, and the `posteq_*` twins for the post-equilibration a
    steady-state measurement (time `inf`) is read at. A problem that does
    neither reports every status `not_run` and says so.
    """
    objective = getattr(problem, "objective", None)
    if objective is None:
        return {"available": False, "why": "no objective"}
    try:
        out = objective(x_free, return_dict=True, sensi_orders=(0,))
    except Exception as e:
        return {"available": False, "why": f"{type(e).__name__}: {e}"}
    rows = []
    for i, r in enumerate(out.get("rdatas") or []):
        pre = _equilibration(r, "preeq")
        rows.append(
            {
                "condition_index": i,
                # AMICI's PEtab import names each simulation `<sim>+<preeq>`
                "condition": _rdata_id(r),
                **pre,
                # the steady state its `time = inf` rows are read at
                "posteq": _equilibration(r, "posteq"),
            }
        )
    any_ran = any(row["ran"] for row in rows)
    posteq_ran = any(row["posteq"]["ran"] for row in rows)
    if any_ran:
        reading = "pre-equilibration ran; see per-condition wrms and time"
    elif posteq_ran:
        reading = (
            "this problem does not pre-equilibrate (every preeq_status is "
            "not_run); its steady-state (time inf) measurements post-equilibrate "
            "under the settings in simulation.amici.steady_state"
        )
    else:
        reading = (
            "this problem does not pre-equilibrate (every preeq_status is "
            "not_run) — the settings in simulation.amici.steady_state are "
            "declared and applied but nothing here exercises them"
        )
    return {
        "available": True,
        "used": any_ran,
        "posteq_used": posteq_ran,
        "per_condition": rows,
        "reading": reading,
        "posteq_reading": (
            "post-equilibration ran for the steady-state (time inf) "
            "measurements; see per-condition posteq wrms and time"
            if posteq_ran
            else "no steady-state (time inf) measurement: nothing post-equilibrates"
        ),
    }
