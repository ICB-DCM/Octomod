"""Which simple functional form one time series follows, and on what timescale.

Deterministic: a fixed library of four forms, each fitted by least squares from
a fixed set of starts and chosen by small-sample AICc, never by an agent.

  constant       c
  linear         a·t + c
  exponential    a·exp(−t/τ) + c                   a > 0 decays toward c, a < 0 rises
  rise_and_fall  a·(exp(−t/τ2) − exp(−t/τ1)) + c   τ1 < τ2: a transient peak (a > 0)
                                                   or dip (a < 0)

Time runs from the stimulus: t = 0, or the first sample when that is negative (a
pre-stimulus sample). Every τ is bounded to [the shortest sampling interval, ten
times the window], the range the sampling can see; a τ at a bound says so.

AICc charges each form its mean parameters, plus the noise variance when no σ is
given. A form other than the constant must beat the constant by MIN_DELTA_AICC,
so pure noise reads as the constant, and a more complex form must beat the
simpler one chosen before it by the same margin. On a short series the bar
is high on purpose: six unreplicated samples cannot carry a five-parameter
rise-and-fall at all, and the result says so rather than reading noise as a peak.

These are descriptions, not tests. AICc treats the points as independent, so a
smooth autocorrelated wander can read as a form; `diagnostics.fit_residual_form`
fits one residual series with this same library (`fit_forms`), on request, and
calibrates the chosen form against white-noise and AR(1) nulls by a parametric
bootstrap.

The same library serves both ends of a round: the raw curves before any model
(`data_signals`, whose shape words reach construction) and the residuals after
a fit (`residuals`, for the interpreter and the expansion agent). `aggregate_*`
groups series whose forms agree, with timescales within a factor of two, into
sentences and names what disagrees.
"""

from __future__ import annotations

import math

import numpy as np

FORMS = ("constant", "linear", "exponential", "rise_and_fall")
# mean parameters per form; the noise variance adds one when no σ is given
K_MEAN = {"constant": 1, "linear": 2, "exponential": 3, "rise_and_fall": 4}
# distinct time points each form needs before it is tried at all
MIN_TIMES = {"constant": 1, "linear": 4, "exponential": 4, "rise_and_fall": 5}
# the AICc margin a shaped form must beat the constant by: without it, pure
# noise picks a line or an exponential in about a quarter of short series
MIN_DELTA_AICC = 2.0
TIMESCALE_AGREEMENT = 2.0  # series agree when every τ is within this factor
N_GRID = 24  # log-spaced τ grid the least-squares starts are chosen from
N_STARTS = 3
# a rise-and-fall whose two τ are closer than this is the degenerate
# alpha-function limit, and its amplitude parameter is not identified
MIN_TAU_RATIO = 1.05


def sig(x, digits: int = 4):
    """`x` to `digits` significant figures; None and non-finite values kept."""
    if x is None:
        return None
    x = float(x)
    if not math.isfinite(x) or x == 0.0:
        return x
    return float(f"{x:.{digits}g}")


def _prep(t, y, sigma):
    """Finite points sorted by (t, y), their weights, and whether σ was given.

    Sorting makes the fit independent of row order, so an artifact built from a
    shuffled table is byte-identical.
    """
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    if sigma is None:
        s = None
    else:
        s = np.broadcast_to(np.asarray(sigma, dtype=float), t.shape).astype(float)
    ok = np.isfinite(t) & np.isfinite(y)
    if s is not None:
        ok &= np.isfinite(s) & (s > 0)
    t, y = t[ok], y[ok]
    s = None if s is None else s[ok]
    order = np.lexsort((y, t))
    t, y = t[order], y[order]
    if s is not None:
        s = s[order]
    w = np.ones_like(t) if s is None else 1.0 / s
    return t, y, w, s


def _window(t: np.ndarray) -> tuple[float, float, float, float]:
    """(anchor, window length, shortest interval, longest τ) for sample times `t`."""
    anchor = min(0.0, float(t.min()))
    span = float(t.max()) - anchor
    span = span if span > 0 else 1.0
    gaps = np.diff(np.unique(t))
    gaps = gaps[gaps > 0]
    dt_min = float(gaps.min()) if gaps.size else span / 10.0
    return anchor, span, min(dt_min, span), 10.0 * span


