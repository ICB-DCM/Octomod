"""Mechanism attribution: which measurements pay for the winner's ΔAIC.

The Δ decomposition splits each rival's ΔAIC over (observable, condition) from
AMICI's own rdatas, so it matches AMICI's likelihood exactly or is not shown.
Term neutralisation sets one mechanism parameter to its declared neutral value
and reports which series move, in units of each point's sigma.
"""

from __future__ import annotations

import math

import numpy as np

LOG2PI = float(np.log(2 * np.pi))

# How closely the per-point split must reproduce AMICI's per-condition likelihood
# for the decomposition to be shown. A tripwire, not a tolerance: it fires on a
# transformation or noise distribution the split does not implement.
SPLIT_TOL = 1e-6
# How far the split's ΔAIC may sit from the discrimination table's before the two
# are reported as disagreeing: the table rounds to 3 decimals and the split
# re-evaluates the likelihood, so a few hundredths is solver noise.
TABLE_TOL = 0.05

# A rival contributing less than this share of |Δnllh| at one group is noise
# in the reader's way, not attribution.
REPORT_SHARE = 0.02
TOP_GROUPS = 6
TOP_POINTS = 8


def _scaled_x(summary: dict, scales: dict, x_names: list[str], free_idx) -> np.ndarray:
    """The recorded MLE, back on the estimation scale the objective expects."""
    best = summary["best_x_unscaled"]
    out = []
    for i in free_idx:
        name = x_names[i]
        v = float(best[name])
        sc = scales.get(name, "lin")
        # numpy, not math: a switched-off term is exactly 0, `math.log10(0)`
        # raises, and `np.log10(0)` gives -inf, which pyPESTO unscales back to 0
        with np.errstate(divide="ignore"):
            out.append(
                float(np.log10(v))
                if sc == "log10"
                else (float(np.log(v)) if sc == "log" else v)
            )
    return np.asarray(out, dtype=float)


def _split_group(
    meas: np.ndarray,
    sim: np.ndarray,
    sigma: np.ndarray,
    transformation: str,
    distribution: str,
) -> np.ndarray:
    """PEtab's per-point negative log-likelihood contributions."""
    y, yhat = np.asarray(meas, float), np.asarray(sim, float)
    if transformation == "log10":
        y, yhat = np.log10(y), np.log10(yhat)
    elif transformation == "log":
        y, yhat = np.log(y), np.log(yhat)
    if distribution == "laplace":
        return np.log(2 * sigma) + np.abs(y - yhat) / sigma
    return 0.5 * (LOG2PI + 2 * np.log(sigma)) + 0.5 * ((y - yhat) / sigma) ** 2


