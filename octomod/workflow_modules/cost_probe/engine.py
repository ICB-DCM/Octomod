"""Cost profiling — measure before committing.

A handful of probe starts, purely to measure: simulation time per condition
and wall-clock per optimisation start. The human approves a budget with those
numbers in hand, not a guess. Workflow-mandated; the agent cannot skip it.
"""

from __future__ import annotations

import datetime
import json
import math
import re
import time

import numpy as np

from octomod.agents import payload
from octomod.orchestration import (
    timing,  # noqa: E402
)
from octomod.orchestration.interaction import gate_note, humangate
from octomod.orchestration.run_context import ModuleFailure, RunContext
from octomod.result.slots import CostRecord
from octomod.result.write import write_record
from octomod.workflow_modules.assembly import petab_io
from octomod.workflow_modules.estimation import estimation_settings
from octomod.workflow_modules.estimation.problem import (
    non_gaussian_observables,
    run_multistart,
    uses_fim_hessian,
)

# The human's `n` at a budget gate re-asked for one candidate, recorded in the
# fitted problem's group (`ctx.work`). A resume replays the candidate loop from
# the first candidate; this record is how the answer outlives the invocation
# that took it, so a stored answer meant for a later candidate is never
# consumed here.
DECLINED_KEY = "budget_declined"

# the probe's measurements are a sibling of `cost` in the fitted problem's
# group (`ctx.work`); the structural-null measurement is
# `structural_nulls.node(ctx.work)` beside them.
PROBE_RECORD = "probe_record"


def _write_cost_profile(work, profile: dict) -> None:
    """Validated against its record before it is written (at `work / "cost"`)."""
    write_record(work / "cost", CostRecord, profile)


class BudgetDeclinedForCandidate(Exception):
    """The human answered `n` to a budget gate re-asked for one candidate.

    Not a ModuleFailure: `n` there means "do not fit this candidate", so the
    orchestrator's candidate loop drops it by name and the round continues. `n` at
    the round's first budget gate still stops the run. `remembered` is True when
    the answer is read back from `DECLINED_KEY` rather than given at a card
    just now: the candidate was dropped when it was given, and nothing is asked.
    """

    def __init__(self, candidate: str | None, note: str, *, remembered: bool = False):
        super().__init__(
            f"candidate {candidate!r}: estimation budget declined "
            + (
                f"earlier this round (`{DECLINED_KEY}` in its record) — not asked again"
                if remembered
                else "at the re-asked gate"
            )
            + (f" ({note})" if note else "")
        )
        self.candidate = candidate
        self.note = note
        self.remembered = remembered


def remembered_decline(work) -> dict | None:
    """The recorded `n` at this candidate's re-asked budget gate, or None.

    The record is the decision: an unreadable body loses its note and reasons,
    not the answer. `work` is the fitted problem's group (`ctx.work`)."""
    node = work / DECLINED_KEY
    if not node.exists():
        return None
    try:
        rec = node.get(None)
    except Exception:
        rec = {}
    return rec if isinstance(rec, dict) else {}


def reuse_verdict(
    profile: dict, reference: dict | None, max_ratio: float
) -> tuple[bool, list[str]]:
    """May this candidate reuse the round's budget approval? (ok, reasons).

    Refused when a probe objective is non-finite (the candidate may not be
    fittable) or its median start time differs from the approved candidate's by
    more than `max_ratio` either way; without a reference only the first check runs.
    """
    reasons: list[str] = []
    fvals = [float(v) for v in (profile.get("probe_fvals") or [])]
    bad = [v for v in fvals if not math.isfinite(v)]
    if fvals and bad:
        reasons.append(
            f"{len(bad)} of {len(fvals)} probe starts returned a non-finite "
            f"objective ({', '.join(str(v) for v in fvals)}) — this candidate "
            f"may not be fittable at all, and every full start would die the "
            f"same way"
        )
    ref_median = (reference or {}).get("median_start_s")
    mine = profile.get("median_start_s")
    if ref_median and mine is not None and float(ref_median) > 0:
        ratio = float(mine) / float(ref_median)
        if ratio > max_ratio or (ratio > 0 and ratio < 1.0 / max_ratio):
            reasons.append(
                f"median start {float(mine):.3g}s against {float(ref_median):.3g}s "
                f"for the approved candidate {reference.get('candidate')!r} "
                f"({ratio:.2g}x; the declared ceiling is {max_ratio:g}x either "
                f"way) — the projection the approval was based on does not "
                f"describe this candidate"
            )
    return (not reasons), reasons


def _record_convergence_predeclaration(ctx, note: str) -> str | None:
    """Record `convergence: accept <why>` given at the budget gate; the reason or None.

    Declared per round (`ctx.cache`, and a ledger row a restarted process reads
    back); `_record_accept` then writes one ledger row per candidate as each fit
    reaches the convergence gate. A reason of two words or more is required.
    """
    m = re.search(r"\bconvergence\s*[:=]\s*accept\b[:\s]*(.*)", str(note or ""), re.I)
    if not m:
        return None
    why = m.group(1).strip()
    if len(why.split()) < 2:
        print(
            "  ⚑ `convergence: accept` needs a reason (two words or more) — "
            "ignored, the convergence gate will ask normally"
        )
        ctx.ledger.append(
            "note",
            module="cost_boundary_estimation",
            round_idx=ctx.round_idx,
            note="convergence pre-declaration REFUSED: no reason given",
        )
        return None
    ctx.cache["_convergence_predeclared"] = why
    ctx.ledger.append(
        "note",
        module="cost_boundary_estimation",
        round_idx=ctx.round_idx,
        # what a restarted process reads back (estimation.predeclared_from_ledger);
        # the cache above is only the in-process copy
        predeclared_reason=why[:300],
        note=(
            f"human PRE-declared `convergence: accept` for this round at the "
            f"budget gate: {why[:300]}. The estimation_convergence gate will not pause "
            f"for a plateau or gradient-norm failure; integration failures "
            f"still ask. Every affected candidate gets its own ledger row and "
            f"the report caveat."
        ),
        convergence_predeclared=True,
        scope="round",
    )
    print("  convergence pre-declared for this round — s6 will not pause on a plateau")
    return why


def _solver_note_forms(tol_check: dict, sensi: dict) -> list[str]:
    """The solver note forms this model's own measurement makes available."""
    forms = []
    if tol_check.get("proposal"):
        p = tol_check["proposal"]
        forms.append(
            f"tighten      fit every candidate of this round with the proposed "
            f"tolerances (atol {p['atol']:.1e}, rtol {p['rtol']:.1e}) — the "
            f"declared ones do not reproduce the trajectory"
        )
    if sensi.get("proposed_sensi_method") == "adjoint":
        from octomod.workflow_modules.cost_probe.solver_probe import ADJOINT_CONSEQUENCE

        forms.append(
            "adjoint      switch this round's fits to adjoint sensitivities "
            "(removes per-residual sres; the FIM screen falls back to finite "
            f"differences and says so). {ADJOINT_CONSEQUENCE}"
        )
    return forms