def _wls2(B: np.ndarray, y: np.ndarray, w: np.ndarray):
    """Weighted least squares of y on [b, 1] for every row b of B at once.

    Closed-form 2x2 normal equations, vectorised over the τ grid. Returns
    (a, c, weighted RSS) per row; a degenerate basis gets a = 0.
    """
    w2 = w**2
    sw = w2.sum()
    sb = B @ w2
    sbb = (B**2) @ w2
    sy = float(w2 @ y)
    sby = B @ (w2 * y)
    syy = float(w2 @ (y**2))
    det = sbb * sw - sb**2
    safe = np.abs(det) > 1e-12 * np.maximum(sbb * sw, 1e-300)
    a = np.where(safe, (sby * sw - sb * sy) / np.where(safe, det, 1.0), 0.0)
    c = (sy - a * sb) / sw
    rss = syy - a * sby - c * sy
    return a, c, np.maximum(rss, 0.0)


def _model(form: str, p: dict, tt: np.ndarray) -> np.ndarray:
    """The fitted curve of `form` at anchored times `tt`."""
    if form == "constant":
        return np.full_like(tt, p["c"], dtype=float)
    if form == "linear":
        return p["a"] * tt + p["c"]
    if form == "exponential":
        return p["a"] * np.exp(-tt / p["tau"]) + p["c"]
    return p["a"] * (np.exp(-tt / p["tau2"]) - np.exp(-tt / p["tau1"])) + p["c"]


def _wrss(form: str, p: dict, tt, y, w) -> float:
    return float(np.sum((w * (y - _model(form, p, tt))) ** 2))


def _refine(fun, x0, lo, hi):
    """One bounded least-squares refinement of the time constants; None when
    it fails."""
    from scipy.optimize import least_squares

    x0 = np.clip(np.asarray(x0, float), lo + 1e-9, hi - 1e-9)
    try:
        res = least_squares(fun, x0, bounds=(lo, hi), method="trf", max_nfev=200)
    except (ValueError, FloatingPointError):
        return None
    return res.x if np.all(np.isfinite(res.x)) else None


def _best_starts(rss: np.ndarray, k: int) -> list[int]:
    return [int(i) for i in np.argsort(rss, kind="stable")[:k]]


def _projected(basis: np.ndarray, y, w) -> tuple[float, float, np.ndarray]:
    """(a, c, weighted residual) of y on [basis, 1]: the linear parameters
    solved in closed form, so least squares only moves the time constants."""
    a, c, _ = _wls2(basis[None, :], y, w)
    a, c = float(a[0]), float(c[0])
    return a, c, w * (y - (a * basis + c))


def _fit_exponential(tt, y, w, tau_lo, tau_hi, refine: bool = True) -> dict:
    """Variable projection: τ on a log grid, the best starts refined by
    least squares in log τ (the grid alone when not `refine`), amplitude and
    asymptote solved at every step."""
    taus = np.geomspace(tau_lo, tau_hi, N_GRID)
    a, c, rss = _wls2(np.exp(-np.outer(1.0 / taus, tt)), y, w)
    lo, hi = np.array([math.log(tau_lo)]), np.array([math.log(tau_hi)])

    def fun(x):
        return _projected(np.exp(-tt / math.exp(x[0])), y, w)[2]

    best = None
    for i in _best_starts(rss, N_STARTS):
        cands = [
            (float(rss[i]), {"a": float(a[i]), "tau": float(taus[i]), "c": float(c[i])})
        ]
        x = _refine(fun, [math.log(taus[i])], lo, hi) if refine else None
        if x is not None:
            tau = float(math.exp(x[0]))
            aa, cc, r = _projected(np.exp(-tt / tau), y, w)
            cands.append((float(r @ r), {"a": aa, "tau": tau, "c": cc}))
        for cand in cands:
            if best is None or cand[0] < best[0]:
                best = cand
    return {"wrss": best[0], "params": best[1]}


