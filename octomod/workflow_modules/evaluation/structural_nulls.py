"""Structurally flat directions: parameter combinations no output depends on.

Counted before the fit and reported as an indicator; AIC and BIC still charge
every estimated parameter. A structural symmetry (e.g. parameters entering only
as a product `w·Rtot`) is flat along the same log-parameter vector at every
point, while a merely sloppy direction is not, so the normalised residual
Jacobians at a few random points are stacked and a direction counts only if it
is flat at every one of them.

The points are drawn near the nominal parameter vector, not anywhere in the
bounds: on a stiff model most of the box does not integrate, and a probe that
samples there measures nothing. Nearness is what makes the count local, so it
is measured again at the fit (`recheck_at_mle`), where the information screen
has already computed the Jacobian: a direction flat near the nominal and flat
around the optimum is flat at two unrelated places in the box.
"""

from __future__ import annotations

import numpy as np

# the measurement lives in the record, per fitted problem — beside the
# candidate's `estimation` (`rounds/round_k/candidates/<id>/structural_nulls`),
# and the re-measurement at the optimum beside it (`…/structural_nulls_at_mle`)
KEY = "structural_nulls"
KEY_AT_MLE = "structural_nulls_at_mle"


def node(work):
    """Where a fitted problem's measurement lives: `work / "structural_nulls"`
    (`work` = `ctx.work`, the candidate's group)."""
    return work / KEY


def node_at_mle(work):
    """The re-measurement at the optimum: `work / "structural_nulls_at_mle"`."""
    return work / KEY_AT_MLE


# A weak single parameter is weak along the same vector at every point, so a few
# points cannot separate it from a symmetry, which is a combination: a
# one-parameter direction counts only below EXACT_TOL (a column exactly zero), a
# combination below rel_tol. RULE_VERSION tags records measured under this rule
# and this sampling; a record sampled anywhere in the bounds is measured again.
RULE_VERSION = 3
EXACT_TOL = 1.0e-12

# A pre-fit direction and one found at the fit are the same direction when the
# cosine between them (or between one and the other's span) reaches this.
SAME_DIRECTION_COS = 0.9


def _free_names(problem) -> list[str]:
    names = list(getattr(problem, "x_names", []) or [])
    free = list(getattr(problem, "x_free_indices", range(len(names))))
    return [names[i] for i in free] if names else [f"x{i}" for i in free]


def nominal_center(problem, petab_problem=None) -> tuple[np.ndarray, str]:
    """The free parameters' nominal values on the estimation scale, and their basis.

    Read from the PEtab parameter table (`x_nominal_scaled`, aligned with
    `x_ids`) by name, because a hierarchical problem drops its inner parameters
    from the optimiser's vector. A parameter without a finite nominal value, or a
    problem without a PEtab table, takes its box midpoint, and the basis says so.
    """
    lb = np.asarray(problem.lb, dtype=float)
    ub = np.asarray(problem.ub, dtype=float)
    names = _free_names(problem)
    mid = 0.5 * (lb + ub)
    nominal: dict[str, float] = {}
    if petab_problem is not None:
        try:
            nominal = {
                str(k): float(v)
                for k, v in zip(
                    petab_problem.x_ids, petab_problem.x_nominal_scaled, strict=False
                )
            }
        except Exception:  # an unreadable table is no nominal
            nominal = {}
    center = np.array([nominal.get(n, float("nan")) for n in names], dtype=float)
    missing = ~np.isfinite(center)
    center[missing] = mid[missing]
    if not nominal:
        return center, "the box midpoint (no nominal values on file)"
    if missing.any():
        return center, (
            f"the nominal parameter values (the box midpoint for "
            f"{int(missing.sum())} without one)"
        )
    return center, "the nominal parameter values"


def _near(center, spread: float, lb, ub, rng) -> np.ndarray:
    """One point: every coordinate within `spread` of `center`, clipped to the box."""
    step = rng.uniform(-spread, spread, size=len(center))
    return np.clip(center + step, lb, ub)