SOLVER_WORDS = ("tighten", "adjoint")


def read_budget_note(note, tol_check: dict, sensi: dict, lo: int, hi: int):
    """What the budget gate takes from its note — the one reader, by the
    `gate_note` rules. `tighten` / `adjoint` count only as words on their own
    (or `solver: adjoint`), and only when the probe measured a reason to offer
    them; `n=` only as a whole token."""
    r = gate_note.Reading()
    n = gate_note.key_int(note, "n")
    if n is not None:
        r.read["n"] = int(np.clip(n, lo, hi))
        if r.read["n"] != n:
            r.unread[f"n={n}"] = f"outside {lo}-{hi}, so {r.read['n']}"
    offered = {
        "tighten": bool(tol_check.get("proposal")),
        "adjoint": sensi.get("proposed_sensi_method") == "adjoint",
    }
    words = gate_note.standalone(note, SOLVER_WORDS)
    named = gate_note.key_value(note, "solver") or ""
    words |= {w for w in SOLVER_WORDS if w in named.lower().split()}
    for w in sorted(words):
        if offered[w]:
            r.read[w] = True
        else:
            r.unread[w] = (
                "not offered: the two tolerances agree"
                if w == "tighten"
                else "not offered: the probe did not propose adjoint"
            )
    r.unread.update(gate_note.unread_in_prose(note, SOLVER_WORDS, words))
    m = re.search(r"\bconvergence\s*[:=]\s*accept\b[:\s]*(.*)", str(note or ""), re.I)
    if m:
        r.read["convergence"] = f"accept {m.group(1).strip()}".strip()
    return r


def _apply_gate_choices(
    ctx, reading, tol_check, sensi, profile, *, for_round: bool
) -> dict:
    """Record `tighten` / `adjoint` if the human chose them; return the choice ({}).

    Written to `estimation_settings` for the round, or for this candidate at a
    re-asked gate, so every problem built afterwards gets it, across a restart
    too; the profile and the ledger record what the solver actually holds.
    """
    from octomod.workflow_modules.estimation import solver_settings as _ss

    chosen: dict = {}
    if reading.read.get("tighten"):
        chosen.update(tol_check["proposal"])
    if reading.read.get("adjoint"):
        chosen["sensi_method"] = "adjoint"
    if not chosen:
        return {}
    estimation_settings.record_gate_choice(
        ctx, chosen, for_round=for_round, note=reading.line()
    )
    problem, _, _ = estimation_settings.build(ctx)
    objective = getattr(problem, "objective", None)
    held = (
        _ss.read_back(
            getattr(objective, "amici_solver", None),
            getattr(objective, "amici_model", None),
        )
        if getattr(objective, "amici_solver", None) is not None
        else {}
    )
    applied = {k: held.get(k) for k in chosen}
    scope = (
        "every candidate of this round" if for_round else f"candidate {ctx.candidate!r}"
    )
    profile["gate_overrides"] = {
        "requested": chosen,
        "applied": applied,
        "scope": scope,
    }
    _write_cost_profile(ctx.work, profile)
    ctx.ledger.append(
        "note",
        module="cost_boundary_estimation",
        round_idx=ctx.round_idx,
        note=(
            f"human chose solver settings at the cost gate: {chosen} — "
            f"{scope} is built with them ({estimation_settings.ROUND_KEY}), "
            f"not with the spec's declared values, and they survive a restart"
        ),
        solver_settings=applied,
        solver_requested=chosen,
        scope="round" if for_round else "candidate",
    )
    return chosen


def _reprobe_after_override(
    ctx, problem, profile: dict, n_probe: int, seed: int, n_approved: int
) -> float:
    """Re-measure the start cost after a solver override, and re-project.

    `adjoint` changes what a start costs (no FIM Hessian, Fides runs BFGS), so the
    approved projection does not describe the fit that runs. The profile keeps both
    numbers and the new projection is printed and ledgered. Returns the new median.
    """
    from octomod.workflow_modules.estimation.problem import make_engine

    forward_median = float(profile.get("median_start_s") or 0.0)
    print(f"  re-probing {n_probe} starts with the chosen solver settings ...")
    # the forward probe's start cost settles whether to dispatch at once
    probe, engine_rec, median = _run_probe(
        ctx, problem, n_probe, seed, known_start_s=forward_median or None
    )
    wall = float(engine_rec["wall_s"])
    engine = make_engine(ctx.spec, median)
    n_par = int(getattr(engine, "n_procs", 1) or 1)
    projected = median * n_approved / max(1, min(n_par, n_approved))
    profile["forward_median_start_s"] = forward_median
    profile["adjoint_probe"] = {
        "median_start_s": round(median, 3),
        "probe_wall_s": round(wall, 2),
        "probe_engine": engine_rec,
        "probe_fvals": sorted(
            float(o.fval) if o.fval is not None else float("inf")
            for o in probe.optimize_result.list
        ),
        "projected_wall_s": round(projected, 1),
        "n_starts": int(n_approved),
        "slowdown_vs_forward": (
            round(median / forward_median, 2) if forward_median > 0 else None
        ),
    }
    profile["median_start_s"] = round(median, 3)
    profile["projected_wall_s"] = round(projected, 1)
    _write_cost_profile(ctx.work, profile)
    line = (
        f"adjoint re-probe: median start {median:.2f}s (forward was "
        f"{forward_median:.2f}s"
        + (f", {median / forward_median:.1f}x" if forward_median > 0 else "")
        + f") -> {n_approved} starts projected at ~{projected:.0f}s wall. The "
        f"forward-mode projection is NOT what this fit will cost: Fides runs "
        f"BFGS without the FIM Hessian."
    )
    print(f"  {line}")
    ctx.ledger.append(
        "note",
        module="cost_boundary_estimation",
        round_idx=ctx.round_idx,
        candidate=ctx.candidate,
        note=line,
        adjoint_reprobe=dict(profile["adjoint_probe"]),
    )
    return median


def _tolerance_lines(check: dict) -> list[str]:
    if not check.get("available"):
        return [f"integrator convergence: NOT CHECKED — {check.get('why', '?')}"]
    d = check["declared"]
    head = (
        f"integrator convergence: atol {d['atol']:.0e} / rtol {d['rtol']:.0e}, "
        f"vs {check['tighten_factor']:g}x tighter -> worst relative "
        f"trajectory difference {check['worst_rel_diff']:.2e} "
        f"(limit {check['threshold']:.0e})"
    )
    if check["agrees"]:
        return [head + "  OK"]
    return [
        head + "  ** THE DECLARED TOLERANCE IS WRONG FOR THIS MODEL **",
        f"    worst at {check['worst_at']}; proposed instead: "
        f"atol {check['proposal']['atol']:.1e}, rtol {check['proposal']['rtol']:.1e} "
        f"(answer `tighten` to use it)",
    ]