def _fit_rise_and_fall(tt, y, w, tau_lo, tau_hi, refine: bool = True) -> dict:
    """Variable projection over (log τ1, log τ2) with τ1 < τ2, as above."""
    taus = np.geomspace(tau_lo, tau_hi, N_GRID)
    pairs = [(t1, t2) for i, t1 in enumerate(taus) for t2 in taus[i + 1 :]]
    t1s = np.array([p[0] for p in pairs])
    t2s = np.array([p[1] for p in pairs])
    B = np.exp(-np.outer(1.0 / t2s, tt)) - np.exp(-np.outer(1.0 / t1s, tt))
    a, c, rss = _wls2(B, y, w)
    lo = np.full(2, math.log(tau_lo))
    hi = np.full(2, math.log(tau_hi))

    def basis(t1: float, t2: float) -> np.ndarray:
        return np.exp(-tt / t2) - np.exp(-tt / t1)

    def fun(x):
        t1, t2 = sorted((math.exp(x[0]), math.exp(x[1])))
        return _projected(basis(t1, t2), y, w)[2]

    best = None
    for i in _best_starts(rss, N_STARTS):
        cands = [
            (
                float(rss[i]),
                {
                    "a": float(a[i]),
                    "tau1": float(t1s[i]),
                    "tau2": float(t2s[i]),
                    "c": float(c[i]),
                },
            )
        ]
        x = (
            _refine(fun, [math.log(t1s[i]), math.log(t2s[i])], lo, hi)
            if refine
            else None
        )
        if x is not None:
            t1, t2 = sorted((float(math.exp(x[0])), float(math.exp(x[1]))))
            # the alpha-function limit (τ1 → τ2) leaves the amplitude
            # unidentified: the grid start stands instead
            if t2 / t1 >= MIN_TAU_RATIO:
                aa, cc, r = _projected(basis(t1, t2), y, w)
                cands.append((float(r @ r), {"a": aa, "tau1": t1, "tau2": t2, "c": cc}))
        for cand in cands:
            if best is None or cand[0] < best[0]:
                best = cand
    return {"wrss": best[0], "params": best[1]}


def _fit_linear(tt, y, w) -> dict:
    a, c, rss = _wls2(tt[None, :], y, w)
    return {"wrss": float(rss[0]), "params": {"a": float(a[0]), "c": float(c[0])}}


def _fit_constant(tt, y, w) -> dict:
    c = float(np.sum(w**2 * y) / np.sum(w**2))
    return {"wrss": _wrss("constant", {"c": c}, tt, y, w), "params": {"c": c}}


def aicc(
    wrss: float, n: int, form: str, sigma_given: bool, scale: float
) -> float | None:
    """Small-sample AICc of one fitted form, or None when it is undefined.

    With σ given, −2 log L is the weighted RSS (χ²) and only the mean
    parameters count; without, the variance is profiled out and counts as one
    more parameter. Undefined when n − k − 1 ≤ 0: that many points cannot
    carry that many parameters.
    """
    if not carries(n, form, sigma_given):
        return None
    k = K_MEAN[form] + (0 if sigma_given else 1)
    if sigma_given:
        neg2 = wrss
    else:
        neg2 = n * math.log(max(wrss / n, 1e-12 * scale, 1e-300))
    return neg2 + 2 * k + 2 * k * (k + 1) / (n - k - 1)


def carries(n: int, form: str, sigma_given: bool) -> bool:
    """Whether `n` observations can carry `form`'s parameters: n − k − 1 > 0,
    with the noise variance counted as one more when no σ is given."""
    k = K_MEAN[form] + (0 if sigma_given else 1)
    return n - k - 1 > 0


def choose(scores: dict) -> str:
    """The chosen form: the constant unless a form beats it, and a more complex
    form only when it beats the one chosen so far, each by MIN_DELTA_AICC.

    Walked in order of complexity, so a rise-and-fall whose extreme lies past
    the window never displaces the exponential it imitates on a sliver of AICc.
    """
    choice = "constant"
    if scores.get("constant") is None:
        return choice
    for form in FORMS[1:]:
        a = scores.get(form)
        if a is not None and scores[choice] - a >= MIN_DELTA_AICC:
            choice = form
    return choice


def _fit_all(tt, y, w, n_times: int, tau_lo, tau_hi, refine: bool):
    """(fits, note, skipped): every form the series' time points allow, fitted
    at anchored times `tt`, each {wrss, params}; the note when no shape can be
    tried at all, and why a form was left out."""
    fits = {"constant": _fit_constant(tt, y, w)}
    note, skipped = None, []
    if n_times < MIN_TIMES["linear"]:
        note = (
            f"only {n_times} time point(s): too few for any shape (a line or an "
            f"exponential needs {MIN_TIMES['exponential']})"
        )
        return fits, note, skipped
    fits["linear"] = _fit_linear(tt, y, w)
    fits["exponential"] = _fit_exponential(tt, y, w, tau_lo, tau_hi, refine)
    if n_times >= MIN_TIMES["rise_and_fall"]:
        fits["rise_and_fall"] = _fit_rise_and_fall(tt, y, w, tau_lo, tau_hi, refine)
    else:
        skipped.append(
            f"rise-and-fall needs {MIN_TIMES['rise_and_fall']} time points, "
            f"this series has {n_times}"
        )
    return fits, note, skipped


