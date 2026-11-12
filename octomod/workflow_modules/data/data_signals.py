"""What the data itself says before any model exists: deterministic, no agent.

Chiefly the noise model: the slope of replicate spread against signal magnitude
separates additive from multiplicative error (with few replicates a slope is
still estimable, a distribution family is not). Also value support, group-level
drift, closure sums, raw curve shapes and `curve_descriptors`: each raw series
fitted with the `curve_forms` library, compared with its control condition and
across doses. The artifact routes to the observation-model agent only;
construction never sees measurement values. What it may see of the curves is
`phenomenology`, sentences built from the descriptors that carry shape words and
rounded timescales only.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

# Slope 0: the spread does not follow the signal (additive); slope 1: it scales
# with it (multiplicative). A verdict needs the interval to exclude one of them.
ADDITIVE, MULTIPLICATIVE = 0.0, 1.0
MIN_POINTS_FOR_SLOPE = 3

# Columns a whole-group offset may be read against; each must cross-cut the
# (condition, time) cells. Not `time`: its within-cell offsets are identically
# zero, and a per-time scaling is not separable from dynamics here.
DRIFT_COLUMNS = ("replicate", "batch", "injection", "plate", "run", "experiment")
# Above this F the offsets are worth a sentence in the card. Not a verdict
# and not a p-value: it decides what gets SAID, never what gets fitted.
DRIFT_F_NOTABLE = 4.0
# max/min of the cross-observable sum above which the card asks the
# conserved-pool question. 1.5x is a wide margin for a real conservation.
CLOSURE_SPREAD_NOTABLE = 1.5


def _replicate_stats(group: pd.DataFrame) -> tuple[float, float, int]:
    """(mean, sample sd, n) of one (observable, condition, time) cell.

    The sd is nan for n < 2, without calling `np.std(ddof=1)`, which warns on a
    single value."""
    vals = group["value"].to_numpy(dtype=float)
    n = int(len(vals))
    sd = float(np.std(vals, ddof=1)) if n >= 2 else float("nan")
    return float(np.mean(vals)), sd, n


def _slope_with_ci(
    logm: np.ndarray, logs: np.ndarray
) -> tuple[float, float, float, float]:
    """OLS slope of log(sd) on log(mean), with a 95% interval.

    Returned rather than thresholded, so the caller can say how close it came.
    """
    n = len(logm)
    x = logm - logm.mean()
    sxx = float(np.sum(x**2))
    if n < MIN_POINTS_FOR_SLOPE or sxx <= 0:
        return float("nan"), float("nan"), float("nan"), float("nan")
    slope = float(np.sum(x * (logs - logs.mean())) / sxx)
    intercept = float(logs.mean() - slope * logm.mean())
    resid = logs - (intercept + slope * logm)
    dof = n - 2
    if dof <= 0:
        return slope, float("nan"), float("nan"), float("nan")
    s2 = float(np.sum(resid**2) / dof)
    se = math.sqrt(s2 / sxx) if sxx > 0 else float("nan")
    # t quantiles without scipy (1.96 is optimistic at small dof)
    t = {1: 12.71, 2: 4.30, 3: 3.18, 4: 2.78, 5: 2.57, 6: 2.45, 7: 2.36}.get(
        dof, 2.0 + 4.0 / max(dof, 1)
    )
    return slope, se, slope - t * se, slope + t * se


def _verdict(slope: float, lo: float, hi: float, n_points: int) -> dict:
    """Additive, multiplicative, or honestly inconclusive."""
    if n_points < MIN_POINTS_FOR_SLOPE or not math.isfinite(slope):
        return {
            "error_model": "inconclusive",
            "why": (
                f"only {n_points} usable replicate cell(s); a slope needs at "
                f"least {MIN_POINTS_FOR_SLOPE}"
            ),
        }
    if not (math.isfinite(lo) and math.isfinite(hi)):
        return {
            "error_model": "inconclusive",
            "why": "the slope has no usable interval (no residual degrees of freedom)",
        }
    excludes_add = lo > ADDITIVE or hi < ADDITIVE
    excludes_mult = lo > MULTIPLICATIVE or hi < MULTIPLICATIVE
    if excludes_mult and not excludes_add:
        return {
            "error_model": "additive",
            "why": (
                f"the spread-vs-magnitude slope is {slope:.2f} "
                f"[{lo:.2f}, {hi:.2f}], which excludes 1 (proportional) and "
                f"contains 0 (constant)"
            ),
        }
    if excludes_add and not excludes_mult:
        return {
            "error_model": "multiplicative",
            "why": (
                f"the spread-vs-magnitude slope is {slope:.2f} "
                f"[{lo:.2f}, {hi:.2f}], which excludes 0 (constant) and "
                f"contains 1 (proportional)"
            ),
        }
    if excludes_add and excludes_mult:
        return {
            "error_model": "neither",
            "why": (
                f"the slope {slope:.2f} [{lo:.2f}, {hi:.2f}] excludes BOTH 0 and "
                f"1 — the spread follows the signal, but not proportionally. "
                f"Worth a look before choosing a noise formula."
            ),
        }
    return {
        "error_model": "inconclusive",
        "why": (
            f"the slope {slope:.2f} [{lo:.2f}, {hi:.2f}] spans both 0 and 1: "
            f"these replicates cannot separate constant from proportional "
            f"error. More replicates per point would; more timepoints would not."
        ),
    }


def _shape(times: np.ndarray, values: np.ndarray) -> dict:
    """Bin-free descriptors of one raw series, computed without a model.

    No bins: a peak's location is a signature that bins would lose. A
    steady-state measurement (time `inf`) is not on the time course, so it is
    left out.
    """
    on_course = np.isfinite(times)
    times, values = times[on_course], values[on_course]
    order = np.argsort(times)
    t, v = times[order], values[order]
    if len(t) < 3:
        return {"n_points": int(len(t)), "note": "too few timepoints for a shape"}
    # Spearman without scipy: Pearson on the ranks
    rt = pd.Series(t).rank().to_numpy()
    rv = pd.Series(v).rank().to_numpy()
    denom = float(np.std(rt) * np.std(rv))
    rho = float(np.mean((rt - rt.mean()) * (rv - rv.mean())) / denom) if denom else 0.0
    i_max = int(np.argmax(v))
    return {
        "n_points": int(len(t)),
        "monotone_trend_rho": round(rho, 3),
        "time_of_max": float(t[i_max]),
        "at_last_timepoint_fraction_of_max": (
            round(float(v[-1] / v[i_max]), 3) if v[i_max] else None
        ),
        "peaks_then_declines": bool(
            0 < i_max < len(v) - 1 and v[i_max] > 0 and v[-1] < 0.9 * v[i_max]
        ),
    }


def _support(values: np.ndarray) -> dict:
    """What values this observable takes: zeros, negatives, integers, range.

    `log_transform_legal` settles whether a log-normal noise model is possible
    at all (a background-subtracted intensity, for one, goes negative).
    """
    finite = values[np.isfinite(values)]
    n_zero = int(np.sum(finite == 0.0))
    n_neg = int(np.sum(finite < 0.0))
    integral = bool(finite.size and np.all(np.equal(np.mod(finite, 1), 0)))
    lo = float(np.min(finite)) if finite.size else float("nan")
    hi = float(np.max(finite)) if finite.size else float("nan")
    pos = finite[finite > 0]
    return {
        "n_values": int(values.size),
        "n_non_finite": int(values.size - finite.size),
        "n_zero": n_zero,
        "n_negative": n_neg,
        "integer_valued": integral,
        "min": round(lo, 6) if math.isfinite(lo) else None,
        "max": round(hi, 6) if math.isfinite(hi) else None,
        "dynamic_range": (
            round(float(np.max(pos) / np.min(pos)), 3)
            if pos.size and float(np.min(pos)) > 0
            else None
        ),
        "log_transform_legal": bool(finite.size and n_zero == 0 and n_neg == 0),
        "reading": (
            "COUNT-LIKE: every value is a whole number — a Gaussian noise "
            "model is a choice here, not a default"
            if integral
            else (
                "a log transform is NOT legal: "
                + ", ".join(
                    filter(
                        None,
                        [
                            f"{n_zero} zero(s)" if n_zero else "",
                            f"{n_neg} negative value(s)" if n_neg else "",
                        ],
                    )
                )
                if (n_zero or n_neg)
                else "strictly positive; a log transform is legal"
            )
        ),
    }


def _level_drift(obs_df: pd.DataFrame, by: str) -> dict:
    """Do whole `by` groups sit at different levels than replicate noise explains?

    E.g. intensities that drift between injections, which without a per-group
    scaling parameter would be read as model misfit. The deviations from each
    (condition, time) cell mean are split into per-group offsets and a residual,
    compared as a one-way F ratio (against the raw within-cell variance the ratio
    would saturate near 1 when `by` is the replicate index). Evidence, not a
    decision: a real per-group mechanism looks the same.
    """
    if by not in obs_df.columns:
        return {"available": False, "why": f"no {by!r} column"}
    devs: list[float] = []
    labels: list[object] = []
    for (_cond, _t), cell in obs_df.groupby(["condition_key", "time"]):
        sub = cell[np.isfinite(cell["value"].to_numpy(dtype=float))]
        if len(sub) < 2:
            continue
        m = float(np.mean(sub["value"].to_numpy(dtype=float)))
        for _i, row in sub.iterrows():
            devs.append(float(row["value"]) - m)
            labels.append(row[by])
    if not devs:
        return {"available": False, "why": "no cell had two finite values"}
    dev_arr = np.asarray(devs, dtype=float)
    lab_arr = np.asarray([str(x) for x in labels])
    groups = sorted(set(lab_arr.tolist()))
    if len(groups) < 2:
        return {"available": False, "why": f"fewer than 2 {by} groups with replicates"}

    offsets = {g: float(np.mean(dev_arr[lab_arr == g])) for g in groups}
    resid = dev_arr - np.array([offsets[g] for g in lab_arr])
    df_resid = len(dev_arr) - len(groups)
    if df_resid < 1:
        return {"available": False, "why": "no residual degrees of freedom"}
    ms_resid = float(np.sum(resid**2) / df_resid)
    ss_between = float(sum(int(np.sum(lab_arr == g)) * offsets[g] ** 2 for g in groups))
    ms_between = ss_between / (len(groups) - 1)
    if not ms_resid > 0:
        return {"available": False, "why": "no residual spread to compare against"}
    f_stat = ms_between / ms_resid
    return {
        "available": True,
        "grouped_by": by,
        "n_groups": len(groups),
        "n_deviations": int(dev_arr.size),
        "ms_between_group_offsets": round(ms_between, 8),
        "ms_residual": round(ms_resid, 8),
        "f_ratio": round(f_stat, 3),
        "df": [len(groups) - 1, df_resid],
        "group_offsets": {g: round(offsets[g], 6) for g in groups},
        "reading": (
            f"whole-{by} offsets are {f_stat:.1f}x the residual spread "
            f"(F[{len(groups) - 1},{df_resid}]) — consider a per-{by} scaling "
            f"or offset parameter; without one this drift lands in the "
            f"residuals and reads as model misfit"
            if f_stat > DRIFT_F_NOTABLE
            else f"whole-{by} offsets are within residual noise "
            f"(F={f_stat:.2f}); no scaling parameter is indicated"
        ),
    }


def _closure(long_df: pd.DataFrame) -> dict:
    """Do the observables at one (condition, time) sum to something stable?

    When the observables are components of one conserved pool, a moving per-cell
    sum is a per-cell scaling factor, visible without replicates. The engine
    cannot know whether they are, so the reading asks rather than guesses.
    """
    labels = sorted({str(x) for x in long_df["observable_label"].unique()})
    if len(labels) < 3:
        return {
            "available": False,
            "why": f"{len(labels)} observable(s); a closure sum needs at least 3",
        }
    sums, cells = [], []
    for (cond, t), cell in long_df.groupby(["condition_key", "time"]):
        vals = cell.groupby("observable_label")["value"].mean()
        if len(vals) < len(labels):
            continue  # a partly-measured cell has no comparable sum
        total = float(np.sum(vals.to_numpy(dtype=float)))
        sums.append(total)
        cells.append({"condition": str(cond), "time": float(t), "sum": round(total, 6)})
    if len(sums) < 2:
        return {
            "available": False,
            "why": "fewer than 2 cells measured every observable",
        }
    arr = np.asarray(sums, dtype=float)
    mean = float(np.mean(arr))
    cv = float(np.std(arr) / abs(mean)) if mean != 0 else float("nan")
    spread = float(np.max(arr) / np.min(arr)) if float(np.min(arr)) > 0 else None
    cells.sort(key=lambda c: (c["condition"], c["time"]))
    return {
        "available": True,
        "n_observables_summed": len(labels),
        "per_cell_sum": cells[:24],
        "mean": round(mean, 6),
        "cv": round(cv, 4) if math.isfinite(cv) else None,
        "max_over_min": round(spread, 3) if spread else None,
        "reading": _closure_reading(arr, labels, mean, cv, spread),
    }


def _closure_reading(arr, labels, mean, cv, spread) -> str:
    """The closure sentence: undefined (sums not all positive), notable, or stable.

    An undefined ratio gets its own reading and never falls through to "stable".
    """
    lo, hi = float(np.min(arr)), float(np.max(arr))
    if spread is None:
        return (
            f"the {len(labels)} observables sum to between {lo:.3g} and "
            f"{hi:.3g}, which is not strictly positive, so a closure ratio is "
            f"undefined. These are probably not components of one conserved "
            f"quantity — if they are, something upstream (a background "
            f"subtraction, a baseline) has moved them off that scale."
        )
    if spread > CLOSURE_SPREAD_NOTABLE:
        return (
            f"the {len(labels)} observables sum to between {lo:.3g} and "
            f"{hi:.3g} across cells ({spread:.1f}x). IF they are components of "
            f"one conserved quantity — fractions of a pool, states of one "
            f"molecule — that spread is a per-cell SCALING factor and the "
            f"model needs one; fitting fractions against it without a scaling "
            f"parameter fails on magnitude. If they are unrelated quantities, "
            f"this number means nothing. Which is it?"
        )
    return (
        f"the observables sum to {mean:.3g} with cv {cv:.2f} across cells "
        f"({spread:.2f}x) — stable, so no per-cell scaling is indicated by "
        f"closure"
    )


# A level within this ratio band of its control's reads as "at" the control.
AT_CONTROL_BAND = (0.8, 1.25)


def held_out_keys(long_df: pd.DataFrame, holdout_labels) -> set[str]:
    """The condition keys the staged holdout names, matched the way the S3 split
    matches them: by declared label, or by semantic key (a table without a
    label column is matched by key alone)."""
    if not holdout_labels or "condition_key" not in long_df.columns:
        return set()
    from octomod.workflow_modules.data.engine import parse_declared_label

    keys = long_df["condition_key"].fillna("").astype(str)
    out = {k for k in (parse_declared_label(str(h)) for h in holdout_labels) if k}
    out &= set(keys)
    if "condition_label" in long_df.columns:
        from octomod.workflow_modules.data.data_processing import holdout_conditions

        labels = holdout_conditions(long_df, holdout_labels)
        out |= set(keys[long_df["condition_label"].astype(str).isin(labels)])
    return out


def attributes_of(condition_key: str) -> dict[str, str]:
    """{column: value} of a semantic condition key ('dose=1|cell=B')."""
    return dict(
        part.split("=", 1) for part in str(condition_key).split("|") if "=" in part
    )


def _pooled_replicate_sd(obs_df: pd.DataFrame) -> float | None:
    """The replicate SD pooled over every (condition, time) cell with two or
    more values, or None without replicates."""
    var = obs_df.groupby(["condition_key", "time"])["value"].var(ddof=1).dropna()
    var = var[var > 0]
    return float(math.sqrt(float(var.mean()))) if len(var) else None


def _noise_scale(obs_df: pd.DataFrame) -> float:
    """One number for "within noise" when conditions are compared: the pooled
    replicate SD, or a tenth of the cell means' range without replicates."""
    sd = _pooled_replicate_sd(obs_df)
    if sd is not None:
        return sd
    means = obs_df.groupby(["condition_key", "time"])["value"].mean()
    return 0.1 * float(means.max() - means.min()) if len(means) else 0.0