def evaluate_at_mle(
    inp,
    summary: dict,
    cache: dict,
    *,
    overrides: dict[str, float] | None = None,
    spec=None,
    solver: dict | None = None,
) -> dict:
    """Per-point nllh at the recorded MLE, grouped by (observable, condition).

    `inp` is the candidate's assembled problem, a `petab_io.PetabInput`
    (`petab_io.from_work(ctx.work, ctx.model)`).

    `overrides` replaces named parameters (unscaled) first; term neutralisation
    uses it. The split comes from AMICI's rdatas, not a re-simulation (roadrunner
    agrees only to ~1e-4 relative). The record carries `total` (the split's sum),
    `amici_total`, `split_exact` and `drift` (re-evaluated minus recorded nllh).
    """
    from octomod.workflow_modules.estimation.problem import (
        build_problem,
        parameter_scales,
    )

    # the solver settings the fit ran under (`solver`: this candidate's recorded
    # choices), or `drift` would report a settings difference as solver noise
    problem, _petab_problem, _ = build_problem(inp, cache, spec, overrides=solver)
    scales = parameter_scales(inp)
    x_names = list(problem.x_names)
    free_idx = list(problem.x_free_indices)

    summary = dict(summary)
    # A candidate whose every start failed has an infinite `best_fval` or an
    # empty best vector: no optimum to evaluate. A NaN `best_fval` only means no
    # value was recorded.
    best_fval = summary.get("best_fval")
    try:
        dead_fval = best_fval is not None and np.isinf(float(best_fval))
    except (TypeError, ValueError):
        dead_fval = False
    if dead_fval or not summary.get("best_x_unscaled"):
        return {
            "available": False,
            "why": (
                "candidate has no finite optimum (see estimation_convergence): every "
                "start failed, so there is no MLE to evaluate and nothing to "
                "decompose"
            ),
        }
    if overrides:
        best = dict(summary["best_x_unscaled"])
        unknown = sorted(set(overrides) - set(best))
        if unknown:
            return {"available": False, "why": f"unknown parameter(s) {unknown}"}
        # No scale guard: a log10 parameter overridden to 0 is -inf on the scaled
        # vector, which pyPESTO unscales back to 0 before AMICI sees it.
        for k, v in overrides.items():
            best[k] = float(v)
        summary["best_x_unscaled"] = best

    try:
        x = _scaled_x(summary, scales, x_names, free_idx)
        res = problem.objective(x, sensi_orders=(0,), return_dict=True)
    except Exception as e:  # a failed evaluation is no attribution
        return {"available": False, "why": f"{type(e).__name__}: {e}"}
    rdatas = res.get("rdatas") or []
    if not rdatas:
        return {"available": False, "why": "the objective returned no AMICI rdatas"}

    obj = problem.objective
    obs_ids = list(obj.amici_model.get_observable_ids())
    edatas = list(getattr(obj, "edatas", []) or [])
    obs_df = inp.observables
    obs_meta = {
        str(r["observableId"]): (
            str(r.get("observableTransformation", "lin") or "lin"),
            str(r.get("noiseDistribution", "normal") or "normal"),
        )
        for _, r in obs_df.iterrows()
    }
    cond_ids = [
        str(getattr(e, "id", "") or f"condition_{k}") for k, e in enumerate(edatas)
    ]

    groups: dict[str, dict] = {}
    total = 0.0
    per_condition_mismatch = 0.0
    for k, rd in enumerate(rdatas):
        y = np.asarray(rd.y, dtype=float)
        sigma = np.asarray(rd.sigmay, dtype=float)
        ts = np.asarray(rd.ts, dtype=float)
        if k >= len(edatas):
            return {"available": False, "why": "fewer edatas than rdatas"}
        meas = np.asarray(edatas[k].get_measurements(), dtype=float).reshape(y.shape)
        cond_id = cond_ids[k]
        cond_total = 0.0
        for j, oid in enumerate(obs_ids):
            m = meas[:, j]
            mask = np.isfinite(m)
            if not mask.any():
                continue
            trans, dist = obs_meta.get(oid, ("lin", "normal"))
            sig = np.maximum(sigma[mask, j], 1e-300)
            vals = _split_group(m[mask], y[mask, j], sig, trans, dist)
            groups[f"{oid}@{cond_id}"] = {
                "observable": oid,
                "condition": cond_id,
                "nllh": float(vals.sum()),
                "n": int(mask.sum()),
                "times": [float(t) for t in ts[mask]],
                "measured": [float(v) for v in m[mask]],
                "simulated": [float(v) for v in y[mask, j]],
                "sigma": [float(v) for v in sig],
                "point_nllh": [float(v) for v in vals],
            }
            cond_total += float(vals.sum())
            total += float(vals.sum())
        per_condition_mismatch = max(
            per_condition_mismatch, abs(cond_total - (-float(rd.llh)))
        )

    amici_total = -float(sum(float(d.llh) for d in rdatas))
    recorded = float(summary.get("best_fval", float("nan")))
    return {
        "available": True,
        "groups": groups,
        "total": total,
        "amici_total": amici_total,
        "split_exact": abs(total - amici_total) <= SPLIT_TOL
        and per_condition_mismatch <= SPLIT_TOL,
        "split_mismatch": float(abs(total - amici_total)),
        "worst_condition_mismatch": float(per_condition_mismatch),
        "recorded_nllh": recorded,
        "drift": (float(amici_total - recorded) if math.isfinite(recorded) else None),
        "overrides": {k: float(v) for k, v in (overrides or {}).items()},
    }