def fit_forms(t, y, refine: bool = True) -> dict:
    """Every library form one series can carry, fitted but not chosen between,
    its noise variance unknown: {n, anchor, fits: {form: {wrss, params}}}.
    `refine=False` keeps each τ on its log grid instead of polishing it by
    least squares: about forty times faster, for a bootstrap that refits
    hundreds of null series by the same procedure as the observed one.

    The fitting half of `fit_series`, for a caller that scores the forms by its
    own criterion: the residual-form request (`diagnostics.fit_residual_form`)
    ranks them by BIC and calibrates the winner by a bootstrap. A form is left
    out when its time points do not allow it or the series cannot carry its
    parameters (the same rule `aicc` applies).
    """
    t, y, w, _ = _prep(t, y, None)
    n = int(len(t))
    if n == 0:
        return {"n": 0, "anchor": None, "fits": {}}
    anchor, _span, tau_lo, tau_hi = _window(t)
    fits, _note, _skipped = _fit_all(
        t - anchor, y, w, int(len(np.unique(t))), tau_lo, tau_hi, refine
    )
    return {
        "n": n,
        "anchor": sig(anchor),
        "fits": {f: v for f, v in fits.items() if carries(n, f, False)},
    }


def timescales_of(form: str, params: dict) -> list:
    """The fitted τ of `form` (τ1 then τ2 for a rise-and-fall), or []."""
    if form == "exponential":
        return [sig(params["tau"])]
    if form == "rise_and_fall":
        return [sig(params["tau1"]), sig(params["tau2"])]
    return []


def _peak(p: dict) -> float:
    """Anchored time of a rise-and-fall's extremum."""
    t1, t2 = p["tau1"], p["tau2"]
    return t1 * t2 * math.log(t2 / t1) / (t2 - t1)


def fit_series(t, y, sigma=None) -> dict:
    """The form one series follows, chosen by AICc against the constant.

    `t`, `y` are every observation (replicates included); `sigma` is a known
    per-point or scalar noise level, or None to profile it out. Returns
    {form, direction, params, timescales, amplitude, amplitude_units,
    peak_time, r2, n, n_times, anchor, window, aicc, delta_aicc_vs_constant,
    timescale_at_bound, note}. `timescales` are the fitted τ (τ1 then τ2 for a
    rise-and-fall), in the series' own time unit, and `timescale_at_bound` says
    "lower" (faster than the first sampling interval resolves) or "upper"
    (slower than the window) when one sits on its bound; `amplitude` is signed and in
    units of σ when σ is given: the change from the asymptote for an
    exponential, the peak excursion for a rise-and-fall, the change over the
    window for a line, the level for the constant.
    """
    t, y, w, s = _prep(t, y, sigma)
    n = int(len(t))
    n_times = int(len(np.unique(t))) if n else 0
    sigma_given = s is not None
    out: dict = {
        "form": "constant",
        "direction": None,
        "params": {},
        "timescales": [],
        "amplitude": None,
        "amplitude_units": "sigma" if sigma_given else "data",
        "peak_time": None,
        "r2": None,
        "n": n,
        "n_times": n_times,
        "anchor": None,
        "window": None,
        "aicc": {},
        "delta_aicc_vs_constant": None,
        "timescale_at_bound": None,
        "note": None,
    }
    if n == 0:
        out["note"] = "no finite points"
        return out
    anchor, span, tau_lo, tau_hi = _window(t)
    tt = t - anchor
    out["anchor"] = sig(anchor)
    out["window"] = [sig(float(t.min())), sig(float(t.max()))]
    sigma_ref = float(np.median(s)) if sigma_given else None
    scale = float(np.mean(y**2)) + 1e-300

    fits, out["note"], skipped = _fit_all(tt, y, w, n_times, tau_lo, tau_hi, True)
    scores = {f: aicc(fit["wrss"], n, f, sigma_given, scale) for f, fit in fits.items()}
    undefined = [f for f, a in scores.items() if a is None]
    if undefined:
        skipped.append(
            f"AICc undefined for {', '.join(undefined)}: {n} observation(s) "
            f"cannot carry that many parameters"
        )
    base = scores.get("constant")
    form = choose(scores)
    fit = fits[form]
    p = fit["params"]
    out["form"] = form
    out["params"] = {k: sig(v, 6) for k, v in p.items()}
    out["aicc"] = {f: (None if a is None else sig(a, 6)) for f, a in scores.items()}
    if base is not None and scores.get(form) is not None:
        out["delta_aicc_vs_constant"] = sig(base - scores[form], 4)
    if skipped:
        out["note"] = "; ".join(filter(None, [out["note"], *skipped]))

    yw = np.sum(w**2 * y) / np.sum(w**2)
    tss = float(np.sum((w * (y - yw)) ** 2))
    out["r2"] = sig(1.0 - fit["wrss"] / tss, 4) if tss > 0 else None

    if form == "constant":
        amp = p["c"]
    elif form == "linear":
        amp = p["a"] * (float(t.max()) - float(t.min()))
        out["direction"] = "increasing" if p["a"] > 0 else "decreasing"
    elif form == "exponential":
        amp = p["a"]
        out["direction"] = "decay" if p["a"] > 0 else "rise"
        out["timescales"] = timescales_of(form, p)
    else:
        tp = _peak(p)
        amp = float(_model(form, p, np.array([tp]))[0] - p["c"])
        out["direction"] = "peak" if p["a"] > 0 else "dip"
        out["timescales"] = timescales_of(form, p)
        out["peak_time"] = sig(anchor + tp)
    taus = [v for k, v in p.items() if k.startswith("tau")]
    if any(abs(math.log(v / tau_lo)) < 0.01 for v in taus):
        out["timescale_at_bound"] = "lower"
    elif any(abs(math.log(v / tau_hi)) < 0.01 for v in taus):
        out["timescale_at_bound"] = "upper"
    out["amplitude"] = sig(amp / sigma_ref if sigma_given else amp, 4)
    return out


