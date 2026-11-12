"""Identifiability screen: the Fisher information at the MLE, reported as a
SPECTRUM, never a rank verdict (full rank proves nothing).

The report carries the eigenvalue spread in decades and which parameter
COMBINATIONS the smallest eigenvalues leave flat. The FIM comes from AMICI
residual sensitivities (J^T J in scaled space), else finite differences of the
residuals, else of the gradient (observed information); the result names which.
The residuals are read with AMICI's sigma residuals on, as the structural probe
reads them (`SigmaResiduals`), so which of the three it is does not depend on
what ran earlier in the process.
"""

from __future__ import annotations

import re

import numpy as np


class SigmaResiduals:
    """AMICI's sigma residuals, on for the residual reads and restored after.

    Residual mode on a problem that estimates a noise parameter refuses without
    them ("Cannot use least squares solver with parameter dependent sigma"),
    until one residual call with sensitivities has passed on that objective:
    pyPESTO checks once per objective and then stops checking. A reader that
    did not set them would get a Jacobian without the sigma rows after such a
    call and a refusal before it, i.e. a result that depends on what ran
    earlier in the process. With them on the call never refuses, and the
    sigmas are constrained as the likelihood's log-sigma terms constrain them.
    """

    def __init__(self, problem):
        model = getattr(getattr(problem, "objective", None), "amici_model", None)
        self._get = getattr(model, "getAddSigmaResiduals", None) or getattr(
            model, "get_add_sigma_residuals", None
        )
        self._set = getattr(model, "setAddSigmaResiduals", None) or getattr(
            model, "set_add_sigma_residuals", None
        )
        self._before = None

    def __enter__(self):
        if self._get is not None and self._set is not None:
            self._before = bool(self._get())
            self._set(True)
        return self

    def __exit__(self, *exc):
        if self._before is not None:
            self._set(self._before)
        return False


def requires_forward_sensitivities() -> str:
    """Why the FIM path needs `SensitivityMethod.forward`.

    Adjoint computes the objective gradient without forming the per-residual
    Jacobian, so there is no `sres` for `FIM = J^T J`; the finite-difference
    fallback costs 2n extra solves and is less accurate, so the report says why.
    """
    return (
        "the FIM is J^T J over per-residual sensitivities (`sres`), which "
        "AMICI produces under SensitivityMethod.forward only — adjoint "
        "computes the objective gradient without forming J at all"
    )


def sensi_method_note(problem) -> dict:
    """What the live solver's sensitivity method is, and what that costs this
    screen: under adjoint (approved at the cost gate) the FIM falls back to
    finite differences, and the report says so where the number is shown."""
    solver = getattr(getattr(problem, "objective", None), "amici_solver", None)
    getter = getattr(solver, "get_sensitivity_method", None) or getattr(
        solver, "getSensitivityMethod", None
    )
    if getter is None:
        return {
            "known": False,
            "why": "this AMICI exposes no sensitivity-method getter",
        }
    try:
        value = int(getter())
    except Exception as e:
        return {"known": False, "why": f"{type(e).__name__}: {e}"}
    try:
        import amici.sim.sundials as sd

        adjoint = int(sd.SensitivityMethod.adjoint)
        forward = int(sd.SensitivityMethod.forward)
    except Exception:
        adjoint, forward = 2, 1
    name = {forward: "forward", adjoint: "adjoint"}.get(value, str(value))
    return {
        "known": True,
        "sensi_method": name,
        "sres_available": name == "forward",
        "requires": requires_forward_sensitivities(),
        "consequence": (
            "FIM = J^T J from AMICI residual sensitivities"
            if name == "forward"
            else "NO `sres` under adjoint — the FIM falls back to finite "
            "differences of the residual vector (2n extra solves, lower "
            "accuracy). This is a consequence of the sensitivity method "
            "approved at the cost gate, not a model or data problem."
        ),
    }