def decompose(
    winner_id: str,
    evals: dict[str, dict],
    n_est: dict[str, int],
    table_delta_aic: dict[str, float] | None = None,
) -> dict:
    """Split the ΔAIC between the winner and each rival over (observable, condition).

    ΔAIC has two terms, reported separately: `2*Δnllh`, which splits over
    measurements, and the parameter term, which does not. With
    `d_nllh = nllh_rival - nllh_winner` and `d_k = k_winner - k_rival`,

        ΔAIC(rival − winner) = 2·d_nllh − 2·d_k

    so the parameter term is negative when the winner carries more parameters.
    `table_delta_aic` (candidate id -> ΔAIC to the criterion minimum), when given,
    is reconciled against every rival's split and a mismatch is recorded.
    """
    win = evals.get(winner_id) or {}
    if not win.get("available"):
        return {
            "available": False,
            "why": f"the winner could not be re-evaluated: {win.get('why', '?')}",
        }
    if not win.get("split_exact"):
        return {
            "available": False,
            "why": (
                f"the per-point split does not reproduce AMICI's own likelihood "
                f"(off by {win['split_mismatch']:.3e}); an observable "
                f"transformation or noise distribution is in use that the split "
                f"does not implement, so no decomposition is shown"
            ),
        }
    rivals = []
    for cid, ev in evals.items():
        if cid == winner_id:
            continue
        if not (ev.get("available") and ev.get("split_exact")):
            rivals.append(
                {
                    "rival": cid,
                    "available": False,
                    "why": ev.get("why") or "the split was not exact",
                }
            )
            continue
        d_nllh = ev["total"] - win["total"]  # > 0 when the winner fits better
        d_k = n_est.get(winner_id, 0) - n_est.get(cid, 0)
        contributions = []
        shared = set(win["groups"]) & set(ev["groups"])
        for g in sorted(shared):
            delta = ev["groups"][g]["nllh"] - win["groups"][g]["nllh"]
            contributions.append(
                {
                    "group": g,
                    "observable": win["groups"][g]["observable"],
                    "condition": win["groups"][g]["condition"],
                    "delta_nllh": float(delta),
                    "delta_aic_units": float(2 * delta),
                    "n": win["groups"][g]["n"],
                }
            )
        contributions.sort(key=lambda c: -abs(c["delta_nllh"]))
        scale = sum(abs(c["delta_nllh"]) for c in contributions) or 1.0
        for c in contributions:
            c["share"] = round(abs(c["delta_nllh"]) / scale, 4)
        only_win = sorted(set(win["groups"]) - shared)
        only_rival = sorted(set(ev["groups"]) - shared)
        delta_aic = float(2 * d_nllh - 2 * d_k)
        rec = {
            "rival": cid,
            "available": True,
            "delta_nllh": float(d_nllh),
            "delta_k": int(d_k),
            "delta_aic": delta_aic,
            "likelihood_units": float(2 * d_nllh),
            # negative when the winner carries more parameters (see the docstring)
            "parameter_units": float(-2 * d_k),
            "contributions": contributions,
            "groups_only_in_winner": only_win,
            "groups_only_in_rival": only_rival,
            "top": [
                c for c in contributions[:TOP_GROUPS] if c["share"] >= REPORT_SHARE
            ],
        }
        if table_delta_aic and cid in table_delta_aic and winner_id in table_delta_aic:
            # the selection table's ΔAIC is to the criterion MINIMUM; the
            # split is winner-relative, so compare rival-minus-winner
            from_table = float(table_delta_aic[cid]) - float(table_delta_aic[winner_id])
            rec["table_delta_aic"] = from_table
            rec["matches_table"] = abs(from_table - delta_aic) <= TABLE_TOL
        rivals.append(rec)
    rivals.sort(key=lambda r: -(r.get("delta_aic") or 0))
    mismatched = [
        r["rival"]
        for r in rivals
        if r.get("available") and r.get("matches_table") is False
    ]
    return {
        "available": True,
        "winner": winner_id,
        "rivals": rivals,
        "reconciliation": {
            "winner_recorded_nllh": win["recorded_nllh"],
            "winner_reevaluated_nllh": win["amici_total"],
            "winner_drift": win["drift"],
            "split_tolerance": SPLIT_TOL,
            "table_checked": table_delta_aic is not None,
            "table_mismatches": mismatched,
            "table_tolerance": TABLE_TOL,
            "note": (
                "the split is exact against AMICI's own per-condition likelihood; "
                "`drift` is the difference between re-evaluating the recorded "
                "optimum and the value the fit recorded there, which is solver "
                "noise between two evaluations and is not attributed to any "
                "measurement"
            ),
        },
    }