def predict(fit: dict, t) -> np.ndarray:
    """The fitted curve of `fit` at times `t`."""
    t = np.asarray(t, dtype=float)
    if not fit.get("params"):
        return np.full_like(t, np.nan)
    return _model(fit["form"], fit["params"], t - float(fit.get("anchor") or 0.0))


def _bisect(g, lo: float, hi: float, n: int = 60) -> float | None:
    """A root of `g` on [lo, hi] when the sign changes there, else None."""
    glo, ghi = g(lo), g(hi)
    if not (math.isfinite(glo) and math.isfinite(ghi)) or glo * ghi > 0:
        return None
    for _ in range(n):
        mid = 0.5 * (lo + hi)
        gm = g(mid)
        if glo * gm <= 0:
            hi = mid
        else:
            lo, glo = mid, gm
    return 0.5 * (lo + hi)


def shape(fit: dict) -> dict:
    """What a raw curve does, read off its fitted form.

    Half-maximum rise time, peak time, the time it is half-way back, whether it
    settles within the window and whether it turns back toward where it
    started; plus the fitted level at the first and last sample and the largest
    fitted change from the first sample (`excursion`), which conditions are
    compared on. Times are in the series' own unit.
    """
    form, p = fit.get("form"), fit.get("params") or {}
    out = {
        "form": form,
        "direction": fit.get("direction"),
        "rise_half_time": None,
        "change_half_time": None,
        "peak_time": None,
        "return_half_time": None,
        "settled_by_end": None,
        "returns_toward_baseline": None,
        "start_level": None,
        "end_level": None,
        "excursion": None,
    }
    if not p or not fit.get("window"):
        return out
    t0, t1 = (float(v) for v in fit["window"])
    anchor = float(fit.get("anchor") or 0.0)
    grid = np.linspace(t0, t1, 201)
    f = predict(fit, grid)
    start = float(f[0])
    k = int(np.argmax(np.abs(f - start)))
    out["start_level"] = sig(start)
    out["end_level"] = sig(float(f[-1]))
    out["excursion"] = sig(float(f[k] - start))
    if form == "exponential":
        half = anchor + p["tau"] * math.log(2.0)
        out["change_half_time"] = sig(half)
        out["settled_by_end"] = bool(t1 - anchor >= 3.0 * p["tau"])
        if fit.get("direction") == "rise":
            out["rise_half_time"] = sig(half)
            out["returns_toward_baseline"] = False
    elif form == "rise_and_fall":
        tp = _peak(p)
        exc = float(_model(form, p, np.array([tp]))[0] - p["c"])

        def g(tau):
            return float(_model(form, p, np.array([tau]))[0] - p["c"]) - 0.5 * exc

        out["peak_time"] = sig(anchor + tp)
        rise = _bisect(g, 0.0, tp)
        back = _bisect(g, tp, tp + 20.0 * p["tau2"])
        out["rise_half_time"] = None if rise is None else sig(anchor + rise)
        out["return_half_time"] = None if back is None else sig(anchor + back)
        in_window = t0 <= anchor + tp <= t1
        out["returns_toward_baseline"] = bool(in_window)
        out["settled_by_end"] = bool(back is not None and anchor + back <= t1)
    elif form == "linear":
        out["settled_by_end"] = False
        out["returns_toward_baseline"] = False
    else:
        out["settled_by_end"] = True
    return out