def _sensitivity_lines(s: dict) -> list[str]:
    if not s.get("available"):
        return [f"sensitivities: NOT MEASURED — {s.get('residual_error', '?')}"]
    if s.get("sensi_error"):
        return [
            f"sensitivities: THE GRADIENT DOES NOT INTEGRATE — {s['sensi_error']}",
            "    the residual is fine; the fit would reach S6 and die there",
        ]
    out = [
        f"sensitivities: residual {s['residual_s'] * 1e3:.1f} ms, "
        f"residual+gradient {s['sensi_s'] * 1e3:.1f} ms "
        f"(ratio {s['ratio']}x over {s['n_estimated']} estimated parameters)"
    ]
    if not s.get("gradient_computable"):
        out.append(f"    ** gradient not usable: {s.get('gradient_note')} **")
    if s.get("proposed_sensi_method") == "adjoint":
        out.append(f"    PROPOSED: switch to adjoint — {s['why']}")
    return out


def _steady_state_lines(ss: dict) -> list[str]:
    if not ss.get("available"):
        return []
    out: list[str] = []
    if ss.get("used"):
        out += _equilibration_lines(
            [r for r in ss["per_condition"] if r["ran"]],
            "pre-equilibration",
            # S3's roadrunner screen passed these, and the compiled model is the
            # one the fit runs on
            "the S3 screen passed them, AMICI is the one the fit runs on",
        )
    if ss.get("posteq_used"):
        # the steady state a `time = inf` row is read at: a condition that does
        # not settle has no value to compare that row against
        out += _equilibration_lines(
            [
                {
                    **r["posteq"],
                    "condition": r.get("condition"),
                    "condition_index": r.get("condition_index"),
                }
                for r in ss["per_condition"]
                if (r.get("posteq") or {}).get("ran")
            ],
            "post-equilibration (steady-state measurements, time inf)",
            "their time inf rows have no steady state to be compared against",
        )
    return out  # empty for a problem that does neither


def _equilibration_lines(rows: list[dict], what: str, consequence: str) -> list[str]:
    """The card lines for one kind of AMICI steady-state computation: how many
    conditions ran it, the worst weighted residual and the time, and any
    condition AMICI did not settle."""
    worst_row = max(rows, key=lambda r: r["wrms"] or 0.0) if rows else None
    worst = (worst_row["wrms"] or 0.0) if worst_row else 0.0
    where = (
        f" ({worst_row['condition']})"
        if worst_row and worst_row.get("condition")
        else ""
    )
    out = [
        f"{what}: ran for {len(rows)} condition(s), worst "
        f"steady-state wrms {worst:.2e}{where} (AMICI calls it settled below "
        f"1), {sum(r['cpu_time_s'] for r in rows):.2f}s total"
    ]
    # a negative status is AMICI's failure code for one of its three attempts
    # (Newton, simulation, Newton again); one success (1) settles the condition
    failed = [
        r for r in rows if any(f < 0 for f in r["status"]) and 1 not in r["status"]
    ]
    if failed:
        names = ", ".join(
            str(r.get("condition") or r["condition_index"]) for r in failed
        )
        out.append(
            f"    ** AMICI did not settle {len(failed)} {what.split(' (')[0]}(s): "
            f"{names} (status {failed[0]['status']}); {consequence} **"
        )
    return out


def _hessian_lines(ctx, problem, petab_problem) -> list[str]:
    """The card line (and ledger row) saying this candidate's Hessian is BFGS, and why.

    Nothing is decided here: `build_problem` made the switch from the problem's own
    observable table.
    """
    non_gaussian = non_gaussian_observables(petab_problem.observable_df)
    if not non_gaussian:
        return []
    line = (
        f"Hessian: observable(s) {non_gaussian} declare a non-Gaussian "
        f"likelihood, for which AMICI computes no Fisher information -> the "
        f"FIM Hessian is OFF for this candidate and Fides uses a BFGS update. "
        f"Correct, but starts run several times slower than a Gaussian twin's; "
        f"the probe times below already include that."
    )
    ctx.ledger.append(
        "note",
        module="cost_boundary_estimation",
        round_idx=ctx.round_idx,
        candidate=ctx.candidate,
        note=(
            f"non-Gaussian noise on {non_gaussian} -> fim_for_hess=False "
            f"(BFGS Hessian in Fides); expect slower starts"
        ),
        fim_for_hess=bool(uses_fim_hessian(problem)),
        non_gaussian_observables=non_gaussian,
    )
    print(f"  {line}")
    return [line]


def _declared_settings(spec, problem) -> dict:
    """The declared solver settings beside what the solver actually holds, read back."""
    from octomod.workflow_modules.estimation import solver_settings as _ss

    objective = getattr(problem, "objective", None)
    solver = getattr(objective, "amici_solver", None)
    if solver is None:
        return {"available": False}
    return {
        "available": True,
        "declared": _ss.flatten_spec(spec),
        "read_back": _ss.read_back(solver, getattr(objective, "amici_model", None)),
    }


def proposed_n_starts(ctx: RunContext) -> int:
    """The start count the budget gate proposes (the human may answer `n=`)."""
    n_default = int(
        ctx.cache.get("n_starts_override")
        or ctx.spec.require("estimation.n_starts_default")
    )
    lo, hi = ctx.spec.require("estimation.n_starts_bounds")
    return int(np.clip(n_default, lo, hi))


def fit_already_on_disk(ctx: RunContext, n_starts: int) -> dict | None:
    """This candidate's fit of at least `n_starts` starts, if already in the
    record, or None.

    Asked before a round is priced, so the budget card can say which candidates
    cost nothing. A record-level look first; only a problem the run fitted before
    is built for the exact check.
    """
    from octomod.orchestration import reuse
    from octomod.workflow_modules.estimation.problem import problem_content_hash

    with timing.span("compute", "fit_lookup"):
        try:
            problem_hash = problem_content_hash(petab_io.from_work(ctx.work, ctx.model))
        except Exception:  # no assembled problem in the record yet
            return None
        if not reuse.fits_of_problem(ctx.root, problem_hash):
            return None
        try:
            problem, _, _ = estimation_settings.build(ctx)
            src, key, _ = reuse.fit_in_record(ctx, problem, n_starts)
        except Exception:  # a candidate that cannot be built is not reusable
            return None
        if src is None:
            return None
        stored = reuse.stored_fit(src)
        return {
            "from": ("this candidate's own group" if src == ctx.work else src.key),
            "src": src,
            "key": key,
            "n_starts": int(stored.get("n_starts") or n_starts),
            "best_fval": stored.get("best_fval"),
        }


