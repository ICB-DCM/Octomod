"""Quantities the lab note declares constant, measured in the model.

The conservation scan reports what a model does conserve; this checks what the
experiment says should be. The agent declares the constants and the engine
measures their drift. It is a flag, not a constraint: advisory at S1, re-measured
at the fit in S7 as a misfit indicator, and handed to the expansion agent.
"""

from __future__ import annotations

import numpy as np

from octomod.workflow_modules.model.simwrap import RRModel, SimError, eval_formula

DEFAULT_TOLERANCE = 0.10


def parse(construction: dict | None) -> list[dict]:
    """Normalise the declared constants of a construction reply.

    An unusable row is dropped rather than failing a gate, so one bad row does not
    lose the whole check.
    """
    out = []
    for item in (construction or {}).get("declared_constants") or []:
        if isinstance(item, str):
            item = {"expression": item}
        if not isinstance(item, dict):
            continue
        expr = str(item.get("expression") or item.get("quantity") or "").strip()
        if not expr:
            continue
        try:
            tol = float(item.get("tolerance", DEFAULT_TOLERANCE))
        except (TypeError, ValueError):
            tol = DEFAULT_TOLERANCE
        out.append(
            {
                "expression": expr,
                "tolerance": abs(tol) if 0 < abs(tol) <= 1 else DEFAULT_TOLERANCE,
                "locator": str(item.get("locator") or item.get("source") or ""),
                "why": str(item.get("why") or item.get("supports") or ""),
            }
        )
    return out


def drift(
    sbml: str,
    constants: list[dict],
    t_end: float,
    overrides: dict[str, float] | None = None,
    label: str = "nominal",
) -> list[dict]:
    """Relative excursion of every declared constant over 0..t_end.

    Measured against its own value at t=0; the worst excursion and its time are
    reported. A row that cannot be simulated or evaluated carries `error` instead.
    """
    if not constants:
        return []
    try:
        model = RRModel(sbml)
        traj = model.simulate(float(t_end), n_points=101, overrides=overrides or None)
    except (SimError, Exception) as exc:
        return [
            {**c, "condition": label, "error": f"{type(exc).__name__}: {exc}"}
            for c in constants
        ]
    rows = []
    for c in constants:
        try:
            series = np.asarray(
                eval_formula(c["expression"], {k: v for k, v in traj.items()}),
                dtype=float,
            )
        except Exception as exc:
            rows.append({**c, "condition": label, "error": f"cannot evaluate: {exc}"})
            continue
        if series.ndim == 0 or series.size < 2 or not np.all(np.isfinite(series)):
            rows.append({**c, "condition": label, "error": "not a time series"})
            continue
        start = float(series[0])
        scale = abs(start) if abs(start) > 1e-12 else float(np.max(np.abs(series)))
        if scale <= 1e-12:
            rows.append({**c, "condition": label, "error": "zero throughout"})
            continue
        excursion = np.abs(series - start) / scale
        k = int(np.argmax(excursion))
        rows.append(
            {
                **c,
                "condition": label,
                "at_t0": start,
                "worst": float(series[k]),
                "at_time": float(traj["time"][k]),
                "drift": float(excursion[k]),
                "within_tolerance": bool(excursion[k] <= c["tolerance"]),
            }
        )
    return rows


def offenders(rows: list[dict]) -> list[dict]:
    """The rows that contradict the note, worst first."""
    bad = [r for r in rows if r.get("drift") is not None and not r["within_tolerance"]]
    return sorted(bad, key=lambda r: -float(r["drift"]))


# What a scope-gate note does, stated once so no surface overstates it: it is
# recorded and shown to the agent proposing the next move, never enforced.
SCOPE_NOTE_EFFECT = (
    "if you are certain the note is right, say so at the scope gate: your "
    "words are recorded and put in front of the agent proposing the next "
    "move. It is an instruction to the modeller, not a constraint the engine "
    "enforces — no gate refuses a model for breaking a declaration."
)


def verdict_prose(summary_or_rows) -> list[str]:
    """Plain-language lines for a selected model that contradicts a declaration.

    A run can accept a model that breaks a stated conservation, so the report
    says so as a decision taken against the note. Empty when nothing was
    declared or everything holds.
    """
    rows = (
        summary_or_rows.get("rows") or []
        if isinstance(summary_or_rows, dict)
        else (summary_or_rows or [])
    )
    bad = offenders(rows)
    if not bad:
        return []
    out = []
    for r in bad:
        where = (
            f" in {r['condition']}"
            if r.get("condition") and r["condition"] != "nominal"
            else ""
        )
        out.append(
            f"This model moves {r['expression']} by {float(r['drift']):.0%}"
            f"{where}; the experiment's own note says it is constant"
            + (f" ({str(r['locator'])[:120]})" if r.get("locator") else "")
            + f"; the tolerance was {float(r['tolerance']):.0%}. The data were "
            f"preferred here."
        )
    out.append(
        "Either the note is wrong or the mechanism is, and this run did not "
        "settle which — " + SCOPE_NOTE_EFFECT
    )
    return out


def card_lines(rows: list[dict], where: str = "at nominal parameters") -> list[str]:
    """Gate-card lines for the declared constants; empty when none were declared."""
    if not rows:
        return []
    bad = offenders(rows)
    errs = [r for r in rows if r.get("error")]
    if not bad and not errs:
        return [
            f"declared constants hold {where}: "
            + ", ".join(f"{r['expression']} ({r['drift']:.1%})" for r in rows[:4])
        ]
    out = []
    if bad:
        out.append(
            f"⚑ THE NOTE SAYS THESE ARE CONSTANT, AND THIS MODEL MOVES THEM "
            f"({where}):"
        )
        for r in bad:
            out.append(
                f"  · {r['expression']}: {r['at_t0']:.4g} → {r['worst']:.4g} by "
                f"t = {r['at_time']:.3g} — {r['drift']:.0%} drift, tolerance "
                f"{r['tolerance']:.0%}"
                + (f" [{r['condition']}]" if r["condition"] != "nominal" else "")
            )
            if r.get("locator"):
                out.append(f"      the note: {str(r['locator'])[:96]}")
        out.append(
            "  a flag, not a refusal: the note may be wrong, or the mechanism "
            "may be. What must not happen is neither of you noticing."
        )
        out.append("  " + SCOPE_NOTE_EFFECT)
    for r in errs:
        out.append(f"  · {r['expression']}: not measured — {r['error'][:90]}")
    return out


def summary(rows: list[dict]) -> dict:
    """The record for report_core and the expansion payload.

    `measured` is kept apart from `declared`: a row that could not be simulated
    has no drift, and an empty measurement is not a pass.
    """
    measured = [r for r in rows if r.get("drift") is not None]
    return {
        "declared": len(rows),
        "measured": len(measured),
        "unmeasured": len(rows) - len(measured),
        "violated": len(offenders(rows)),
        "worst_drift": (max(float(r["drift"]) for r in measured) if measured else None),
        "rows": rows,
    }
