"""S6 — parameter estimation. No LLM judgment anywhere in this module.

Multistart estimation with a recorded seed; post-fit gates decide whether the
optimisation itself is trustworthy. One human gate: when a post-fit CHECK
fails, `estimation_convergence` asks a person whether it is acceptable for THIS model
rather than ending the run. The seed is not among those checks — it is an
engine invariant, asserted below.
"""

from __future__ import annotations

import re

import pandas as pd

from octomod.gates import run_gate_set
from octomod.gates.fit_gates import make_fit_gates
from octomod.orchestration import reuse as _reuse
from octomod.orchestration import (
    timing,  # noqa: E402
)
from octomod.orchestration.run_context import ModuleFailure, NoteRefused, RunContext
from octomod.workflow_modules.assembly import petab_io
from octomod.workflow_modules.cost_probe.engine import measured_start_s
from octomod.workflow_modules.estimation import estimation_settings
from octomod.workflow_modules.estimation.problem import (
    SELECTION_KEY,
    parameter_scales,
    read_optimize_result,
    resolve_optimizer,
    run_multistart,
    summarize_result,
    write_optimize_result,
)

# What `_convergence_gate` returns when the human accepted the fit as it is:
# the module is finished and the caller still has to mark it done. Any other
# return means the gate re-entered `run` itself (the refit path).
ACCEPTED = "accepted"

# The three records that are one fit, kept aside as `attempts/<n>/…` when a
# refit replaces them (`reuse.FIT_KEYS` names the same three).
FIT_RECORDS = ("estimation", "starts", "multistart")


@timing.phase("estimation")
def run(ctx: RunContext, n_starts: int) -> None:
    if ctx.marker("s6").exists():
        print("  (already done — resumed from marker; estimation result stands)")
        return
    ctx.require_marker("cost", needed_by="estimation")
    inp = petab_io.from_work(ctx.work, ctx.model)

    # the candidate's recorded settings (declared, the budget-gate choice, its
    # own refits), so a refit's solver changes reach its multistart and a
    # resume fits with what was bought, not with the defaults
    problem, petab_problem, _ = estimation_settings.build(ctx)
    n_starts = max(int(n_starts), estimation_settings.refit_n_starts(ctx) or 0)
    seed = int(ctx.spec.require("estimation.seed"))
    optimizer_overrides = estimation_settings.optimizer_overrides(ctx) or None
    # An explicit spec value, else this run's selection (cost probe or
    # convergence gate), else the default. Resolved before the reuse check,
    # whose fit fingerprint includes it.
    opt_name, opt_why = resolve_optimizer(ctx.spec, ctx.work)
    # Exactly this fit may already be in the record (`reuse.py`): this
    # candidate's own, when a resume answers its convergence gate (the marker
    # is set only after the gate), or an earlier round's, when this round's
    # base is the model that round fitted.
    src, fit_key, fit_parts = _reuse.fit_in_record(ctx, problem, n_starts)
    multistart = ctx.work / "multistart"
    result = None
    if src is not None:
        if src != ctx.work:
            _reuse.adopt_fit(src, ctx.work)
        result = read_optimize_result(multistart)
    reused = result is not None
    if reused:
        where = "this candidate's own group" if src == ctx.work else src.key
        have = int(_reuse.stored_fit(ctx.work).get("n_starts") or n_starts)
        starts = (
            f"{have} starts"
            if have == n_starts
            else f"{have} starts (≥ the {n_starts} approved)"
        )
        print(
            f"  multistart estimation: this exact fit is already on disk ({where}, "
            f"{starts}, fingerprint {fit_key}) — reused, not recomputed"
        )
        ctx.ledger.append(
            "note",
            module="estimation",
            round_idx=ctx.round_idx,
            note=(
                f"fit reused from {where}: identical problem, solver settings, "
                f"optimiser, seed {seed} and engine code, {starts} (fingerprint "
                f"{fit_key}); nothing recomputed"
            ),
            fit_reused=True,
            fit_key=fit_key,
            reused_from=where,
            n_starts_reused=have,
        )
    else:
        print(f"  multistart estimation: {n_starts} starts, seed {seed} ...")
        print(f"  optimiser: {opt_name} — {opt_why}")
        # the cost probe already measured what a start costs here; the engine
        # choice is made from that number rather than from a guess
        result = run_multistart(
            problem,
            n_starts,
            seed,
            ctx.spec,
            measured_start_s(ctx),
            optimizer_overrides,
            optimizer_name=opt_name,
        )
    ctx.cache[ctx.candidate_key("pypesto_result")] = result  # S7 profiling reuses it

    n_data = len(inp.measurements)
    summary = summarize_result(
        result,
        problem,
        parameter_scales(inp),
        n_data,
        seed,
        ctx.spec,
        optimizer_name=opt_name,
    )
    from octomod.result.slots import EstimationRecord
    from octomod.result.write import write_record

    write_record(ctx.work / "estimation", EstimationRecord, summary)
    (ctx.work / "starts").put_table(pd.DataFrame(summary["starts"]))
    # The seed is an engine invariant, not a gate: it can only fail on an
    # engine bug, so no person is asked to answer for it.
    if summary.get("seed") is None:
        raise ModuleFailure(
            "engine invariant violated: the multistart seed was not recorded "
            "in the estimation record, so this fit cannot be reproduced. This is "
            "an engine bug, not a modelling decision — report it rather than "
            "answering for it."
        )
    ctx.ledger.append(
        "note",
        module="estimation",
        round_idx=ctx.round_idx,
        note=f"reproducibility invariant holds: seed {summary['seed']} recorded",
        invariant="estimation_reproducibility_stamp",
    )
    # the Result object itself, not just its summary: profiling needs it, and
    # a resume would otherwise re-run the whole multistart
    if not reused:
        try:
            write_optimize_result(result, multistart)
            ctx.ledger.append(
                "artifact",
                module="estimation",
                round_idx=ctx.round_idx,
                artifact=multistart.key,
                producer="engine",
            )
        except Exception as e:
            ctx.ledger.append(
                "note",
                module="estimation",
                round_idx=ctx.round_idx,
                note=f"optimize result not persisted ({e}); a resume will re-run it",
            )
            print(f"  ⚑ optimize result not persisted: {e}")
    if multistart.exists():
        _reuse.record_fit(
            ctx.root,
            ctx.work,
            fit_key,
            fit_parts,
            len(summary.get("starts") or []) or n_starts,
            summary.get("best_fval"),
        )

    ok, _fit_results = run_gate_set(
        make_fit_gates(summary, ctx.spec),
        ctx.gates,
        ctx.ledger,
        "estimation",
        round_idx=ctx.round_idx,
    )
    if not ok:
        # waterfall plateau, gradient norm and integration failures are T2
        # statistics a large model can legitimately cross: a person decides
        outcome = _convergence_gate(ctx, _fit_results, problem, n_starts, seed)
        if outcome != ACCEPTED:
            # a refit re-entered `run` and already completed the module
            return outcome

    # reached on a clean ladder and on an accepted one: both set the marker
    ctx.set_marker(
        "s6", best_fval=summary["best_fval"], n_ensemble=len(summary["ensemble"])
    )