def _reuse_instead_of_probing(ctx: RunContext, carried: dict, n_approved: int) -> int:
    """The cost module for a candidate whose fit is already in the record: no
    probe, no gate.

    The `cost` record is still written (the compiled slot requires one), with
    the reused fit's measured numbers and a note saying so.
    """
    src = carried["src"]
    source = {}
    try:
        source = (src / "cost").get({}) or {}
    except Exception:  # an unreadable source profile is an empty one
        source = {}
    if not isinstance(source, dict):
        source = {}
    profile = {k: v for k, v in source.items() if k != "gate_overrides"}
    profile.setdefault("median_start_s", None)
    profile.setdefault("compile_s", None)
    profile["reused_fit"] = {
        "from": carried["from"],
        "fit_key": carried["key"],
        "n_starts": carried["n_starts"],
        "source_gate_overrides": source.get("gate_overrides"),
        "note": (
            "no probe ran for this candidate: its fit is already in the record, "
            "and the numbers in this record are the measured ones of that fit"
        ),
    }
    _write_cost_profile(ctx.work, profile)
    line = (
        f"candidate {ctx.candidate!r}: its fit is already in the record "
        f"({carried['from']}, {carried['n_starts']} starts) — not probed, "
        f"not budgeted; S6 reuses it"
    )
    print(f"  {line}")
    ctx.ledger.append(
        "note",
        module="cost_boundary_estimation",
        round_idx=ctx.round_idx,
        candidate=ctx.candidate,
        note=line,
        fit_on_disk=True,
        reused_from=carried["from"],
    )
    ctx.set_marker(
        "cost",
        approved_n_starts=n_approved,
        median_start_s=profile.get("median_start_s"),
        reused_fit=carried["from"],
    )
    return n_approved


def _probe_hit_rate(probe_result, alpha: float) -> tuple[float, str]:
    """The default optimiser's per-start success rate, from the probe's own starts.

    It cannot detect a default that converges reliably to the same wrong basin
    (that scores 100%); `select_when: always` covers such a problem. A rate, not
    "any start disagreed": one outlier start is the multistart working.
    """
    from octomod.workflow_modules.estimation.optimizer_compare import success_threshold

    starts = probe_result.optimize_result.list
    vals = [float(o.fval) for o in starts if o.fval is not None and np.isfinite(o.fval)]
    if not vals or not starts:
        return 0.0, "no probe start produced a finite objective"
    thr = success_threshold(alpha)
    best = min(vals)
    hits = sum(1 for v in vals if v - best <= thr)
    rate = hits / len(starts)
    return rate, (
        f"the default reached its best on {hits} of {len(starts)} probe starts "
        f"({rate:.0%}, within {thr:.3g})"
    )


def _maybe_select_optimizer(
    ctx,
    problem,
    seed: int,
    median_start_s: float,
    probe_result=None,
    n_estimation_starts: int = 0,
):
    """Run the optimiser comparison and write the run's selection, or return None.

    None when the spec names an optimiser, the comparison is off or not triggered,
    or it does not fit the budget; the run then uses the default. Its starts come
    from `max_budget_fraction` of the estimation and the measured per-start time.
    """
    from octomod.workflow_modules.estimation import optimizer_compare as _oc
    from octomod.workflow_modules.estimation import problem as _est

    requested = str(ctx.spec.get("estimation.optimizer", "auto"))
    if requested != "auto":
        print(f"  optimiser: {requested} (explicitly set in the workflow spec)")
        return None
    if not bool(ctx.spec.get("estimation.optimizer_compare.enabled", True)):
        return None

    alpha = float(ctx.spec.get("estimation.optimizer_compare.success_alpha", 0.05))

    # the trigger costs nothing: the probe already measured how often the default
    # reaches its own optimum
    when = str(ctx.spec.get("estimation.optimizer_compare.select_when", "never"))
    if when == "never":
        return None
    if when == "probe_rate_low" and probe_result is not None:
        floor = float(
            ctx.spec.get("estimation.optimizer_compare.select_probe_rate_below", 0.5)
        )
        rate, why = _probe_hit_rate(probe_result, alpha)
        if rate >= floor:
            print(
                f"  optimiser: {_oc.DEFAULT_OPTIMIZER} — {why}, "
                f"at or above {floor:.0%}"
            )
            ctx.ledger.append(
                "note",
                module="cost_probe",
                round_idx=ctx.round_idx,
                note=f"optimiser comparison not run: {why}, at or above {floor:.0%}",
            )
            return None
        print(
            f"  optimiser choice: the default is struggling here: {why}, below {floor:.0%}"
        )

    cands = list(ctx.spec.get("estimation.optimizer_compare.candidates") or [])
    # the default ran in the probe already: only the other candidates run, and
    # the probe's result becomes the incumbent's row
    others = [c for c in cands if c != _oc.DEFAULT_OPTIMIZER]
    plan = _oc.plan(
        len(others),
        n_estimation_starts,
        median_start_s,
        fraction=float(
            ctx.spec.get("estimation.optimizer_compare.max_budget_fraction", 0.35)
        ),
        min_starts=int(
            ctx.spec.get("estimation.optimizer_compare.min_compare_starts", 3)
        ),
    )
    if plan is None:
        why = (
            f"a comparison worth running does not fit the budget for a "
            f"{n_estimation_starts}-start estimation"
        )
        print(f"  optimiser: {_oc.DEFAULT_OPTIMIZER} — {why}")
        ctx.ledger.append(
            "note",
            module="cost_probe",
            round_idx=ctx.round_idx,
            note=f"optimiser comparison not run: {why}",
        )
        return None
    n_sel = plan["n_starts"]
    print(
        f"  choosing an optimiser: {len(others)} candidate(s) x {n_sel} "
        f"starts, projected {plan['projected_s']:.0f}s of a "
        f"{plan['budget_s']:.0f}s budget (the incumbent's row is reused from "
        f"the probe)"
    )
    with timing.span("compute", "optimizer_comparison"):
        rows = _oc.compare(
            problem,
            methods=others,
            n_starts=n_sel,
            seed=seed,
            alpha=alpha,
            # the projection is a guess; this is the bound that actually holds
            budget_s=plan["stop_s"],
        )
    n_probe_starts = len(probe_result.optimize_result.list)
    rows.insert(
        0,
        _oc.row_from_probe(
            probe_result, wall_s=median_start_s * max(n_probe_starts, 1)
        ),
    )
    rows = _oc.score(rows, alpha=alpha)
    sel = _oc.select(
        rows,
        min_success_gain=float(
            ctx.spec.get("estimation.optimizer_compare.select_min_success_gain", 0.25)
        ),
        alpha=alpha,
    )
    # the chosen optimiser's own per-start cost, as the comparison measured it:
    # the probe timed only the default
    chosen = next((r for r in rows if r.name == sel["selected"]), None)
    if chosen is not None and chosen.n_attempted:
        sel["start_s"] = float(chosen.wall_s / chosen.n_attempted)
        sel["start_s_vs_default"] = (
            float(sel["start_s"] / median_start_s) if median_start_s else None
        )
    # the table stars the selected optimiser: its legend calls it the one used
    payload_json = _oc.as_json(rows, incumbent=sel["selected"], alpha=alpha)
    payload_json["selection"] = sel
    # Two siblings of `cost` in the fitted problem's group: the
    # comparison and the selection, each with this one writer at probe time
    # (the convergence gate's `compare` rewrites both, later, in S6).
    (ctx.work / "optimizer_comparison").put(payload_json)
    (ctx.work / _est.SELECTION_KEY).put(sel)
    for line in _oc.table_lines(rows, incumbent=sel["selected"]):
        print("  " + line)
    print(f"  -> optimiser for this run: {sel['selected']}")
    ctx.ledger.append(
        "note",
        module="cost_probe",
        round_idx=ctx.round_idx,
        note=f"optimiser selected: {sel['selected']} — {sel['reason']}",
        optimizer_selection=sel,
    )
    return sel