# ------------------------------------------------------------- aggregation


def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _is_numeric(values) -> bool:
    return bool(values) and all(_num(v) is not None for v in values)


def _sorted_values(values) -> list[str]:
    vals = sorted({str(v) for v in values})
    if _is_numeric(vals):
        return sorted(vals, key=lambda v: _num(v))
    return vals


# Condition-attribute values that mark a control arm (compared case-insensitively;
# a numeric 0 counts too): the attribute carrying one is the perturbation.
CONTROL_VALUES = frozenset(
    {
        "0",
        "none",
        "no",
        "control",
        "ctrl",
        "reference",
        "ref",
        "unstimulated",
        "unstim",
        "untreated",
        "mock",
        "vehicle",
        "basal",
        "dmso",
        "-",
    }
)


def is_control_value(value) -> bool:
    text = str(value).strip().lower()
    if text in CONTROL_VALUES:
        return True
    return _num(text) == 0.0


def stratum_attribute(rows: list[dict], key=None) -> str | None:
    """The condition attribute each sentence is written for, or None for one
    sentence per observable.

    Only when the design crosses two or more non-numeric attributes (stimuli
    and populations, say): one attribute is then the stratum ("under IFN-a")
    and the others are listed inside the sentence ("in B, NK"). The stratum is
    the attribute that carries a control value (the perturbation), else the
    one whose strata group most coherently, the fewest groups of agreeing
    series over every observable; ties go to fewer values, then the name. One
    choice for the whole design, so every observable's sentences read alike.
    """
    if not rows:
        return None
    key = key or form_key
    common = set(rows[0].get("attributes") or {})
    for r in rows[1:]:
        common &= set(r.get("attributes") or {})
    values = {a: {str(r["attributes"][a]) for r in rows} for a in sorted(common)}
    multi = [a for a, v in values.items() if len(v) >= 2 and not _is_numeric(v)]
    if len(multi) < 2:
        return None
    pool = [a for a in multi if any(is_control_value(v) for v in values[a])] or multi
    observables = sorted({str(r["observable"]) for r in rows})

    def score(attr: str) -> tuple:
        n_groups = 0
        for obs in observables:
            for v in values[attr]:
                cell = [
                    r
                    for r in rows
                    if str(r["observable"]) == obs and str(r["attributes"][attr]) == v
                ]
                n_groups += len(clusters(cell, key)) if cell else 0
        return (n_groups, len(values[attr]), attr)

    return min(pool, key=score)


def strata(
    rows: list[dict], key=None
) -> list[tuple[str, str | None, str | None, list[dict]]]:
    """(observable, stratum attribute, its value, rows) for every stratum;
    `key` is the grouping the sentences will use (see `clusters`)."""
    out = []
    attr = stratum_attribute(rows, key)
    for obs in sorted({str(r["observable"]) for r in rows}):
        obs_rows = [r for r in rows if str(r["observable"]) == obs]
        if attr is None:
            out.append((obs, None, None, obs_rows))
            continue
        for val in _sorted_values(r["attributes"][attr] for r in obs_rows):
            out.append(
                (
                    obs,
                    attr,
                    val,
                    [r for r in obs_rows if str(r["attributes"][attr]) == val],
                )
            )
    return out


def form_key(row: dict) -> tuple:
    """What two series must share before their timescales are compared."""
    return (row["fit"]["form"], row["fit"].get("direction"))


def under_text(stratum_rows: list[dict], attr: str | None, val) -> str:
    """' under stimulus=G-CSF, population=Monocyte': the stratum's value, and
    every other attribute that is the same on all of its rows."""
    parts = [f"{attr}={val}"] if attr else []
    if stratum_rows:
        first = stratum_rows[0].get("attributes") or {}
        for a in sorted(first):
            if a == attr:
                continue
            if len(stratum_rows) > 1 or len(first) > 1 or attr:
                same = {str((r.get("attributes") or {}).get(a)) for r in stratum_rows}
                if len(same) == 1:
                    parts.append(f"{a}={first[a]}")
    return (" under " + ", ".join(parts)) if parts else ""