# The cap on gate-bought comparisons lives in the RECORD, not ctx.cache: in
# file-gate mode each answer is a new process, so an in-memory counter reset to
# 0 on every resume and `compare` could be answered indefinitely — each time
# re-running the bake-off AND a full re-estimation to get back to the gate.
COMPARE_RUNS_KEY = "optimizer_compare_runs"


def _compare_runs_done(ctx) -> int:
    """How many comparisons the convergence gate has bought for this fitted
    problem (round, and candidate). An unreadable count is a spent one."""
    node = ctx.work / COMPARE_RUNS_KEY
    if not node.exists():
        return 0
    try:
        return int((node.get() or {}).get("runs", 0))
    except Exception:
        return int(ctx.spec.get("estimation.optimizer_compare.max_per_run", 1))


def _keep_attempt(ctx, n: int):
    """Keep the current fit aside as `attempts/<n>` before a refit replaces it;
    returns that group's node."""
    keep = ctx.work / "attempts" / str(n)
    for name in FIT_RECORDS:
        (ctx.work / name).copy_to(keep / name)
    return keep


def _convergence_gate(ctx, results, problem, n_starts, seed):
    """Ask, rather than end the run, when a post-fit CHECK fails.

    Answers: accept it as expected for this model (a reason is required — an
    unreasoned accept is how a bad fit becomes a result), compare optimisers,
    buy a refit with declared overrides, or stop. A refit keeps the previous
    attempt in the record (`attempts/<n>`), so the two can be compared.
    """
    from octomod.gates import failure_summary
    from octomod.orchestration.interaction import humangate
    from octomod.workflow_modules.estimation import convergence_record as _cr
    from octomod.workflow_modules.estimation.problem import apply_refit, resolve_refit

    summary_text = failure_summary(results, "S6 post-fit", ctx.gates)
    attempts = estimation_settings.refit_attempts(ctx)
    budget = int(ctx.spec.get("retry.refit_max", 2))
    presets = sorted(ctx.spec.get("estimation.refit_presets") or {})
    decision = ctx.work / "decisions/estimation_convergence"
    who = f"candidate {ctx.candidate}" if ctx.candidate else "this model"

    # `convergence: accept <why>` answered at the budget gate pre-answers this
    # gate: the pause is skipped, the evidence never is.
    pre = ctx.cache.get("_convergence_predeclared") or predeclared_from_ledger(ctx)
    if pre:
        failed = {r.gate_id for r in results if not r.passed and r.blocking}
        blocked = sorted(failed & set(_cr.NOT_PREDECLARABLE))
        if blocked:
            print(
                f"  a convergence pre-declaration is on file, but {blocked} is "
                f"not covered by it — asking"
            )
        else:
            # the card's content still prints: only the pause is skipped
            print(summary_text)
            print(
                f"  convergence PRE-declared at the budget gate for {who} "
                f"(reason: {str(pre)[:120]}) — not pausing"
            )
            _record_accept(ctx, results, who, str(pre), pre_declared=True)
            return ACCEPTED

    forms = [
        "accept <why>   this is expected for THIS model — a reason is required",
        "compare        run the spec's optimisers on the SAME starts; if one "
        "is conclusively better, refit with it now, else ask again with the table",
        f"refit <preset|key=value>   re-fit with declared overrides "
        f"(presets: {', '.join(presets)})",
        "stop           end the run honestly",
    ]
    if ctx.candidate:
        forms.insert(
            2,
            f"refit {ctx.candidate}: <preset>   the same, addressed by "
            f"candidate id — this gate is asked once per candidate and is "
            f"asking about {ctx.candidate}",
        )
    approved, note = humangate.ask_once(
        ctx,
        decision,
        f"The fit for {who} crossed a convergence check. "
        f"Accept it, refit, or stop?",
        summary_text.splitlines()
        + _compare_recommendation(ctx, results)
        + _escalation_lines(ctx, results)
        + [
            "",
            f"refits used for {who} this round: {attempts} of {budget} "
            f"(each candidate carries its own budget)",
            "accepting does NOT make the fit better — it records that you "
            "judged the check inapplicable, and every downstream claim carries "
            "that caveat",
        ],
        module="estimation_convergence",
        record_decline=False,
        intent=ctx.intent,
        note_forms=tuple(forms),
        consequences=(
            "the round continues to evaluation with the failure recorded",
            "the run stops",
        ),
    )
    text = (note or "").strip()
    if not approved:
        raise ModuleFailure("user stopped at the convergence gate\n" + summary_text)

    # `ask_once` has already recorded the answer: a refusal clears it, so a
    # resume asks again instead of replaying the same note into the same error,
    # and the stop is a resumable one for the same reason.
    def _refuse(msg: str):
        decision.delete()
        return NoteRefused(
            msg
            + " That answer is cleared, so the gate asks again on resume.\n"
            + summary_text,
            gate="estimation_convergence",
        )

    if re.match(r"\s*compare\b", text, re.I):
        # Optimiser comparison on the same starts: it writes the artifact, then
        # refits with a conclusively better optimiser or comes back to this
        # gate with the table. It runs only after a check has already failed.
        from octomod.workflow_modules.estimation import optimizer_compare as _oc

        # the cap is counted in the record, not ctx.cache: in file-gate mode
        # each answer is a new process
        done = _compare_runs_done(ctx)
        cap = int(ctx.spec.get("estimation.optimizer_compare.max_per_run", 1))
        if not bool(ctx.spec.get("estimation.optimizer_compare.enabled", True)):
            raise _refuse(
                "optimiser comparison is disabled in the workflow spec "
                "(estimation.optimizer_compare.enabled). Answer "
                "`accept <why>`, `refit <preset>` or `n`."
            )
        if done >= cap:
            raise _refuse(
                f"optimiser comparison already run {done} time(s) this run "
                f"(cap {cap}); a second comparison measures the same thing "
                f"again. Answer `accept <why>`, `refit <preset>` or `n`."
            )
        cands = list(ctx.spec.get("estimation.optimizer_compare.candidates") or [])
        median_s = measured_start_s(ctx)
        # Sized from the budget as on the probe path, but `on_request`: a human
        # asked, so a small fit is a reason to state the cost, not to refuse.
        min_cmp = int(
            ctx.spec.get("estimation.optimizer_compare.min_compare_starts", 3)
        )
        fraction = float(
            ctx.spec.get("estimation.optimizer_compare.max_budget_fraction", 0.35)
        )
        plan = _oc.plan(
            len(cands),
            int(n_starts),
            median_s,
            fraction=fraction,
            min_starts=min_cmp,
            on_request=True,
        )
        if plan is None:
            raise _refuse(
                "the per-start cost of this fit was never measured, so a "
                "comparison cannot be projected and would be an open-ended "
                "spend. Answer `accept <why>`, `refit <preset>` or `n`."
            )
        n_cmp = plan["n_starts"]
        print(
            f"  optimiser comparison: {len(cands)} method(s) x {n_cmp} "
            f"starts, projected {plan['projected_s']:.0f}s of a "
            f"{plan['budget_s']:.0f}s budget"
        )
        if plan["over_budget"]:
            print(
                f"  (that is more than the usual {fraction:.0%} share, because "
                f"a {n_starts}-start fit is small and {min_cmp} starts per "
                f"method is the least that means anything — you asked for the "
                f"comparison, so it runs and this is what it costs)"
            )
        # The resolved optimiser, not the spec word (`auto` matches no row). It
        # runs first, so a budget that runs out cannot lose the row every
        # verdict is relative to.
        incumbent, _ = resolve_optimizer(ctx.spec, ctx.work)
        # one alpha decides both which starts count as successful and which
        # differences are big enough to act on
        alpha = float(ctx.spec.get("estimation.optimizer_compare.success_alpha", 0.05))
        with timing.span("compute", "optimizer_comparison"):
            rows = _oc.compare(
                problem,
                methods=cands,
                n_starts=n_cmp,
                seed=int(seed),
                alpha=alpha,
                budget_s=plan["stop_s"],
                incumbent=incumbent,
            )
        payload = _oc.as_json(rows, incumbent=incumbent, alpha=alpha)
        # keep this run's selection in the artifact the report reads; the probe
        # path writes its selection into the same record group
        comparison = ctx.work / "optimizer_comparison"
        selection = ctx.work / SELECTION_KEY
        payload = _oc.with_selection(payload, selection.get(None))
        comparison.put(payload)
        # with the incumbent: the legend stars the optimiser used for this fit,
        # and the default argument would star fides
        for line in _oc.table_lines(rows, incumbent=incumbent):
            print("  " + line)
        (ctx.work / COMPARE_RUNS_KEY).put({"runs": done + 1})
        ctx.ledger.append(
            "note",
            module="estimation_convergence",
            round_idx=ctx.round_idx,
            note=(
                "optimiser comparison: winner="
                f"{payload['verdict'].get('winner')} "
                f"incumbent_gap={payload['verdict'].get('incumbent_gap')} "
                f"materially_better={payload['verdict'].get('materially_better')} "
                f"unavailable={payload['verdict'].get('unavailable')}"
            ),
            optimizer_comparison=payload["verdict"],
        )
        # A conclusively better optimiser is selected for this fitted problem
        # and the fit re-run with it (the human bought that by answering
        # `compare`); anything else comes back to the gate.
        gain = float(
            ctx.spec.get("estimation.optimizer_compare.select_min_success_gain", 0.25)
        )
        decision_after = _oc.gate_decision(
            rows,
            incumbent,
            alpha=alpha,
            min_success_gain=gain,
            refits_left=budget - attempts,
        )
        sel = decision_after["selection"]
        if sel.get("conclusive") and sel.get("selected") != incumbent:
            chosen = next((r for r in rows if r.name == sel["selected"]), None)
            if chosen is not None and chosen.n_attempted and median_s:
                sel["start_s"] = float(chosen.wall_s / chosen.n_attempted)
                sel["start_s_vs_default"] = float(sel["start_s"] / median_s)
            sel["selected_at"] = "estimation_convergence"
            selection.put(sel)
            payload["selection"] = sel
            comparison.put(payload)
            ctx.ledger.append(
                "note",
                module="estimation_convergence",
                round_idx=ctx.round_idx,
                note=f"optimiser selected at the gate: {sel['selected']} — {sel['reason']}",
                optimizer_selection=sel,
            )
        decision.delete()  # the gate asks again, with the table on the card
        if decision_after["action"] == "refit_with":
            keep = _keep_attempt(ctx, attempts + 1)
            # recorded in `estimation_settings`, so a file-gate resume sees it
            estimation_settings.record_refit(
                ctx,
                {},
                f"optimiser {sel['selected']} after the comparison",
                int(n_starts),
            )
            ctx.ledger.append(
                "note",
                module="estimation_convergence",
                round_idx=ctx.round_idx,
                note=(
                    f"refitting {who} with {sel['selected']} after the comparison "
                    f"(bought by `compare`); previous attempt kept in {keep.key}"
                ),
                human_refit=True,
                attempt=attempts + 1,
                candidate=ctx.candidate,
                optimizer=sel["selected"],
            )
            print(f"  → refitting with {sel['selected']}: {decision_after['why']}")
            return run(ctx, n_starts)
        print(f"  → back to the gate: {decision_after['why']}")
        return _convergence_gate(ctx, results, problem, n_starts, seed)

    from octomod.orchestration.interaction import gate_note

    m = re.match(r"\s*refit\b[:\s]*(.*)", text, re.I)
    accepting = None if m else re.match(r"\s*accept\b[:\s]*(.*)", text, re.I)
    gate_note.report(
        gate_note.Reading(
            read=(
                {"refit": m.group(1).strip()}
                if m
                else {"accept": accepting.group(1).strip()} if accepting else {}
            )
        ),
        text,
        ledger=ctx.ledger,
        module="estimation_convergence",
        round_idx=ctx.round_idx,
        candidate=ctx.candidate,
    )
    if m:
        if attempts >= budget:
            raise _refuse(
                f"refit budget spent ({budget}) for {who}; answer "
                f"`accept <why>` or `n` to stop."
            )
        try:
            request = _strip_candidate(ctx, m.group(1))
            overrides, described = resolve_refit(ctx.spec, request)
        except ValueError as e:
            raise _refuse(f"cannot refit: {str(e).rstrip('.')}.") from e
        keep = _keep_attempt(ctx, attempts + 1)
        factor = float(overrides.get("n_starts_factor", 1) or 1)
        n_refit = max(1, int(round(n_starts * factor)))
        # Recorded, then built: `build_problem` applies the recorded settings,
        # so overrides set only on a live solver would be overwritten. The
        # multistart below and any resume run with the refit's settings.
        refit = estimation_settings.record_refit(ctx, overrides, described, n_refit)
        rebuilt, _, _ = estimation_settings.build(ctx)
        applied, opt_overrides = apply_refit(rebuilt, overrides)  # what now holds
        ctx.ledger.append(
            "note",
            module="estimation_convergence",
            round_idx=ctx.round_idx,
            note=(
                f"human bought a refit for {who} ({described}); solver changes "
                f"in force: {applied or 'none'}; optimizer: "
                f"{opt_overrides or 'unchanged'}; {n_refit} starts; "
                f"previous attempt kept in {keep.key}"
            ),
            human_refit=True,
            attempt=refit["attempts"],
            candidate=ctx.candidate,
        )
        decision.delete()  # the gate must ask again after it
        print(f"  → refitting at your request: {described}")
        return run(ctx, n_refit)

    if not re.match(r"\s*accept\b", text, re.I) or len(text.split()) < 2:
        raise _refuse(
            "the convergence gate needs `accept <why>`, `refit <preset>` or "
            "`n`. An accept without a reason is how an unconverged fit becomes "
            "a result."
        )
    _record_accept(ctx, results, who, text, pre_declared=False)
    return ACCEPTED