def measured_start_s(ctx: RunContext) -> float | None:
    """What the probe measured a single start to cost, or None when no probe ran.

    Read back from this module's `cost` record, so the modules after it size
    their engines and comparisons from a measurement rather than from a guess
    about the model's size. A malformed record is a missing probe, not a crash.
    """
    prof = ctx.work / "cost"
    if not prof.exists():
        return None
    try:
        return float(prof.get()["median_start_s"])
    except Exception:
        return None


def projection_start_s(
    selection: dict | None, probe_median_s: float
) -> tuple[float, str]:
    """Per-start cost for the projections, and a card line naming its source.

    The probe times the default optimiser; when the comparison switched to
    another, that one's measured per-start time is used. Returns the probe's
    number and "" when nothing switched.
    """
    if not selection or not selection.get("start_s"):
        return probe_median_s, ""
    if selection.get("selected") == selection.get("default"):
        return probe_median_s, ""
    start_s = float(selection["start_s"])
    ratio = selection.get("start_s_vs_default")
    return start_s, (
        f"a start with {selection['selected']} costs {start_s:.2f}s, measured "
        f"over the comparison's own starts"
        + (f" ({ratio:.1f}x the default's)" if ratio else "")
        + " — the projections below use it, not the probe's"
    )


def _solver_message_lines(rec: dict | None) -> list[str]:
    from octomod.workflow_modules.cost_probe import solver_messages as _msgs

    return _msgs.card_lines(rec)


def _probe_key(ctx: RunContext, inp, problem, seed: int, n_probe: int) -> str:
    """Fingerprint of what the budget card's measurements depend on.

    The problem's content, the settings the solver holds, the optimiser the probe
    runs (the spec's word) and its overrides, the seed and the probe size; a
    change to any of them measures again.
    """
    from octomod.orchestration.ledger import sha256_text
    from octomod.workflow_modules.estimation import solver_settings as _ss
    from octomod.workflow_modules.estimation.problem import problem_content_hash

    objective = getattr(problem, "objective", None)
    solver = getattr(objective, "amici_solver", None)
    parts = {
        "problem": problem_content_hash(inp),
        "solver": (
            _ss.read_back(solver, getattr(objective, "amici_model", None))
            if solver is not None
            else {}
        ),
        "optimizer": str(ctx.spec.get("estimation.optimizer", "auto")),
        "optimizer_overrides": estimation_settings.optimizer_overrides(ctx) or {},
        "seed": int(seed),
        "n_probe": int(n_probe),
    }
    return sha256_text(json.dumps(parts, sort_keys=True, default=str))


def _run_probe(ctx, problem, n_probe: int, seed: int, capture=None, known_start_s=None):
    """Run the probe's starts; return (result, engine record, median start).

    The median is SERIAL-EQUIVALENT (`start_engine.py`): each start's wall
    when it ran alone, its CPU when others ran beside it, so it compares with
    a serially timed number whichever way the probe ran. The record carries
    the probe's own wall and CPU and whether dispatching paid (`speedup`).
    """
    from octomod.workflow_modules.estimation.problem import make_probe_engine

    engine = make_probe_engine(
        ctx.spec, seed, capture=capture, known_start_s=known_start_s
    )
    t0 = time.perf_counter()
    result = run_multistart(
        problem, n_probe, seed, ctx.spec, purpose="cost_probe", engine=engine
    )
    wall = time.perf_counter() - t0
    rec = _probe_engine_record(engine, result, wall)
    times = [s["start_s"] for s in rec["starts"]]
    median = float(np.median(times)) if times else wall / max(n_probe, 1)
    if rec["kind"] == "parallel" or rec.get("fallback"):
        for line in _probe_timing_lines(rec, median, n_probe)[1:]:
            print(f"  {line}")
    return result, rec, median


def _probe_engine_record(engine, result, wall_s: float) -> dict:
    """What the probe's engine recorded, or — when the starts ran without it
    timing them (a stand-in multistart) — the optimiser's own clock, serial."""
    from octomod.workflow_modules.estimation.start_engine import serial_summary

    rec = engine.summary() if hasattr(engine, "summary") else None
    if rec and rec["n_starts"]:
        return rec
    starts = list(getattr(getattr(result, "optimize_result", None), "list", []) or [])
    out = serial_summary(len(starts), decided="timed by the optimiser's own clock")
    out["starts"] = [
        {
            "id": str(getattr(o, "id", k)),
            "where": "here",
            "alone": True,
            "wall_s": float(o.time),
            "cpu_s": None,
            "start_s": float(o.time),
            "finite": o.fval is not None and bool(np.isfinite(float(o.fval))),
        }
        for k, o in enumerate(starts)
        if getattr(o, "time", None) is not None
    ]
    out["wall_s"] = round(float(wall_s), 3)
    out["cpu_s"] = None
    out["serial_equivalent_s"] = round(sum(s["start_s"] for s in out["starts"]), 3)
    return out


def _speedup_words(speedup) -> str:
    if not speedup:
        return ""
    if speedup >= 1:
        return f": {speedup:.1f}x faster dispatched than one at a time"
    return (
        f": {1 / speedup:.1f}x SLOWER dispatched than one at a time — the pool's "
        f"start-up outweighed the work"
    )