def _series_sigma(cdf: pd.DataFrame, pooled: float | None):
    """(σ for one series' fit, where it came from).

    A declared per-row σ column first (the noise model the data came with),
    then the observable's pooled replicate SD, else None: the fit then profiles
    the variance out, which on a short unreplicated series leaves little power
    to see a shape at all.
    """
    if "sigma" in cdf.columns:
        sd = pd.to_numeric(cdf["sigma"], errors="coerce").to_numpy(dtype=float)
        if len(sd) and np.all(np.isfinite(sd)) and np.all(sd > 0):
            return sd, "declared"
    if pooled is not None:
        return pooled, "replicates"
    return None, "profiled"


def _control_of(key: str, attrs: dict, all_attrs: dict[str, dict]) -> str | None:
    """The condition that differs from `key` in one attribute only and carries a
    control value there (`curve_forms.CONTROL_VALUES`); None when the design
    has none for it."""
    from octomod.workflow_modules.data import curve_forms as _cf

    for other in sorted(all_attrs):
        if other == key:
            continue
        o = all_attrs[other]
        if set(o) != set(attrs):
            continue
        diff = [a for a in attrs if str(attrs[a]) != str(o[a])]
        if (
            len(diff) == 1
            and _cf.is_control_value(o[diff[0]])
            and not _cf.is_control_value(attrs[diff[0]])
        ):
            return other
    return None