def _residuals(problem, x_scaled: np.ndarray, sensi: bool):
    """(res, sres | None) via the objective's residual mode, or (None, None)."""
    try:
        import pypesto.C as C

        out = problem.objective(
            x_scaled,
            sensi_orders=(0, 1) if sensi else (0,),
            mode=C.MODE_RES,
            return_dict=True,
        )
        res = (
            np.asarray(out.get("res"), dtype=float)
            if out.get("res") is not None
            else None
        )
        sres = out.get("sres") if sensi else None
        sres = np.asarray(sres, dtype=float) if sres is not None else None
        return res, sres
    except Exception:
        return None, None


def residuals(problem, x_scaled: np.ndarray, sensi: bool):
    """Public name for the residual-mode reader, so the structural-flatness
    screen (`structural_nulls.py`) reads the SAME Jacobian as this one."""
    return _residuals(problem, x_scaled, sensi)


def combination_text(comp: dict) -> str:
    """Public name: a direction's composition as the text both screens print."""
    return _combination_text(comp)


def fim_at_mle(
    problem,
    x_scaled: np.ndarray,
    x_names: list[str],
    scales: dict[str, str] | None = None,
    flat_decades: float = 8.0,
    loading_min: float = 0.3,
    jacobian_out: dict | None = None,
) -> dict:
    """Fisher information at the MLE for the FREE parameters, in the scaled
    space the optimiser saw. Returns the spectrum and the flat combinations.

    `jacobian_out`, when given, receives the residual Jacobian under `"J"` if
    AMICI's residual sensitivities produced it, so the structural re-check at
    the fit reads this screen's Jacobian instead of computing it again."""
    x_scaled = np.asarray(x_scaled, dtype=float)
    free = list(problem.x_free_indices)
    names = [x_names[i] for i in free]
    n = len(free)
    method = None
    fim = None

    # The objective takes the FREE vector; `x_scaled` may arrive over every
    # parameter, fixed ones included, so it is sliced once here.
    x_free = x_scaled[free] if len(x_scaled) == len(x_names) else x_scaled

    # The residual-sensitivity path requires forward sensitivities: record the
    # solver's setting so a finite-difference fallback can name its cause.
    sensi_note = sensi_method_note(problem)

    # every residual read under one setting, the probe's: sigma residuals on
    with SigmaResiduals(problem):
        res, sres = _residuals(problem, x_free, sensi=True)
        if sres is not None and sres.ndim == 2 and sres.shape[1] >= n:
            J = sres[:, free] if sres.shape[1] == len(x_names) else sres[:, :n]
            fim = J.T @ J
            method = (
                "residual sensitivities (AMICI, sigma residuals included) at the "
                "MLE, FIM = J^T J"
            )
            if jacobian_out is not None:
                jacobian_out["J"] = J
        if fim is None and res is not None:
            J = np.zeros((len(res), n))
            h = 1e-4
            for k in range(n):
                xp = x_free.copy()
                xp[k] += h
                xm = x_free.copy()
                xm[k] -= h
                rp, _ = _residuals(problem, xp, sensi=False)
                rm, _ = _residuals(problem, xm, sensi=False)
                if rp is None or rm is None:
                    J = None
                    break
                J[:, k] = (rp - rm) / (2 * h)
            if J is not None:
                fim = J.T @ J
                method = (
                    "finite differences of the residual vector at the MLE, "
                    "FIM = J^T J"
                    + (
                        " — AMICI residual sensitivities were unavailable because "
                        "the solver is set to adjoint: "
                        + requires_forward_sensitivities()
                        if sensi_note.get("known")
                        and not sensi_note.get("sres_available")
                        else ""
                    )
                )
    if fim is None:
        # observed information: finite differences of the gradient
        try:

            def grad(x):
                return np.asarray(problem.objective(x, sensi_orders=(1,)), dtype=float)

            gf = grad(x_free)
            gf = gf[free] if len(gf) == len(x_names) else gf
            H = np.zeros((n, n))
            h = 1e-4
            for k in range(n):
                xp = x_free.copy()
                xp[k] += h
                gp = grad(xp)
                gp = gp[free] if len(gp) == len(x_names) else gp
                H[:, k] = (gp - gf) / h
            fim = 0.5 * (H + H.T)
            method = (
                "finite differences of the gradient at the MLE (observed information)"
            )
        except Exception as e:
            return {
                "available": False,
                "note": f"FIM unavailable: {type(e).__name__}: {e}",
            }

    fim = 0.5 * (fim + fim.T)
    eigvals, eigvecs = np.linalg.eigh(fim)
    order = np.argsort(eigvals)[::-1]
    eigvals, eigvecs = eigvals[order], eigvecs[:, order]
    pos = np.clip(eigvals, 1e-300, None)
    log10 = np.log10(pos)
    top = float(log10[0]) if n else 0.0
    flat = []
    for k in range(n):
        if eigvals[k] <= 0 or top - log10[k] >= flat_decades:
            comp = {
                names[j]: round(float(eigvecs[j, k]), 3)
                for j in range(n)
                if abs(eigvecs[j, k]) >= loading_min
            }
            flat.append(
                {
                    "eigenvalue_log10": (
                        None if eigvals[k] <= 0 else round(float(log10[k]), 3)
                    ),
                    "decades_below_largest": (
                        None if eigvals[k] <= 0 else round(top - float(log10[k]), 2)
                    ),
                    "composition": comp,
                    "reads_as": _combination_text(comp),
                }
            )
    return {
        "available": True,
        "method": method,
        "space": "scaled parameter space (as optimised)",
        "n_free": n,
        "x_names": names,
        "eigenvalues_log10": [
            None if v <= 0 else round(float(np.log10(v)), 3) for v in eigvals
        ],
        "spread_decades": round(float(top - log10[-1]), 2) if n else 0.0,
        "flat_decades_threshold": flat_decades,
        "flat_directions": flat,
        "eigenvector_composition_smallest": (
            {names[j]: round(float(eigvecs[j, -1]), 3) for j in range(n)} if n else {}
        ),
        # FIM_pp, the curvature along one parameter with the others held fixed:
        # the profile projection's low end reads its quadratic half-width here
        "diagonal_scaled": {
            names[j]: (float(fim[j, j]) if np.isfinite(fim[j, j]) else None)
            for j in range(n)
        },
        "note": (
            "local, necessary-condition screen at one point: a direction this many "
            "decades below the largest eigenvalue is a parameter COMBINATION the data "
            "barely constrain (sloppy-model register); full rank proves nothing. "
            "Report the spectrum, never a rank verdict."
        ),
    }


