"""How close each structural-misfit indicator came to firing.

A verdict ("quiet") is not a measurement; the margin is. The indicators point
in opposite directions (two are "value above a ceiling", one is "p below an
alpha"), so each is also expressed as CLOSENESS:

    closeness >= 1  means the indicator fired
    closeness  < 1  means it did not, and the number is how far it got

  · ceiling tests (sigma over the floor):   closeness = value / threshold
  · p-value tests (chi2, residual shape):   closeness = alpha / p
"""

from __future__ import annotations

# The spec defaults, used only to read a run that did not record its own
# thresholds; an entry sourced from here is labelled as such.
FALLBACK = {
    "alpha": 0.01,
    "max_sigma_over_floor": 1.3,
    "autocorr_alpha": 0.05,
}


def thresholds_from_spec(spec) -> dict:
    """The three misfit thresholds a run applies, read from its spec.

    The one place they are read. Required, not defaulted, so every threshold
    that judges a run is in workflow_sha; `FALLBACK` is for reading old runs,
    never for judging a new one."""
    return {
        "alpha": float(spec.require("gates.misfit.alpha")),
        "max_sigma_over_floor": float(
            spec.require("gates.misfit.max_sigma_over_floor")
        ),
        "autocorr_alpha": float(spec.require("gates.misfit.autocorr_alpha")),
    }


def _entry(
    indicator: str,
    what: str,
    value: float | None,
    threshold: float | None,
    kind: str,
    fired: bool,
    recorded: bool,
    extra: str = "",
) -> dict:
    """One indicator, with its closeness and a line a reader can act on."""
    closeness = None
    if value is not None and threshold not in (None, 0):
        if kind == "ceiling":
            closeness = float(value) / float(threshold)
        else:  # "p": smaller p is stronger evidence
            closeness = float(threshold) / float(value) if value else float("inf")
    out = {
        "indicator": indicator,
        "what": what,
        "value": None if value is None else float(value),
        "threshold": None if threshold is None else float(threshold),
        "kind": kind,
        "fired": bool(fired),
        "closeness": None if closeness is None else round(closeness, 3),
        "threshold_recorded": bool(recorded),
    }
    out["reads_as"] = _reads_as(out, extra)
    return out


def _reads_as(e: dict, extra: str = "") -> str:
    if e["value"] is None or e["threshold"] is None:
        return f"{e['what']}: not measured on this round"
    v, th = e["value"], e["threshold"]
    if e["kind"] == "ceiling":
        gap = f"{abs(v - th):.3g} {'over' if v > th else 'below'}"
        core = f"{e['what']} {v:.4g} against a {th:.4g} threshold — {gap}"
    else:
        core = (
            f"{e['what']} p={v:.3g} against alpha {th:.3g} — "
            f"{'below' if v < th else 'above'} it by {abs(v - th):.3g}"
        )
    if e["closeness"] is not None and not e["fired"]:
        core += f" ({e['closeness']:.0%} of the way to firing)"
    if not e["threshold_recorded"]:
        core += " [threshold is today's default; this run did not record its own]"
    return core + (f"; {extra}" if extra else "")