def _saved_probe_engine(ctx, saved: dict, n_probe: int) -> dict:
    """The engine record of a saved probe; for one saved before probes
    recorded it, what that version ran, read from `estimation.engine`."""
    from octomod.workflow_modules.estimation.problem import engine_kind, resolve_n_procs
    from octomod.workflow_modules.estimation.start_engine import serial_summary

    rec = saved.get("probe_engine")
    if isinstance(rec, dict) and "decided" in rec:
        return rec
    out = serial_summary(
        n_probe,
        decided="saved before the probe recorded its engine; read from "
        "estimation.engine",
    )
    out["wall_s"] = saved.get("probe_wall_s")
    out["cpu_s"] = out["serial_equivalent_s"] = None
    if engine_kind(ctx.spec) == "parallel":
        # that version dispatched every start, and timed each by its wall
        out.update(
            kind="parallel",
            mode="parallel",
            n_here=0,
            n_dispatched=n_probe,
            n_workers=min(resolve_n_procs(ctx.spec), n_probe),
            median_is="concurrent wall (no per-start CPU was recorded)",
        )
    return out


def _probe_timing_lines(rec: dict, median_s: float, n_probe: int) -> list[str]:
    """The budget card's lines on what a start costs and how the probe ran."""
    if rec.get("kind") != "parallel":
        lines = [
            f"median wall per optimisation start ({n_probe} probes, run one at "
            f"a time): {median_s:.2f}s"
        ]
    elif rec.get("median_is"):
        lines = [
            f"median wall per optimisation start ({n_probe} probes, dispatched "
            f"to {rec['n_workers']} workers; saved before per-start CPU was "
            f"recorded): {median_s:.2f}s — a wall measured beside other "
            f"starts, which can overstate what one start costs"
        ]
    else:
        lines = [
            f"median per optimisation start ({n_probe} probes: {rec['n_here']} "
            f"here, {rec['n_dispatched']} dispatched to {rec['n_workers']} "
            f"workers): {median_s:.2f}s, as one start costs by itself (its "
            f"wall when it ran alone, its CPU when others ran beside it)",
            f"probe wall {rec['wall_s']:.1f}s for {rec['serial_equivalent_s']:.1f}s "
            f"of one-at-a-time work{_speedup_words(rec.get('speedup'))}; CPU "
            f"{rec['cpu_s']:.1f}s in the starts"
            + (
                f", {rec['process_cpu_s']:.1f}s in all processes (the rest is "
                f"pool start-up)"
                if rec.get("process_cpu_s")
                else ""
            )
            + f" — {rec['decided']}",
        ]
    if rec.get("fallback"):
        lines.append(f"⚑ {rec['fallback']}")
    return lines


def _read_probe_record(work, key: str) -> dict | None:
    """The saved probe measurements, when they were taken for exactly `key`."""
    node = work / PROBE_RECORD
    if not node.exists():
        return None
    try:
        rec = node.get(None)
    except Exception:  # an unreadable record is no record: measure again
        return None
    return rec if isinstance(rec, dict) and rec.get("key") == key else None


