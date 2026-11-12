"""Residual diagnostics rich enough to reason from.

The expansion agent is asked what a fitted model space was missing, a question
about residual structure that scalar summaries cannot answer. Per candidate:

  * the fit point by point per observable and condition, so an over- or
    under-shoot is visible as a shape rather than averaged away;
  * the sign-run structure and lag-1 autocorrelation (systematic or noise);
  * the fitted sigma against the assay's replicate noise floor, per observable;
  * a cross-model table: which candidate improved which measurement on the
    base, and which measurements no ingredient in the space touched;
  * the free control: condition pairs the model predicts identically, whose
    residual difference is pure noise and calibrates every other number;
  * `residual_forms`: each residual series of the selected model and the base
    fitted with the `curve_forms` library, and the series whose forms agree
    grouped into sentences ("exponential decay, τ 35–48 in population B, NK").
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _thin(n: int, cap: int) -> list[int]:
    """Indices of at most `cap` points, evenly spaced, endpoints kept."""
    if n <= cap:
        return list(range(n))
    return sorted(set(np.linspace(0, n - 1, cap).round().astype(int).tolist()))


def series_report(
    times, meas, sim, sigma_floor: float | None, max_points: int = 40
) -> dict:
    """The fit itself for one observable in one condition, point by point.

    Not summary buckets: early/mid/late bins collapse a peak and a slow drift
    to the same numbers and average away an overshoot's peak location. Each
    point carries time, measurement, simulation and the residual in units of
    the assay's replicate noise; long series are thinned to `max_points`
    evenly spaced samples, so the shape survives at lower resolution. A
    steady-state row (time `inf`) is not the sample after the last one: the
    shape reads the time course, and the row is reported beside it
    (`steady_state`).
    """
    m_all, s_all = np.asarray(meas, float), np.asarray(sim, float)
    res = m_all - s_all
    t = np.asarray(times, float)
    on_course = np.isfinite(t)
    df = (
        pd.DataFrame(
            {
                "t": t[on_course],
                "m": m_all[on_course],
                "s": s_all[on_course],
                "r": res[on_course],
            }
        )
        .groupby("t")
        .mean()
    )
    tt = df.index.to_numpy()
    mm, ss, rr = df["m"].to_numpy(), df["s"].to_numpy(), df["r"].to_numpy()
    u = (rr / sigma_floor) if sigma_floor else None

    keep = _thin(len(tt), max_points)
    curve = [
        {
            "t": round(float(tt[i]), 3),
            "measured": round(float(mm[i]), 4),
            "simulated": round(float(ss[i]), 4),
            "residual_in_noise_units": (None if u is None else round(float(u[i]), 2)),
        }
        for i in keep
    ]

    signs = "".join("+" if v > 0 else ("-" if v < 0 else "0") for v in rr)
    runs = 1 + sum(
        1
        for a, b in zip(signs, signs[1:], strict=False)
        if a != b and "0" not in (a, b)
    )
    auto1 = (
        float(np.corrcoef(rr[:-1], rr[1:])[0, 1])
        if len(rr) > 2 and np.ptp(rr) > 0
        else None
    )
    imax = int(np.argmax(np.abs(rr))) if len(rr) else None
    # Does |residual| grow with the SIGNAL? That is the multiplicative-noise
    # signature, and it separates a wrong error model from a wrong mechanism —
    # without it an agent proposes structure for what is an observation defect.
    hetero = None
    if len(rr) > 3 and np.ptp(np.abs(ss)) > 0 and np.ptp(np.abs(rr)) > 0:
        hetero = float(np.corrcoef(np.abs(rr), np.abs(ss))[0, 1])
    out = {
        "fit_over_time": curve,
        "abs_residual_vs_signal_corr": (
            None if hetero is None or not np.isfinite(hetero) else round(hetero, 3)
        ),
        "n_timepoints": int(len(tt)),
        "thinned_from": (None if len(keep) == len(tt) else int(len(tt))),
        "rmse": float(np.sqrt(np.mean(res**2))),
        # shape descriptors that do NOT depend on arbitrary bin edges
        "largest_deviation": (
            None
            if imax is None
            else {
                "at_time": round(float(tt[imax]), 3),
                "signed_residual": round(float(rr[imax]), 4),
                "in_noise_units": (None if u is None else round(float(u[imax]), 2)),
            }
        ),
        "residual_sign_pattern_over_time": signs,
        "n_sign_runs": runs,
        "lag1_autocorr": None if auto1 is None else round(auto1, 3),
    }
    if len(tt) > 2:
        from scipy import stats as _st

        rho = _st.spearmanr(tt, rr)
        out["monotone_trend_with_time"] = {
            "spearman_rho": round(float(rho.statistic), 3),
            "p": float(rho.pvalue),
        }
    if sigma_floor:
        out["rmse_over_replicate_noise_floor"] = round(out["rmse"] / sigma_floor, 2)
    if not on_course.all():
        r_ss = float(np.mean(res[~on_course]))
        out["steady_state"] = {
            "measured": round(float(np.mean(m_all[~on_course])), 4),
            "simulated": round(float(np.mean(s_all[~on_course])), 4),
            "residual_in_noise_units": (
                None if not sigma_floor else round(r_ss / sigma_floor, 2)
            ),
        }
    return out


def identical_prediction_controls(sim_by_key: dict) -> list[dict]:
    """Condition pairs a model predicts IDENTICALLY. Their measured difference
    is pure noise, so it calibrates how large a residual difference has to be
    before it means anything."""
    out = []
    keys = sorted(sim_by_key)
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            (oa, ca), (ob, cb) = a, b
            if oa != ob:
                continue
            sa, sb = sim_by_key[a], sim_by_key[b]
            if len(sa) != len(sb) or not np.allclose(sa, sb, rtol=1e-9, atol=1e-12):
                continue
            out.append(
                {
                    "observable": oa,
                    "conditions": [ca, cb],
                    "note": "the model predicts these identically, so any "
                    "difference between their residuals is noise",
                }
            )
    return out


RANK_KEYS = ("rmse_over_replicate_noise_floor", "rmse")


def rank_of(series: dict) -> tuple[float, str]:
    """How bad this series is, and by which statistic.

    `rmse_over_replicate_noise_floor` first: it is comparable across
    observables, and a fit worse than the assay's repeatability has something
    left to explain. Falls back to raw RMSE when the data carry no replicates,
    and returns which key it used so the ranking can be checked.
    """
    if not isinstance(series, dict):
        return (0.0, "none")
    for key in RANK_KEYS:
        v = series.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return (float(v), key)
    return (0.0, "none")


def budget_by_observable(ranked: list, n: int) -> set:
    """Which series a budget of `n` keeps: one per OBSERVABLE first, then the
    worst remaining overall.

    Straight top-N can spend the whole budget on one observable and leave the
    others with nothing to reason from. `ranked` is worst-first, so the first
    series seen for an observable is that observable's worst.
    """
    keep: set = set()
    seen: set = set()
    for label, _s in ranked:
        if len(keep) >= n:
            return keep
        obs = str(label).split("@")[0]
        if obs not in seen:
            seen.add(obs)
            keep.add(label)
    for label, _s in ranked:
        if len(keep) >= n:
            break
        keep.add(label)
    return keep


def series_tier(raw, n_series: int) -> int:
    """A tier boundary as declared in the spec; `null` means every series."""
    return n_series if raw is None else int(raw)


def thin_series(det: dict, spec, carries_curves: bool) -> None:
    """Tier one candidate's series: full curve, full summary, or one number.

    Three tiers, both boundaries declared in the workflow spec:

      worst `full_curves_top_n`      full summary AND the point-by-point curve
      next `full_summaries_top_n`    full summary, no curve
      the rest                       one number — the rank statistic — plus a
                                     note naming the request that fetches them

    The number the third tier keeps lets an agent see that a series exists and
    how bad it is, and ask for it. Mutates `det` in place, so it is called on
    the payload under construction, never on an artifact.
    """
    series = det.get("per_series")
    if not isinstance(series, dict) or not series:
        return
    # a null tier thins nothing: every series keeps its summary, and a
    # curve-carrying model every curve
    n_curves = series_tier(spec.get("diagnostics.full_curves_top_n"), len(series))
    n_summaries = series_tier(spec.get("diagnostics.full_summaries_top_n"), len(series))
    ranked = sorted(series.items(), key=lambda kv: -rank_of(kv[1])[0])
    key_used = rank_of(ranked[0][1])[1] if ranked else "none"

    # The summary tier decides first: a curve on a series the summary tier then
    # removes would be silently thrown away. The curve budget is chosen from
    # what survives.
    kept_labels = (
        {label for label, _ in ranked}
        if len(ranked) <= n_summaries
        else budget_by_observable(ranked, n_summaries)
    )
    kept_ranked = [(label, s) for label, s in ranked if label in kept_labels]

    keep_curves = (
        budget_by_observable(kept_ranked, n_curves) if carries_curves else set()
    )
    for label, s in ranked:
        if label not in keep_curves and isinstance(s, dict):
            s.pop("fit_over_time", None)
    if carries_curves and len(kept_ranked) > len(keep_curves):
        det["curves_note"] = (
            f"point-by-point curves for {len(keep_curves)} series: the worst by "
            f"{key_used} within each observable first, then the worst "
            f"remaining overall. The rest carry their shape descriptors — "
            f"request residual_curve(candidate_id, observable_id, "
            f"condition_id) for any of them."
        )

    if len(ranked) <= n_summaries:
        return
    other: dict[str, float] = {}
    for label, s in ranked:
        if label in kept_labels:
            continue
        other[label] = rank_of(s)[0]
        series.pop(label, None)
    det["other_series_" + key_used] = other
    det["note"] = (
        f"{len(other)} further series carry their {key_used} only — enough to "
        f"see they exist and how bad they are. Every observable keeps at "
        f"least one full summary above; these are the rest. Request "
        f"residual_curve(candidate_id, observable_id, condition_id) for any "
        f"of them."
    )


def base_id_of(model_ids) -> str:
    """Which of these ids is the BASE — the shortest one.

    A convention, stated once because three readers depend on it: the
    cross-model table's reference column, the choice of who gets full curves,
    and the note that says so.
    """
    ids = [str(m) for m in (model_ids or [])]
    return min(ids, key=len) if ids else ""


def cross_model_table(per_model: dict, base_id: str) -> list[dict]:
    """For each observable/condition: the base model's error, the best error any
    candidate achieved, and which candidate achieved it. A row where no
    candidate improved on the base is a measurement the whole space failed to
    address — the prime suspect for what is missing."""
    keys = set()
    for rep in per_model.values():
        keys |= set(rep)
    rows = []
    for k in sorted(keys):
        base = per_model.get(base_id, {}).get(k, {}).get("rmse")
        scored = [
            (mid, rep[k]["rmse"])
            for mid, rep in per_model.items()
            if k in rep and rep[k].get("rmse") is not None
        ]
        if not scored:
            continue
        best_id, best = min(scored, key=lambda p: p[1])
        floor_ratio = (
            per_model.get(best_id, {}).get(k, {}).get("rmse_over_replicate_noise_floor")
        )
        row = {
            "observable": k[0],
            "condition": k[1],
            "base_rmse": None if base is None else round(base, 4),
            "best_rmse": round(best, 4),
            "best_model": best_id,
            "best_rmse_over_noise_floor": floor_ratio,
        }
        if base:
            row["improvement_vs_base"] = round(1 - best / base, 3)
            unimproved = bool(best >= base * 0.98)
            # "No candidate improved this" only matters if there was anything to
            # improve. A series already sitting at the assay's own repeatability
            # is unimprovable BY CONSTRUCTION, and pointing an agent at it is how
            # you get a mechanism invented to explain noise.
            if not unimproved:
                row["verdict"] = "improved by at least one candidate"
            elif floor_ratio is None:
                row["verdict"] = (
                    "unimproved; no replicate floor available, so "
                    "whether anything remains to fix is unknown"
                )
            elif floor_ratio <= 1.2:
                row["verdict"] = (
                    "unimproved BUT already at the assay's noise "
                    "floor — nothing left to explain here"
                )
            else:
                row["verdict"] = (
                    "PRIME SUSPECT: no candidate improved it and it "
                    "is still above the assay's noise floor, so the "
                    "space contains no structure that addresses it"
                )
            row["unimproved_by_every_candidate"] = unimproved
        rows.append(row)
    return rows


def _qq_tail(entry: dict) -> str | None:
    """Which way the QQ plot bends, in one word. Heavy tails and light tails
    are different complaints about the assumed distribution."""
    qq = entry.get("qq") or {}
    theo, samp = qq.get("theoretical") or [], qq.get("sample") or []
    if len(theo) != len(samp) or len(theo) < 6:
        return None
    t = np.asarray(theo, dtype=float)
    x = np.asarray(samp, dtype=float)
    k = max(2, len(t) // 5)
    tails = np.concatenate(
        [np.abs(x[:k]) - np.abs(t[:k]), np.abs(x[-k:]) - np.abs(t[-k:])]
    )
    m = float(np.mean(tails))
    if abs(m) < 0.15:
        return "close to the assumed distribution"
    return "heavier tails than assumed" if m > 0 else "lighter tails than assumed"


def _observation_evidence(ctx, details: dict, winner: str, core: dict | None) -> dict:
    """The observation-layer half of the differential diagnosis.

    An agent given only residual curves proposes mechanism for what may be a
    wrong error model, and vice versa. Everything here is already computed by
    S7 (the noise check, the fitted-sigma-vs-floor ratios) plus each series'
    heteroscedasticity correlation, grouped into one block. `core` is the
    round's report core when the caller has it; otherwise it is read from the
    record (`evaluation_core`) via `ctx`.
    """
    if core is None:
        core = (ctx.round / "evaluation_core").get(None) or {}
    noise = core.get("noise_check") or {}
    signals = (core.get("misfit_evidence") or {}).get("signals", {}) or {}
    ratios = {
        str(rec.get("observable")): rec
        for rec in (signals.get("sigma_vs_floor") or [])
        if isinstance(rec, dict)
    }
    per_observable: dict[str, dict] = {}
    # `details[winner]` is the candidate record {sigma_vs_replicate_floor,
    # per_series}; the observable@condition series are under `per_series`.
    for label, series in ((details.get(winner) or {}).get("per_series") or {}).items():
        obs_id = str(label).split("@")[0]
        rec = per_observable.setdefault(
            obs_id,
            {
                "noise_check": {
                    k: v
                    for k, v in (noise.get(obs_id) or {}).items()
                    if k in ("assumed", "test", "n", "statistic", "p_value")
                },
                "qq_tail_deviation": _qq_tail(noise.get(obs_id) or {}),
                "fitted_sigma_vs_replicate_floor": ratios.get(obs_id, {}),
                "abs_residual_vs_signal_corr_by_condition": {},
            },
        )
        if isinstance(series, dict):
            rec["abs_residual_vs_signal_corr_by_condition"][str(label)] = series.get(
                "abs_residual_vs_signal_corr"
            )
    for rec in per_observable.values():
        vals = [
            v
            for v in rec["abs_residual_vs_signal_corr_by_condition"].values()
            if isinstance(v, (int, float))
        ]
        rec["abs_residual_vs_signal_corr_median"] = (
            round(float(np.median(vals)), 3) if vals else None
        )
    return {
        "for_model": winner,
        "per_observable": per_observable,
        "reads_as": (
            "the error-model half of the diagnosis: a positive "
            "abs_residual_vs_signal_corr with a rejecting noise check points "
            "at proportional noise, not at a missing mechanism"
        ),
    }


def _sig(x, digits: int = 4):
    """A number to `digits` significant figures, None kept as None."""
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(x) or x == 0:
        return x
    return float(f"{x:.{digits}g}")


def bound_pressure(ctx, cand_ids: list[str], near: float = 0.02) -> dict:
    """Per candidate, every estimated parameter at a bound of its box or near one.

    "Near" is within `near`, a fraction of the box in the estimation scale.
    Each row has the bound, the edge, the fitted value and, where the bound is
    active, the gradient component pressing out of the box, which tells a
    bound-limited fit from a parameter simply unneeded at its edge. Read from
    each fit's `estimation` record (`grad_at_active_bounds`, `near_bounds`)
    and its `petab/parameters` table; rows are ordered by the size of the
    pressing component."""
    from octomod.result import node as _tree

    out: dict[str, list[dict]] = {}
    for cid in cand_ids:
        work = _tree.work_node(ctx.round, cid)
        try:
            summ = (work / "estimation").get()
            par = (work / "petab/parameters").table()
        except Exception:
            continue
        box = {
            str(r["parameterId"]): (
                float(r["lowerBound"]),
                float(r["upperBound"]),
                str(r.get("parameterScale", "lin")),
            )
            for _, r in par.iterrows()
        }
        best = summ.get("best_x_unscaled") or {}
        parked = {str(g["id"]): g for g in summ.get("grad_at_active_bounds") or []}
        rows: list[dict] = []
        for pid in dict.fromkeys(list(summ.get("at_bounds") or []) + list(parked)):
            lb, ub, scale = box.get(pid, (None, None, None))
            g = parked.get(pid)
            val = best.get(pid)
            if g is not None:
                edge = g["edge"]
            elif None not in (val, lb, ub):
                edge = (
                    "lower" if abs(float(val) - lb) <= abs(ub - float(val)) else "upper"
                )
            else:
                edge = None
            rows.append(
                {
                    "id": pid,
                    "edge": edge,
                    "bound": _sig(
                        lb if edge == "lower" else ub if edge == "upper" else None
                    ),
                    "value": _sig(val),
                    "scale": scale,
                    "at_bound": True,
                    "pressing": g is not None,
                    "gradient_component": _sig(g["component"]) if g else None,
                }
            )
        for nb in summ.get("near_bounds") or []:
            if float(nb.get("from_edge", 1.0)) > near:
                continue
            pid = str(nb["id"])
            lb, ub, scale = box.get(pid, (None, None, None))
            rows.append(
                {
                    "id": pid,
                    "edge": nb.get("edge"),
                    "bound": _sig(lb if nb.get("edge") == "lower" else ub),
                    "value": _sig(best.get(pid)),
                    "scale": scale,
                    "at_bound": False,
                    "from_edge": nb.get("from_edge"),
                }
            )
        rows.sort(key=lambda r: -abs(r.get("gradient_component") or 0.0))
        out[cid if cid else "model"] = rows
    return out


BOUND_PRESSURE_NOTE = (
    "Per fitted candidate: each estimated parameter at a bound of its box, or "
    "within 2 % of one (from_edge, a fraction of the box in the estimation "
    "scale). `gradient_component` is d(-log L)/d(parameter) in the estimation "
    "scale (log10 for a log10 parameter), given where the bound is active and "
    "the gradient points OUT of the box — the fit would still improve past the "
    "bound. A large component says the fit is bound-limited: the model wants a "
    "value the box excludes, so either the bound is wrong or the parameter is "
    "doing another mechanism's job. A component near zero, or none, says the "
    "parameter is simply not needed at that edge. Several parameters pinned "
    "together can mean the fit is walking toward a limiting form of the model."
)


# where S7 keeps the round's residual forms for the report: the round's
# `residual_forms` record (`rounds/round_k/residual_forms`)
RESIDUAL_FORMS_KEY = "residual_forms"

RESIDUAL_FORMS_NOTE = (
    "Each residual series (measured minus simulated, every replicate) of the "
    "selected model and the base, fitted with constant, linear, exponential "
    "and rise-and-fall forms and chosen by small-sample AICc against the "
    "constant, against the replicate noise floor (else the fitted sigma): "
    "`amplitude` is in units of that sigma, `timescales` in the data's own "
    "time unit; a field a form does not have (a constant's timescale, a "
    "peak time off a transient) is left out of its row. `summary` groups the "
    "series whose forms agree, with every "
    "timescale within a factor of two, per observable and stimulus, and names "
    "what disagrees. One timescale shared across conditions points at one "
    "missing process; an amplitude that scales with dose points at where it "
    "enters; a form that changes by condition points at what the condition "
    "changes. A description, not a test: AICc treats the points as "
    "independent, so confirm a form with the fit_residual_form request before "
    "building an axis on it."
)


def _condition_attributes(assembly: dict, long_df) -> dict[str, dict]:
    """{condition id: {data column: value}} from the long table's semantic keys."""
    if long_df is None or not {"condition_label", "condition_key"} <= set(long_df):
        return {}
    from octomod.workflow_modules.assembly.assembly_edit import condition_attributes

    key_by_label = dict(
        zip(
            long_df["condition_label"].astype(str),
            long_df["condition_key"].fillna("").astype(str),
            strict=False,
        )
    )
    return condition_attributes(assembly or {}, key_by_label)