def per_timepoint(winner_eval: dict, rival_eval: dict, group: str) -> list[dict]:
    """Where inside one series the ΔAIC is paid: the largest per-point differences."""
    w = (winner_eval.get("groups") or {}).get(group)
    r = (rival_eval.get("groups") or {}).get(group)
    if not (w and r):
        return []
    rows = [
        {
            "time": w["times"][i],
            "measured": w["measured"][i],
            "winner_sim": w["simulated"][i],
            "rival_sim": r["simulated"][i],
            "delta_nllh": float(r["point_nllh"][i] - w["point_nllh"][i]),
        }
        for i in range(min(len(w["times"]), len(r["times"])))
    ]
    rows.sort(key=lambda x: -abs(x["delta_nllh"]))
    return rows[:TOP_POINTS]


def mechanism_parameters(axes: list[dict], axes_on: list[str], encoding: dict) -> dict:
    """Neutralisable mechanism parameters of the winner, and why the rest are not.

    A declared neutral value that the encoding check (per axis, the model's
    `encoding` record)
    showed not to reproduce the base model is refused: simulating it would
    describe a term that was never switched off.
    """
    from octomod.workflow_modules.model import supermodel

    verdicts = ((encoding or {}).get("verification") or {}).get("per_axis") or {}
    usable: dict[str, dict] = {}
    refused: dict[str, str] = {}
    on = set(axes_on or [])
    for a in axes or []:
        aid = str(a.get("id"))
        if aid not in on:
            continue
        verdict = verdicts.get(aid)
        if verdict is not None and not verdict.get("neutralizes"):
            refused[aid] = (
                f"its declared neutral value was shown NOT to neutralize it "
                f"(the simulation check: {verdict.get('why', 'no detail')[:160]}) — "
                f"simulating it would describe a term that was never off"
            )
            continue
        switches, _inert = supermodel.neutral_split(a)
        if not switches:
            refused[aid] = (
                f"no neutral_value on any parameter of {aid}, so there is no "
                f"value at which its term is known to be off"
            )
            continue
        # switches only: an inert parameter (a half-saturation the switch makes
        # irrelevant) has no off-state; switching the strength off covers the term
        for prm in switches:
            why = supermodel.neutral_problem(prm)
            if why:
                refused[aid] = why
                continue
            usable[str(prm["id"])] = {
                "axis": aid,
                "neutral_value": float(prm[supermodel.NEUTRAL_FIELD]),
                "denotes": str(prm.get("denotes", "") or ""),
                "verified_by_simulation": bool((verdict or {}).get("neutralizes")),
            }
    return {"usable": usable, "refused": refused}


def neutralise(
    inp,
    summary: dict,
    cache: dict,
    mechanism: dict,
    baseline: dict,
    spec=None,
    solver: dict | None = None,
) -> dict:
    """For each usable mechanism parameter, what moves when it is switched off.

    Movement is in units of each point's own sigma.
    """
    out: dict[str, dict] = {}
    for pid, meta in (mechanism.get("usable") or {}).items():
        ev = evaluate_at_mle(
            inp,
            summary,
            cache,
            overrides={pid: meta["neutral_value"]},
            spec=spec,
            solver=solver,
        )
        if not ev.get("available"):
            out[pid] = {"available": False, "why": ev.get("why", "?"), **meta}
            continue
        moved = []
        for g, base in (baseline.get("groups") or {}).items():
            off = (ev.get("groups") or {}).get(g)
            if not off:
                continue
            sig = np.maximum(np.asarray(base["sigma"], float), 1e-300)
            shift = np.abs(
                np.asarray(off["simulated"], float)
                - np.asarray(base["simulated"], float)
            )
            moved.append(
                {
                    "group": g,
                    "worst_shift_in_sigma": float(np.max(shift / sig)),
                    "mean_shift_in_sigma": float(np.mean(shift / sig)),
                    "delta_nllh": float(off["nllh"] - base["nllh"]),
                }
            )
        moved.sort(key=lambda m: -m["worst_shift_in_sigma"])
        out[pid] = {
            "available": True,
            **meta,
            "nllh_off": ev["total"],
            "nllh_on": baseline["total"],
            "cost_of_switching_off_aic_units": float(
                2 * (ev["total"] - baseline["total"])
            ),
            "series": moved,
            "series_that_move": [
                m["group"] for m in moved if m["worst_shift_in_sigma"] >= 1.0
            ],
        }
    return {"parameters": out, "refused": mechanism.get("refused") or {}}


