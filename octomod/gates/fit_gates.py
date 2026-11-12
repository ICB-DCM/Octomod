"""S6 post-fit gates: is the optimisation itself trustworthy?

All T2 — thresholds declared in the workflow spec, never by the agent, and
verdicts carry the optimiser configuration with them (finite-sample caveat).
"""

from __future__ import annotations

import numpy as np

from octomod.gates import GateResult, gate


def make_fit_gates(summary: dict, spec) -> list:
    """The post-fit gates for one multistart result.

    `summary` is the estimation summary: fvals (sorted ascending, may contain
    inf), best_grad_norm, n_starts, at_bounds (parameter ids), n_data, best_fval.
    """
    fvals = np.asarray(summary["fvals"], dtype=float)
    finite = fvals[np.isfinite(fvals)]

    @gate("estimation_waterfall_plateau", "T2")
    def g_waterfall():
        k = int(spec.get("gates.waterfall.k", 3))
        eps = float(spec.get("gates.waterfall.eps", 0.5))
        if len(finite) == 0:
            return GateResult(
                "estimation_waterfall_plateau",
                "T2",
                False,
                detail="no start converged to a finite objective",
            )
        n_plateau = int(np.sum(finite <= finite.min() + eps))
        passed = n_plateau >= k
        return GateResult(
            "estimation_waterfall_plateau",
            "T2",
            passed,
            value=n_plateau,
            threshold=f">={k} starts within {eps} of best",
            detail=f"best {finite.min():.4f}; plateau {n_plateau}/{len(finite)} "
            f"finite starts",
        )

    @gate("estimation_gradient_norm", "T2")
    def g_grad():
        # The projected gradient: the raw norm also counts components at active
        # bounds that point out of the box, which no optimiser may follow. The
        # raw norm stays in the detail.
        tol = float(spec.get("gates.grad_norm_tol", 10.0))
        raw = summary.get("best_grad_norm")
        gnorm = summary.get("best_projected_grad_norm")
        if gnorm is None:
            gnorm = raw  # a summary without the projected norm
        if gnorm is None:
            return GateResult(
                "estimation_gradient_norm",
                "T2",
                True,
                blocking=False,
                detail="gradient unavailable from optimiser; skipped",
            )
        parked = summary.get("grad_at_active_bounds") or []
        nonfinite = summary.get("grad_nonfinite") or []
        detail = "projected gradient norm at the optimum (scaled space"
        if parked:
            detail += (
                f"; raw {float(raw):.4g}, of which {len(parked)} parameter(s) "
                f"parked at a bound point out of the box: "
                + ", ".join(f"{p['id']} ({p['edge']})" for p in parked[:12])
                + (" …" if len(parked) > 12 else "")
            )
        detail += ")"
        if nonfinite:
            detail += f"; NON-FINITE gradient component(s): {', '.join(nonfinite[:8])}"
        return GateResult(
            "estimation_gradient_norm",
            "T2",
            gnorm <= tol,
            value=round(float(gnorm), 4),
            threshold=tol,
            detail=detail,
        )

    @gate("estimation_integration_failures", "T2")
    def g_fail():
        max_frac = float(spec.get("gates.max_frac_integration_failures", 0.3))
        frac = 1.0 - len(finite) / max(len(fvals), 1)
        passed = frac <= max_frac
        return GateResult(
            "estimation_integration_failures",
            "T2",
            passed,
            value=round(frac, 3),
            threshold=max_frac,
            detail="fraction of starts with non-finite objective — a plateau of "
            "survivors over a field of crashes is survivorship, not convergence",
        )

    @gate("estimation_parameters_at_bounds", "T2")
    def g_bounds():
        at_bounds = summary.get("at_bounds", [])
        return GateResult(
            "estimation_parameters_at_bounds",
            "T2",
            True,
            blocking=False,
            value=at_bounds,
            detail=(
                "no estimated parameter at a bound"
                if not at_bounds
                else f"AT BOUND (flag, carried into the report): {at_bounds}"
            ),
        )

    return [g_waterfall, g_grad, g_fail, g_bounds]