_PREDECLARED_NOTE = re.compile(
    r"PRE-declared `convergence: accept` for this round at the budget gate: (.*?)\. "
    r"The estimation_convergence gate",
    re.S,
)


def predeclared_from_ledger(ctx) -> str | None:
    """A `convergence: accept <why>` answered at this round's budget gate, read
    back from the ledger when the in-process copy is gone (a restart between
    the budget gate and the fits).

    Only a declaration made AFTER the round's latest budget-gate answer counts:
    a re-entry that answered the budget gate again without one has withdrawn it.
    """
    rows = [e for e in ctx.ledger.entries() if e.get("round") == ctx.round_idx]
    last_answer = max(
        (
            i
            for i, e in enumerate(rows)
            if e.get("event") == "human_gate"
            and e.get("module") == "cost_boundary_estimation"
        ),
        default=-1,
    )
    for e in rows[last_answer + 1 :]:
        if e.get("module") != "cost_boundary_estimation":
            continue
        if not e.get("convergence_predeclared"):
            continue
        if e.get("predeclared_reason"):
            return str(e["predeclared_reason"])
        m = _PREDECLARED_NOTE.search(str(e.get("note") or ""))
        if m:  # older rows carry the reason only in the note
            return m.group(1).strip()
    return None


def _record_accept(ctx, results, who: str, text: str, *, pre_declared: bool) -> None:
    """Ledger the accept WITH the numbers the human was shown.

    The measured values travel in the row rather than being looked up later
    from `gates/<id>`, because a refit rewrites those verdicts — the numbers
    that were on the card when the person decided are only recoverable if they
    are written down at that moment.
    """
    from octomod.workflow_modules.estimation import convergence_record as _cr

    reason = str(text).strip()
    ctx.ledger.append(
        "note",
        module="estimation_convergence",
        round_idx=ctx.round_idx,
        note=(
            f"convergence {'PRE-declared' if pre_declared else 'accepted'} by "
            f"human for {who}: {reason[:300]}"
        ),
        convergence="pre-declared-by-human" if pre_declared else "accepted-by-human",
        failed_checks=[r.gate_id for r in results if not r.passed and r.blocking],
        failed_measured=_cr.measured_from_results(results),
        accept_reason=reason[:300],
        candidate=ctx.candidate,
    )
    print(f"  convergence accepted by you for {who} — the report will say so")