def _vs_control(level, ctrl_level, tol: float) -> dict:
    """The last-sample level against the control's: a ratio when the control's
    level is clear of noise, and a below / at / above bucket either way."""
    if level is None or ctrl_level is None:
        return {"ratio": None, "bucket": None}
    lo, hi = AT_CONTROL_BAND
    if abs(ctrl_level) > tol and ctrl_level != 0:
        ratio = level / ctrl_level
        bucket = "below" if ratio < lo else ("above" if ratio > hi else "at")
        return {"ratio": round(ratio, 3), "bucket": bucket}
    diff = level - ctrl_level
    bucket = "above" if diff > tol else ("below" if diff < -tol else "at")
    return {"ratio": None, "bucket": bucket}


def _order_of(responses: list[float], tol: float) -> str:
    """increasing / decreasing / flat / non_monotone across ordered levels."""
    steps = [
        0 if abs(b - a) <= tol else (1 if b > a else -1)
        for a, b in zip(responses, responses[1:], strict=False)
    ]
    if all(s == 0 for s in steps):
        return "flat"
    if all(s >= 0 for s in steps):
        return "increasing"
    if all(s <= 0 for s in steps):
        return "decreasing"
    return "non_monotone"


def _dose_orders(label: str, rows: list[dict], tol: float) -> list[dict]:
    """Response across the levels of each numeric attribute, per group of
    conditions that agree on every other attribute (one stimulus, one
    population, several doses). The response is the largest fitted change from
    the first sample."""
    out = []
    names = sorted({a for r in rows for a in r["attributes"]})
    for a in names:
        vals = [r["attributes"].get(a) for r in rows]
        try:
            [float(v) for v in vals if v is not None]
        except ValueError:
            continue
        groups: dict[tuple, list[dict]] = {}
        for r in rows:
            if a not in r["attributes"]:
                continue
            fixed = tuple(
                sorted((k, str(v)) for k, v in r["attributes"].items() if k != a)
            )
            groups.setdefault(fixed, []).append(r)
        for fixed, members in sorted(groups.items()):
            members = sorted(members, key=lambda r: float(r["attributes"][a]))
            levels = [str(r["attributes"][a]) for r in members]
            responses = [r["shape"].get("excursion") for r in members]
            if len(set(levels)) < 2 or any(v is None for v in responses):
                continue
            out.append(
                {
                    "observable": label,
                    "attribute": a,
                    "held_fixed": dict(fixed),
                    "levels": levels,
                    "order": _order_of([float(v) for v in responses], tol),
                }
            )
    return out


