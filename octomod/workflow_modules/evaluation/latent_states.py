"""Are the unmeasured states plausible at the fit?

S1 screens non-negativity at nominal parameters only. Three deterministic
checks at the MLE, in every condition:

  non-negativity   a negative concentration means the fitted model left the
                   physical domain to buy likelihood
  conservation     a structural total that drifts at the fit means
                   integration error or a stoichiometry the fit exploits
  declared ranges  a range the intent declares for a state

Advisory, except a range the intent declares itself: that is hard.
"""

from __future__ import annotations

import numpy as np

from octomod.workflow_modules.model.simwrap import RRModel, SimError


def _totals(sbml: str) -> list[dict]:
    """Conserved moiety relations, as {label, coefficients}.

    A conservation relation y satisfies y.T @ S == 0, so with `svd(S.T)` the
    relations are the rows of vh beyond the rank, vectors over species (the
    columns of u would be the flux modes, in reaction space).

    An SVD basis is arbitrary, so only a relation whose non-zero coefficients
    share one sign is reported: a moiety total is a non-negative combination
    of species, and a mixed-sign vector is a basis artefact.
    """
    try:
        model = RRModel(sbml)
        S = np.asarray(model.rr.getFullStoichiometryMatrix(), dtype=float)
        ids = list(model.species_ids)
    except Exception:
        return []
    if S.size == 0 or S.shape[0] != len(ids):
        return []
    try:
        _u, sv, vh = np.linalg.svd(S.T)
    except np.linalg.LinAlgError:
        return []
    tol = max(S.shape) * np.finfo(float).eps * (sv[0] if sv.size else 1.0)
    rank = int((sv > tol).sum())
    out: list[dict] = []
    for row in vh[rank:]:
        vec = np.asarray(row, dtype=float)
        big = np.abs(vec) > 1e-8
        if big.sum() < 2:
            continue
        signs = np.sign(vec[big])
        if not (np.all(signs > 0) or np.all(signs < 0)):
            continue  # a basis artefact, not a moiety total
        vec = vec * float(signs[0])
        scale = float(np.min(np.abs(vec[big])))
        if scale <= 0:
            continue
        coefs = {ids[i]: float(vec[i] / scale) for i in range(len(ids)) if big[i]}
        label = " + ".join(
            (sid if abs(c - 1.0) < 1e-6 else f"{c:g}*{sid}") for sid, c in coefs.items()
        )
        out.append({"label": label, "coefficients": coefs})
    return out


def screen(
    sbml: str,
    t_end: float,
    conditions: dict[str, dict],
    best: dict,
    ranges: dict | None = None,
    nonneg_tol: float = -1e-6,
) -> dict:
    """Simulate at the MLE in every condition and report what is implausible.

    `conditions` is {condition_id: overrides}; `ranges` is
    {species_or_expression: [lo, hi]} declared by the intent.
    """
    ranges = ranges or {}
    totals = _totals(sbml)
    findings: list[dict] = []
    checked = 0
    for cond_id, overrides in (conditions or {"nominal": {}}).items():
        # `best` arrives already filtered to names the model knows: passing an
        # observable or noise parameter as an override RAISES, and a raised
        # simulation reads as an errored row rather than a finding
        merged = {**best, **(overrides or {})}
        try:
            traj = RRModel(sbml).simulate(float(t_end), n_points=101, overrides=merged)
        except (SimError, Exception) as exc:
            findings.append(
                {
                    "kind": "simulation",
                    "condition": cond_id,
                    "hard": False,
                    "detail": f"could not simulate at the MLE: {exc}",
                }
            )
            continue
        checked += 1
        for sid, series in traj.items():
            if sid == "time":
                continue
            worst = float(np.min(series))
            if worst < nonneg_tol:
                findings.append(
                    {
                        "kind": "negative_state",
                        "condition": cond_id,
                        "state": sid,
                        "hard": False,
                        "value": worst,
                        "detail": f"{sid} reaches {worst:.3g} at the MLE — the "
                        f"fitted model leaves the physical domain",
                    }
                )
        for relation in totals:
            coefs = relation["coefficients"]
            label = relation["label"]
            if any(sid not in traj for sid in coefs):
                continue
            total = sum(
                float(c) * np.asarray(traj[sid], dtype=float)
                for sid, c in coefs.items()
            )
            start = float(total[0])
            scale = abs(start) if abs(start) > 1e-12 else float(np.max(np.abs(total)))
            if scale <= 1e-12:
                continue
            rel = float(np.max(np.abs(total - start)) / scale)
            if rel > 1e-4:
                findings.append(
                    {
                        "kind": "conservation",
                        "condition": cond_id,
                        "state": label,
                        "hard": False,
                        "value": rel,
                        "detail": f"{label} is structurally conserved but moves "
                        f"{rel:.2%} at the MLE — integration error, or a "
                        f"stoichiometry the fit exploits",
                    }
                )
        for expr, bounds in ranges.items():
            if expr not in traj:
                continue
            try:
                lo, hi = float(bounds[0]), float(bounds[1])
            except (TypeError, ValueError, IndexError):
                continue
            series = np.asarray(traj[expr], dtype=float)
            if float(np.min(series)) < lo or float(np.max(series)) > hi:
                findings.append(
                    {
                        "kind": "declared_range",
                        "condition": cond_id,
                        "state": expr,
                        "hard": True,
                        "detail": f"{expr} spans {float(np.min(series)):.3g} to "
                        f"{float(np.max(series)):.3g} at the MLE, outside "
                        f"the declared [{lo:g}, {hi:g}]",
                    }
                )
    return {
        "conditions_checked": checked,
        "conserved_totals": [t["label"] for t in totals],
        "declared_ranges": {k: list(v) for k, v in ranges.items()},
        "findings": findings,
        "hard_failures": [f for f in findings if f.get("hard")],
    }


def card_lines(result: dict) -> list[str]:
    findings = result.get("findings") or []
    if not findings:
        n = result.get("conditions_checked", 0)
        if not n:
            return []
        return [
            f"latent states plausible at the fit in all {n} condition(s): "
            f"non-negative, and {len(result.get('conserved_totals') or [])} "
            f"structural total(s) held"
        ]
    out = ["⚑ LATENT STATES AT THE FIT — states nobody measured:"]
    for f in findings[:4]:
        mark = "HARD (the intent declared this range)" if f.get("hard") else "advisory"
        out.append(f"  · [{f['condition']}] {str(f['detail'])[:120]} ({mark})")
    if len(findings) > 4:
        out.append(f"  · … {len(findings) - 4} more, in the report")
    return out