def _agrees(cluster: list[dict], row: dict, key) -> bool:
    """Same key as the cluster, every τ within the agreement factor."""
    f = row["fit"]
    if key(cluster[0]) != key(row):
        return False
    for i, tau in enumerate(f.get("timescales") or []):
        vals = [m["fit"]["timescales"][i] for m in cluster] + [tau]
        if max(vals) > TIMESCALE_AGREEMENT * min(vals):
            return False
    return True


def clusters(rows: list[dict], key=form_key) -> list[list[dict]]:
    """Rows grouped by agreeing form, largest group first.

    Greedy over rows sorted by (key, first τ): a row joins the first group with
    its key whose timescales it agrees with, else starts a new one. `key` is
    what must match exactly (form and direction by default). Deterministic for
    a fixed set of rows.
    """
    ordered = sorted(
        rows,
        key=lambda r: (
            FORMS.index(r["fit"]["form"]),
            str(key(r)),
            (r["fit"].get("timescales") or [0.0])[0],
            str(r["condition"]),
        ),
    )
    groups: list[list[dict]] = []
    for r in ordered:
        for g in groups:
            if _agrees(g, r, key):
                g.append(r)
                break
        else:
            groups.append([r])
    groups.sort(key=lambda g: (-len(g), min(condition_order(r) for r in g)))
    return groups


def condition_order(row: dict) -> tuple:
    """A row's place in the design: attribute by attribute, numbers in numeric
    order, so equal-sized groups read in dose order."""
    attrs = row.get("attributes") or {}
    key = []
    for a in sorted(attrs):
        v = _num(attrs[a])
        key.append((0, v, "") if v is not None else (1, 0.0, str(attrs[a])))
    return (tuple(key), str(row.get("condition")))


def plain(x, digits: int) -> str:
    """`x` at `digits` significant figures, written without an exponent:
    20, not 2e+01."""
    v = sig(x, digits)
    if v is None:
        return "?"
    return np.format_float_positional(v, trim="-")


def span_text(values, digits: int) -> str:
    """'35–48' or '40', at `digits` significant figures."""
    vals = [sig(v, digits) for v in values if v is not None]
    if not vals:
        return "?"
    lo, hi = min(vals), max(vals)
    return plain(lo, digits) if lo == hi else f"{plain(lo, digits)}–{plain(hi, digits)}"


def where_text(group: list[dict], stratum_rows: list[dict], skip: str | None) -> str:
    """Where a group's series sit: the attribute values it covers, per attribute
    that varies within the stratum ('in population B, NK at dose 1'). An
    attribute the group covers entirely is left unsaid beside one it does not;
    alone it reads 'in every population'. A group that is the whole stratum
    needs no place at all."""
    if len(group) == len(stratum_rows):
        return ""
    attrs = sorted(
        {
            a
            for r in stratum_rows
            for a in (r.get("attributes") or {})
            if a != skip
            and len({str((m.get("attributes") or {}).get(a)) for m in stratum_rows}) > 1
        }
    )
    if not attrs:
        conds = _sorted_values(r["condition"] for r in group)
        if len(stratum_rows) == 1:
            return ""
        return "in " + _listed(conds)
    parts, whole = [], []
    # populations before doses: 'in population Mono at dose 1'
    numeric = {
        a: _is_numeric([(r.get("attributes") or {}).get(a) for r in stratum_rows])
        for a in attrs
    }
    for a in sorted(attrs, key=lambda a: (numeric[a], a)):
        mine = _sorted_values((r.get("attributes") or {}).get(a) for r in group)
        every = _sorted_values((r.get("attributes") or {}).get(a) for r in stratum_rows)
        prep = "at" if _is_numeric(every) else "in"
        if mine == every:
            whole.append(f"{prep} every {a}")
        else:
            parts.append(f"{prep} {a} {_listed(mine)}")
    return " ".join(parts or whole[:1])


def _listed(values: list[str], limit: int = 6) -> str:
    if len(values) <= limit:
        return ", ".join(values)
    return ", ".join(values[:limit]) + f" and {len(values) - limit} more"