def _compare_recommendation(ctx, results) -> list[str]:
    """Say, on the card, when a comparison is the right next step.

    The plateau check failing means few starts reached the best value; the
    integration check failing means many starts crashed. Either is one of two
    things — too few starts, or an optimiser that rarely reaches this basin —
    and the comparison is the instrument that tells them apart on the same
    starts. So it is recommended FIRST for those failures, once per run, and
    only when the feature is on and a comparison has not been run already.
    """
    if not bool(ctx.spec.get("estimation.optimizer_compare.enabled", True)):
        return []
    cap = int(ctx.spec.get("estimation.optimizer_compare.max_per_run", 1))
    if _compare_runs_done(ctx) >= cap:
        return ["", "a comparison already ran this round; its table is above"]
    failed = {r.gate_id for r in results if not r.passed and r.blocking}
    pointing = failed & {
        "estimation_waterfall_plateau",
        "estimation_integration_failures",
    }
    if not pointing:
        return []
    why = (
        "few starts reached the best value"
        if "estimation_waterfall_plateau" in pointing
        else "many starts failed to integrate"
    )
    return [
        "",
        "suggested first: compare",
        f"  — {why}: that is either too few starts or an optimiser that rarely "
        f"reaches this basin, and the comparison runs the spec's optimisers on "
        f"the same starts to tell which. If one is conclusively better it refits "
        f"with it now; otherwise you are asked again with the numbers.",
    ]