def curve_descriptors(long_df: pd.DataFrame, exclude=()) -> dict:
    """Every raw series fitted with the `curve_forms` library, then compared.

    Per (observable, condition): the fitted form and its shape (`curve_forms.
    shape`), and the last-sample level against the condition's control (a
    condition that differs in one attribute only, carrying a control value
    there). Per numeric attribute: whether the response is monotone across its
    levels. Conditions in `exclude` (the held-out ones) are left out of every
    fit and every comparison, so nothing downstream describes the exam.
    """
    from octomod.workflow_modules.data import curve_forms as _cf

    exclude = {str(k) for k in exclude or ()}
    per_series: list[dict] = []
    orders: list[dict] = []
    steady_only: list[dict] = []
    df = long_df.copy()
    df["condition_key"] = df["condition_key"].fillna("").astype(str)
    for label, obs_df in df.groupby("observable_label"):
        obs_df = obs_df[~obs_df["condition_key"].isin(exclude)]
        obs_df = obs_df[np.isfinite(obs_df["value"].to_numpy(dtype=float))]
        if obs_df.empty:
            continue
        tol = _noise_scale(obs_df)
        pooled = _pooled_replicate_sd(obs_df)
        rows = []
        for key, cdf in obs_df.groupby("condition_key"):
            if not np.isfinite(cdf["time"].to_numpy(dtype=float)).any():
                # measured at steady state only (time inf): there is no time
                # course to fit, and the constant form would call it "flat"
                steady_only.append({"observable": str(label), "condition": str(key)})
                continue
            sigma, source = _series_sigma(cdf, pooled)
            fit = _cf.fit_series(
                cdf["time"].to_numpy(dtype=float),
                cdf["value"].to_numpy(dtype=float),
                sigma,
            )
            rows.append(
                {
                    "observable": str(label),
                    "condition": str(key),
                    "attributes": attributes_of(str(key)),
                    "sigma_source": source,
                    "fit": fit,
                    "shape": _cf.shape(fit),
                }
            )
        attrs = {r["condition"]: r["attributes"] for r in rows}
        by_key = {r["condition"]: r for r in rows}
        for r in rows:
            ctrl = _control_of(r["condition"], r["attributes"], attrs)
            r["control"] = ctrl
            r["vs_control"] = (
                None
                if ctrl is None
                else _vs_control(
                    r["shape"].get("end_level"),
                    by_key[ctrl]["shape"].get("end_level"),
                    tol,
                )
            )
        orders += _dose_orders(str(label), rows, tol)
        per_series += rows
    out = {
        "per_series": per_series,
        "dose_response": orders,
        "excluded_conditions": sorted(exclude),
        "reads_as": (
            "each raw series fitted with one of constant, linear, exponential "
            "and rise-and-fall, chosen by small-sample AICc against the "
            "constant, against the declared σ column, else the pooled "
            "replicate SD, else a profiled variance (`sigma_source`); times in "
            "the data's own time unit. Held-out conditions are excluded from "
            "every fit and comparison."
        ),
    }
    if steady_only:
        # a steady-state row (time inf) is never on a fitted time course; a
        # series with nothing else is named here instead of described
        out["steady_state_only"] = steady_only
    return out