def _block(problem, x, n: int) -> np.ndarray | None:
    """The normalised residual Jacobian at `x`, or None where it is unavailable."""
    from octomod.workflow_modules.evaluation.identifiability import (
        SigmaResiduals,
        residuals,
    )

    # the information screen reads under the same setting (`SigmaResiduals`),
    # so the flat directions found are the model's, and a re-check at the fit
    # that reuses the screen's Jacobian reads the same rows
    with SigmaResiduals(problem):
        _res, sres = residuals(problem, x, sensi=True)
    return _normalised(problem, sres, n)


def _normalised(problem, sres, n: int) -> np.ndarray | None:
    if sres is None:
        return None
    sres = np.asarray(sres, dtype=float)
    if sres.ndim != 2 or not np.all(np.isfinite(sres)):
        return None
    J = sres[:, list(problem.x_free_indices)] if sres.shape[1] != n else sres
    top = np.linalg.norm(J, 2)
    if not np.isfinite(top) or top <= 0:
        return None
    return J / top


def _sample(problem, center, spread, n_points, seed, max_tries, lb, ub):
    """Up to `n_points` normalised Jacobians near `center`, and the tries spent."""
    n = int(lb.size)
    rng = np.random.default_rng(seed)
    blocks, tried = [], 0
    while len(blocks) < n_points and tried < max_tries:
        tried += 1
        block = _block(problem, _near(center, spread, lb, ub, rng), n)
        if block is not None:
            blocks.append(block)
    return blocks, tried


def _flat(blocks, names, rel_tol: float, loading_min: float) -> dict:
    """The directions flat at every block at once, by the counting rule."""
    from octomod.workflow_modules.evaluation.identifiability import combination_text

    n = len(names)
    S = np.vstack(blocks)
    _u, s, vt = np.linalg.svd(S, full_matrices=False)
    rel = s / s[0]
    flat_idx, weak, directions = [], [], []
    for i in range(len(rel)):
        if rel[i] >= rel_tol:
            continue
        v = vt[i]
        comp = {
            names[j]: round(float(v[j]), 3)
            for j in range(n)
            if abs(v[j]) >= loading_min
        }
        entry = {
            "relative_singular_value": float(rel[i]),
            "composition": comp,
            "reads_as": combination_text(comp),
            # the whole vector, so the check at the fit tests this direction and
            # not its rounded, truncated reading
            "vector": [float(x) for x in v],
        }
        if len(comp) <= 1 and rel[i] >= EXACT_TOL:
            weak.append(entry)  # one weak parameter, not a symmetry
            continue
        flat_idx.append(i)
        directions.append(entry)
    kept = [float(rel[i]) for i in range(len(rel)) if i not in flat_idx]
    return {
        "S": S,
        "s0": float(s[0]),
        "directions": directions,
        "weak": weak,
        "kept": kept,
    }


