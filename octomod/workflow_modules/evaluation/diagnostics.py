"""Engine-run diagnostics a tool-less agent may request, executed and ledgered here.

Whitelisted kinds (`KINDS`):
  simulate_with      simulate a fitted candidate with parameter overrides
                     (no fitting), in the series_report shape
  residuals_for      a candidate's residuals grouped by a named data column
  compare_conditions the identical-prediction control for a named pair
  fit_residual_form  fit one residual series with the curve_forms library
                     (constant, linear, exponential, rise-and-fall), judged
                     against white-noise and AR(1) nulls: suggestive only
  residual_curve     one series' point-by-point fit, which the payload summarises
  profile_path       one parameter's profile-likelihood path, read from the record

Nothing fits a model, reads outside the run record or runs free code. The
callers persist requests and results in the round (`expansion_diagnostics`),
so a resume replays them.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from octomod.orchestration.ledger import sha256_text
from octomod.workflow_modules.data import curve_forms as _cf

KINDS = (
    "simulate_with",
    "residuals_for",
    "compare_conditions",
    "fit_residual_form",
    "residual_curve",
    "profile_path",
)

STANDING_NOTE = (
    "suggestive, never selective: a diagnostic motivates an axis; the "
    "axis is still fitted in the real likelihood and selected by the "
    "criterion"
)


def _candidate(ctx, cid: str):
    """(tables, best, assembly, long_df, floors) for a fitted candidate; raises
    ValueError when it has no estimation result."""
    from octomod.workflow_modules.evaluation import fitted

    f = fitted.load(ctx, cid)
    return (
        f.tables,
        f.best,
        f.assembly,
        f.long_df,
        fitted.floors(f.misfit_evidence(ctx.spec)),
    )


def _sim(
    tables, obs_id: str, cond_id: str, times: np.ndarray, params: dict
) -> np.ndarray:
    return tables.simulate_observables(cond_id, times, param_override=params)[obs_id]


def _series(
    tables, best, floors, obs_id: str, cond_id: str, params: dict | None = None
) -> dict:
    from octomod.workflow_modules.evaluation.residuals import series_report

    grp = tables.measurements[
        (tables.measurements["observableId"] == obs_id)
        & (tables.measurements["simulationConditionId"] == cond_id)
    ]
    times = grp["time"].to_numpy(dtype=float)
    meas = grp["measurement"].to_numpy(dtype=float)
    sim = _sim(tables, obs_id, cond_id, times, params or best)
    return series_report(times, meas, sim, floors.get(obs_id))


def _simulate_with(ctx, cand_ids, args) -> dict:
    cid = str(args.get("candidate_id", ""))
    if cid not in cand_ids:
        raise ValueError(f"candidate_id must be one of {sorted(cand_ids)}, got {cid!r}")
    tables, best, asm, _long, floors = _candidate(ctx, cid)
    overrides = args.get("parameter_overrides") or {}
    unknown = [k for k in overrides if k not in best and k not in tables.model_entities]
    if unknown:
        raise ValueError(
            f"parameter_overrides name unknown parameters {unknown}; "
            f"fitted parameters are {sorted(best)}"
        )
    params = {**best, **{k: float(v) for k, v in overrides.items()}}
    want_obs = set(
        args.get("observables") or tables.observables["observableId"].astype(str)
    )
    want_cond = set(
        args.get("conditions") or tables.conditions["conditionId"].astype(str)
    )
    series = {}
    for (obs_id, cond_id), _ in tables.measurements.groupby(
        ["observableId", "simulationConditionId"]
    ):
        if str(obs_id) in want_obs and str(cond_id) in want_cond:
            series[f"{obs_id}@{cond_id}"] = _series(
                tables, best, floors, str(obs_id), str(cond_id), params
            )
    return {
        "candidate_id": cid,
        "overrides_applied": {k: float(v) for k, v in overrides.items()},
        "series": series,
        "how_to_read_this": "the same fit-over-time shape as the payload, simulated at "
        "the overridden parameters — no fitting happened",
    }


def _residuals_for(ctx, cand_ids, args) -> dict:
    from octomod.workflow_modules.evaluation.residuals import series_report

    cid = str(args.get("candidate_id", ""))
    if cid not in cand_ids:
        raise ValueError(f"candidate_id must be one of {sorted(cand_ids)}, got {cid!r}")
    col = str(args.get("group_by", ""))
    tables, best, asm, long_df, floors = _candidate(ctx, cid)
    if long_df is None:
        raise ValueError("no long measurement table in this round")
    # data columns live inside condition_key ('u=4|bx11=1'); replicate is its own column
    keys = long_df["condition_key"].fillna("").astype(str)
    cols = sorted(
        {tok.split("=")[0] for k in keys for tok in k.split("|") if "=" in tok}
    )
    allowed = set(cols) | {"replicate", "condition", "observable"}
    if col not in allowed:
        raise ValueError(f"group_by must be a data column, one of {sorted(allowed)}")
    obs_by_label = {
        o["maps_to_label"]: o["observable_id"] for o in asm.get("observables", [])
    }
    cond_by_label = {
        c["maps_to_label"]: c["condition_id"] for c in asm.get("conditions", [])
    }
    trained = set(tables.measurements["simulationConditionId"].astype(str))
    rows = []
    for _, r in long_df.iterrows():
        oid = obs_by_label.get(r["observable_label"])
        cnd = cond_by_label.get(r["condition_label"])
        if oid is None or cnd is None or cnd not in trained:
            continue
        kv = dict(
            tok.split("=", 1)
            for tok in str(r.get("condition_key", "")).split("|")
            if "=" in tok
        )
        group = {
            "replicate": str(r.get("replicate")),
            "condition": cnd,
            "observable": oid,
        }.get(col, kv.get(col))
        rows.append(
            {
                "obs": oid,
                "cond": cnd,
                "t": float(r["time"]),
                "y": float(r["value"]),
                "g": group,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("no training rows resolved against the assembly")
    sims = {}
    for (oid, cnd), grp in df.groupby(["obs", "cond"]):
        times = np.sort(grp["t"].unique())
        sims[(oid, cnd)] = dict(
            zip(times, _sim(tables, oid, cnd, times, best), strict=False)
        )
    df["sim"] = [
        sims[(o, c)][t] for o, c, t in zip(df["obs"], df["cond"], df["t"], strict=False)
    ]
    out = {}
    for (oid, g), grp in df.groupby(["obs", "g"]):
        rep = series_report(
            grp["t"].to_numpy(),
            grp["y"].to_numpy(),
            grp["sim"].to_numpy(),
            floors.get(oid),
        )
        rep["n_points"] = int(len(grp))
        rep["mean_residual"] = round(float((grp["y"] - grp["sim"]).mean()), 5)
        out.setdefault(oid, {})[str(g)] = rep
    return {
        "candidate_id": cid,
        "grouped_by": col,
        "groups": out,
        "how_to_read_this": f"residual structure per value of {col!r}: a mean "
        f"residual that changes sign or size across groups is a "
        f"{col}-dependent defect; the same shape in every group is not",
    }


def _compare_conditions(ctx, cand_ids, args) -> dict:
    cid = str(args.get("candidate_id", ""))
    if cid not in cand_ids:
        raise ValueError(f"candidate_id must be one of {sorted(cand_ids)}, got {cid!r}")
    obs_id = str(args.get("observable_id", ""))
    conds = list(args.get("conditions") or [])
    if len(conds) != 2:
        raise ValueError("conditions must name exactly two condition ids")
    tables, best, asm, _long, floors = _candidate(ctx, cid)
    known_c = set(tables.conditions["conditionId"].astype(str))
    if (
        obs_id not in set(tables.observables["observableId"].astype(str))
        or not set(conds) <= known_c
    ):
        raise ValueError(
            f"observable_id/conditions not in the problem (observables "
            f"{sorted(set(tables.observables['observableId']))}, conditions {sorted(known_c)})"
        )
    m = tables.measurements
    ta = np.sort(
        m[(m.observableId == obs_id) & (m.simulationConditionId == conds[0])][
            "time"
        ].unique()
    )
    tb = np.sort(
        m[(m.observableId == obs_id) & (m.simulationConditionId == conds[1])][
            "time"
        ].unique()
    )
    times = np.union1d(ta, tb).astype(float)
    sa, sb = _sim(tables, obs_id, conds[0], times, best), _sim(
        tables, obs_id, conds[1], times, best
    )
    identical = bool(np.allclose(sa, sb, rtol=1e-9, atol=1e-12))
    ra = _series(tables, best, floors, obs_id, conds[0])
    rb = _series(tables, best, floors, obs_id, conds[1])
    return {
        "candidate_id": cid,
        "observable_id": obs_id,
        "conditions": conds,
        "identical_prediction": identical,
        "max_abs_sim_difference": round(float(np.max(np.abs(sa - sb))), 6),
        "residuals": {conds[0]: ra, conds[1]: rb},
        "how_to_read_this": (
            "the model predicts these two conditions identically, so any "
            "difference between their residuals is pure noise and "
            "calibrates every other number"
            if identical
            else "the model predicts these two conditions differently; compare "
            "the residual shapes, not their sizes"
        ),
    }


def _fit_residual_form_request(ctx, cand_ids, args) -> dict:
    cid = str(args.get("candidate_id", ""))
    if cid not in cand_ids:
        raise ValueError(f"candidate_id must be one of {sorted(cand_ids)}, got {cid!r}")
    obs_id, cond_id = str(args.get("observable_id", "")), str(
        args.get("condition_id", "")
    )
    tables, best, asm, _long, floors = _candidate(ctx, cid)
    grp = tables.measurements[
        (tables.measurements["observableId"] == obs_id)
        & (tables.measurements["simulationConditionId"] == cond_id)
    ]
    if grp.empty:
        raise ValueError(f"no training measurements for {obs_id}@{cond_id}")
    times = grp["time"].to_numpy(dtype=float)
    meas = grp["measurement"].to_numpy(dtype=float)
    sim = _sim(tables, obs_id, cond_id, times, best)
    df = pd.DataFrame({"t": times, "r": meas - sim}).groupby("t").mean()
    floor = floors.get(obs_id)
    if floor:
        scale = float(floor)
        unit = "replicate noise floor"
    else:
        sig = tables.sigma_series(obs_id, cond_id, df.index.to_numpy(dtype=float), best)
        scale = float(np.mean(sig)) or 1.0
        unit = "fitted sigma"
    r_units = df["r"].to_numpy() / scale
    rmse_units = float(np.sqrt(np.mean(r_units**2)))
    out = fit_residual_form(
        df.index.to_numpy(dtype=float),
        r_units,
        at_floor=(floor is not None and rmse_units <= 1.2),
        n_boot=int(ctx.spec.require("diagnostics.form_fit.n_bootstrap")),
        alpha=float(ctx.spec.require("diagnostics.form_fit.alpha")),
    )
    out.update(
        {
            "candidate_id": cid,
            "observable_id": obs_id,
            "condition_id": cond_id,
            "residual_units": unit,
            "rmse_in_noise_units": round(rmse_units, 3),
        }
    )
    return out


def _bic(rss: float, n: int, k: int) -> float:
    return n * math.log(max(rss, 1e-300) / n) + k * math.log(max(n, 2))


def _fit_all(t: np.ndarray, r: np.ndarray) -> dict:
    """Every `curve_forms` form the series can carry, each scored by BIC.

    Fitted on the τ grid (`refine=False`): the observed series and every
    bootstrap replicate go through this one procedure, so the null
    distribution is of the statistic reported. The noise variance is counted
    in no model here, forms and nulls alike, so the comparison is unaffected.
    """
    n = len(t)
    fitted = _cf.fit_forms(t, r, refine=False)
    return {
        name: {
            "rss": v["wrss"],
            "bic": _bic(v["wrss"], n, _cf.K_MEAN[name]),
            "k": _cf.K_MEAN[name],
            "params": v["params"],
        }
        for name, v in fitted["fits"].items()
    }


def _chosen(forms: dict) -> str:
    """The library's own rule over BIC: the constant unless a form beats it,
    and a more complex form only when it beats the one chosen so far, each by
    the library's margin — so a rise-and-fall imitating an exponential on a
    sliver of criterion does not displace it."""
    return _cf.choose({name: f["bic"] for name, f in forms.items()})


def _ar1_fit(r: np.ndarray) -> tuple[float, float, float]:
    """(phi, sigma_e, BIC) of the AR(1) null, exact stationary Gaussian likelihood.

    -2 lnL = n ln(RSS/n) - ln(1 - phi^2) + const.
    """
    n = len(r)
    phi = float(np.sum(r[1:] * r[:-1]) / max(np.sum(r[:-1] ** 2), 1e-300))
    phi = float(np.clip(phi, -0.98, 0.98))
    innov = r[1:] - phi * r[:-1]
    rss = float(np.sum(innov**2) + r[0] ** 2 * (1 - phi**2))
    sigma_e = math.sqrt(max(rss / n, 1e-300))
    bic = (
        n * math.log(max(rss, 1e-300) / n)
        - math.log(1 - phi**2)
        + 1 * math.log(max(n, 2))
    )
    return phi, sigma_e, bic


def _simulate_ar1(rng, n: int, phi: float, sigma_e: float) -> np.ndarray:
    r = np.empty(n)
    r[0] = rng.normal(0, sigma_e / math.sqrt(max(1 - phi**2, 1e-6)))
    e = rng.normal(0, sigma_e, n)
    for i in range(1, n):
        r[i] = phi * r[i - 1] + e[i]
    return r


def fit_residual_form(
    t,
    r,
    at_floor: bool = False,
    n_boot: int = 100,
    alpha: float = 0.05,
    seed: int = 20260907,
) -> dict:
    """Name the trend in a residual series against white-noise and AR(1) nulls.

    The forms are the `curve_forms` library's four (constant, linear,
    exponential, rise-and-fall), chosen by that library's rule over BIC. The
    chosen form's ΔBIC over each null is calibrated by a parametric bootstrap
    under that null (BIC's asymptotics mean nothing on an eight-point series,
    and a smooth curve fits an autocorrelated random walk well); beating a null
    means bootstrap p below `alpha`. A series already at the noise floor
    (`at_floor`) is refused: fitting forms to it manufactures mechanism. The
    `n_boot`/`alpha` defaults mirror `diagnostics.form_fit` for unit tests;
    engine callers pass the spec's values.
    """
    t = np.asarray(t, dtype=float)
    r = np.asarray(r, dtype=float)
    n = len(t)
    if at_floor:
        return {
            "refused": "series already at the assay's noise floor — no trend to name; "
            "fitting a form here would manufacture mechanism",
            "n": int(n),
            "standing_rule": STANDING_NOTE,
        }
    if n < 5:
        return {
            "refused": f"only {n} time points — too few to distinguish any form from noise",
            "n": int(n),
            "standing_rule": STANDING_NOTE,
        }
    forms = _fit_all(t, r)
    if not forms:
        return {
            "refused": "no form is fittable on this series",
            "n": int(n),
            "standing_rule": STANDING_NOTE,
        }
    bic_white = _bic(float(np.sum(r**2)), n, 0)
    phi, sigma_e, bic_ar1 = _ar1_fit(r)
    best_name = _chosen(forms)
    best = forms[best_name]
    d_white = bic_white - best["bic"]
    d_ar1 = bic_ar1 - best["bic"]

    rng = np.random.default_rng(seed)
    boot_ar1, boot_white = [], []
    sigma_w = math.sqrt(max(float(np.mean(r**2)), 1e-300))
    for _ in range(int(n_boot)):
        rb = _simulate_ar1(rng, n, phi, sigma_e)
        fb = _fit_all(t, rb)
        if fb:
            boot_ar1.append(_ar1_fit(rb)[2] - fb[_chosen(fb)]["bic"])
        rw = rng.normal(0, sigma_w, n)
        fw = _fit_all(t, rw)
        if fw:
            boot_white.append(_bic(float(np.sum(rw**2)), n, 0) - fw[_chosen(fw)]["bic"])
    p_ar1 = float((np.sum(np.asarray(boot_ar1) >= d_ar1) + 1) / (len(boot_ar1) + 1))
    p_white = float(
        (np.sum(np.asarray(boot_white) >= d_white) + 1) / (len(boot_white) + 1)
    )

    if best_name == "constant":
        verdict = "no time-shape beats a constant offset: the residuals carry a level, not a trend"
    elif p_ar1 < alpha and p_white < alpha:
        verdict = (
            f"{best_name} beats both nulls (bootstrap p vs AR(1) {p_ar1:.3f}, vs white "
            f"{p_white:.3f}) — a nameable trend, not autocorrelated noise"
        )
    elif p_white < alpha:
        verdict = (
            f"{best_name} beats white noise (p {p_white:.3f}) but NOT the AR(1) null "
            f"(p {p_ar1:.3f}): consistent with autocorrelated noise; not a trend to build on"
        )
    else:
        verdict = "no form beats white noise: the residuals carry no nameable trend"
    return {
        "n": int(n),
        "best_form": best_name,
        "best_params": {a: round(v, 6) for a, v in best["params"].items()},
        "timescales": _cf.timescales_of(best_name, best["params"]),
        "delta_bic_vs_white": round(d_white, 3),
        "delta_bic_vs_ar1": round(d_ar1, 3),
        "p_vs_white_null": round(p_white, 4),
        "p_vs_ar1_null": round(p_ar1, 4),
        "alpha": alpha,
        "n_bootstrap": int(n_boot),
        "ar1_null": {"phi": round(phi, 3), "sigma_e": round(sigma_e, 4)},
        "forms": {
            k: {
                "rss": round(v["rss"], 6),
                "bic": round(v["bic"], 3),
                "k": v["k"],
                "params": {a: round(x, 6) for a, x in v["params"].items()},
            }
            for k, v in forms.items()
        },
        "verdict": verdict,
        "standing_rule": STANDING_NOTE,
    }


def _residual_curve(ctx, cand_ids, args) -> dict:
    """One series' point-by-point fit, the curve behind the payload's descriptors.

    Nothing is fitted; the series is re-simulated at the candidate's optimum.
    """
    cid = str(args.get("candidate_id", ""))
    if cid not in cand_ids:
        raise ValueError(f"candidate_id must be one of {sorted(cand_ids)}, got {cid!r}")
    obs_id = str(args.get("observable_id", ""))
    cond_id = str(args.get("condition_id", ""))
    tables, best, _asm, _long, floors = _candidate(ctx, cid)
    known_o = set(tables.observables["observableId"].astype(str))
    known_c = set(tables.conditions["conditionId"].astype(str))
    if obs_id not in known_o or cond_id not in known_c:
        raise ValueError(
            f"observable_id/condition_id not in the problem (observables "
            f"{sorted(known_o)}, conditions {sorted(known_c)})"
        )
    grp = tables.measurements[
        (tables.measurements["observableId"] == obs_id)
        & (tables.measurements["simulationConditionId"] == cond_id)
    ]
    if grp.empty:
        raise ValueError(
            f"{obs_id}@{cond_id} carries no measurement in this candidate's "
            f"problem — nothing was fitted there, so there is no residual"
        )
    return {
        "candidate_id": cid,
        "series": f"{obs_id}@{cond_id}",
        **_series(tables, best, floors, obs_id, cond_id),
        "how_to_read_this": (
            "the same series the payload summarised, point by point: "
            "`fit_over_time` is measured, simulated and the residual in units "
            "of the assay's own replicate noise"
        ),
    }


def _profile_path(ctx, cand_ids, args) -> dict:
    """One parameter's profile-likelihood path, read from the round's
    `evaluation_core`.

    The agent view of the report drops the paths; this returns one on request.
    """
    from octomod.agents.payload import for_agents

    pid = str(args.get("parameter_id", ""))
    core = (ctx.round / "evaluation_core").get(None)
    if core is None:
        raise ValueError(
            f"{(ctx.round / 'evaluation_core').key} does not exist yet — "
            f"profiles are written by the evaluation module"
        )
    profiles = core.get("profiles") or {}
    known = sorted(k for k in profiles if not str(k).startswith("_"))
    if pid not in profiles or pid.startswith("_"):
        raise ValueError(f"parameter_id must be one of {known}, got {pid!r}")
    rec = dict(profiles[pid])
    if not rec.get("path"):
        raise ValueError(
            f"{pid} has a profile record but no path — the profile did not run "
            f"to completion here"
        )
    return {
        "parameter_id": pid,
        **for_agents(rec),
        "how_to_read_this": (
            "the profile likelihood along this parameter: `path.x_unscaled` "
            "against `path.nllh`, with `path.nllh_threshold` the level whose "
            "crossing defines `ci95` and `path.likelihood_ratio` the same "
            "thing normalised (1.0 at the optimum, `ratio_threshold` at the "
            "interval's edge). A path that runs into its bound without the "
            "likelihood falling away did not bound the parameter, and "
            "`ci_finite` says whether it closed. `path.x_full_scaled` is the "
            "whole parameter vector at each point, which is where to look for "
            "the parameters that compensate as this one moves."
        ),
    }


_RUNNERS = {
    "simulate_with": _simulate_with,
    "residuals_for": _residuals_for,
    "compare_conditions": _compare_conditions,
    "fit_residual_form": _fit_residual_form_request,
    # detail the payload leaves out, on request; nothing is fitted
    "residual_curve": _residual_curve,
    "profile_path": _profile_path,
}


def run_request(
    ctx, cand_ids: list[str], request: dict, module: str = "revision"
) -> dict:
    """Execute one whitelisted request and ledger it.

    Never raises: an error is returned in the result, for the agent to read.
    """
    import json as _json

    kind = str((request or {}).get("kind", ""))
    args = (request or {}).get("args") or {}
    out = {"kind": kind, "args": args}
    if kind not in _RUNNERS:
        out["error"] = f"unknown diagnostic kind {kind!r}; whitelisted: {list(KINDS)}"
    else:
        try:
            out["result"] = _RUNNERS[kind](ctx, cand_ids, args)
        except Exception as e:
            out["error"] = f"{type(e).__name__}: {e}"
    ctx.ledger.append(
        "diagnostic_request",
        module=module,
        round_idx=ctx.round_idx,
        kind=kind,
        args=args,
        ok="error" not in out,
        result_sha=sha256_text(_json.dumps(out, sort_keys=True, default=str)),
        error=out.get("error"),
    )
    return out


def run_requests(
    ctx,
    cand_ids: list[str],
    requests: list,
    max_requests: int | None,
    module: str = "revision",
) -> list[dict]:
    """Execute the requests, at most `max_requests` of them (None = no cap).

    `module` names which agent asked, the expansion proposer or the interpreter.
    Requests beyond the cap are not run; a ledger note says how many.
    """
    # no cap is affordable: every kind is a read or a quick simulation
    reqs = list(requests or [])
    if max_requests is not None:
        reqs = reqs[: max(int(max_requests), 0)]
    results = [run_request(ctx, cand_ids, r, module) for r in reqs]
    if len(requests or []) > len(reqs):
        ctx.ledger.append(
            "note",
            module=module,
            round_idx=ctx.round_idx,
            note=f"{len(requests) - len(reqs)} diagnostic request(s) beyond "
            f"the cap of {max_requests} were not run",
        )
    return results