def compute(long_df: pd.DataFrame, exclude_conditions=()) -> dict:
    """The signals artifact: one record per measured quantity, plus a summary.

    `long_df` is S2's `measurements_long.tsv`: observable_label,
    condition_key, time, value, replicate. `exclude_conditions` are condition
    keys left out of the curve descriptors only (the held-out conditions); the
    noise statistics read every replicate.
    """
    required = {"observable_label", "condition_key", "time", "value"}
    missing = sorted(required - set(long_df.columns))
    if missing:
        return {"available": False, "why": f"the long table lacks {missing}"}

    per_observable: dict[str, dict] = {}
    for label, obs_df in long_df.groupby("observable_label"):
        cells = []
        n_with_replicates = 0
        dropped_nonpositive = 0
        dropped_zero_spread = 0
        for (_cond, _t), cell in obs_df.groupby(["condition_key", "time"]):
            mean, sd, n = _replicate_stats(cell)
            if n < 2:
                continue  # a single measurement has no spread to read
            n_with_replicates += 1
            if mean <= 0:
                # log(mean) is undefined; counted, never silently skipped
                dropped_nonpositive += 1
                continue
            if not (sd > 0):
                # identical replicates: log(0) is undefined, and the cell says
                # nothing about how spread follows signal
                dropped_zero_spread += 1
                continue
            cells.append((mean, sd, n))
        usable = [(m, s) for m, s, _ in cells]
        # the counts reconcile, so a cell dropped for an unnamed reason shows
        assert n_with_replicates == (
            len(usable) + dropped_nonpositive + dropped_zero_spread
        )
        n_rep = sorted({n for _m, _s, n in cells})
        if usable:
            logm = np.log10(np.array([m for m, _ in usable]))
            logs = np.log10(np.array([s for _, s in usable]))
            slope, se, lo, hi = _slope_with_ci(logm, logs)
        else:
            slope = se = lo = hi = float("nan")

        # pooled, descriptive tail shape: with few replicates per point it is
        # not a distribution-family verdict
        devs = []
        for (_cond, _t), cell in obs_df.groupby(["condition_key", "time"]):
            vals = cell["value"].to_numpy(dtype=float)
            if len(vals) >= 2:
                devs.extend(vals - float(np.mean(vals)))
        devs_arr = np.asarray(devs, dtype=float)
        kurt = None
        if len(devs_arr) >= 8 and float(np.std(devs_arr)) > 0:
            z = (devs_arr - devs_arr.mean()) / np.std(devs_arr)
            kurt = round(float(np.mean(z**4) - 3.0), 3)

        series_shapes = {}
        for cond, cdf in obs_df.groupby("condition_key"):
            agg = cdf.groupby("time")["value"].mean().reset_index()
            series_shapes[str(cond)] = _shape(
                agg["time"].to_numpy(dtype=float), agg["value"].to_numpy(dtype=float)
            )

        drift = {}
        for _by in DRIFT_COLUMNS:
            d = _level_drift(obs_df, _by)
            if d.get("available"):
                drift[_by] = d

        per_observable[str(label)] = {
            "support": _support(obs_df["value"].to_numpy(dtype=float)),
            "level_drift": drift
            or {
                "available": False,
                "why": (
                    "no cross-cutting group column "
                    f"({', '.join(DRIFT_COLUMNS)}) had two groups with "
                    "replicates; note that `time` is deliberately not one — "
                    "a per-time offset is not separable from dynamics here"
                ),
            },
            "noise": {
                **_verdict(slope, lo, hi, len(usable)),
                "spread_vs_magnitude_slope": (
                    round(slope, 4) if math.isfinite(slope) else None
                ),
                "slope_ci95": (
                    [round(lo, 4), round(hi, 4)]
                    if math.isfinite(lo) and math.isfinite(hi)
                    else None
                ),
                "slope_se": round(se, 4) if math.isfinite(se) else None,
                "n_cells_with_replicates": n_with_replicates,
                "n_usable_cells": len(usable),
                "n_cells_dropped_nonpositive_mean": dropped_nonpositive,
                "n_cells_dropped_zero_spread": dropped_zero_spread,
                "replicates_per_cell": n_rep,
                "pooled_excess_kurtosis": kurt,
                "distribution_family": (
                    "NOT TESTED — with "
                    f"{n_rep or 'these'} replicate(s) per point the tail shape "
                    "is out of reach; the kurtosis above is descriptive only"
                ),
            },
            "shape_per_condition": series_shapes,
        }

    try:
        descriptors = curve_descriptors(long_df, exclude_conditions)
    except Exception as e:  # a description never stops the data module
        descriptors = {"available": False, "why": f"{type(e).__name__}: {e}"}
    return {
        "available": True,
        "per_observable": per_observable,
        "closure": _closure(long_df),
        "curve_descriptors": descriptors,
        "how_to_read_this": (
            "Computed from the measurements alone, with no model and no agent. "
            "`noise.error_model` is the additive-vs-multiplicative read: the "
            "slope of log(replicate spread) on log(signal), which is 0 for "
            "constant error and 1 for proportional. A verdict is given only "
            "when the interval excludes one of those; otherwise it says so. "
            "`shape_per_condition` describes the raw curves without binning "
            "them. These are OBSERVATION-MODEL evidence, not structural "
            "evidence: a noise statistic never reaches model construction. "
            "`curve_descriptors` fits each raw curve with a four-form library "
            "and compares conditions; construction is shown only sentences "
            "built from them (`data_phenomenology`: shape words and rounded "
            "timescales, no values)."
        ),
        "deferred": (
            "lagged cross-correlation orderings and dose-response "
            "saturation fits are the `full`-mode structural hints; nothing "
            "consumes them while the knob stays at noise_only, so they are not "
            "computed. Function-library / SINDy-style term discovery stays "
            "deferred per the entry: derivative estimation on ~8-point, "
            "2-replicate series is not robust."
        ),
    }