def measure(
    problem,
    *,
    n_points: int = 2,
    rel_tol: float = 1.0e-5,
    seed: int = 0,
    max_tries: int = 8,
    loading_min: float = 0.1,
    center=None,
    center_basis: str | None = None,
    spread: float = 0.5,
) -> dict:
    """Count the directions flat at every one of `n_points` points near `center`.

    Each point is `center` plus a uniform draw in ±`spread` per coordinate
    (scaled units: half a decade for a log10 parameter at 0.5), clipped to the
    bounds. Without a `center` the box midpoint is used.

    `problem` needs `lb`, `ub` (the FREE parameters, in the optimiser's scaled
    space), `x_names`, `x_free_indices`, and an objective answering residual
    mode with sensitivities — `identifiability.residuals` is the one reader of
    that, so both screens see the same Jacobian."""
    lb = np.asarray(problem.lb, dtype=float)
    ub = np.asarray(problem.ub, dtype=float)
    names = _free_names(problem)
    n = int(lb.size)
    if center is None:
        center, center_basis = 0.5 * (lb + ub), "the box midpoint (no centre given)"
    center = np.clip(np.asarray(center, dtype=float), lb, ub)
    basis = center_basis or "the given centre"
    spread = float(spread)
    blocks, tried = _sample(problem, center, spread, n_points, seed, max_tries, lb, ub)
    if len(blocks) < n_points:
        return {
            "available": False,
            "why": (
                f"residual sensitivities were available at {len(blocks)} of the "
                f"{tried} point(s) tried within ±{spread:g} (scaled units) of "
                f"{basis} (need {n_points}) — adjoint sensitivities, a "
                f"hierarchical objective, or integration failures even that "
                f"close to it"
            ),
            "n_estimated": n,
            "n_flat": 0,
            "center_basis": basis,
            "spread": spread,
        }
    found = _flat(blocks, names, rel_tol, loading_min)
    directions = found["directions"]
    kept = found["kept"]
    return {
        "available": True,
        "method": (
            f"residual sensitivities at {len(blocks)} random points within "
            f"±{spread:g} (scaled units) of {basis}, clipped to the bounds, each "
            "normalised, stacked; a direction counts only if it is flat at every "
            "point at once"
        ),
        "rule": RULE_VERSION,
        "n_estimated": n,
        "n_flat": len(directions),
        "k_effective": n - len(directions),
        "rel_tol": rel_tol,
        "exact_tol_single_parameter": EXACT_TOL,
        "weak_single_parameters": found["weak"],
        "smallest_counted_relative": min(
            (d["relative_singular_value"] for d in directions), default=None
        ),
        "smallest_not_counted_relative": min(kept) if kept else None,
        "directions": directions,
        "seed": seed,
        "center_basis": basis,
        "spread": spread,
        "center": {names[j]: round(float(center[j]), 6) for j in range(n)},
    }


def n_flat(rec: dict | None) -> int:
    return int((rec or {}).get("n_flat") or 0) if (rec or {}).get("available") else 0


def for_candidate(ctx) -> dict:
    """The candidate's measurement, from the record (`work / "structural_nulls"`),
    or measured now and written there. The probe measures it first (so the
    budget card can show it); selection reads it back, and measures it itself
    when the probe never ran — a fit reused from an earlier round is not
    probed."""
    where = node(ctx.work)
    try:
        rec = where.get(None)
        # a record measured under an earlier rule is measured again
        if isinstance(rec, dict) and rec.get("rule") == RULE_VERSION:
            return rec
    except Exception:
        pass
    try:
        from octomod.workflow_modules.estimation import estimation_settings

        problem, petab_problem, _s = estimation_settings.build(ctx)
        rec = measure_with_spec(problem, ctx.spec, petab_problem)
    except Exception as e:
        rec = {"available": False, "why": f"{type(e).__name__}: {e}", "n_flat": 0}
    where.put(rec)
    return rec


def measure_with_spec(problem, spec, petab_problem=None) -> dict:
    """`measure` under the spec's settings, centred on the nominal parameters."""
    center, basis = nominal_center(problem, petab_problem)
    return measure(
        problem,
        n_points=int(spec.get("gates.structural_nulls.n_points", 2)),
        rel_tol=float(spec.get("gates.structural_nulls.rel_tol", 1.0e-5)),
        seed=int(spec.require("estimation.seed")) + 17,
        center=center,
        center_basis=basis,
        spread=float(spec.get("gates.structural_nulls.spread", 0.5)),
    )


# ----------------------------------------------------------- at the fit


def _unit(v) -> np.ndarray | None:
    v = np.asarray(v, dtype=float)
    norm = float(np.linalg.norm(v))
    return v / norm if norm > 0 and np.isfinite(norm) else None


