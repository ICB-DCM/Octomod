"""Optimiser comparison on the same start points, measured by the engine.

Read by a human, on the gate card and in the report; no agent picks a solver
(`estimation.optimizer` is workflow-owned). Run only by the cost probe (when
the default reaches its optimum on too few starts) and the convergence gate,
and sized from the budget by `plan()`. Metrics follow Grein & Penas (2026):
optimality gap and overall efficiency (see `score`).
"""

from __future__ import annotations

import importlib
import logging
import time
from dataclasses import dataclass, field

import numpy as np

# name -> (backing import, human label). The candidate set is spec-declared;
# this table says what each name needs to run. `[k/30]` is how many of the 30
# benchmark problems the method reached the best known objective on (Grein &
# Penas 2026, from their `best_fx_marvin.csv`). The unbenchmarked names are
# opt-in only (differential evolution is the one global method with no extra
# dependency) and not in the shipped candidate list.
BACKENDS: dict[str, tuple[str | None, str]] = {
    # benchmarked, top tier
    "cmaes": ("cma", "CMA-ES (global, population) [26/30]"),
    "fides": ("fides", "fides (trust-region, gradient) [25/30]"),
    "nlopt_auglag": ("nlopt", "NLopt AUGLAG + L-BFGS (gradient) [20/30]"),
    "nlopt_lbfgs": ("nlopt", "NLopt LD_LBFGS (gradient) [20/30]"),
    "scipy_lbfgsb": ("scipy", "SciPy L-BFGS-B (quasi-Newton, gradient) [19/30]"),
    "nlopt_var2": ("nlopt", "NLopt LD_VAR2 (variable metric) [19/30]"),
    "ipopt": ("cyipopt", "Ipopt (interior point, gradient) [19/30]"),
    # NOT in the benchmark — reachable, but never presented as evidence-backed
    "scipy_de": ("scipy", "SciPy differential evolution (global) [not benchmarked]"),
    "scipy_powell": ("scipy", "SciPy Powell (derivative-free) [not benchmarked]"),
}


# The fallback optimiser, at or near the best on 25 of the 30 benchmark
# problems; every inconclusive comparison resolves here.
DEFAULT_OPTIMIZER = "fides"


@dataclass
class MethodResult:
    """One optimiser's row in the comparison."""

    name: str
    label: str
    available: bool
    reason: str = ""
    # installed, but the budget ran out before it started (not the same as absent)
    not_run: bool = False
    fvals: list[float] = field(default_factory=list)
    # starts attempted, not len(fvals): a start with a non-finite objective is a
    # failed start, and dividing successes by the survivors overstates the rate
    n_attempted: int = 0
    wall_s: float = 0.0
    best_fval: float = float("inf")
    n_success: int = 0
    optimality_gap: float = float("nan")
    overall_efficiency: float = float("nan")
    t_per_success_s: float = float("nan")


def success_threshold(alpha: float = 0.05) -> float:
    """The likelihood-ratio threshold a start must be within to count as
    successful: chi2.ppf(1 - alpha, df=1) / 2 (1.92 at alpha = 0.05).

    df=1 rather than the number of parameters on purpose — this asks whether a
    start is at a point the data cannot distinguish from the best one found,
    which is the same one-dimensional question a profile CI asks.
    """
    from octomod.workflow_modules.estimation.problem import lr_threshold

    return lr_threshold(alpha)


def available(name: str) -> tuple[bool, str]:
    """Whether this optimiser can actually run here.

    Checked by import rather than by running it, because a missing backend
    does not raise through pyPESTO — it returns inf per start and would be
    scored as a bad optimiser instead of an absent one.
    """
    spec = BACKENDS.get(name)
    if spec is None:
        return False, f"unknown optimiser name {name!r}"
    module, _ = spec
    if module is None:
        return True, ""
    try:
        importlib.import_module(module)
    except ImportError:
        return False, f"not installed (needs `{module}`)"
    except Exception as exc:
        # nlopt and cma are native extensions: a broken build raises
        # OSError/RuntimeError from the loader, not ImportError, and one
        # unusable method must not end the comparison
        return (
            False,
            f"`{module}` is installed but unusable: {type(exc).__name__}: {exc}",
        )
    return True, ""