def card_lines(signals: dict, limit: int = 6) -> list[str]:
    """What the observation-model agent and a human reader are told."""
    if not signals.get("available"):
        return []
    out = ["WHAT THE REPLICATES SAY ABOUT THE ERROR MODEL (data alone, no model):"]
    for label, rec in list((signals.get("per_observable") or {}).items())[:limit]:
        n = rec["noise"]
        slope = n.get("spread_vs_magnitude_slope")
        out.append(
            f"  · {label}: {n['error_model']}"
            + (f" (slope {slope:+.2f}" if slope is not None else " (slope n/a")
            + (
                f", 95% CI [{n['slope_ci95'][0]:+.2f}, {n['slope_ci95'][1]:+.2f}]"
                if n.get("slope_ci95")
                else ""
            )
            + f", {n['n_usable_cells']} of {n['n_cells_with_replicates']} "
            f"replicate cells usable)"
        )
        out.append(f"      {n['why']}")
        # the support decides which noise models are legal, so it is on the card
        sup = rec.get("support") or {}
        if sup.get("reading"):
            out.append(f"      support: {sup['reading']}")
        # a whole-group offset the model has no parameter for
        for _by, d in (rec.get("level_drift") or {}).items():
            if (
                isinstance(d, dict)
                and d.get("available")
                and d.get("f_ratio", 0) > DRIFT_F_NOTABLE
            ):
                out.append(f"      drift:   {d['reading']}")
    closure = signals.get("closure") or {}
    if closure.get("available"):
        out += [
            "",
            "AND ACROSS OBSERVABLES (the conserved-pool question):",
            f"  {closure['reading']}",
        ]
    return out