def margins(evidence: dict | None, thresholds: dict | None = None) -> list[dict]:
    """Every indicator that was MEASURED, with its distance from threshold.

    Ordered by closeness, nearest first, so the head of the list is the answer
    to "what almost fired". Indicators that did fire sort first by definition
    (closeness >= 1), which is the right order for a card: what fired, then
    what nearly did.

    An indicator that could not be measured is included with `value: None`
    rather than omitted — "not measured" and "measured and quiet" are
    different states, and dropping the first makes a silent screen look like a
    passing one.
    """
    ev = evidence or {}
    th = dict(FALLBACK)
    recorded = bool(ev.get("thresholds"))
    th.update(ev.get("thresholds") or {})
    if thresholds:
        th.update(thresholds)
        recorded = True

    out: list[dict] = []
    signals = ev.get("signals") or {}

    # 1. fitted sigma over the replicate floor, per observable.
    # A JOINT condition: the ratio must clear the threshold AND the fitted
    # sigma must sit outside the floor's own confidence interval. Reporting
    # only the ratio would overstate how close the indicator was, so the CI
    # side travels in the line.
    fired_obs = {
        str(r.get("observable")) for r in (ev.get("sigma_inflated") or []) if r
    }
    for rec in signals.get("sigma_vs_floor") or []:
        obs = str(rec.get("observable", "?"))
        ci = rec.get("upper_ci")
        sig = rec.get("sigma_fitted")
        extra = ""
        if ci is not None and sig is not None:
            extra = (
                f"and the joint condition needs sigma {sig:.4g} above the "
                f"floor's upper CI {ci:.4g} — "
                f"{'it is' if sig > ci else f'{ci - sig:.3g} below'}"
            )
        out.append(
            _entry(
                f"sigma over replicate floor · {obs}",
                f"fitted sigma is {rec.get('ratio')}x the replicate floor;",
                rec.get("ratio"),
                th.get("max_sigma_over_floor"),
                "ceiling",
                obs in fired_obs,
                recorded,
                extra,
            )
        )
    for rec in signals.get("sigma_not_constant") or []:
        out.append(
            _entry(
                f"sigma over replicate floor · {rec.get('observable', '?')}",
                "NOT COMPARABLE — the noise formula depends on the model "
                "state, so there is no single sigma to hold against a floor",
                None,
                None,
                "ceiling",
                False,
                recorded,
            )
        )

    # 2. chi2/dof against the model-free floor
    gof = ev.get("gof_at_noise_floor")
    out.append(
        _entry(
            "chi2/dof at the noise floor",
            (
                f"chi2/dof {gof['chi2_per_dof']} on {gof['dof']} dof;"
                if gof
                else "goodness of fit against the replicate floor"
            ),
            (gof or {}).get("p"),
            th.get("alpha"),
            "p",
            bool(gof and gof.get("p") is not None and gof["p"] < th.get("alpha", 0)),
            recorded,
        )
    )

    # 3. residual shape, corroborating only
    ac = ev.get("autocorrelation")
    out.append(
        _entry(
            "residual shape (corroborating only)",
            (
                f"residuals run positive in time, Stouffer Z "
                f"{ac['stouffer_z']} over {ac['n_series']} series;"
                if ac
                else "positive residual autocorrelation in time"
            ),
            (ac or {}).get("p"),
            th.get("autocorr_alpha"),
            "p",
            bool(
                ac and ac.get("p") is not None and ac["p"] < th.get("autocorr_alpha", 0)
            ),
            recorded,
        )
    )

    # measured first, ordered nearest-to-firing; unmeasured last, since they
    # answer a different question
    return sorted(
        out,
        key=lambda e: (e["closeness"] is None, -(e["closeness"] or 0.0)),
    )


def nearest(evidence: dict | None, thresholds: dict | None = None) -> dict | None:
    """The measured indicator closest to firing WITHOUT having fired.

    None when nothing was measured, or when everything measured fired — in
    which case the misfit flag is open and "what nearly fired" is not the
    question the reader has.
    """
    for e in margins(evidence, thresholds):
        if e["closeness"] is not None and not e["fired"]:
            return e
    return None


def _compact_part(e: dict) -> str:
    """One indicator on the one-line summary.

    A percentage "of the way to firing" means something only below the
    threshold (past it, a p-value's alpha/p grows without bound), so a fired
    indicator shows its statistic against its threshold instead."""
    name = e["indicator"].replace("sigma over replicate floor · ", "sigma·")
    if e["fired"]:
        if e["kind"] == "p":
            return f"{name} p={e['value']:.2g} < {e['threshold']:.2g}*"
        return f"{name} {e['value']:.3g} > {e['threshold']:.3g}*"
    if e["closeness"] >= 1:
        return f"{name} past its threshold (not counted as firing)"
    return f"{name} {e['closeness']:.0%}"


def card_line_compact(evidence: dict | None, thresholds: dict | None = None) -> str:
    """Every indicator's closeness on ONE line, ranked, or "" if none.

    The per-indicator form is for a report; a gate card's evidence lines are
    capped (`CARD_EVIDENCE_LINES`), so the card gets the ranking compressed and
    the full arithmetic stays in the report's §8.
    """
    rows = [e for e in margins(evidence, thresholds) if e["closeness"] is not None]
    if not rows:
        return ""
    fired = [e for e in rows if e["fired"]]
    parts = [_compact_part(e) for e in rows]
    head = (
        f"{len(fired)} of {len(rows)} indicators FIRED (*)"
        if fired
        else f"no indicator fired, closest {rows[0]['closeness']:.0%}"
    )
    unrecorded = (
        "" if rows[0]["threshold_recorded"] else " [thresholds: today's default]"
    )
    return (
        f"indicators, % of the way to firing — {head}: "
        + " · ".join(parts)
        + unrecorded
    )