@timing.phase("cost_probe")
def run(
    ctx: RunContext,
    ask_human: bool = True,
    n_candidates: int = 1,
    preapproved_n: int | None = None,
    carried_lines: list[str] | None = None,
) -> int:
    """Measure the cost and ask the budget gate; return the approved start count.

    In mechanism discrimination the first candidate measures and asks (projected
    x n_candidates); the rest reuse the approval when their own probe matches,
    else the gate is re-asked for them. A candidate whose fit is already in the
    record is not probed; `carried_lines` name those candidates on the first card.
    """
    ctx.require_marker("s3", needed_by="cost_profile")

    declined = remembered_decline(ctx.work)
    if declined is not None:
        # the human declined this candidate's budget at its re-asked card
        # earlier this round: nothing is compiled, probed or asked for a
        # candidate that is not fitted (a re-entry at estimation asks again)
        raise BudgetDeclinedForCandidate(
            ctx.candidate, str(declined.get("note") or ""), remembered=True
        )

    if ctx.marker("cost").exists():
        rec = ctx.marker("cost").get()
        # on a resume the reference candidate (whose probe was approved) seeds
        # the comparison later candidates are held to
        if rec.get("budget_reference") and ctx.cache.get("_budget_reference") is None:
            ctx.cache["_budget_reference"] = {
                "candidate": ctx.candidate,
                "median_start_s": rec.get("median_start_s"),
                "n_starts": int(rec["approved_n_starts"]),
            }
        return int(rec["approved_n_starts"])

    inp = petab_io.from_work(ctx.work, ctx.model)

    print("  compiling AMICI model (cached by content hash) ...")
    problem, petab_problem, compile_s = estimation_settings.build(ctx)
    if preapproved_n is not None and not ask_human:
        # the approval is known: a fit already in the record for it is neither
        # probed nor budgeted
        carried = fit_already_on_disk(ctx, int(preapproved_n))
        if carried is not None:
            return _reuse_instead_of_probing(ctx, carried, int(preapproved_n))
    hessian_lines = _hessian_lines(ctx, problem, petab_problem)

    n_probe = int(ctx.spec.get("estimation.n_probe_starts", 5))
    if n_probe < 1:
        raise ValueError(
            f"estimation.n_probe_starts must be at least 1 (a start is what the "
            f"probe measures); the workflow spec has {n_probe}"
        )
    seed = int(ctx.spec.require("estimation.seed"))
    lo, hi = ctx.spec.require("estimation.n_starts_bounds")
    n_proposed = proposed_n_starts(ctx)
    from octomod.workflow_modules.evaluation import structural_nulls as _sn

    struct_node = _sn.node(ctx.work)

    # In file-gate mode the card is answered on the next invocation, which
    # re-enters here: measurements saved under a matching fingerprint are reused.
    probe_key = _probe_key(ctx, inp, problem, seed, n_probe)
    saved = _read_probe_record(ctx.work, probe_key)
    if saved is not None:
        fval0, obj_eval_s, n_cond = saved["fval0"], saved["obj_eval_s"], saved["n_cond"]
        tol_check, sensi, steady = saved["tol_check"], saved["sensi"], saved["steady"]
        struct = saved["struct"]
        struct_node.put(struct)
        probe_fvals, probe_wall_s = saved["probe_fvals"], saved["probe_wall_s"]
        median_start_s = saved["median_start_s"]
        selection = saved.get("selection")
        # a record saved before messages were read has none; the card then
        # shows the objective values alone, as it did
        solver_msgs = saved.get("solver_messages")
        probe_engine_rec = _saved_probe_engine(ctx, saved, n_probe)
        print(
            f"  probe: the measurements behind the card you answered are in the "
            f"record (fingerprint {probe_key[:16]}) — reused, nothing re-measured"
        )
        ctx.ledger.append(
            "note",
            module="cost_boundary_estimation",
            round_idx=ctx.round_idx,
            candidate=ctx.candidate,
            note=f"probe measurements reused from {(ctx.work / PROBE_RECORD).key} "
            "(same problem, solver, optimiser, seed and probe size); nothing "
            "re-measured",
            probe_reused=True,
            probe_key=probe_key,
        )
    else:
        # single objective evaluation ~ simulation cost of all conditions once
        rng = np.random.default_rng(int(ctx.spec.require("estimation.seed")))
        x0 = problem.lb + rng.random(len(problem.lb)) * (problem.ub - problem.lb)
        t0 = time.perf_counter()
        fval0 = float(problem.objective(x0))
        obj_eval_s = time.perf_counter() - t0
        n_cond = len(inp.conditions)

        # the solver checks run here: the first time AMICI touches the model, at a
        # gate that shows measured numbers before anyone pays
        from octomod.workflow_modules.cost_probe import solver_probe as _sp

        x_free = (
            x0[problem.x_free_indices] if len(x0) != len(problem.x_free_indices) else x0
        )
        print("  checking integrator convergence (two tolerances) ...")
        with timing.span("compute", "solver_probe"):
            tol_check = _sp.tolerance_agreement(problem, ctx.spec, x_free)
            print("  timing sensitivities (residual vs residual+gradient) ...")
            sensi = _sp.sensitivity_probe(problem, x_free, ctx.spec)
        with timing.span("compute", "steady_state"):
            steady = _sp.steady_state_report(problem, x_free)
        # directions no output depends on at any parameter value: an indicator on
        # the card (AIC still charges every estimated parameter), measured near
        # the nominal values, where the model integrates, and re-checked at the fit
        print("  looking for structurally flat directions (near the nominal) ...")
        with timing.span("compute", "structural_nulls"):
            struct = _sn.measure_with_spec(problem, ctx.spec, petab_problem)
        struct_node.put(struct)

        print(f"  probing cost with {n_probe} full optimisation starts ...")
        from octomod.workflow_modules.cost_probe import solver_messages as _msgs

        # what AMICI says while the starts run, counted by kind: a failed start
        # on the card then carries its reason, and nothing about the run changes
        # (the engine hands back what its workers counted)
        with _msgs.Capture() as _captured:
            probe_result, probe_engine_rec, median_start_s = _run_probe(
                ctx, problem, n_probe, seed, capture=_captured
            )
        probe_wall_s = float(probe_engine_rec["wall_s"])
        solver_msgs = _msgs.probe_record(
            problem, probe_result.optimize_result.list, _captured
        )
        ctx.ledger.append(
            "note",
            module="cost_boundary_estimation",
            round_idx=ctx.round_idx,
            candidate=ctx.candidate,
            note=_msgs.ledger_note(solver_msgs),
            solver_messages=solver_msgs,
        )
        probe_fvals = sorted(
            float(o.fval) if o.fval is not None else float("inf")
            for o in probe_result.optimize_result.list
        )

        # The optimiser is chosen here, after n_proposed (the comparison is sized as
        # a fraction of the estimation) and before the projections (a switch
        # changes what a start costs), so its starts are bought at the budget gate.
        selection = _maybe_select_optimizer(
            ctx, problem, seed, median_start_s, probe_result, n_proposed
        )
        (ctx.work / PROBE_RECORD).put(
            {
                "key": probe_key,
                "fval0": fval0,
                "obj_eval_s": obj_eval_s,
                "n_cond": n_cond,
                "tol_check": tol_check,
                "sensi": sensi,
                "steady": steady,
                "struct": struct,
                "probe_fvals": probe_fvals,
                "probe_wall_s": probe_wall_s,
                "median_start_s": median_start_s,
                "selection": selection,
                "solver_messages": solver_msgs,
                "probe_engine": probe_engine_rec,
            }
        )

    # project with the per-start cost of the optimiser that will run
    start_s, switch_line = projection_start_s(selection, median_start_s)

    # the estimation's engine is decided from the median start, so project it
    from octomod.workflow_modules.estimation.problem import engine_reason, make_engine

    engine = make_engine(ctx.spec, start_s)
    n_par = int(getattr(engine, "n_procs", 1) or 1)
    workers = max(1, min(n_par, n_proposed))
    serial_wall_s = start_s * n_proposed
    est_wall_s = serial_wall_s / workers

    def _project(n: int) -> float:
        return start_s * n / max(1, min(n_par, n))

    profile = {
        "compile_s": round(compile_s, 2),
        "objective_eval_s": round(obj_eval_s, 4),
        "sim_s_per_condition": round(obj_eval_s / max(n_cond, 1), 4),
        "objective_at_probe_point": fval0,
        "n_probe_starts": n_probe,
        "probe_wall_s": round(probe_wall_s, 2),
        # how the probe's starts ran: serial, or dispatched after the first
        "probe_engine": probe_engine_rec,
        # the per-start cost the projections used (read by S6, S7, `make_engine`)
        "median_start_s": round(start_s, 3),
        "probe_median_start_s": round(median_start_s, 3),
        "start_s_basis": (
            selection["selected"]
            if selection and start_s != median_start_s
            else "cost probe (default optimiser)"
        ),
        "probe_fvals": probe_fvals,
        "proposed_n_starts": n_proposed,
        "projected_wall_s": round(est_wall_s, 1),
        "projected_serial_wall_s": round(serial_wall_s, 1),
        "engine": type(engine).__name__,
        "n_parallel_workers": workers,
        # the solver settings these numbers were measured under
        "solver_settings": _declared_settings(ctx.spec, problem),
        # AMICI's FIM, or BFGS when an observable's likelihood has no FIM
        "hessian": {
            "fim_for_hess": uses_fim_hessian(problem),
            "non_gaussian_observables": non_gaussian_observables(
                petab_problem.observable_df
            ),
        },
        "tolerance_agreement": tol_check,
        "sensitivity_probe": sensi,
        "steady_state": steady,
        "structural_nulls": struct,
        # AMICI's messages over the probe's starts, counted by kind
        "solver_messages": solver_msgs,
    }
    _write_cost_profile(ctx.work, profile)

    # a later candidate reuses the round's approval only if its own probe looks
    # like the approved one
    reference = ctx.cache.get("_budget_reference")
    reask_lines: list[str] = []
    reasons: list[str] = []
    if preapproved_n is not None and not ask_human:
        max_ratio = float(ctx.spec.require("estimation.probe_reuse_max_ratio"))
        ok, reasons = reuse_verdict(profile, reference, max_ratio)
        if ok:
            ctx.set_marker(
                "cost",
                approved_n_starts=preapproved_n,
                median_start_s=median_start_s,
                reused_approval=True,
            )
            return preapproved_n
        who = (reference or {}).get("candidate")
        reask_lines = [
            f"** THIS CANDIDATE'S PROBE DOES NOT MATCH THE APPROVED ONE — the "
            f"budget approved for candidate {who!r} is NOT reused here; it is "
            f"asked again for candidate {ctx.candidate!r} **",
            *[f"    · {r}" for r in reasons],
        ]
        profile["reuse_refused"] = {"reference": reference, "reasons": reasons}
        _write_cost_profile(ctx.work, profile)
        ctx.ledger.append(
            "note",
            module="cost_boundary_estimation",
            round_idx=ctx.round_idx,
            candidate=ctx.candidate,
            note=(
                f"budget approval NOT reused for candidate {ctx.candidate!r}: "
                + "; ".join(reasons)
            ),
            reuse_refused=True,
            reasons=reasons,
            reference_candidate=who,
        )
        for line in reask_lines:
            print(f"  {line}")
        # the re-asked card proposes the count the round already approved,
        # projected from THIS candidate's own probe — not the spec default
        n_proposed = int(np.clip(int(preapproved_n), lo, hi))
        est_wall_s = _project(n_proposed)
    reask = bool(reask_lines)

    total = est_wall_s * max(n_candidates, 1)
    approved, note = humangate.ask(
        (
            f"Run the full estimation for candidate {ctx.candidate!r} with "
            f"{n_proposed} starts (projected ~{est_wall_s:.0f}s wall)? Its probe "
            f"differs from the approved candidate's — see the first lines."
            if reask
            else f"Run the full estimation with {n_proposed} starts"
            + (
                f" x {n_candidates} candidates (projected ~{total:.0f}s total)"
                if n_candidates > 1
                else f" (projected ~{est_wall_s:.0f}s wall)"
            )
            + "?"
        ),
        reask_lines
        + ([] if reask else list(carried_lines or []))
        + [
            f"AMICI compile: {compile_s:.1f}s (0 = cache hit)",
            f"one objective evaluation: {obj_eval_s * 1e3:.1f} ms "
            f"({n_cond} conditions -> {obj_eval_s / max(n_cond, 1) * 1e3:.1f} ms/condition)",
            *_probe_timing_lines(probe_engine_rec, median_start_s, n_probe),
            # the optimiser this estimation will use, and why
            *(
                [
                    f"optimiser: {selection['selected']} "
                    f"({'chosen from a measured comparison' if selection.get('conclusive') else 'default — the comparison was inconclusive'})",
                    f"  — {selection['reason']}",
                    *([f"  — {switch_line}"] if switch_line else []),
                ]
                if selection
                else []
            ),
            (
                f"then {workers} starts at a time ({type(engine).__name__})"
                if workers > 1
                else f"starts run one at a time ({engine_reason(ctx.spec, start_s)})"
            ),
            f"measured projections: n=100 -> ~{_project(100):.0f}s · "
            f"n=500 -> ~{_project(500):.0f}s (deterministic CPU, no tokens)",
            f"probe objective values: {profile['probe_fvals']}",
            # the failed starts, and what AMICI said about them, kind by kind
            *_solver_message_lines(solver_msgs),
            # why a non-Gaussian candidate's starts are slow
            *hessian_lines,
            # a tolerance wrong for this model makes every fit below it wrong
            *_tolerance_lines(tol_check),
            # slow sensitivities would otherwise first show in S6
            *_sensitivity_lines(sensi),
            *_steady_state_lines(steady),
            # structurally flat directions: an indicator beside the criterion
            *_sn.card_lines(struct),
            # the agent cost measured so far this run, never projected
            payload.cost_gate_line(ctx.ledger, ctx.spec),
        ],
        ledger=ctx.ledger,
        module="cost_boundary_estimation",
        round_idx=ctx.round_idx,
        auto=ctx.auto,
        intent=ctx.intent,
        consequences=(
            (
                "this candidate is fitted with the approved start count, its "
                "probe notwithstanding",
                "this candidate is DROPPED by name (ledgered); the round "
                "continues over the other candidates",
            )
            if reask
            else (
                "the full multistart estimation runs with the approved start "
                "count (plus automatic profile likelihoods afterwards if the "
                "high end of their projection stays under the spec cap)",
                "run stops; nothing is estimated",
            )
        ),
        note_forms=[
            f"n=<starts>   run that many optimisation starts instead "
            f"(default {n_proposed}, allowed {lo}-{hi})",
            *_solver_note_forms(tol_check, sensi),
            "convergence: accept <why>   pre-answer the post-fit convergence "
            "gate for this round — 'don't worry about plateaus, just accept "
            "it'. The failed checks still print; only the pause is skipped. "
            "Integration failures are NOT covered and still ask.",
            "(nothing)    accept the proposed start count",
        ],
    )
    if not approved:
        if reask:
            # written before the raise: the next invocation replays the loop
            # from the first candidate and must find this answer already given
            (ctx.work / DECLINED_KEY).put(
                {
                    "candidate": ctx.candidate,
                    "note": note,
                    "reasons": reasons,
                    "at": datetime.datetime.now().isoformat(timespec="seconds"),
                },
            )
            raise BudgetDeclinedForCandidate(ctx.candidate, note)
        raise ModuleFailure("user declined the estimation budget")

    # one reading of the note: what is acted on is what is printed
    reading = read_budget_note(note, tol_check, sensi, lo, hi)
    n_approved = int(reading.read.get("n", n_proposed))
    chosen = _apply_gate_choices(
        ctx, reading, tol_check, sensi, profile, for_round=not reask
    )
    if chosen:
        problem, _, _ = estimation_settings.build(ctx)  # the settings now in force
    if chosen.get("sensi_method") == "adjoint":
        # the approved projection was measured with forward sensitivities and the
        # FIM Hessian; neither describes the fit that is about to run
        median_start_s = _reprobe_after_override(
            ctx, problem, profile, n_probe, seed, n_approved
        )
    _record_convergence_predeclaration(ctx, note)
    gate_note.report(
        reading,
        note,
        ledger=ctx.ledger,
        module="cost_boundary_estimation",
        round_idx=ctx.round_idx,
        candidate=ctx.candidate,
    )
    # the round's first approval is the reference later probes are compared
    # with; a re-asked candidate's approval is its own
    is_reference = not reask and reference is None
    if is_reference:
        ctx.cache["_budget_reference"] = {
            "candidate": ctx.candidate,
            "median_start_s": median_start_s,
            "n_starts": n_approved,
        }
    ctx.set_marker(
        "cost",
        approved_n_starts=n_approved,
        median_start_s=median_start_s,
        budget_reference=is_reference,
        reasked=reask,
    )
    return n_approved