def _combination_text(comp: dict) -> str:
    if not comp:
        return "(no single parameter dominates this direction)"
    parts = []
    for name, w in sorted(comp.items(), key=lambda kv: -abs(kv[1])):
        parts.append(f"{'+' if w >= 0 else '-'}{abs(w):.2f}*log({name})")
    return " ".join(parts).lstrip("+")


COMBINATION_PREFIX = "flat combination (FIM): "

# The marker that says "this entry is a parameter COMBINATION, not an id", and
# the term shape its weights are written in. Matched loosely on the way back in:
# an agent that retypes the entry is echoing prose.
_COMBINATION_MARKER = "flat combination"
_LOG_TERM = re.compile(r"log\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")


def computed_flat_combinations(ident: dict) -> list[str]:
    """Entries for the machine-computed `cannot_distinguish` reference: one per
    flat direction, as text the interpretation agent must echo verbatim."""
    if not ident or not ident.get("available"):
        return []
    return [
        f"{COMBINATION_PREFIX}{d['reads_as']}"
        for d in ident.get("flat_directions", [])
        if d.get("composition")
    ]


def combination_key(entry: object) -> str | None:
    """The stable identity of a flat-combination entry, or None if it is not
    one. `flat:` plus the parameter ids it names, sorted.

    The blocking consistency gate compares the interpreter's echoed
    `cannot_distinguish` with the computed list. A weight's spelling (1.0 vs
    1.00, a U+2212 minus) and a term's position carry no claim; the set of
    parameters in the flat direction does. Used on both sides of the comparison.
    """
    # collapse whitespace first, so "flat  combination" still finds the marker
    text = " ".join(str(entry).split())
    if _COMBINATION_MARKER not in text.casefold():
        return None
    ids = sorted(set(_LOG_TERM.findall(text)))
    # no key without a parameter: an empty key would make every unparseable
    # paraphrase equal to every other
    return f"flat:{'|'.join(ids)}" if ids else None