def residual_series_sigma(tables, floors: dict, obs_id: str, cond_id: str, times, best):
    """(σ the residual is measured against, where it came from): the replicate
    noise floor of the observable, else the fit's own sigma, else None."""
    floor = floors.get(obs_id)
    if floor:
        return float(floor), "replicate floor"
    try:
        sd = np.asarray(tables.sigma_series(obs_id, cond_id, times, best), float)
        if len(sd) and np.all(np.isfinite(sd)) and np.all(sd > 0):
            return sd, "fitted sigma"
    except Exception:  # an unreadable noise formula leaves the variance profiled
        pass
    return None, "profiled"


def residual_forms(series: dict[str, list[dict]], selected: str, base: str) -> dict:
    """`residual_forms` for the selected model and the base: every residual
    series' fitted form, and one sentence per (observable, stimulus) stratum.

    `series` maps a model key to its residual series ({observable, condition,
    attributes, t, r, sigma, sigma_source}). The selected model's sentences come
    first, strongest residual first; then the base's.
    """
    from octomod.workflow_modules.data import curve_forms as _cf

    per_series: list[dict] = []
    summary: list[str] = []
    for model in dict.fromkeys(m for m in (selected, base) if m in series):
        rows = []
        for s in series[model]:
            fit = _cf.fit_series(s["t"], s["r"], s["sigma"])
            start = None
            if fit.get("window"):
                start = float(_cf.predict(fit, [fit["window"][0]])[0])
            rows.append(
                {
                    "observable": s["observable"],
                    "condition": s["condition"],
                    "attributes": s.get("attributes") or {},
                    "fit": fit,
                    "early_sign": (
                        None
                        if start is None or start == 0
                        else ("above" if start > 0 else "below")
                    ),
                }
            )
            per_series.append(
                {
                    "model": model,
                    "series": f"{s['observable']}@{s['condition']}",
                    "attributes": s.get("attributes") or {},
                    "sigma_source": s.get("sigma_source"),
                    **{
                        k: fit[k]
                        for k in (
                            "form",
                            "direction",
                            "timescales",
                            "amplitude",
                            "amplitude_units",
                            "peak_time",
                            "r2",
                            "n",
                            "delta_aicc_vs_constant",
                            "timescale_at_bound",
                        )
                        # an absent field is said once, in how_to_read_this,
                        # not as a null in every row
                        if fit.get(k) not in (None, [])
                    },
                }
            )
        if selected == base:
            label = model
        else:
            label = f"{model} ({'selected' if model == selected else 'base'})"
        ranked = sorted(
            _cf.aggregate_residuals(rows, label), key=lambda p: (-p[0], p[1])
        )
        summary += [text for _w, text in ranked]
    return {
        "per_series": per_series,
        "summary": summary,
        "how_to_read_this": RESIDUAL_FORMS_NOTE,
    }