def recheck_at_mle(
    problem,
    x_mle,
    pre: dict | None,
    *,
    jacobian=None,
    n_points: int = 2,
    rel_tol: float = 1.0e-5,
    seed: int = 0,
    max_tries: int = 8,
    loading_min: float = 0.1,
    spread: float = 0.5,
) -> dict:
    """The pre-fit flat directions, checked again around the optimum.

    The stack is the Jacobian at the MLE — `jacobian`, the one the information
    screen already computed, when it has one — and `n_points` points within
    ±`spread` of the MLE, under the counting rule `measure` uses. Each pre-fit
    direction is `confirmed_at_mle` when its own vector is still flat in that
    stack (its relative singular value there below the tolerance it was counted
    under); a direction flat at the fit that no pre-fit direction spans is
    listed in `flat_at_mle_only`.
    """
    lb = np.asarray(problem.lb, dtype=float)
    ub = np.asarray(problem.ub, dtype=float)
    names = _free_names(problem)
    n = int(lb.size)
    x_mle = np.clip(np.asarray(x_mle, dtype=float), lb, ub)
    spread = float(spread)
    at_mle = _normalised(problem, jacobian, n) if jacobian is not None else None
    reused = at_mle is not None
    if at_mle is None:
        at_mle = _block(problem, x_mle, n)
    if at_mle is None:
        return {
            "available": False,
            "why": "no residual sensitivities at the MLE — adjoint sensitivities, "
            "a hierarchical objective or an integration failure at the optimum",
        }
    around, tried = _sample(problem, x_mle, spread, n_points, seed, max_tries, lb, ub)
    if len(around) < n_points:
        return {
            "available": False,
            "why": (
                f"residual sensitivities were available at {len(around)} of the "
                f"{tried} point(s) tried within ±{spread:g} of the MLE (need "
                f"{n_points})"
            ),
        }
    found = _flat([at_mle, *around], names, rel_tol, loading_min)
    S, s0 = found["S"], found["s0"]
    pre = pre or {}
    pre_available = bool(pre.get("available"))
    pre_dirs = list(pre.get("directions") or []) if pre_available else []
    checked, pre_vectors = [], []
    for d in pre_dirs:
        row = {
            "reads_as": d.get("reads_as"),
            "composition": d.get("composition"),
            "relative_singular_value_before": d.get("relative_singular_value"),
        }
        v = _unit(d.get("vector")) if d.get("vector") is not None else None
        if v is None or len(v) != n:
            row.update(
                confirmed_at_mle=None,
                why="the pre-fit record carries no full direction vector to test",
            )
        else:
            pre_vectors.append(v)
            along = float(np.linalg.norm(S @ v) / s0)
            tol = EXACT_TOL if len(d.get("composition") or {}) <= 1 else rel_tol
            row.update(
                confirmed_at_mle=bool(along < tol),
                relative_singular_value_at_mle=along,
                tolerance=tol,
            )
        checked.append(row)
    span = np.array(pre_vectors).T if pre_vectors else None
    missed = []
    for d in found["directions"]:
        u = _unit(d["vector"])
        if span is not None and u is not None:
            q, _r = np.linalg.qr(span)
            if float(np.linalg.norm(q.T @ u)) >= SAME_DIRECTION_COS:
                continue
        missed.append({k: v for k, v in d.items() if k != "vector"})
    confirmed = [r for r in checked if r.get("confirmed_at_mle") is True]
    not_confirmed = [r for r in checked if r.get("confirmed_at_mle") is False]
    return {
        "available": True,
        "method": (
            "the residual Jacobian at the MLE"
            + (" (the information screen's own)" if reused else "")
            + f" and at {len(around)} random points within ±{spread:g} (scaled "
            "units) of it, each normalised, stacked; each pre-fit direction is "
            "tested along its own vector"
        ),
        "rule": RULE_VERSION,
        "pre_fit_available": pre_available,
        "pre_fit_why": None if pre_available else pre.get("why", "no pre-fit record"),
        "n_pre_fit": len(pre_dirs),
        "directions": checked,
        "n_confirmed": len(confirmed),
        "n_not_confirmed": len(not_confirmed),
        "flat_at_mle_only": missed,
        "n_flat_at_mle": len(found["directions"]),
        "jacobian_reused": reused,
        "spread": spread,
        "seed": seed,
    }