def compact(
    dec: dict,
    neut: dict,
    evals: dict,
    winner_id: str,
    full_record: str = "attribution",
) -> dict:
    """The attribution as the round's `evaluation_core` carries it.

    `full_record` names where the full record is kept: the record key of the
    round's `attribution` (e.g. `rounds/round_0/attribution`). The per-point
    record stays there; this keeps the totals, the per-group split, and the
    per-timepoint detail of each rival's largest contributor.
    """
    out = {
        "available": bool(dec.get("available")),
        "winner": winner_id,
        "reconciliation": dec.get("reconciliation"),
        "full_record": full_record,
    }
    if not dec.get("available"):
        out["why"] = dec.get("why")
    rivals = []
    for r in dec.get("rivals") or []:
        if not r.get("available"):
            rivals.append({k: r[k] for k in ("rival", "available", "why") if k in r})
            continue
        entry = {
            k: r[k]
            for k in (
                "rival",
                "available",
                "delta_aic",
                "delta_nllh",
                "delta_k",
                "likelihood_units",
                "parameter_units",
                "contributions",
                "top",
                "groups_only_in_winner",
                "groups_only_in_rival",
            )
        }
        if r.get("top"):
            g = r["top"][0]["group"]
            entry["worst_group_detail"] = {
                "group": g,
                "points": per_timepoint(
                    evals.get(winner_id) or {}, evals.get(r["rival"]) or {}, g
                ),
            }
        rivals.append(entry)
    out["rivals"] = rivals
    out["neutralisation"] = {
        "note": neut.get("note"),
        "refused": neut.get("refused") or {},
        "parameters": {
            pid: {k: v for k, v in rec.items() if k != "series"}
            | {
                "series": [
                    m
                    for m in (rec.get("series") or [])
                    if m.get("worst_shift_in_sigma", 0) >= 0.1
                ][:TOP_GROUPS]
            }
            for pid, rec in (neut.get("parameters") or {}).items()
        },
    }
    return out


def card_lines(dec: dict, neut: dict | None = None, limit: int = 4) -> list[str]:
    """Attribution lines for the verdict card and the interpreter's context."""
    if not dec.get("available"):
        return [f"mechanism attribution unavailable: {dec.get('why', '?')}"]
    lines: list[str] = []
    for r in (dec.get("rivals") or [])[:limit]:
        if not r.get("available"):
            lines.append(f"vs {r['rival']}: not decomposed ({r.get('why', '?')})")
            continue
        top = r.get("top") or []
        where = "; ".join(f"{c['group']} {c['delta_aic_units']:+.1f}" for c in top[:3])
        lines.append(
            f"vs {r['rival']}: ΔAIC {r['delta_aic']:+.1f} = "
            f"{r['likelihood_units']:+.1f} likelihood {r['parameter_units']:+.1f} "
            f"parameters" + (f" — paid at {where}" if where else "")
        )
    for pid, rec in ((neut or {}).get("parameters") or {}).items():
        if not rec.get("available"):
            continue
        movers = rec.get("series_that_move") or []
        lines.append(
            f"switching {pid} off (axis {rec['axis']}, neutral "
            f"{rec['neutral_value']:g}) costs "
            f"{rec['cost_of_switching_off_aic_units']:+.1f} AIC units and moves "
            + (
                f"{', '.join(movers[:3])}"
                if movers
                else "no series by more than 1 sigma"
            )
        )
    for aid, why in ((neut or {}).get("refused") or {}).items():
        lines.append(f"axis {aid} not neutralised: {why[:140]}")
    return lines