def expansion_payload(
    ctx, cand_ids: list[str], winner: str, core: dict | None = None
) -> dict:
    """Everything the expansion agent needs to reason about what is missing:
    every candidate's residual structure, not only the winner's.

    `core` is the round's report core when the caller has it in hand; passing
    it avoids re-reading the round's `evaluation_core`, written by the calling
    module, which may not be the version the caller is reasoning about."""
    from octomod.workflow_modules.evaluation import fitted
    from octomod.workflow_modules.evaluation.engine import sim_group

    per_model: dict[str, dict] = {}
    detail_models: set[str] = set()
    details: dict[str, dict] = {}
    controls: list[dict] = []
    long_df = (ctx.round / "data/measurements").table(None)
    keys = [c if c else "model" for c in cand_ids]
    # the residual forms are fitted for the selected model and the base only
    form_models = {
        winner if winner in keys else (keys[0] if keys else ""),
        base_id_of(keys),
    }
    form_series: dict[str, list[dict]] = {}

    for cid in cand_ids:
        # a single-model round has no candidate id; "model" is the stable key
        key = cid if cid else "model"
        try:
            f = fitted.load(ctx, cid, long_df=long_df)
            tables, best = f.tables, f.best
            ev = f.misfit_evidence(ctx.spec)
            floors = fitted.floors(ev)
            attrs = (
                _condition_attributes(f.assembly, long_df) if key in form_models else {}
            )
            rep, sims = {}, {}
            for (obs_id, cond_id), grp in tables.measurements.groupby(
                ["observableId", "simulationConditionId"]
            ):
                times = grp["time"].to_numpy(dtype=float)
                meas = grp["measurement"].to_numpy(dtype=float)
                sim = sim_group(tables, str(obs_id), str(cond_id), times, best)
                rep[(str(obs_id), str(cond_id))] = series_report(
                    times, meas, sim, floors.get(str(obs_id))
                )
                sims[(str(obs_id), str(cond_id))] = np.asarray(sim, float)
                if key in form_models:
                    sd, source = residual_series_sigma(
                        tables, floors, str(obs_id), str(cond_id), times, best
                    )
                    form_series.setdefault(key, []).append(
                        {
                            "observable": str(obs_id),
                            "condition": str(cond_id),
                            "attributes": attrs.get(str(cond_id), {}),
                            "t": times,
                            "r": meas - np.asarray(sim, float),
                            "sigma": sd,
                            "sigma_source": source,
                        }
                    )
            per_model[key] = rep
            details[key] = {
                "sigma_vs_replicate_floor": [
                    {"observable": s["observable"], "ratio": s["ratio"]}
                    for s in (ev.get("signals", {}).get("sigma_vs_floor") or [])
                ],
                "per_series": {f"{o}@{c}": v for (o, c), v in rep.items()},
            }
            detail_models.add(cid)
            if cid == winner:
                controls = identical_prediction_controls(sims)
        except Exception as e:  # a diagnostic must never kill the run
            details[key] = {"error": f"{type(e).__name__}: {e}"}

    base_id = base_id_of(per_model) or winner
    # Point-by-point curves only for the SELECTED model (what is still wrong)
    # and the BASE (what the space started from); for the rest, the shape
    # descriptors plus the cross-model table say what each ingredient bought.
    for cid, det in details.items():
        if cid in (winner, base_id) or "per_series" not in det:
            continue
        for s in det["per_series"].values():
            s.pop("fit_over_time", None)
        det["note"] = (
            "point-by-point fit omitted for this candidate; shape "
            "descriptors kept. Full curves are given for the "
            f"selected model ({winner}) and the base ({base_id}), "
            "and cross_model_by_measurement compares all of them."
        )
    # The rule above bounds curves by MODEL; this one bounds curves and
    # summaries by SERIES, since per_candidate_residuals scales with
    # candidates x observables x conditions x timepoints.
    for cid, det in details.items():
        thin_series(det, ctx.spec, carries_curves=cid in (winner, base_id))

    # on a single-model round the "winner" IS the one model
    focus = winner if winner in details else (next(iter(details), "") or "")
    try:
        forms = residual_forms(form_series, focus, base_id)
    except Exception as e:  # a diagnostic must never kill the run
        forms = {"error": f"{type(e).__name__}: {e}", "per_series": [], "summary": []}
    return {
        "observation_evidence": _observation_evidence(ctx, details, focus, core),
        "per_candidate_residuals": details,
        "cross_model_by_measurement": cross_model_table(per_model, base_id),
        "identical_prediction_controls": controls,
        "residual_forms": forms,
        "how_to_read_this": "fit_over_time is the fit itself: measured, simulated, and the "
        "residual in units of the assay's own replicate noise, per "
        "timepoint. Read the SHAPE. A residual that grows and then returns "
        "is an overshoot and points at a regulatory term the model lacks; "
        "largest_deviation.at_time tells you WHEN, which usually tells you "
        "where in the network. A residual that drifts one way throughout is "
        "a wrong rate or a missing sink, and monotone_trend_with_time will "
        "be significant while an overshoot's will not. Few n_sign_runs over "
        "many timepoints means systematic, not noise. A steady_state entry "
        "is a time-inf measurement read against the model's steady state, "
        "kept out of the time course and every statistic over it. Residuals within "
        "about 1 noise unit are the assay talking, not the model. A row in "
        "cross_model_by_measurement marked PRIME SUSPECT is a measurement "
        "no structure in the space could fix while it is still above the "
        "noise floor — start there. Rows marked already-at-the-noise-floor "
        "are unimprovable by construction; inventing mechanism for those is "
        "how a model gets fitted to noise. identical_prediction_controls "
        "are condition pairs this model cannot tell apart, so their "
        "residual difference is pure noise and calibrates everything else. "
        "THEN the differential diagnosis, which is one act with two answers: "
        "observation_evidence says whether the defect is the ERROR MODEL "
        "rather than the mechanism. When |residual| grows with the signal "
        "(abs_residual_vs_signal_corr well above 0) AND the noise check "
        "rejects the assumed distribution, propose an OBSERVATION axis — "
        "proportional noise, a scaling or an offset — not a mechanism; the "
        "curve's shape is then a consequence of the wrong error model. When "
        "the residual SHAPE localises in time or in a condition while the "
        "noise check does not reject and |residual| is flat in the signal, "
        "propose STRUCTURE. A fitted sigma above the replicate floor says the "
        "likelihood has already absorbed something into the noise, so read it "
        "alongside both. residual_forms names each residual's functional form "
        "and timescale and groups the series that agree: its summary is the "
        "shortest statement of what is still wrong, and its how_to_read_this "
        "says what a shared timescale or a dose-scaled amplitude points at.",
    }