def recheck_with_spec(problem, x_mle, pre, spec, jacobian=None) -> dict:
    """`recheck_at_mle` under the spec settings the pre-fit probe used."""
    return recheck_at_mle(
        problem,
        x_mle,
        pre,
        jacobian=jacobian,
        n_points=int(spec.get("gates.structural_nulls.n_points", 2)),
        rel_tol=float(spec.get("gates.structural_nulls.rel_tol", 1.0e-5)),
        seed=int(spec.require("estimation.seed")) + 29,
        spread=float(spec.get("gates.structural_nulls.spread", 0.5)),
    )


def recheck_line(rec: dict | None) -> str | None:
    """One line for the verdict card, the report and the ledger, or None."""
    if not rec:
        return None
    if not rec.get("available"):
        return (
            "structural flat directions at the fit: not re-checked — "
            f"{rec.get('why', '?')}"
        )
    checked = rec.get("directions") or []
    missed = rec.get("flat_at_mle_only") or []
    parts: list[str] = []
    if not rec.get("pre_fit_available"):
        # every direction flat at the fit is one the probe could not have found
        return "structural flat directions: not measured before the fit; " + (
            f"{len(missed)} flat at it: "
            + "; ".join(str(d["reads_as"]) for d in missed[:3])
            if missed
            else "none at it"
        )
    if not checked:
        parts.append("none before the fit")
    else:
        bad = [r for r in checked if r.get("confirmed_at_mle") is False]
        untested = [r for r in checked if r.get("confirmed_at_mle") is None]
        good = len(checked) - len(bad) - len(untested)
        if good:
            parts.append(f"{good} of {len(checked)} flat at the fit too")
        if bad:
            parts.append(
                "not flat at the fit: "
                + "; ".join(
                    f"{r['reads_as']} ({r['relative_singular_value_at_mle']:.0e} "
                    f"of the largest there)"
                    for r in bad[:3]
                )
                + (f" (+{len(bad) - 3} more)" if len(bad) > 3 else "")
            )
        if untested:
            parts.append(f"{len(untested)} not testable (no vector on file)")
    if missed:
        parts.append(
            f"{len(missed)} flat at the fit that the pre-fit probe did not find: "
            + "; ".join(str(d["reads_as"]) for d in missed[:3])
        )
    elif not checked:
        parts.append("none at it")
    return "structural flat directions: " + ", ".join(parts)


def card_lines(rec: dict | None) -> list[str]:
    """For the budget card: the structurally flat directions, as an indicator
    (the criterion charges every estimated parameter regardless)."""
    if not rec:
        return []
    if not rec.get("available"):
        return [f"structural flat directions: not measured — {rec.get('why', '?')}"]
    k, n = rec["n_flat"], rec["n_estimated"]
    where = (
        f"near {rec['center_basis']}" if rec.get("center_basis") else "random points"
    )
    if not k:
        sm = rec.get("smallest_not_counted_relative")
        gap = (
            f"; smallest singular value {sm:.1e} of the largest"
            if isinstance(sm, float)
            else ""
        )
        out = [
            f"structural flat directions: none among {n} estimated parameters "
            f"({where}{gap}) — AIC charges all {n}"
        ]
    else:
        out = [
            f"structural flat directions: {k} — parameter combination(s) no output "
            f"depends on {where} (an indicator; AIC still charges all {n} "
            f"estimated parameters; re-checked at the fit)"
        ]
        out += [f"  · {d['reads_as']}" for d in rec["directions"][:6]]
        if len(rec["directions"]) > 6:
            out.append(f"  (+{len(rec['directions']) - 6} more in the record ({KEY})")
    weak = rec.get("weak_single_parameters") or []
    if weak:
        out.append(
            f"  {len(weak)} weak single parameter(s), charged as usual (an effect, "
            f"however small, is not a symmetry): "
            + ", ".join(
                f"{d['reads_as']} ({d['relative_singular_value']:.0e})"
                for d in weak[:4]
            )
        )
    return out