def build(name: str):
    """The pyPESTO optimiser object. Raises for an unknown name — the spec's
    vocabulary is closed, exactly like `estimation.optimizer`."""
    import pypesto.optimize as po

    if name == "fides":
        return po.FidesOptimizer(verbose=logging.WARNING)
    if name == "scipy_lbfgsb":
        return po.ScipyOptimizer(method="L-BFGS-B")
    if name == "scipy_powell":
        return po.ScipyOptimizer(method="Powell")
    if name == "scipy_de":
        return po.ScipyDifferentialEvolutionOptimizer()
    if name == "cmaes":
        return po.CmaOptimizer()
    if name == "ipopt":
        return po.IpoptOptimizer()
    if name.startswith("nlopt_"):
        import nlopt

        if name == "nlopt_lbfgs":
            return po.NLoptOptimizer(method=nlopt.LD_LBFGS)
        if name == "nlopt_var2":
            return po.NLoptOptimizer(method=nlopt.LD_VAR2)
        if name == "nlopt_auglag":
            # AUGLAG does nothing without an inner method (as in the benchmark);
            # L-BFGS, the strongest drop-in gradient method of the family
            return po.NLoptOptimizer(method=nlopt.AUGLAG, local_method=nlopt.LD_LBFGS)
    raise ValueError(f"unknown optimiser for comparison: {name}")


# How much dearer than the incumbent's a challenger's start is assumed to be: a
# population method evaluates the objective many times per start (CMA-ES scored
# OE 0.091 against fides' 0.690 on the fixture). It only has to keep the
# projection from being low, since over-projecting refuses a gate answer the
# card offers; the real bound is the wall-clock stop in `compare()`.
COST_FACTOR = 2.0