def trend_text(group: list[dict], value, noun: str = "larger") -> str:
    """How `value(row)` moves with each numeric attribute varying in the group:
    'larger at higher dose', or '' when there is no clear direction."""
    attrs = sorted(
        {
            a
            for r in group
            for a, v in (r.get("attributes") or {}).items()
            if _num(v) is not None
        }
    )
    out = []
    for a in attrs:
        pts = [
            (_num((r.get("attributes") or {}).get(a)), value(r))
            for r in group
            if _num((r.get("attributes") or {}).get(a)) is not None
            and value(r) is not None
        ]
        levels = sorted({x for x, _ in pts})
        if len(levels) < 2:
            continue
        if len(levels) == 2:
            lo = np.mean([v for x, v in pts if x == levels[0]])
            hi = np.mean([v for x, v in pts if x == levels[1]])
            if lo > 0 and hi / lo >= 1.5:
                out.append(f"{noun} at the higher {a}")
            elif hi > 0 and lo / hi >= 1.5:
                out.append(f"{_opposite(noun)} at the higher {a}")
            continue
        from scipy.stats import spearmanr

        rho = spearmanr([x for x, _ in pts], [v for _, v in pts]).statistic
        if rho is not None and math.isfinite(rho) and rho >= 0.8:
            out.append(f"{noun} at higher {a}")
        elif rho is not None and math.isfinite(rho) and rho <= -0.8:
            out.append(f"{_opposite(noun)} at higher {a}")
    return ", ".join(out)


def _opposite(noun: str) -> str:
    return {"larger": "smaller", "smaller": "larger"}.get(noun, "less " + noun)


# ------------------------------------------------------------ residual forms


def _residual_form_text(fit: dict, digits: int = 2) -> str:
    """One residual group's shape, in words."""
    form, d = fit["form"], fit.get("direction")
    if form == "linear":
        return "linear drift " + ("upward" if d == "increasing" else "downward")
    if form == "exponential":
        return "exponential decay" if d == "decay" else "exponential rise"
    if form == "rise_and_fall":
        return "transient excess" if d == "peak" else "transient deficit"
    return "no time shape"


def residual_group_text(group: list[dict], stratum_rows, skip) -> str:
    """'exponential decay in population B, NK, τ 35–48, data above the model
    early; amplitude 2–3 σ, larger at higher dose (3 series)'."""
    f0 = group[0]["fit"]
    where = where_text(group, stratum_rows, skip)
    parts = [_residual_form_text(f0) + (f" {where}" if where else "")]
    taus = [r["fit"].get("timescales") or [] for r in group]
    if f0["form"] == "exponential":
        parts.append("τ " + span_text([t[0] for t in taus if t], 2))
        early = [r.get("early_sign") for r in group if r.get("early_sign")]
        if early and len(set(early)) == 1:
            parts.append(f"data {early[0]} the model early")
    elif f0["form"] == "rise_and_fall":
        parts.append(
            "τ1 "
            + span_text([t[0] for t in taus if t], 2)
            + ", τ2 "
            + span_text([t[1] for t in taus if len(t) > 1], 2)
            + ", extreme near t ≈ "
            + span_text([r["fit"].get("peak_time") for r in group], 2)
        )
    head = ", ".join(parts)
    amps = [
        abs(r["fit"]["amplitude"])
        for r in group
        if r["fit"].get("amplitude") is not None
    ]
    unit = " σ" if f0.get("amplitude_units") == "sigma" else " (data units)"
    tail = []
    if amps:
        what = "offset" if f0["form"] == "constant" else "amplitude"
        tail.append(f"{what} {span_text(amps, 2)}{unit}")
    trend = trend_text(
        group,
        lambda r: (
            abs(r["fit"]["amplitude"])
            if r["fit"].get("amplitude") is not None
            else None
        ),
    )
    if trend:
        tail.append(trend)
    n = f" ({len(group)} series)" if len(group) > 1 else " (1 series)"
    return head + ("; " + ", ".join(tail) if tail else "") + n


def aggregate_residuals(rows: list[dict], model: str) -> list[tuple[float, str]]:
    """(weight, sentence) per stratum of one model's residual forms.

    The largest group of agreeing series leads; every other group is named after
    'disagrees:'. The weight is the largest |amplitude| among shaped groups, so
    the caller can put the strongest residual first.
    """
    out = []
    for obs, attr, val, srows in strata(rows):
        groups = clusters(srows)
        under = under_text(srows, attr, val)
        lead = residual_group_text(groups[0], srows, attr)
        rest = [residual_group_text(g, srows, attr) for g in groups[1:]]
        text = f"{model}: residual of {obs}{under}: {lead}"
        if rest:
            text += "; disagrees: " + "; ".join(rest)
        weight = max(
            (
                abs(r["fit"]["amplitude"] or 0.0)
                for g in groups
                if g[0]["fit"]["form"] != "constant"
                for r in g
            ),
            default=0.0,
        )
        out.append((weight, text + "."))
    return out