def _escalation_lines(ctx, results) -> list[str]:
    """The order the spec says to try presets in, specialised to what FAILED.

    Nothing auto-escalates at this judgment gate, so `estimation.escalation`
    is a recommendation on the card; the person still chooses.
    """
    order = [str(p) for p in (ctx.spec.get("estimation.escalation") or [])]
    if not order:
        return []
    failed = {r.gate_id for r in results if not r.passed and r.blocking}
    crashes = "estimation_integration_failures" in failed
    if crashes and "robust_solver" in order:
        order = ["robust_solver"] + [p for p in order if p != "robust_solver"]
    why = (
        "the integration-failure check is among those that failed, and more "
        "starts over a field of crashes is survivorship, not convergence — so "
        "the solver is tried before the start count"
        if crashes
        else "the integration check passed, so this is the spec's declared order"
    )
    return ["", f"suggested order for this failure: {', '.join(order)}", f"  — {why}"]


def _strip_candidate(ctx, request: str) -> str:
    """Accept `refit <candidate_id>: <preset>` as well as `refit <preset>`.

    The gate is asked once per candidate (own work group, decision record and
    refit budget), so the id is redundant, but it is the form a per-candidate
    card shows; a mismatched id raises ValueError rather than refitting the
    wrong candidate.
    """
    text = (request or "").strip()
    if ":" not in text:
        return text
    named, rest = text.split(":", 1)
    named, rest = named.strip(), rest.strip()
    if ctx.candidate is None:
        raise ValueError(
            f"this round fits a single model, so there is no candidate "
            f"{named!r} to address — give the preset alone"
        )
    if named != ctx.candidate:
        raise ValueError(
            f"this gate is asking about candidate {ctx.candidate!r}, not "
            f"{named!r}. Each candidate is asked separately, so answer this "
            f"one and {named!r} will get its own card if its fit also crosses "
            f"a check"
        )
    return rest