def plan(
    n_candidates: int,
    n_estimation_starts: int,
    median_start_s: float | None,
    *,
    fraction: float,
    min_starts: int,
    on_request: bool = False,
) -> dict | None:
    """How many starts each candidate may have, derived from the budget.

        per_method = floor(fraction * n_estimation_starts
                           / (n_candidates * COST_FACTOR))

    Returns None when that buys fewer than `min_starts` each: a comparison on
    too few starts invites a switch on noise. With `on_request` (a human typed
    `compare` at the convergence gate) the floor is used instead, `over_budget`
    says so, and the caller prints what it will cost.
    """
    if median_start_s is None or median_start_s <= 0 or n_candidates <= 0:
        return None
    budget_starts = fraction * float(n_estimation_starts)
    per_method = int(budget_starts // (n_candidates * COST_FACTOR))
    over_budget = per_method < min_starts
    if over_budget:
        if not on_request:
            return None
        per_method = min_starts
    budget_s = float(budget_starts * median_start_s)
    projected_s = float(n_candidates * per_method * COST_FACTOR * median_start_s)
    return {
        "n_starts": per_method,
        "n_candidates": n_candidates,
        "over_budget": over_budget,
        "budget_s": budget_s,
        "projected_s": projected_s,
        # what `compare(budget_s=...)` stops at: on an `on_request` floor the
        # allowance is below the projection, and stopping there would report
        # methods that never ran as though they had lost
        "stop_s": max(budget_s, projected_s),
    }


def compare(
    problem,
    *,
    methods: list[str],
    n_starts: int,
    seed: int,
    alpha: float = 0.05,
    startpoints: np.ndarray | None = None,
    budget_s: float | None = None,
    incumbent: str = DEFAULT_OPTIMIZER,
) -> list[MethodResult]:
    """Run each available method on the same starts and score them.

    `startpoints` (from the main fit) make the comparison paired; without them
    every method gets the same seed. The incumbent runs first whatever the
    order of `methods`, because every verdict is relative to its row. With
    `budget_s`, methods not started in time are reported as not run.
    """
    import pypesto.optimize as po

    ordered = [c for c in methods if c == incumbent] + [
        c for c in methods if c != incumbent
    ]
    rows: list[MethodResult] = []
    t_start = time.perf_counter()
    for name in ordered:
        # the wall-clock bound: once the budget is spent, the rest are not run
        if budget_s is not None and (time.perf_counter() - t_start) > budget_s:
            label = BACKENDS.get(name, (None, name))[1]
            rows.append(
                MethodResult(
                    name,
                    label,
                    False,
                    reason=f"the comparison's {budget_s:.0f}s budget was "
                    f"spent before it started",
                    not_run=True,
                )
            )
            continue
        ok, why = available(name)
        label = BACKENDS.get(name, (None, name))[1]
        if not ok:
            rows.append(MethodResult(name, label, False, why))
            continue
        np.random.seed(seed)
        if startpoints is not None:
            problem.set_x_guesses(startpoints)
        t0 = time.perf_counter()
        try:
            res = po.minimize(
                problem=problem,
                optimizer=build(name),
                n_starts=n_starts,
                progress_bar=False,
                filename=None,
            )
        except Exception as exc:  # a method that dies is reported, never fatal
            rows.append(
                MethodResult(name, label, False, f"raised {type(exc).__name__}: {exc}")
            )
            continue
        wall = time.perf_counter() - t0
        attempted = len(res.optimize_result.list)
        fvals = [
            float(o["fval"])
            for o in res.optimize_result.list
            if o["fval"] is not None and np.isfinite(o["fval"])
        ]
        rows.append(
            MethodResult(
                name,
                label,
                True,
                fvals=fvals,
                n_attempted=attempted,
                wall_s=wall,
                best_fval=min(fvals) if fvals else float("inf"),
                # n_success and the two metrics need the field best, which is
                # only known once every method has run — filled in by score().
            )
        )
    return score(rows, alpha=alpha)


def row_from_probe(probe_result, *, wall_s: float, name: str = DEFAULT_OPTIMIZER):
    """The incumbent's row, built from the cost probe's timed starts, not a re-run.

    Its start count differs from the challengers'; the table's `success` column
    prints hits over attempts, so that stays visible.
    """
    starts = probe_result.optimize_result.list
    fvals = [
        float(o.fval) for o in starts if o.fval is not None and np.isfinite(o.fval)
    ]
    return MethodResult(
        name,
        BACKENDS.get(name, (None, name))[1],
        True,
        fvals=fvals,
        n_attempted=len(starts),
        wall_s=float(wall_s),
    )


def score(rows: list[MethodResult], *, alpha: float = 0.05) -> list[MethodResult]:
    """Optimality gap and overall efficiency against the best value any
    available method reached (pure arithmetic, testable from fvals alone).

    `OG_i = J*_i - J*` is a gap in objective value, not a parameter distance
    (optima are not unique). `OE_i = min_i' <t_succ,i'> / <t_succ,i>` in
    `(0, 1]`, with `<t_succ,i> = T_i / S_i` the wall time per successful
    start; `1/OE_i` is how many times longer method i runs to buy one
    successful start. A start succeeds within `success_threshold(alpha)`.
    """
    thr = success_threshold(alpha)
    # the per-method best comes from the starts, not from the caller
    for r in rows:
        if r.available and r.fvals:
            r.best_fval = float(min(r.fvals))
    ran = [r for r in rows if r.available and np.isfinite(r.best_fval)]
    if not ran:
        return rows
    best = min(r.best_fval for r in ran)
    for r in ran:
        r.optimality_gap = float(r.best_fval - best)
        r.n_success = sum(1 for f in r.fvals if (f - best) <= thr)
        # a row built from fvals alone carries no attempt count
        if not r.n_attempted:
            r.n_attempted = len(r.fvals)
        r.t_per_success_s = (
            float(r.wall_s / r.n_success) if r.n_success else float("inf")
        )
    finite = [r.t_per_success_s for r in ran if np.isfinite(r.t_per_success_s)]
    if finite:
        fastest = min(finite)
        for r in ran:
            r.overall_efficiency = (
                float(fastest / r.t_per_success_s)
                if np.isfinite(r.t_per_success_s) and r.t_per_success_s > 0
                else 0.0
            )
    return rows


def starts_for_confidence(p_success: float, confidence: float = 0.95) -> int | None:
    """How many independent starts give `confidence` of at least one success,
    at an observed per-start success rate.

    `ceil(log(1 - confidence) / log(1 - p))`. None when p is 0 (no number of
    starts helps a method that never reaches the basin) or 1 (any start does).
    A low but nonzero rate is a start-count problem, not an optimiser problem.
    """
    import math

    if not (0.0 < p_success < 1.0):
        return None
    return int(math.ceil(math.log(1.0 - confidence) / math.log(1.0 - p_success)))


def select(
    rows: list[MethodResult],
    *,
    default: str = DEFAULT_OPTIMIZER,
    min_success_gain: float = 0.25,
    alpha: float = 0.05,
) -> dict:
    """Which optimiser the run should use, from a comparison — deterministic,
    declared, and biased towards the default.

    Decides only the `auto` case (the caller resolves an explicit request
    first), and is hard to talk into switching: a wrong switch costs a whole
    estimation at a worse optimiser. The rule, in order:

    1. A materially better optimum: some method beats the default by more than
       the likelihood-ratio threshold (a difference the data can resolve).
       Take the best such method, ties broken by overall efficiency.
    2. The same answer, far more reliably: every method inside the threshold,
       and some method's per-start success rate exceeds the default's by at
       least `min_success_gain` (absolute: 0.25 is 25 points). Ties broken by
       overall efficiency.
    3. Anything else, including any inconclusive comparison: the default.

    Returns the choice and the reason it was made.
    """
    ran = [r for r in rows if r.available and np.isfinite(r.best_fval)]
    inc = next((r for r in ran if r.name == default), None)
    base = {"selected": default, "default": default, "n_compared": len(ran)}
    if len(ran) < 2 or inc is None:
        return {
            **base,
            "reason": (
                f"inconclusive: {len(ran)} optimiser(s) produced a finite result"
                + ("" if inc is not None else f" and {default} was not among them")
                + f" — keeping the default {default}"
            ),
            "conclusive": False,
        }
    # the spec's alpha: the threshold `score()` counted successes at
    thr = success_threshold(alpha)

    # 1. a materially better optimum
    better = [r for r in ran if inc.best_fval - r.best_fval > thr]
    if better:
        win = min(better, key=lambda r: (r.best_fval, -r.overall_efficiency))
        return {
            **base,
            "selected": win.name,
            "conclusive": True,
            "reason": (
                f"{win.label} reached {win.best_fval:.6g} against {default}'s "
                f"{inc.best_fval:.6g}, a gap of {inc.best_fval - win.best_fval:.4g} "
                f"which is outside the likelihood-ratio threshold of {thr:.3g} — "
                f"the data can tell these two answers apart"
            ),
        }

    # 2. same answer, much better hit rate
    def rate(r: MethodResult) -> float:
        """Successes over ATTEMPTED starts. A start that failed is a start
        this method did not solve, and must count against it."""
        return (r.n_success / r.n_attempted) if r.n_attempted else 0.0

    inc_rate = rate(inc)
    # no minimum-sample check here: `plan()` never sizes a comparison below
    # a usable start count
    tied = [
        r for r in ran if r.name != default and rate(r) - inc_rate >= min_success_gain
    ]
    if tied:
        win = max(tied, key=lambda r: (rate(r), r.overall_efficiency))
        return {
            **base,
            "selected": win.name,
            "conclusive": True,
            "reason": (
                f"every method landed within {thr:.3g} of the same optimum, so the "
                f"answer is not in question — but {win.label} reached it on "
                f"{rate(win):.0%} of starts against {default}'s {inc_rate:.0%}, a "
                f"margin of at least {min_success_gain:.0%}. At this problem's "
                f"start budget that is the difference between finding the optimum "
                f"and missing it"
            ),
        }

    return {
        **base,
        "conclusive": True,
        "reason": (
            f"no optimiser beat {default} by more than the likelihood-ratio "
            f"threshold ({thr:.3g}) or by {min_success_gain:.0%} of starts — "
            f"keeping the default"
        ),
    }


def table_lines(
    rows: list[MethodResult], incumbent: str = DEFAULT_OPTIMIZER
) -> list[str]:
    """The comparison as the gate card and the report show it."""
    ran = [r for r in rows if r.available]
    # width from the actual labels, which carry a benchmark score
    w = max([len(r.label) for r in rows] + [len("optimiser")]) + 2
    out = [
        f"{'optimiser':{w}} {'best fval':>12} {'opt.gap':>9} "
        f"{'success':>9} {'OE':>6}",
    ]
    for r in sorted(ran, key=lambda r: (r.optimality_gap, -r.overall_efficiency)):
        mark = "*" if r.name == incumbent else " "
        oe = (
            "     -"
            if not np.isfinite(r.overall_efficiency)
            else f"{r.overall_efficiency:6.2f}"
        )
        succ = f"{r.n_success}/{r.n_attempted or len(r.fvals)}"
        out.append(
            f"{mark} {r.label:{w - 2}} {r.best_fval:12.4f} {r.optimality_gap:9.3f} "
            f"{succ:>9} {oe}"
        )
    for r in rows:
        if not r.available:
            # UNAVAILABLE = not installed; NOT RUN = the budget stopped it first
            word = "NOT RUN" if r.not_run else "UNAVAILABLE"
            out.append(f"  {r.label:{w - 2}} {word} — {r.reason}")
    out.append("  * = the optimiser the workflow used for this fit")
    return out


def verdict(
    rows: list[MethodResult],
    incumbent: str = DEFAULT_OPTIMIZER,
    *,
    alpha: float = 0.05,
) -> dict:
    """The engine's own reading of the table — facts only, no recommendation.

    The winner has the smallest optimality gap; overall efficiency breaks ties.
    """
    ran = [r for r in rows if r.available and np.isfinite(r.best_fval)]
    if not ran:
        return {"ran": 0, "winner": None, "incumbent_is_best": None}
    thr = success_threshold(alpha)  # the spec's, for the same reason as select
    best = min(r.optimality_gap for r in ran)
    winners = [r for r in ran if r.optimality_gap <= best + 1e-12]
    winner = max(winners, key=lambda r: (r.overall_efficiency, -r.optimality_gap))
    inc = next((r for r in ran if r.name == incumbent), None)
    return {
        "ran": len(ran),
        "unavailable": [r.name for r in rows if not r.available],
        "threshold": thr,
        "winner": winner.name,
        "winner_label": winner.label,
        "winner_gap": winner.optimality_gap,
        "winner_oe": winner.overall_efficiency,
        "incumbent": incumbent,
        "incumbent_gap": None if inc is None else inc.optimality_gap,
        "incumbent_oe": None if inc is None else inc.overall_efficiency,
        # "materially better" = the incumbent's own best is outside the
        # likelihood-ratio threshold around the winner's, i.e. the data CAN
        # tell the two results apart. Inside it, the methods disagree about
        # nothing the data supports and switching buys only speed.
        "incumbent_is_best": inc is not None and inc.optimality_gap <= 1e-12,
        "materially_better": inc is not None and inc.optimality_gap > thr,
        **_remedy(inc, winner, thr),
    }


def _remedy(inc, winner, thr: float) -> dict:
    """Which fix the numbers point at: more starts, a different optimiser, or
    neither.

    The incumbent's per-start success rate decides both ways: a rate above zero
    means it can find the basin and was under-started, and tied best values
    with a far lower rate are a fragile result, not a fine one.
    `starts_for_confidence` turns the rate into a start count; the remedy for a
    low rate is the existing `estimation.refit_presets.more_starts` preset.
    """
    if inc is None:
        return {"remedy": "inconclusive", "remedy_detail": "the incumbent did not run"}
    n_inc = inc.n_attempted or len(inc.fvals)
    rate = (inc.n_success / n_inc) if n_inc else 0.0
    needed = starts_for_confidence(rate)
    n_win = (winner.n_attempted or len(winner.fvals)) if winner is not None else 0
    best_rate = (winner.n_success / n_win) if n_win else 0.0
    base = {"incumbent_success_rate": rate, "best_success_rate": best_rate}

    # 1. the incumbent's answer is worse. Its success rate is necessarily zero
    #    here (`gap > thr` and `n_success > 0` cannot both hold), so it is not
    #    tested.
    if inc.optimality_gap > thr:
        return {
            **base,
            "remedy": "different_optimizer",
            "remedy_detail": (
                f"the incumbent reached the best basin on NONE of its {n_inc} "
                f"starts while {winner.label} reached it, so more starts of the "
                f"incumbent is a bet on an observed rate of zero"
            ),
        }

    # 2. the answers agree, but the incumbent got there far less reliably.
    #    Half the winner's rate is the line: a difference that small at this
    #    sample size is noise, and a difference that large would have cost the
    #    run its answer at a smaller budget.
    if rate > 0.0 and best_rate > 0.0 and rate < 0.5 * best_rate:
        return {
            **base,
            "remedy": "more_starts",
            "starts_for_95pc": needed,
            "remedy_detail": (
                f"every method found the same optimum, so nothing about this fit's "
                f"ANSWER is wrong — but the incumbent reached it on only "
                f"{inc.n_success} of {n_inc} starts ({rate:.0%}) against "
                f"{best_rate:.0%} for {winner.label}. That is a fragile result "
                f"rather than a wrong one: about {needed} independent starts give "
                f"a 95% chance of at least one success, and a smaller budget than "
                f"that would have missed it"
            ),
        }

    return {
        **base,
        "remedy": "none",
        "remedy_detail": (
            "no method ended outside the likelihood-ratio threshold of the "
            "incumbent, and the incumbent reached the best basin about as often "
            "as the best method did, so the optimiser is not what is wrong here"
        ),
    }


def gate_decision(
    rows: list[MethodResult],
    incumbent: str,
    *,
    alpha: float = 0.05,
    min_success_gain: float = 0.25,
    refits_left: int,
) -> dict:
    """What the convergence gate does with a comparison it has just run (pure).

      refit_with       `select` found a different optimiser conclusively
                       better and a refit is still in budget: refit with it
                       now (the human bought this by answering `compare`)
      return_to_gate   otherwise; the gate is asked again with the table on
                       the card

    Judged by the probe path's rule against the optimiser that produced this fit.
    """
    sel = select(
        rows, default=incumbent, min_success_gain=min_success_gain, alpha=alpha
    )
    switch = bool(sel.get("conclusive")) and sel.get("selected") != incumbent
    if switch and refits_left > 0:
        return {"action": "refit_with", "selection": sel, "why": sel["reason"]}
    if switch:
        return {
            "action": "return_to_gate",
            "selection": sel,
            "why": (
                f"{sel['selected']} was conclusively better ({sel['reason']}) but "
                f"the refit budget is spent — the selection is on file for any "
                f"later fit, and the gate is asked again"
            ),
        }
    return {
        "action": "return_to_gate",
        "selection": sel,
        "why": sel["reason"],
    }


def with_selection(payload: dict, selection) -> dict:
    """Carry a run's optimiser selection into a comparison artifact.

    The probe-time selection and the gate's comparison write the SAME record
    group, `optimizer_comparison`, and the gate wrote last. Its payload had
    no selection in it, so a run that chose an optimiser at the probe and
    later bought a comparison at the gate kept running that optimiser and
    stopped saying so in its report — the reporting half of a decision going
    missing, which is the same bug as the decision going
    missing.

    `selection` is the `optimizer_selection` record as read (a dict), or
    whatever a missing or unreadable one read as. Anything that is not a
    selection leaves the payload alone: there is nothing to say, which is
    different from saying nothing.
    """
    sel = selection
    if isinstance(sel, dict) and sel.get("selected"):
        payload["selection"] = sel
    return payload


def as_json(
    rows: list[MethodResult],
    incumbent: str = DEFAULT_OPTIMIZER,
    *,
    alpha: float = 0.05,
) -> dict:
    """The comparison artifact written beside the fit."""
    return {
        "metric_definitions": {
            "optimality_gap": "best fval of this method minus the best any "
            "method reached (Grein & Penas 2026); 0 for the winner",
            "overall_efficiency": "min_i(wall/successes) / (wall/successes); "
            "1 is best, 1/OE is how many times longer this method must run "
            "to buy one successful start (Villaverde et al. 2018)",
            "success": "a start whose optimality gap is within "
            "chi2.ppf(1-alpha,1)/2 of the best found",
        },
        "verdict": verdict(rows, incumbent, alpha=alpha),
        "methods": [
            {
                "name": r.name,
                "label": r.label,
                "available": r.available,
                # absent (install something) is not never-started (out of budget)
                "not_run": r.not_run,
                "reason": r.reason,
                "best_fval": None if not np.isfinite(r.best_fval) else r.best_fval,
                "optimality_gap": (
                    None if not np.isfinite(r.optimality_gap) else r.optimality_gap
                ),
                "overall_efficiency": (
                    None
                    if not np.isfinite(r.overall_efficiency)
                    else r.overall_efficiency
                ),
                "n_success": r.n_success,
                "n_attempted": r.n_attempted or len(r.fvals),
                "n_finite": len(r.fvals),
                "wall_s": round(r.wall_s, 3),
            }
            for r in rows
        ],
    }
