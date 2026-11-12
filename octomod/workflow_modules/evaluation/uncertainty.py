"""Prediction uncertainty from the profile-based confidence region.

The region is nllh <= best + chi2(alpha, df)/2 (df = n_free by default). Its
members are the profile points under that threshold plus rejection samples
from an ellipsoid fitted to them. With too few such points to fit an ellipsoid
the band is the envelope of the profile points alone, drawn without samples
and flagged as undersampled. The per-time min/max over their simulations is the
(1-alpha) band: parameter uncertainty only, observation noise is added where
bands meet data. A low acceptance rate is flagged: the band may be too narrow.
"""

from __future__ import annotations

import numpy as np

from octomod.gates.petab_gates import PetabTables


def _joint_threshold(alpha: float, df: int) -> float:
    from scipy.stats import chi2

    return float(chi2.ppf(alpha, df=df) / 2.0)


def confidence_region_band(
    problem,
    tables: PetabTables,
    profiles: dict,
    scales: dict,
    best: dict,
    best_nllh: float,
    conditions_times: dict,
    spec,
    rng_seed: int,
    inner: dict | None = None,
) -> dict:
    """Returns {alphas, n_sampled, kept per alpha, acceptance, bands:
    {label: {time, lo95, hi95, lo90, hi90, best}}} — or a 'note' explaining
    why it could not run. A band built from the profile skeleton alone carries
    `skeleton_only` and `skeleton_only_note`, and its acceptance is None for
    every alpha: no samples were drawn to accept."""
    alphas = [float(a) for a in spec.get("uncertainty.alphas", [0.95, 0.90])]
    alphas = sorted(alphas, reverse=True)
    n_samples = int(spec.get("uncertainty.n_box_samples", 400))
    x_names = list(problem.x_names)
    free_idx = list(problem.x_free_indices)
    free_names = [x_names[i] for i in free_idx]
    df_spec = spec.get("uncertainty.joint_df", "n_free")
    df = len(free_names) if df_spec == "n_free" else int(df_spec)

    missing = [
        p for p in free_names if p not in profiles or not profiles[p].get("path")
    ]
    if missing:
        return {
            "note": f"confidence-region band unavailable: no profile "
            f"curve for {missing}"
        }

    thr_widest = _joint_threshold(alphas[0], df)
    thresholds = {a: _joint_threshold(a, df) for a in alphas}
    rng = np.random.default_rng(rng_seed)
    lb = np.asarray(problem.lb_full, dtype=float)[free_idx]
    ub = np.asarray(problem.ub_full, dtype=float)[free_idx]

    # Profile points are re-optimised vectors with a known nllh: those under
    # the joint threshold are region members at no extra cost.
    name_to_col = {
        n: k for k, n in enumerate(profiles.get("_meta", {}).get("x_names", x_names))
    }
    seed_vecs, seed_nllh = [], []
    for pid, prof in profiles.items():
        if pid.startswith("_") or not isinstance(prof, dict):
            continue
        path = prof.get("path") or {}
        for vec, f in zip(
            path.get("x_full_scaled", []), path.get("nllh", []), strict=False
        ):
            if f <= best_nllh + thr_widest:
                seed_vecs.append([vec[name_to_col[n]] for n in free_names])
                seed_nllh.append(float(f))
    seeds = (
        np.asarray(seed_vecs, dtype=float)
        if seed_vecs
        else np.empty((0, len(free_names)))
    )
    seed_nllh = np.asarray(seed_nllh, dtype=float)

    # Proposal: an ellipsoid fitted to those points; its acceptance stays
    # roughly dimension-independent for near-quadratic regions. A full-rank fit
    # needs d+2 points. With fewer there is no proposal worth sampling (a box's
    # acceptance collapses with dimension), so the region is the skeleton alone
    # and the band says it is undersampled.
    d = len(free_names)
    x_best_scaled = np.array(
        [
            (np.log10(max(best[n], 1e-300)) if scales.get(n) == "log10" else best[n])
            for n in free_names
        ]
    )
    skeleton_only_reason = None
    if len(seeds) < d + 2:
        skeleton_only_reason = "too few points under the threshold to fit an ellipsoid"
    else:
        cloud = np.vstack([seeds, x_best_scaled[None, :]])
        C = np.cov(cloud.T) + 1e-10 * np.eye(d)
        try:
            L = np.linalg.cholesky(C)
            mah = np.sqrt(
                np.einsum(
                    "ij,ij->i",
                    (seeds - x_best_scaled) @ np.linalg.inv(C),
                    (seeds - x_best_scaled),
                )
            )
            radius = (
                float(np.max(mah))
                * float(spec.get("uncertainty.ellipsoid_inflate", 1.5))
                or 1.0
            )
        except np.linalg.LinAlgError:
            skeleton_only_reason = (
                "the points under the threshold do not span an ellipsoid"
            )
    if skeleton_only_reason is None:
        method = "profile-skeleton + adaptive-ellipsoid rejection"
        u = rng.standard_normal((n_samples, d))
        u /= np.linalg.norm(u, axis=1, keepdims=True)
        r = rng.random(n_samples) ** (1.0 / d)
        X = x_best_scaled + (u * r[:, None] * radius) @ L.T
        X = np.clip(X, lb, ub)
    else:
        method = f"profile skeleton only: {skeleton_only_reason}, no rejection samples"
        X = np.empty((0, d))

    nllh = np.empty(len(X))
    for k in range(len(X)):
        try:
            nllh[k] = float(problem.objective(X[k]))
        except Exception:
            nllh[k] = np.inf

    kept = {}
    for a, thr in thresholds.items():
        sampled = X[nllh <= best_nllh + thr]
        skel = seeds[seed_nllh <= best_nllh + thr] if len(seeds) else seeds
        kept[a] = np.vstack([skel, sampled]) if len(skel) else sampled
    # no samples drawn, no acceptance rate: None, never a 0 that reads as a
    # region nobody could hit
    acceptance = {
        a: (round(float(np.mean(nllh <= best_nllh + t)), 3) if len(X) else None)
        for a, t in thresholds.items()
    }

    # simulate every retained point (plus the best) per condition
    def unscale_vec(xrow) -> dict:
        out = dict(best)  # fixed parameters stay at their values
        for name, val in zip(free_names, xrow, strict=False):
            out[name] = float(10**val) if scales.get(name) == "log10" else float(val)
        return out

    # One ODE solve per (condition, time grid, parameter vector):
    # `simulate_observables` returns every observable at once, and a narrower
    # alpha's retained set is a subset of the wider one's.
    groups: dict[tuple[str, tuple], list[str]] = {}
    for (obs_id, cond_id), times in conditions_times.items():
        key = (cond_id, tuple(float(t) for t in times))
        groups.setdefault(key, []).append(obs_id)

    bands = {}
    for (cond_id, times_key), obs_ids in groups.items():
        times = np.asarray(times_key, dtype=float)
        best_sims = tables.simulate_observables(cond_id, times, param_override=best)
        # simulate the union of the retained points once; None marks a point
        # whose simulation failed, which is skipped
        sims_for: dict[bytes, dict | None] = {}
        for a in alphas:
            for xrow in kept[a]:
                k = np.asarray(xrow, dtype=float).tobytes()
                if k in sims_for:
                    continue
                try:
                    sims_for[k] = tables.simulate_observables(
                        cond_id, times, param_override=unscale_vec(xrow)
                    )
                except Exception:
                    sims_for[k] = None
        for obs_id in obs_ids:
            label = f"{obs_id}@{cond_id}"
            best_sim = best_sims[obs_id]
            env = {}
            for a in alphas:
                sims = [
                    s[obs_id]
                    for s in (
                        sims_for[np.asarray(x, dtype=float).tobytes()] for x in kept[a]
                    )
                    if s is not None
                ]
                if sims:
                    arr = np.vstack([best_sim] + sims)
                else:
                    arr = best_sim[None, :]
                env[a] = (arr.min(axis=0), arr.max(axis=0))
            bands[label] = {
                "time": [float(t) for t in times],
                "best": [float(v) for v in best_sim],
                **{f"lo{int(a * 100)}": [float(v) for v in env[a][0]] for a in alphas},
                **{f"hi{int(a * 100)}": [float(v) for v in env[a][1]] for a in alphas},
            }

    out = {
        "method": method,
        "n_skeleton_points": int(len(seeds)),
        "df": df,
        "alphas": alphas,
        "n_box_samples": int(len(X)),
        # n_kept includes the retained profile points, so it can exceed
        # n_box_samples; the split below keeps the counts from reading as a
        # contradiction
        "n_kept": {str(a): int(len(k)) for a, k in kept.items()},
        "n_kept_box_samples": {
            str(a): int((nllh <= best_nllh + thresholds[a]).sum()) for a in alphas
        },
        "n_kept_skeleton": {
            str(a): (
                int(len(seeds[seed_nllh <= best_nllh + thresholds[a]]))
                if len(seeds)
                else 0
            )
            for a in alphas
        },
        "acceptance": {str(a): acceptance[a] for a in alphas},
        "bands": bands,
    }
    floor = float(spec.get("uncertainty.min_acceptance_note", 0.05))
    rates = [v for v in acceptance.values() if v is not None]
    if rates and min(rates) < floor:
        out["note"] = (
            f"acceptance below {floor:.0%} — the confidence region "
            f"is a small corner of the proposal; the envelope may be "
            f"undersampled (raise n_box_samples)"
        )
    if skeleton_only_reason is not None:
        # The envelope of a handful of profile points is narrower than the
        # region they sit in: stated beside the band, never implied by it.
        out["skeleton_only"] = True
        out["skeleton_only_note"] = (
            f"confidence region undersampled: {skeleton_only_reason} "
            f"({len(seeds)} profile point(s) under the widest threshold; an "
            f"ellipsoid over {d} free parameter(s) needs at least {d + 2}), so no "
            f"rejection samples were drawn. The band is the envelope of those "
            f"points and the best fit, and is likely narrower than the region."
        )
    if inner:
        # Parameters solved analytically by the inner optimiser are never
        # profiled, so the band omits their contribution and is narrower than
        # the truth (on relative data, the scaling itself): stated, not implied.
        out["outer_only"] = sorted(inner)
        out["outer_only_note"] = (
            f"computed over the OUTER parameters only: "
            f"{', '.join(sorted(inner))} "
            f"{'was' if len(inner) == 1 else 'were'} solved analytically by the "
            f"inner optimiser, so no profile exists for "
            f"{'it' if len(inner) == 1 else 'them'} and "
            f"{'its' if len(inner) == 1 else 'their'} contribution to the "
            f"prediction uncertainty is NOT in this band. The band is therefore "
            f"narrower than the truth. Turn hierarchical estimation off to get "
            f"a band over every parameter."
        )
    return out
